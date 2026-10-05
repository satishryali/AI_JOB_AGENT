import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.jobs import importer


def job_html():
    posting = {"@type": "JobPosting", "title": "Data Engineer", "description": "<p>Build Python and SQL pipelines.</p>",
               "hiringOrganization": {"name": "Example"}, "datePosted": "2026-10-05",
               "jobLocation": {"address": {"addressLocality": "Hyderabad", "addressCountry": "India"}},
               "baseSalary": {"currency": "INR", "value": {"minValue": 100000, "maxValue": 150000, "unitText": "MONTH"}}}
    return '<html><script type="application/ld+json">' + json.dumps({"@graph": [posting]}) + '</script></html>'


def test_nested_structured_job_extraction():
    job = importer.parse_job_page(job_html(), "https://careers.example.com/job/1")
    assert job.title == "Data Engineer" and job.company == "Example"
    assert job.location == "Hyderabad, India"
    assert job.description == "Build Python and SQL pipelines."
    assert job.salary == "INR 100000 - 150000 MONTH"
    assert job.posted_date.year == 2026


def test_public_html_fallback_and_blocked_page():
    html = '<h1>Python Engineer</h1><div class="job-company">Example</div><div class="job-description">Build APIs.</div>'
    assert importer.parse_job_page(html, "https://example.com/1").company == "Example"
    with pytest.raises(importer.JobImportError, match="paste"):
        importer.parse_job_page("<h1>Sign in</h1>", "https://example.com/1")


@pytest.mark.parametrize("url", ["http://127.0.0.1/jobs", "http://[::1]/jobs", "file:///etc/passwd", "https://user:pass@example.com/job"])
async def test_private_and_nonpublic_import_urls_rejected(url):
    with pytest.raises(importer.JobImportError):
        await importer.validate_public_url(url)


async def test_fetch_job_details_follows_validated_redirect(monkeypatch):
    validate = AsyncMock()
    monkeypatch.setattr(importer, "validate_public_url", validate)
    original = httpx.AsyncClient
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "/new"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=job_html())
    monkeypatch.setattr(importer.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    job = await importer.fetch_job_details("https://example.com/old")
    assert job.job_url == "https://example.com/new"
    assert validate.await_count == 2


def test_url_only_import_and_user_overrides(db, monkeypatch):
    from src.api import app as api

    fetched = importer.parse_job_page(job_html(), "https://example.com/job/1")
    fetch = AsyncMock(return_value=fetched)
    monkeypatch.setattr(api, "fetch_job_details", fetch)
    with TestClient(api.create_app()) as client:
        response = client.post("/jobs/import", data={"job_url": fetched.job_url, "company": "Reviewed Company"}, follow_redirects=False)
        assert response.status_code == 303
        page = client.get(response.headers["location"])
        assert "Reviewed Company" in page.text and "Build Python and SQL pipelines." in page.text
        fetch.assert_awaited_once()
        fetch.side_effect = importer.JobImportError("Site requires login; paste details manually")
        assert client.post("/jobs/import", data={"job_url": fetched.job_url}).status_code == 400
