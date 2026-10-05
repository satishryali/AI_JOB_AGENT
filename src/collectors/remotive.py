"""Remotive public job API collector (no API key)."""

from __future__ import annotations

import httpx

from src.collectors.base import BaseCollector
from src.config.logging import get_logger
from src.jobs.normalize import to_normalized
from src.models.job import NormalizedJob

logger = get_logger(__name__)

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


class RemotiveCollector(BaseCollector):
    name = "remotive"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def collect(
        self,
        keywords: list[str],
        locations: list[str],
        max_results: int,
    ) -> list[NormalizedJob]:
        query = " ".join(keywords[:3]).strip() or "python"
        jobs: list[NormalizedJob] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(REMOTIVE_URL, params={"search": query, "limit": max_results})
            response.raise_for_status()
            payload = response.json()

        for item in payload.get("jobs", []):
            if len(jobs) >= max_results:
                break
            if not item.get("title") or not item.get("company_name"):
                continue
            blob = f"{item.get('title') or ''} {item.get('description') or ''}".lower()
            if keywords and not any(k.lower() in blob for k in keywords):
                continue
            location = item.get("candidate_required_location") or "Remote"
            # Remotive is remote-only; do not drop jobs because preferred cities are on-site India.
            jobs.append(
                to_normalized(
                    {
                        "source": "remotive",
                        "external_job_id": str(item.get("id") or ""),
                        "title": item.get("title") or "",
                        "company": item.get("company_name") or "",
                        "location": location,
                        "description": item.get("description") or "",
                        "salary": item.get("salary") or "",
                        "job_url": item.get("url") or item.get("job_url") or "",
                        "posted_date": item.get("publication_date"),
                        "skills": item.get("tags") or [],
                    }
                )
            )
        logger.info(f"Remotive collected {len(jobs)} jobs (query={query})")
        return jobs
