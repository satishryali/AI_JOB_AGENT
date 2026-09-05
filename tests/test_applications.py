import pytest

from src.db.repository import (
    create_or_get_application,
    list_applications,
    set_application_status,
    upsert_job,
)
from src.db.session import session_scope
from src.models.job import ApplicationStatus, NormalizedJob


def _job():
    return NormalizedJob(source="remotive", external_job_id="j1", title="Dev", company="Co")


def test_status_transitions(db):
    with session_scope() as session:
        job, _ = upsert_job(session, _job())
        app, created, warning = create_or_get_application(session, job.id)
        assert created
        assert warning == ""
        assert app.status == ApplicationStatus.SAVED.value
        set_application_status(session, app.id, ApplicationStatus.REVIEW.value)
        set_application_status(session, app.id, ApplicationStatus.READY.value)
        set_application_status(session, app.id, ApplicationStatus.APPLIED.value, mark_applied=True)
        assert app.applied_at is not None


def test_cannot_silently_mark_applied(db):
    with session_scope() as session:
        job, _ = upsert_job(session, _job())
        app, _, _ = create_or_get_application(session, job.id)
        with pytest.raises(ValueError):
            set_application_status(session, app.id, ApplicationStatus.APPLIED.value, mark_applied=False)


def test_duplicate_applied_warning(db):
    with session_scope() as session:
        job, _ = upsert_job(session, _job())
        app, _, _ = create_or_get_application(session, job.id)
        set_application_status(session, app.id, ApplicationStatus.APPLIED.value, mark_applied=True)
        again, created, warning = create_or_get_application(session, job.id)
        assert created is False
        assert "APPLIED" in warning
        assert again.id == app.id
        assert len(list_applications(session)) == 1
