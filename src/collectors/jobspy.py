"""Multi-board discovery via JobSpy, with a timeout per search."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from src.collectors.base import BaseCollector
from src.config.config_loader import get_settings
from src.jobs.normalize import to_normalized

SUPPORTED_SITES = {"linkedin", "indeed", "glassdoor", "google", "naukri", "bayt", "bdjobs", "zip_recruiter"}


class JobSpyCollector(BaseCollector):
    def __init__(self, site: str):
        self.name = site
        self.partial_jobs = []

    async def collect(self, keywords, locations, max_results):
        if importlib.util.find_spec("jobspy") is None:
            raise PermissionError("Install requirements.txt with this Python interpreter to enable JobSpy")
        settings = get_settings().job_search
        jobs = []
        self.partial_jobs = jobs
        seen = set()
        cities = list(dict.fromkeys("Bengaluru" if loc.lower() == "bangalore" else loc for loc in locations)) or [""]
        queries = [(term, loc) for term in keywords or ["data engineer"] for loc in cities]
        for term, location in queries[:settings.max_queries_per_source]:
            options = dict(site_name=[self.name], search_term=term, location=location,
                           google_search_term=f"{term} jobs in {location}",
                           results_wanted=max_results - len(jobs),
                           hours_old=settings.days_back * 24,
                           country_indeed=settings.country, fetch_description=True, verbose=0)
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "src.collectors.jobspy_worker",
                cwd=str(Path(__file__).resolve().parents[2]),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(json.dumps(options).encode()), settings.source_timeout
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                process.kill()
                await process.communicate()
                raise
            if process.returncode:
                raise RuntimeError(f"{self.name} collection failed: {stderr.decode(errors='replace')[-400:]}")
            records = json.loads(stdout)
            if not records and b"ERROR" in stderr:
                raise RuntimeError(f"{self.name} returned no listings: {stderr.decode(errors='replace')[-400:]}")
            for item in records:
                url = item.get("job_url") or ""
                if not item.get("title") or not item.get("company") or not url or url in seen:
                    continue
                seen.add(url)
                salary = " - ".join(str(item[k]) for k in ("min_amount", "max_amount") if item.get(k) is not None)
                jobs.append(to_normalized(dict(source=self.name,
                    external_job_id=item.get("id") or "", title=item["title"], company=item["company"],
                    location=item.get("location") or location, description=item.get("description") or "",
                    salary=f"{salary} {item.get('currency') or ''} {item.get('interval') or ''}".strip() if salary else "",
                    job_url=item.get("job_url_direct") or url, posted_date=item.get("date_posted"))))
                if len(jobs) >= max_results:
                    return jobs
        return jobs
