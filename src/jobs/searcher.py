"""Job search and parsing logic."""

from typing import Optional

from src.ai.matcher import load_user_skills, score_job
from src.collectors.runner import run_collectors
from src.config.config_loader import get_settings
from src.config.logging import get_logger
from src.config.settings import JobSearchSettings
from src.db.repository import update_match, upsert_job
from src.db.session import init_db, session_scope
from src.jobs.normalize import to_job
from src.models.job import Job, MatchResult

logger = get_logger(__name__)


class JobSearcher:
    """Search and collect jobs from multiple sources."""

    def __init__(self, settings: Optional[JobSearchSettings] = None):
        self._settings = settings or get_settings().job_search

    async def search_jobs(
        self,
        keywords: list[str] | None = None,
        locations: list[str] | None = None,
        portals: list[str] | None = None,
        max_results: int | None = None,
    ) -> list[Job]:
        """Search for jobs across configured collectors.

        Portal names are accepted for compatibility; HTTP collectors run first.
        Browser portals are not invoked here so a failed scrape cannot crash collection.
        """
        keywords = keywords or self._settings.keywords
        locations = locations or self._settings.locations
        max_results = max_results or self._settings.max_results_per_portal

        logger.info(
            "Starting job search",
            keywords=keywords,
            locations=locations,
            portals=portals or self._settings.portals,
            max_results=max_results,
        )

        unique, results, duplicates = await run_collectors(keywords, locations, max_results)
        init_db()
        jobs: list[Job] = []
        new_count = 0
        with session_scope() as session:
            for item in unique:
                _record, created = upsert_job(session, item)
                if created:
                    new_count += 1
                jobs.append(to_job(item))

        logger.info(
            "Job search complete",
            total_jobs=len(jobs),
            duplicates=duplicates,
            new_jobs=new_count,
            source_errors=sum(1 for r in results if r.error and not r.skipped),
        )
        return jobs

    async def _search_portal(
        self,
        portal: str,
        keywords: list[str],
        locations: list[str],
        max_results: int,
    ) -> list[Job]:
        """Compatibility wrapper. Isolated so one portal cannot crash the pipeline."""
        try:
            unique, _results, _dupes = await run_collectors(keywords, locations, max_results)
            return [to_job(item) for item in unique if item.source == portal or portal in {"remotive", "adzuna"}]
        except Exception as e:
            logger.error("Portal search failed", portal=portal, error=str(e))
            return []

    async def match_jobs(
        self,
        jobs: list[Job],
        resume_text: str,
        min_score: Optional[float] = None,
    ) -> list[MatchResult]:
        """Match jobs against resume using deterministic scoring."""
        settings = get_settings()
        min_score = min_score if min_score is not None else self._settings.min_match_score
        user_skills = load_user_skills(settings.resume.skills_path)

        logger.info("AI matching started", total_jobs=len(jobs), min_score=min_score)

        results: list[MatchResult] = []
        init_db()
        for job in jobs:
            try:
                result = score_job(
                    job=job,
                    user_skills=user_skills,
                    resume_text=resume_text,
                    preferred_locations=list(settings.user.preferred_locations) or list(self._settings.locations),
                    preferred_roles=list(settings.user.preferred_roles) or list(self._settings.keywords),
                    years_experience=settings.resume.experience_years,
                    salary_expectation=settings.user.salary_expectations,
                    min_score=min_score,
                )
                with session_scope() as session:
                    from src.jobs.normalize import to_normalized

                    row, _ = upsert_job(session, to_normalized(job))
                    update_match(
                        session,
                        row.id,
                        result.score,
                        result.matched_skills,
                        result.missing_skills,
                        result.reasoning,
                    )
                logger.info(
                    "Job matched",
                    job=job.title,
                    company=job.company,
                    score=result.score,
                    status="matched" if result.should_apply else "mismatched",
                )
                results.append(result)
            except Exception as e:
                logger.error("Job matching failed", job=job.title, error=str(e))
                continue

        logger.info("AI matching completed", matched=len(results))
        return results
