import csv
import io
import asyncio

from fastapi.testclient import TestClient

from src.db.repository import upsert_job
from src.db.session import session_scope
from src.models.job import NormalizedJob


def test_csv_preserves_links_quotes_unicode_and_all_rows(db):
    from src.api.app import create_app

    with session_scope() as session:
        for i in range(205):
            upsert_job(session, NormalizedJob(source="naukri", external_job_id=str(i),
                title="Data, Engineer", company='Example "India"', location="Hyderabad",
                job_url=f"https://example.com/jobs/{i}", description="Résumé, SQL\nPython"))
        upsert_job(session, NormalizedJob(source="indeed", external_job_id="formula",
            title="=1+1", company="Example", job_url="https://example.com/jobs/formula"))
    with TestClient(create_app()) as client:
        response = client.get("/jobs/export.csv")
        assert response.status_code == 200
        assert response.content.startswith(b"\xef\xbb\xbf")
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert len(rows) == 206
        normal = next(r for r in rows if r["job_url"].endswith("/0"))
        assert normal["title"] == "Data, Engineer"
        assert normal["company"] == 'Example "India"'
        assert "Résumé" in normal["description"]
        assert next(r for r in rows if r["job_url"].endswith("formula"))["title"] == "'=1+1"
        assert "Download CSV" in client.get("/jobs").text


def test_imported_site_keeps_source_through_normalization():
    from src.jobs.normalize import to_job, to_normalized

    item = NormalizedJob(source="careers.example.com", external_job_id="1", title="Engineer", company="Example")
    assert to_normalized(to_job(item)).source == item.source


async def test_source_timeout_keeps_partial_listings():
    from src.collectors.base import BaseCollector
    from src.collectors.runner import run_collectors

    class PartialSource(BaseCollector):
        name = "partial"
        partial_jobs = [NormalizedJob(source="partial", external_job_id="1", title="Engineer", company="Example")]

        async def collect(self, *args):
            raise asyncio.TimeoutError()

    jobs, results, _ = await run_collectors(["data engineer"], ["Hyderabad"], 10, [PartialSource()])
    assert len(jobs) == 1
    assert "timed out" in results[0].error


async def test_background_collection_keeps_dashboard_available(db, monkeypatch):
    from src.api.app import create_app
    from src.jobs.searcher import JobSearcher
    import httpx

    entered = asyncio.Event()
    finish = asyncio.Event()

    async def search(self):
        entered.set()
        await finish.wait()
        return []

    monkeypatch.setattr(JobSearcher, "search_jobs", search)
    monkeypatch.setattr("src.api.app.save_jobs_csv", lambda path: path)
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/jobs/collect")
        assert response.status_code == 303
        await entered.wait()
        assert (await client.get("/api/collection")).json()["running"]
        assert (await client.get("/jobs")).status_code == 200
        first_task = app.state.collection_task
        await client.post("/jobs/collect")
        assert app.state.collection_task is first_task
        finish.set()
        await first_task
        assert not (await client.get("/api/collection")).json()["running"]
