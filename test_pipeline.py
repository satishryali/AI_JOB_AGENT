"""Legacy pipeline smoke test — uses the SQLAlchemy tracker."""

import asyncio
import os
import tempfile
from pathlib import Path

from src.db.session import reset_engine
from src.jobs.tracker import ApplicationTracker
from src.models.job import ApplicationResult, ApplicationStatus, Job, JobSource, MatchResult


async def test():
    j = Job(
        title="Senior Python Developer",
        company="Tech Corp",
        location="Remote",
        description="We need a Python expert with AI experience",
        source=JobSource.LINKEDIN,
        skills_required=["Python", "AI", "Machine Learning"],
    )
    MatchResult(job=j, score=85, should_apply=True, reasoning="Great match", matched_skills=["Python"], missing_skills=["Kubernetes"])

    db_path = Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    reset_engine()

    tracker = ApplicationTracker(database_url=os.environ["DATABASE_URL"])
    tracker.connect()

    print("Is already applied:", tracker.is_already_applied(j))

    app_result = ApplicationResult(
        job=j,
        status=ApplicationStatus.READY,
        portal="linkedin",
        resume_path="data/resumes/resume.pdf",
    )
    tracker.record_application(app_result)
    print("Prepared application (not applied):", tracker.is_already_applied(j))

    tracker.mark_applied(j, notes="User confirmed submit")
    print("Is now applied:", tracker.is_already_applied(j))

    apps = tracker.get_all_applications()
    print(f"Found {len(apps)} application(s) in DB")
    print(f"Status: {apps[0]['status']}")

    try:
        tracker.mark_applied(j)
        print("ERROR: duplicate apply should have failed")
        raise SystemExit(1)
    except ValueError as e:
        print("Duplicate apply blocked:", e)

    tracker.close()
    print("\nFull pipeline test PASSED!")


if __name__ == "__main__":
    asyncio.run(test())
