"""Adzuna Jobs API collector. Skips itself when credentials are missing."""

from __future__ import annotations

import os

import httpx

from src.collectors.base import BaseCollector
from src.config.logging import get_logger
from src.jobs.normalize import to_normalized
from src.models.job import NormalizedJob

logger = get_logger(__name__)


class AdzunaCollector(BaseCollector):
    name = "adzuna"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.app_id = os.environ.get("ADZUNA_APP_ID", "")
        self.app_key = os.environ.get("ADZUNA_APP_KEY", "")
        self.country = os.environ.get("ADZUNA_COUNTRY", "us")

    async def collect(
        self,
        keywords: list[str],
        locations: list[str],
        max_results: int,
    ) -> list[NormalizedJob]:
        if not self.app_id or not self.app_key:
            logger.info("Adzuna skipped — ADZUNA_APP_ID / ADZUNA_APP_KEY not set")
            raise PermissionError("Adzuna credentials not configured")

        what = " ".join(keywords[:4]).strip() or "python"
        where = locations[0] if locations else ""
        url = f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/1"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": what,
            "results_per_page": min(max_results, 50),
            "content-type": "application/json",
        }
        if where and where.lower() != "remote":
            params["where"] = where

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

        jobs: list[NormalizedJob] = []
        for item in payload.get("results", []):
            company = ""
            if isinstance(item.get("company"), dict):
                company = item["company"].get("display_name") or ""
            location = ""
            if isinstance(item.get("location"), dict):
                location = item["location"].get("display_name") or ""
            salary = ""
            if item.get("salary_min") or item.get("salary_max"):
                salary = f"{item.get('salary_min') or ''} - {item.get('salary_max') or ''}".strip(" -")
            jobs.append(
                to_normalized(
                    {
                        "source": "adzuna",
                        "external_job_id": str(item.get("id") or ""),
                        "title": item.get("title") or "",
                        "company": company,
                        "location": location,
                        "description": item.get("description") or "",
                        "salary": salary,
                        "job_url": item.get("redirect_url") or "",
                        "posted_date": item.get("created"),
                    }
                )
            )
            if len(jobs) >= max_results:
                break
        logger.info("Adzuna collected jobs", count=len(jobs))
        return jobs
