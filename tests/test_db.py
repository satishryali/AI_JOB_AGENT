from src.db.repository import get_job, list_jobs, upsert_job
from src.db.session import session_scope
from src.models.job import NormalizedJob


def test_job_persistence_idempotent(db):
    job = NormalizedJob(
        source="remotive",
        external_job_id="42",
        title="Python Dev",
        company="Acme",
        location="Remote",
        job_url="https://example.com/42",
        skills=["Python"],
    )
    with session_scope() as session:
        first, created1 = upsert_job(session, job)
        first_id = first.id
        assert created1 is True
    with session_scope() as session:
        second, created2 = upsert_job(session, job)
        assert created2 is False
        assert second.id == first_id
        assert get_job(session, first_id).title == "Python Dev"
        assert len(list_jobs(session)) == 1
