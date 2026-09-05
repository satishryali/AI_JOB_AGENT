"""Run collectors with isolated failures."""

from __future__ import annotations

from src.collectors.adzuna import AdzunaCollector
from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.remotive import RemotiveCollector
from src.config.logging import get_logger
from src.jobs.dedupe import deduplicate_jobs
from src.models.job import NormalizedJob

logger = get_logger(__name__)


def default_collectors() -> list[BaseCollector]:
    return [RemotiveCollector(), AdzunaCollector()]


async def run_collectors(
    keywords: list[str],
    locations: list[str],
    max_results: int,
    collectors: list[BaseCollector] | None = None,
) -> tuple[list[NormalizedJob], list[CollectorResult], int]:
    """Collect from all sources. One failure does not stop the others.

    Returns unique jobs, per-source results, duplicate count.
    """
    collectors = collectors or default_collectors()
    logger.info("collector started", sources=[c.name for c in collectors])

    combined: list[NormalizedJob] = []
    results: list[CollectorResult] = []

    for collector in collectors:
        logger.info("source started", source=collector.name)
        try:
            jobs = await collector.collect(keywords, locations, max_results)
            combined.extend(jobs)
            results.append(CollectorResult(source=collector.name, jobs=jobs))
            logger.info("number of jobs collected", source=collector.name, count=len(jobs))
        except PermissionError as e:
            logger.info("source skipped", source=collector.name, reason=str(e))
            results.append(CollectorResult(source=collector.name, skipped=True, error=str(e)))
        except Exception as e:
            logger.error("source failed", source=collector.name, error=str(e))
            results.append(CollectorResult(source=collector.name, error=str(e)))

    unique, duplicates = deduplicate_jobs(combined)
    logger.info(
        "collection complete",
        collected=len(combined),
        duplicates=duplicates,
        new_unique=len(unique),
    )
    return unique, results, duplicates
