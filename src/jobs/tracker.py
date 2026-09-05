"""Application tracking using SQLite via SQLAlchemy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.config.config_loader import get_settings
from src.config.logging import get_logger
from src.config.settings import DatabaseSettings
from src.db.models import ApplicationRecord
from src.db.repository import (
    create_or_get_application,
    get_active_application,
    list_applications,
    set_application_status,
    upsert_job,
)
from src.db.session import init_db, reset_engine, session_scope
from src.jobs.normalize import to_normalized
from src.models.job import ApplicationResult, ApplicationStatus, Job

logger = get_logger(__name__)


class ApplicationTracker:
    """Track jobs and applications. Never silently marks a job as applied."""

    def __init__(self, settings: Optional[DatabaseSettings] = None, database_url: Optional[str] = None):
        self._settings = settings or get_settings().database
        self._database_url = database_url
        self._connected = False

    def connect(self) -> None:
        url = self._database_url or self._settings.sqlalchemy_url()
        init_db(url)
        self._connected = True
        logger.info("Database connected", url="sqlite" if url.startswith("sqlite") else "configured")

    def is_already_applied(self, job: Job) -> bool:
        if not self._connected:
            self.connect()
        normalized = to_normalized(job)
        with session_scope() as session:
            record, _created = upsert_job(session, normalized)
            app = get_active_application(session, record.id)
            return bool(app and app.status == ApplicationStatus.APPLIED.value)

    def record_application(self, result: ApplicationResult) -> ApplicationRecord | None:
        if not self._connected:
            self.connect()
        if result.status == ApplicationStatus.APPLIED and not result.applied_at:
            logger.warning("Refusing to persist APPLIED without applied_at (user confirmation required)")
        normalized = to_normalized(result.job)
        with session_scope() as session:
            job_row, _ = upsert_job(session, normalized)
            existing = get_active_application(session, job_row.id)
            if existing and existing.status == ApplicationStatus.APPLIED.value:
                existing.warning = "This job is already marked APPLIED."
                logger.warning("Duplicate application prevented", job=result.job.title)
                return existing
            app, _created, warning = create_or_get_application(
                session,
                job_row.id,
                status=ApplicationStatus.SAVED.value
                if result.status == ApplicationStatus.APPLIED
                else result.status.value,
            )
            if result.status == ApplicationStatus.APPLIED:
                # Explicit user-controlled mark only when caller sets status + applied_at together
                # via mark_applied(). Recording an ApplicationResult.APPLIED from automation
                # is stored as READY for review instead.
                app.status = ApplicationStatus.READY.value
                app.warning = warning or "Prepared only — not marked applied."
            app.resume_version = result.resume_path or app.resume_version
            app.cover_letter_version = result.cover_letter_path or app.cover_letter_version
            app.notes = result.error_message or app.notes
            return app

    def mark_applied(self, job: Job, notes: str = "") -> ApplicationRecord:
        """User-controlled confirmation that an application was submitted."""
        if not self._connected:
            self.connect()
        normalized = to_normalized(job)
        with session_scope() as session:
            job_row, _ = upsert_job(session, normalized)
            app, _, warning = create_or_get_application(session, job_row.id)
            if warning:
                raise ValueError(warning)
            return set_application_status(
                session,
                app.id,
                ApplicationStatus.APPLIED.value,
                notes=notes,
                mark_applied=True,
            )

    def get_all_applications(self, status: Optional[ApplicationStatus] = None) -> list[dict]:
        if not self._connected:
            self.connect()
        with session_scope() as session:
            rows = list_applications(session, status.value if status else None)
            out = []
            for row in rows:
                job = row.job
                out.append(
                    {
                        "id": row.id,
                        "job_id": row.job_id,
                        "job_title": job.title if job else "",
                        "company": job.company if job else "",
                        "location": job.location if job else "",
                        "status": row.status,
                        "applied_at": row.applied_at.isoformat() if row.applied_at else None,
                        "resume_version": row.resume_version,
                        "cover_letter_version": row.cover_letter_version,
                        "notes": row.notes,
                    }
                )
            return out

    def update_status(
        self,
        job_key: str,
        status: ApplicationStatus,
        error_message: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ) -> None:
        if not self._connected:
            self.connect()
        with session_scope() as session:
            apps = list_applications(session)
            for row in apps:
                job = row.job
                if not job:
                    continue
                key = f"{job.company.lower()}:{job.title.lower()}:{job.location.lower()}"
                alt = f"{job.source}:{job.external_job_id}"
                if job_key in {key, alt}:
                    if status == ApplicationStatus.APPLIED:
                        raise ValueError("Use mark_applied() to set APPLIED")
                    row.status = status.value
                    if error_message:
                        row.notes = error_message
                    return

    def close(self) -> None:
        reset_engine()
        self._connected = False
        logger.info("Database connection closed")
