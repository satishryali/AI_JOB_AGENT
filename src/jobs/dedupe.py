"""Job deduplication helpers."""

from __future__ import annotations

from urllib.parse import urlparse

from src.jobs.normalize import fallback_external_id, to_normalized
from src.models.job import NormalizedJob


def dedupe_key(job: NormalizedJob) -> str:
    """Primary uniqueness key: source + external id."""
    return f"{job.source.lower()}::{job.external_job_id}"


def fallback_key(job: NormalizedJob) -> str:
    """Fallback uniqueness when ids were generated locally."""
    return fallback_external_id(job.company, job.title, job.location, job.job_url)


def _url_key(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = (parsed.path or "").rstrip("/")
    return f"{host}{path}"


def deduplicate_jobs(jobs: list[NormalizedJob]) -> tuple[list[NormalizedJob], int]:
    """Return unique jobs and the number of duplicates dropped."""
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_generated: set[str] = set()
    unique: list[NormalizedJob] = []
    duplicates = 0
    for raw in jobs:
        job = to_normalized(raw)
        id_key = dedupe_key(job)
        url_key = _url_key(job.job_url)
        generated = job.external_job_id.startswith("hash:")
        keys_hit = id_key in seen_ids
        if url_key and url_key in seen_urls:
            keys_hit = True
        if generated and fallback_key(job) in seen_generated:
            keys_hit = True
        if keys_hit:
            duplicates += 1
            continue
        seen_ids.add(id_key)
        if url_key:
            seen_urls.add(url_key)
        if generated:
            seen_generated.add(fallback_key(job))
        unique.append(job)
    return unique, duplicates
