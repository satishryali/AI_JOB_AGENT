"""Run collectors with isolated failures."""

from __future__ import annotations

import asyncio

from src.collectors.adzuna import AdzunaCollector
from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.remotive import RemotiveCollector
from src.collectors.jobspy import JobSpyCollector, SUPPORTED_SITES
from src.config.config_loader import get_settings
from src.config.logging import get_logger
from src.jobs.dedupe import deduplicate_jobs
from src.models.job import NormalizedJob

logger = get_logger(__name__)


def default_collectors() -> list[BaseCollector]:
    collectors = [RemotiveCollector(), AdzunaCollector()]
    for site in dict.fromkeys(get_settings().job_search.collection_sites):
        if site not in SUPPORTED_SITES:
            raise ValueError(f"Unsupported collection site: {site}")
        collectors.append(JobSpyCollector(site))
    return collectors


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

    semaphore = asyncio.Semaphore(3)

    async def collect_source(collector):
        async with semaphore:
            logger.info("source started", source=collector.name)
            try:
                jobs = await collector.collect(keywords, locations, max_results)
                logger.info(f"{collector.name}: {len(jobs)} jobs collected")
                return CollectorResult(source=collector.name, jobs=jobs)
            except PermissionError as e:
                return CollectorResult(source=collector.name, skipped=True, error=str(e))
            except asyncio.TimeoutError:
                return CollectorResult(source=collector.name, jobs=getattr(collector, "partial_jobs", []),
                                       error="Search timed out; try fewer queries or retry later")
            except Exception as e:
                logger.error(f"{collector.name} source failed: {e}")
                return CollectorResult(source=collector.name, jobs=getattr(collector, "partial_jobs", []), error=str(e))

    results = await asyncio.gather(*(collect_source(c) for c in collectors))
    combined = [job for result in results for job in result.jobs]

    unique, duplicates = deduplicate_jobs(combined)
    logger.info(
        "collection complete",
        collected=len(combined),
        duplicates=duplicates,
        new_unique=len(unique),
    )
    return unique, results, duplicates
