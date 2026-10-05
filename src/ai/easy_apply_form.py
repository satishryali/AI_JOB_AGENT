"""Answer LinkedIn Easy Apply questions using profile, resume, and DeepSeek."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from src.config.config_loader import get_settings
from src.config.logging import get_logger
from src.models.job import Job
from src.utils.profile_builder import ProfileBuilder

logger = get_logger(__name__)

_facts_cache: dict[str, Any] | None = None

SYSTEM = (
    "You fill LinkedIn Easy Apply form fields for this candidate. "
    "Use only the profile, skills, and resume facts provided. "
    "Do not invent employers, visas, degrees, salary, or tools that are not in the facts. "
    "If you cannot answer honestly, set needs_human to true and leave value empty. "
    "Prefer short answers. For yes/no, value must be exactly Yes or No matching an option. "
    "For dropdowns, value must match one option exactly when possible. "
    "Never mention API keys or passwords."
)


class FieldAnswer(BaseModel):
    field_id: str
    value: str = ""
    skip: bool = False
    needs_human: bool = False


class EasyApplyPlan(BaseModel):
    answers: list[FieldAnswer] = Field(default_factory=list)


def _llm_enabled() -> bool:
    return bool(get_settings().llm.api_key)


def candidate_facts() -> dict[str, Any]:
    """Facts from config/.env and resume. Excludes secrets (no passwords, no API keys)."""
    global _facts_cache
    if _facts_cache is not None:
        return _facts_cache
    settings = get_settings()
    profile = ProfileBuilder().build()
    skills: list[str] = []
    path = settings.resume.skills_path
    if path.exists():
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for item in data.get("skills", []):
            if isinstance(item, dict) and item.get("name"):
                skills.append(str(item["name"]))
            elif isinstance(item, str):
                skills.append(item)
    resume_text = ""
    try:
        resume_path = settings.resume.path
        if resume_path.suffix.lower() == ".pdf" and resume_path.exists():
            import pdfplumber

            with pdfplumber.open(resume_path) as pdf:
                resume_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        elif resume_path.exists():
            resume_text = resume_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning("Could not read resume for Easy Apply", error=str(e)[:120])

    _facts_cache = {
        "first_name": profile.get("first_name") or settings.user.first_name,
        "last_name": profile.get("last_name") or settings.user.last_name,
        "email": profile.get("email") or settings.user.email,
        "phone": profile.get("phone") or settings.user.phone,
        "city": profile.get("city") or "",
        "experience_years": settings.resume.experience_years,
        "preferred_roles": settings.user.preferred_roles,
        "preferred_locations": settings.user.preferred_locations,
        "salary_expectations": settings.user.salary_expectations,
        "skills": skills,
        "resume_excerpt": (resume_text or "")[:5000],
    }
    return _facts_cache


def heuristic_answer(field: dict, facts: dict[str, Any]) -> FieldAnswer | None:
    """Fill obvious contact/profile fields without calling the LLM."""
    label = f"{field.get('label') or ''} {field.get('type') or ''}".lower()
    fid = field.get("id") or ""
    options = [str(o) for o in field.get("options") or []]

    def pick_option(*needles: str) -> str:
        for opt in options:
            low = opt.lower()
            if any(n in low for n in needles):
                return opt
        return ""

    if "phone" in label and "country" not in label:
        phone = str(facts.get("phone") or "")
        if phone:
            return FieldAnswer(field_id=fid, value=phone)
    if "email" in label:
        email = str(facts.get("email") or "")
        if email:
            return FieldAnswer(field_id=fid, value=email)
    if "first name" in label or label.strip() == "first":
        name = str(facts.get("first_name") or "")
        if name:
            return FieldAnswer(field_id=fid, value=name)
    if "last name" in label:
        name = str(facts.get("last_name") or "")
        if name:
            return FieldAnswer(field_id=fid, value=name)
    if "country code" in label or "phone country" in label:
        opt = pick_option("india", "+91")
        if opt:
            return FieldAnswer(field_id=fid, value=opt)
    if "years of experience" in label or "how many years" in label:
        years = facts.get("experience_years")
        if years is not None:
            return FieldAnswer(field_id=fid, value=str(years))
    return None


async def plan_answers(job: Job, fields: list[dict]) -> list[FieldAnswer]:
    facts = candidate_facts()
    planned: list[FieldAnswer] = []
    remaining: list[dict] = []
    for field in fields:
        if field.get("current") and str(field.get("current")).strip():
            continue
        heuristic = heuristic_answer(field, facts)
        if heuristic:
            planned.append(heuristic)
        else:
            remaining.append(field)

    if not remaining:
        return planned

    if not _llm_enabled():
        logger.warning("LLM_API_KEY not set — pausing on remaining Easy Apply questions")
        for field in remaining:
            planned.append(FieldAnswer(field_id=field.get("id") or "", needs_human=True))
        return planned

    from src.ai.deepseek_client import get_deepseek_client

    payload = {
        "job": {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": (job.description or "")[:2500],
        },
        "candidate": {k: v for k, v in facts.items() if k != "resume_excerpt"},
        "resume_excerpt": facts.get("resume_excerpt"),
        "fields": remaining,
    }
    prompt = (
        "Return JSON {\"answers\": [{\"field_id\": \"...\", \"value\": \"...\", "
        "\"skip\": false, \"needs_human\": false}]}.\n"
        "One answer per field. field_id must match the input.\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        client = get_deepseek_client()
        data = await client.generate_json(prompt, schema=EasyApplyPlan, system_prompt=SYSTEM)
        plan = EasyApplyPlan.model_validate(data)
        planned.extend(plan.answers)
        logger.info("DeepSeek answered Easy Apply fields", count=len(plan.answers))
    except Exception as e:
        logger.error("DeepSeek Easy Apply answers failed", error=str(e)[:200])
        for field in remaining:
            planned.append(FieldAnswer(field_id=field.get("id") or "", needs_human=True))
    return planned


async def scrape_fields(page) -> list[dict]:
    """Read visible inputs in the Easy Apply modal."""
    return await page.evaluate(
        """() => {
          const modal = document.querySelector('.jobs-easy-apply-modal');
          if (!modal) return [];
          const fields = [];
          const radioSeen = new Set();
          const nodes = modal.querySelectorAll('input, select, textarea');
          nodes.forEach((el, i) => {
            const type = (el.type || el.tagName || '').toLowerCase();
            if (type === 'hidden' || type === 'file' || type === 'submit' || type === 'button') return;
            const labelFor = el.id && modal.querySelector(`label[for="${el.id}"]`);
            const fieldset = el.closest('fieldset');
            const wrap = el.closest('.jobs-easy-apply-form-element, .fb-dash-form-element, div');
            let label = '';
            if (labelFor) label = labelFor.innerText;
            else if (fieldset) {
              const legend = fieldset.querySelector('legend');
              label = legend ? legend.innerText : fieldset.innerText.slice(0, 240);
            } else if (el.labels && el.labels[0]) label = el.labels[0].innerText;
            else if (wrap) {
              const lab = wrap.querySelector('label, span[class*="label"], p');
              label = lab ? lab.innerText : '';
            }
            label = (label || '').replace(/\\s+/g, ' ').trim().slice(0, 240);
            if (type === 'radio') {
              const key = el.name || label;
              if (!key || radioSeen.has(key)) return;
              radioSeen.add(key);
              const group = modal.querySelectorAll(`input[type="radio"][name="${el.name}"]`);
              const options = [];
              group.forEach(r => {
                const lab = r.labels && r.labels[0] ? r.labels[0].innerText : (r.value || '');
                options.push(lab.replace(/\\s+/g, ' ').trim());
              });
              const current = [...group].find(r => r.checked);
              fields.push({
                id: el.name || `radio-${i}`,
                type: 'radio',
                name: el.name || '',
                label,
                options,
                current: current ? (current.labels && current.labels[0] ? current.labels[0].innerText : current.value) : '',
                required: [...group].some(r => r.required),
              });
              return;
            }
            let options = [];
            if (el.tagName === 'SELECT') {
              options = [...el.options].map(o => (o.text || o.value || '').trim()).filter(Boolean);
            }
            fields.push({
              id: el.id || el.name || `field-${i}`,
              type: type || el.tagName.toLowerCase(),
              name: el.name || '',
              label,
              options,
              current: el.value || '',
              required: !!el.required,
            });
          });
          return fields;
        }"""
    )


async def apply_answers(page, answers: list[FieldAnswer]) -> None:
    import re

    modal = page.locator(".jobs-easy-apply-modal")
    for answer in answers:
        if answer.skip or answer.needs_human or not answer.value:
            continue
        fid = answer.field_id
        value = answer.value
        try:
            radio = modal.locator(f'input[type="radio"][name="{fid}"]')
            if await radio.count():
                choice = modal.get_by_role("radio", name=re.compile(re.escape(value), re.I))
                if await choice.count():
                    await choice.first.check(force=True)
                else:
                    await modal.locator("label").filter(has_text=re.compile(re.escape(value), re.I)).first.click()
                continue
            select = modal.locator(f"#{fid}, select[name='{fid}']")
            if await select.count() and (await select.first.evaluate("el => el.tagName")) == "SELECT":
                try:
                    await select.first.select_option(label=value)
                except Exception:
                    await select.first.select_option(value=value)
                continue
            box = modal.locator(f"#{fid}, textarea[name='{fid}'], input[name='{fid}']")
            if await box.count():
                tag = await box.first.evaluate("el => el.tagName")
                if tag != "SELECT":
                    await box.first.fill(value)
                    continue
            labeled = modal.get_by_label(re.compile(re.escape(fid), re.I))
            if await labeled.count():
                await labeled.first.fill(value)
        except Exception as e:
            logger.debug("Could not fill Easy Apply field", field=fid, error=str(e)[:120])


async def fill_easy_apply_page(page, job: Job) -> bool:
    """Fill the current Easy Apply page. False means a human must finish this step."""
    try:
        await page.wait_for_selector(".jobs-easy-apply-modal", timeout=5000)
    except Exception:
        return True
    fields = await scrape_fields(page)
    if not fields:
        return True
    if _llm_enabled():
        logger.info("Easy Apply using DeepSeek plus profile/.env (no secrets sent)")
    else:
        logger.info("Easy Apply using profile/.env only — set LLM_API_KEY to enable DeepSeek")
    answers = await plan_answers(job, fields)
    await apply_answers(page, answers)
    if any(a.needs_human for a in answers):
        logger.warning("Easy Apply needs a human answer on this page")
        return False
    return True
