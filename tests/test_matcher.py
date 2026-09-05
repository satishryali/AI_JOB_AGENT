from src.ai.matcher import score_job, skills_match
from src.models.job import Job, JobSource


def _job(**kwargs) -> Job:
    data = dict(
        title="Python Data Engineer",
        company="Example",
        location="Remote",
        description="Looking for Python, SQL, PostgreSQL, ETL, Snowflake. AWS is required.",
        skills_required=["Python", "SQL", "PostgreSQL", "ETL", "Snowflake", "AWS"],
        source=JobSource.REMOTIVE,
        remote=True,
    )
    data.update(kwargs)
    return Job(**data)


def test_match_score_deterministic():
    user = ["Python", "SQL", "PostgreSQL", "ETL", "Snowflake"]
    job = _job()
    a = score_job(job, user, resume_text="Python SQL PostgreSQL ETL Snowflake", years_experience=4)
    b = score_job(job, user, resume_text="Python SQL PostgreSQL ETL Snowflake", years_experience=4)
    assert a.score == b.score
    assert 0 <= a.score <= 100


def test_missing_skill_detection():
    user = ["Python", "SQL", "PostgreSQL", "ETL", "Snowflake"]
    result = score_job(_job(), user, years_experience=4)
    assert "Python" in result.matched_skills or any("python" in s.lower() for s in result.matched_skills)
    assert any("aws" in s.lower() for s in result.missing_skills)
    assert result.score >= 50


def test_skills_match_helper():
    matched, missing = skills_match(
        ["Python", "SQL & Database Development", "PostgreSQL", "ETL/ELT", "Snowflake"],
        ["Python", "SQL", "PostgreSQL", "ETL", "Snowflake", "AWS"],
    )
    assert "AWS" in missing
    assert "Python" in matched
