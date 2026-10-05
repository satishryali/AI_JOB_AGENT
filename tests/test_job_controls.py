"""Exercise the job-list controls in a real browser without external requests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.db.models import ApplicationRecord
from src.db.repository import upsert_job
from src.db.session import session_scope
from src.models.job import NormalizedJob


def test_browser_search_filters_and_column_sort(db, tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    from src.api.app import create_app

    with session_scope() as session:
        for key, title, source, score in [("1", "Zebra SQL Engineer", "indeed", 20),
                                          ("2", "Alpha Data Engineer", "linkedin", 80),
                                          ("3", "Beta Developer", "indeed", None)]:
            job, _ = upsert_job(session, NormalizedJob(source=source, external_job_id=key,
                title=title, company="Example", location="Hyderabad", job_url="https://example.com/" + key))
            job.match_score = score
            if key == "2":
                session.add(ApplicationRecord(job_id=job.id, status="review"))
    with TestClient(create_app()) as client, playwright.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).exists():
            pytest.skip("Install Playwright Chromium to run browser verification")
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            def serve(route):
                response = client.get(route.request.url.replace("http://job-assistant.test", ""))
                route.fulfill(status=response.status_code, body=response.content,
                              content_type=response.headers.get("content-type", "text/html"))
            page.route("http://job-assistant.test/**", serve)
            page.goto("http://job-assistant.test/jobs")
            playwright.expect(page.locator("#job-count")).to_have_text("3 of 3 jobs")
            page.get_by_role("searchbox", name="Search jobs").fill("alpha")
            playwright.expect(page.locator("tr[data-job-id]:visible")).to_have_count(1)
            page.get_by_role("button", name="Reset filters").click()
            page.locator("#job-source").select_option("indeed")
            playwright.expect(page.locator("tr[data-job-id]:visible")).to_have_count(2)
            page.locator("#job-min-score").fill("50")
            playwright.expect(page.locator("#no-jobs")).to_be_visible()
            page.get_by_role("button", name="Reset filters").click()
            page.locator("#job-status").select_option("review")
            playwright.expect(page.locator("tr[data-job-id]:visible")).to_have_count(1)
            page.get_by_role("button", name="Reset filters").click()
            page.get_by_role("button", name="Title", exact=True).click()
            assert page.locator("tr[data-job-id]").first.get_attribute("data-title") == "Alpha Data Engineer"
            page.get_by_role("button", name="Match", exact=True).click()
            assert page.locator("tr[data-job-id]").first.get_attribute("data-score") == "20.0"
            page.get_by_role("button", name="Match", exact=True).click()
            assert page.locator("tr[data-job-id]").first.get_attribute("data-score") == "80.0"
            assert page.locator("tr[data-job-id]").last.get_attribute("data-score") == ""
            assert not errors
            page.screenshot(path=str(tmp_path / "jobs-controls.png"), full_page=True)
        finally:
            browser.close()
