"""Cover letter generation that stays grounded in resume facts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.config.logging import get_logger
from src.models.job import Job

logger = get_logger(__name__)

SYSTEM = (
    "Write a concise cover letter (under 250 words) for the named company and role. "
    "Use only facts from the resume. Do not invent employers, titles, degrees, "
    "certifications, metrics, or technologies. If the resume lacks a detail, skip it."
)


def render_template(template: str, job: Job, extra: dict[str, str] | None = None) -> str:
    values = {
        "date": date.today().isoformat(),
        "job_title": job.title,
        "company": job.company,
        "job_description_match": (job.skills_required[:5] and ", ".join(job.skills_required[:5])) or job.title,
        **(extra or {}),
    }
    text = template
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


async def generate_cover_letter(
    job: Job,
    resume_text: str,
    template_path: Path | None = None,
    use_llm: bool = True,
    output_path: Path | None = None,
) -> str:
    template = ""
    if template_path and template_path.exists():
        template = template_path.read_text(encoding="utf-8")

    letter = ""
    if use_llm:
        try:
            from src.ai.deepseek_client import get_deepseek_client

            client = get_deepseek_client()
            from src.prompts import COVER_LETTER_PROMPT

            prompt = COVER_LETTER_PROMPT.format(
                job_title=job.title,
                company=job.company,
                job_description=(job.description or "")[:4000],
                resume_text=(resume_text or "")[:6000],
            )
            letter = await client.generate(prompt, system_prompt=SYSTEM)
        except Exception as e:
            logger.error("Cover letter LLM failed; using template", error=str(e))

    if not letter.strip() and template:
        letter = render_template(template, job)
    if not letter.strip():
        letter = (
            f"Dear Hiring Manager,\n\nI am applying for the {job.title} role at {job.company}. "
            f"My background is described in the attached resume. I would welcome the chance "
            f"to discuss how that experience relates to this position.\n\nThank you."
        )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(letter, encoding="utf-8")
    return letter
