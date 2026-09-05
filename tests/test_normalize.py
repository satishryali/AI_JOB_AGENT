from src.jobs.normalize import fallback_external_id, to_job, to_normalized
from src.models.job import Job, JobSource


def test_normalize_dict_fills_external_id():
    job = to_normalized(
        {
            "source": "remotive",
            "title": "Python Engineer",
            "company": "Acme",
            "location": "Remote",
            "job_url": "https://example.com/jobs/1",
            "description": "Python and SQL",
            "skills": ["Python", "SQL"],
            "salary": "120000",
        }
    )
    assert job.source == "remotive"
    assert job.title == "Python Engineer"
    assert job.company == "Acme"
    assert job.external_job_id
    assert job.skills == ["Python", "SQL"]


def test_normalize_uses_provided_external_id():
    job = to_normalized({"source": "adzuna", "external_job_id": "abc", "title": "A", "company": "B"})
    assert job.external_job_id == "abc"


def test_fallback_id_is_stable():
    a = fallback_external_id("Acme", "Engineer", "Remote", "https://www.example.com/x/")
    b = fallback_external_id("acme", "engineer", "remote", "https://example.com/x")
    assert a == b


def test_job_round_trip():
    original = Job(
        title="ETL Developer",
        company="DataCo",
        location="NY",
        source=JobSource.REMOTIVE,
        external_job_id="99",
        url="https://example.com/j/99",
    )
    normalized = to_normalized(original)
    restored = to_job(normalized)
    assert restored.title == "ETL Developer"
    assert restored.external_job_id == "99"
    assert restored.source == JobSource.REMOTIVE
