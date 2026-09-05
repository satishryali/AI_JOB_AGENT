from src.jobs.dedupe import deduplicate_jobs
from src.models.job import NormalizedJob


def test_dedupe_by_source_and_external_id():
    jobs = [
        NormalizedJob(source="remotive", external_job_id="1", title="A", company="C"),
        NormalizedJob(source="remotive", external_job_id="1", title="A again", company="C"),
        NormalizedJob(source="adzuna", external_job_id="1", title="A", company="C"),
    ]
    unique, dupes = deduplicate_jobs(jobs)
    assert len(unique) == 2
    assert dupes == 1


def test_dedupe_fallback_company_title_location_url():
    jobs = [
        NormalizedJob(
            source="other",
            external_job_id="x",
            title="Dev",
            company="Acme",
            location="Remote",
            job_url="https://jobs.example.com/1",
        ),
        NormalizedJob(
            source="company",
            external_job_id="y",
            title="Dev",
            company="Acme",
            location="Remote",
            job_url="https://jobs.example.com/1",
        ),
    ]
    unique, dupes = deduplicate_jobs(jobs)
    assert len(unique) == 1
    assert dupes == 1
