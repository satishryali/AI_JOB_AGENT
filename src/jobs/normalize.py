"""Normalize collected jobs into a common structure."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from src.models.job import Job, JobSource, NormalizedJob


_WHITESPACE = re.compile(r"\s+")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", str(value)).strip()


def _source(value: Any) -> JobSource:
    if isinstance(value, JobSource):
        return value
    raw = _clean(value).lower()
    try:
        return JobSource(raw)
    except ValueError:
        return JobSource.OTHER


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = _clean(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(text.replace("Z", ""), fmt.replace("Z", ""))
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def fallback_external_id(company: str, title: str, location: str, job_url: str) -> str:
    """Stable id when a source does not provide one."""
    parts = "|".join(
        [
            _clean(company).lower(),
            _clean(title).lower(),
            _clean(location).lower(),
            _normalize_url(job_url),
        ]
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:32]


def _normalize_url(url: str) -> str:
    url = _clean(url)
    if not url:
        return ""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = (parsed.path or "").rstrip("/")
    return f"{host}{path}"


def to_normalized(payload: dict[str, Any] | NormalizedJob | Job) -> NormalizedJob:
    """Convert dict/Job into NormalizedJob with required fields filled."""
    if isinstance(payload, NormalizedJob):
        data = payload.model_dump()
    elif isinstance(payload, Job):
        data = {
            "source": payload.source.value,
            "external_job_id": payload.external_job_id,
            "title": payload.title,
            "company": payload.company,
            "location": payload.location,
            "description": payload.description,
            "skills": payload.skills_required,
            "salary": payload.salary_range or "",
            "job_url": str(payload.url) if payload.url else "",
            "posted_date": payload.posted_date,
        }
    else:
        data = dict(payload)

    title = _clean(data.get("title"))
    company = _clean(data.get("company"))
    location = _clean(data.get("location"))
    job_url = _clean(data.get("job_url") or data.get("url"))
    raw_source = _clean(data.get("source")).lower() or JobSource.OTHER.value
    external_id = _clean(data.get("external_job_id") or data.get("id"))
    if not external_id:
        external_id = "hash:" + fallback_external_id(company, title, location, job_url)

    skills = data.get("skills") or data.get("skills_required") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]
    skills = [_clean(s) for s in skills if _clean(s)]

    return NormalizedJob(
        source=raw_source,
        external_job_id=external_id,
        title=title,
        company=company,
        location=location,
        description=_clean(data.get("description")),
        skills=skills,
        salary=_clean(data.get("salary") or data.get("salary_range")),
        job_url=job_url,
        posted_date=_parse_datetime(data.get("posted_date") or data.get("publication_date")),
    )


def to_job(normalized: NormalizedJob) -> Job:
    """Convert a normalized job into the existing Job model."""
    url = normalized.job_url or None
    payload = dict(
        title=normalized.title or "Untitled",
        company=normalized.company or "Unknown",
        location=normalized.location,
        description=normalized.description,
        source=_source(normalized.source),
        salary_range=normalized.salary or None,
        posted_date=normalized.posted_date,
        skills_required=list(normalized.skills),
        remote="remote" in normalized.location.lower(),
        external_job_id=normalized.external_job_id,
        collected_at=datetime.now(timezone.utc),
    )
    try:
        return Job(url=url, **payload)
    except Exception:
        return Job(url=None, **payload)
