"""Persistence helpers for jobs, applications, and profile."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.logging import get_logger
from src.db.models import ApplicationRecord, JobRecord, UserProfileRecord
from src.jobs.dedupe import fallback_key
from src.models.job import ApplicationStatus, NormalizedJob

logger = get_logger(__name__)

TERMINAL_APPLIED = {ApplicationStatus.APPLIED.value}


def _skill_str(skills: list[str]) -> str:
    return ",".join(skills)


def _skill_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def upsert_job(session: Session, job: NormalizedJob) -> tuple[JobRecord, bool]:
    """Insert or update a job. Idempotent on source + external_job_id.

    Returns (record, created).
    """
    existing = session.execute(
        select(JobRecord).where(
            JobRecord.source == job.source,
            JobRecord.external_job_id == job.external_job_id,
        )
    ).scalar_one_or_none()

    if existing is None and job.company and job.title:
        fb = fallback_key(job)
        existing = session.execute(
            select(JobRecord).where(JobRecord.fallback_key == fb)
        ).scalar_one_or_none()

    if existing:
        existing.title = job.title or existing.title
        existing.company = job.company or existing.company
        existing.location = job.location or existing.location
        existing.salary = job.salary or existing.salary
        existing.description = job.description or existing.description
        if job.skills:
            existing.skills = _skill_str(job.skills)
        existing.job_url = job.job_url or existing.job_url
        if job.posted_date:
            existing.posted_date = job.posted_date
        return existing, False

    record = JobRecord(
        source=job.source,
        external_job_id=job.external_job_id,
        title=job.title,
        company=job.company,
        location=job.location,
        salary=job.salary,
        description=job.description,
        skills=_skill_str(job.skills),
        job_url=job.job_url,
        posted_date=job.posted_date,
        collected_at=datetime.now(timezone.utc),
        status="collected",
        fallback_key=fallback_key(job),
    )
    session.add(record)
    session.flush()
    return record, True


def get_job(session: Session, job_id: int) -> Optional[JobRecord]:
    return session.get(JobRecord, job_id)


def list_jobs(
    session: Session,
    min_score: Optional[float] = None,
    status: Optional[str] = None,
    limit: int = 200,
) -> list[JobRecord]:
    stmt = select(JobRecord).order_by(JobRecord.match_score.desc().nullslast(), JobRecord.id.desc())
    if min_score is not None:
        stmt = stmt.where(JobRecord.match_score >= min_score)
    if status:
        stmt = stmt.where(JobRecord.status == status)
    stmt = stmt.limit(limit)
    return list(session.execute(stmt).scalars())


def update_match(
    session: Session,
    job_id: int,
    score: float,
    matched: list[str],
    missing: list[str],
    explanation: str,
) -> Optional[JobRecord]:
    job = session.get(JobRecord, job_id)
    if not job:
        return None
    job.match_score = score
    job.matched_skills = _skill_str(matched)
    job.missing_skills = _skill_str(missing)
    job.match_explanation = explanation
    job.status = "matched" if score >= 50 else "mismatched"
    return job


def get_active_application(session: Session, job_id: int) -> Optional[ApplicationRecord]:
    return session.execute(
        select(ApplicationRecord)
        .where(ApplicationRecord.job_id == job_id)
        .order_by(ApplicationRecord.id.desc())
    ).scalar_one_or_none()


def create_or_get_application(
    session: Session,
    job_id: int,
    status: str = ApplicationStatus.SAVED.value,
) -> tuple[ApplicationRecord, bool, str]:
    """Create an application row. Warns if already APPLIED. Never auto-marks applied."""
    existing = get_active_application(session, job_id)
    if existing:
        warning = ""
        if existing.status == ApplicationStatus.APPLIED.value:
            warning = "This job is already marked APPLIED."
            logger.warning("Duplicate application prevented", job_id=job_id)
        return existing, False, warning

    record = ApplicationRecord(job_id=job_id, status=status)
    session.add(record)
    session.flush()
    return record, True, ""


def set_application_status(
    session: Session,
    application_id: int,
    status: str,
    notes: Optional[str] = None,
    resume_version: Optional[str] = None,
    cover_letter_version: Optional[str] = None,
    interview_date: Optional[datetime] = None,
    mark_applied: bool = False,
) -> Optional[ApplicationRecord]:
    app = session.get(ApplicationRecord, application_id)
    if not app:
        return None
    app.status = status
    if notes is not None:
        app.notes = notes
    if resume_version is not None:
        app.resume_version = resume_version
    if cover_letter_version is not None:
        app.cover_letter_version = cover_letter_version
    if interview_date is not None:
        app.interview_date = interview_date
    if mark_applied and status == ApplicationStatus.APPLIED.value:
        app.applied_at = datetime.now(timezone.utc)
    elif status == ApplicationStatus.APPLIED.value and not mark_applied:
        raise ValueError("Refusing to mark APPLIED without explicit user confirmation")
    app.updated_at = datetime.now(timezone.utc)
    return app


def list_applications(session: Session, status: Optional[str] = None) -> list[ApplicationRecord]:
    stmt = select(ApplicationRecord).order_by(ApplicationRecord.id.desc())
    if status:
        stmt = stmt.where(ApplicationRecord.status == status)
    return list(session.execute(stmt).scalars())


def overview_counts(session: Session) -> dict[str, int]:
    jobs = list(session.execute(select(JobRecord)).scalars())
    apps = list(session.execute(select(ApplicationRecord)).scalars())
    return {
        "jobs_collected": len(jobs),
        "relevant_jobs": sum(1 for j in jobs if (j.match_score or 0) >= 50),
        "jobs_requiring_review": sum(
            1 for a in apps if a.status in {ApplicationStatus.REVIEW.value, ApplicationStatus.READY.value}
        ),
        "applications": len(apps),
        "interviews": sum(1 for a in apps if a.status == ApplicationStatus.INTERVIEW.value),
        "offers": sum(1 for a in apps if a.status == ApplicationStatus.OFFER.value),
    }


def get_or_create_profile(session: Session) -> UserProfileRecord:
    profile = session.execute(select(UserProfileRecord).limit(1)).scalar_one_or_none()
    if profile:
        return profile
    profile = UserProfileRecord()
    session.add(profile)
    session.flush()
    return profile


def job_to_dict(job: JobRecord) -> dict:
    latest = job.applications[-1] if job.applications else None
    return {
        "id": job.id,
        "source": job.source,
        "external_job_id": job.external_job_id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary": job.salary,
        "description": job.description,
        "skills": _skill_list(job.skills),
        "job_url": job.job_url,
        "posted_date": job.posted_date.isoformat() if job.posted_date else None,
        "collected_at": job.collected_at.isoformat() if job.collected_at else None,
        "status": job.status,
        "match_score": job.match_score,
        "matched_skills": _skill_list(job.matched_skills),
        "missing_skills": _skill_list(job.missing_skills),
        "match_explanation": job.match_explanation,
        "application_status": latest.status if latest else None,
    }
