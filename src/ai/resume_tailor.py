"""Resume tailoring that never invents facts."""

from __future__ import annotations

import re
from pathlib import Path

from src.ai.schemas import TailoredResumeResponse
from src.config.logging import get_logger
from src.models.job import Job

logger = get_logger(__name__)

INVENTION_BLOCKLIST = (
    "invent",
    "fabricate",
    "made-up",
)

SYSTEM = (
    "You tailor resumes. You may reorder skills, emphasize relevant experience, "
    "improve wording, and tailor the summary. You must NEVER invent employment, "
    "projects, certifications, degrees, technologies, or achievements that are "
    "not present in the source resume. If unsure, omit rather than invent."
)


def _allowed_terms(resume_text: str, user_skills: list[str]) -> set[str]:
    words = set(re.findall(r"[A-Za-z][A-Za-z0-9+.#/-]{1,}", resume_text.lower()))
    for skill in user_skills:
        words.update(re.findall(r"[A-Za-z][A-Za-z0-9+.#/-]{1,}", skill.lower()))
    return words


def _strip_invented_skills(skills: list[str], allowed: set[str], user_skills: list[str]) -> list[str]:
    kept: list[str] = []
    user_l = {s.lower() for s in user_skills}
    for skill in skills:
        sl = skill.lower()
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9+.#/-]{1,}", sl)
        if sl in user_l or (tokens and all(t in allowed or t in {"and", "of", "the"} for t in tokens)):
            kept.append(skill)
    return kept


def deterministic_tailor(
    resume_text: str,
    job: Job,
    user_skills: list[str],
    matched_skills: list[str],
) -> TailoredResumeResponse:
    """Reorder known skills and write a summary from existing facts only."""
    ordered = []
    seen = set()
    for skill in matched_skills + user_skills:
        key = skill.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(skill)

    title = job.title or "the role"
    company = job.company or "the company"
    skill_phrase = ", ".join(ordered[:8]) if ordered else "the skills listed in the resume"
    summary = (
        f"Candidate for {title} at {company}. "
        f"Experience and skills drawn only from the provided resume, emphasizing {skill_phrase}."
    )
    return TailoredResumeResponse(
        summary=summary,
        ordered_skills=ordered,
        emphasized_experience=[],
        notes="Deterministic tailor: skills reordered from the user profile; no new facts added.",
    )


async def tailor_resume(
    resume_text: str,
    job: Job,
    user_skills: list[str],
    matched_skills: list[str],
    use_llm: bool = False,
    output_path: Path | None = None,
) -> TailoredResumeResponse:
    fallback = deterministic_tailor(resume_text, job, user_skills, matched_skills)
    if not use_llm:
        _maybe_write(output_path, fallback, resume_text)
        return fallback

    try:
        from src.ai.deepseek_client import get_deepseek_client

        client = get_deepseek_client()
        prompt = (
            f"JOB TITLE: {job.title}\nCOMPANY: {job.company}\n"
            f"JOB DESCRIPTION:\n{job.description[:4000]}\n\n"
            f"SOURCE RESUME (facts only):\n{resume_text[:8000]}\n\n"
            f"KNOWN SKILLS:\n{user_skills}\nMATCHED SKILLS:\n{matched_skills}\n"
        )
        data = await client.generate_json(prompt, schema=TailoredResumeResponse, system_prompt=SYSTEM)
        result = TailoredResumeResponse(**data)
        allowed = _allowed_terms(resume_text, user_skills)
        result.ordered_skills = _strip_invented_skills(result.ordered_skills, allowed, user_skills) or fallback.ordered_skills
        if not result.summary.strip():
            result.summary = fallback.summary
        _maybe_write(output_path, result, resume_text)
        return result
    except Exception as e:
        logger.error("Resume tailoring LLM failed; using deterministic output", error=str(e))
        _maybe_write(output_path, fallback, resume_text)
        return fallback


def _maybe_write(path: Path | None, result: TailoredResumeResponse, resume_text: str) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"{result.summary}\n\nSkills (reordered):\n"
        + "\n".join(f"- {s}" for s in result.ordered_skills)
        + "\n\n--- Original resume (unchanged facts) ---\n"
        + resume_text
    )
    path.write_text(body, encoding="utf-8")
