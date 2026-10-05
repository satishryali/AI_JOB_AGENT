"""The shortlist workflow prepares documents and leaves submission to the user."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.models.job import Job, MatchResult


@pytest.mark.asyncio
@pytest.mark.parametrize("rank", [False, True])
async def test_cli_collects_links_without_applying(monkeypatch, capsys, rank):
    from src import main
    from src.portals.linkedin import LinkedInClient

    job = Job(title="Python Engineer", company="Example", url="https://example.com/jobs/1")
    searcher = main.JobSearcher()
    monkeypatch.setattr(searcher, "search_jobs", AsyncMock(return_value=[job]))
    monkeypatch.setattr(searcher, "match_jobs", AsyncMock(return_value=[MatchResult(job=job, score=85)]))
    monkeypatch.setattr(main, "JobSearcher", lambda: searcher)
    monkeypatch.setattr(main, "read_resume_text", AsyncMock(return_value="Python engineer"))
    monkeypatch.setattr(main, "setup_logging", lambda _: None)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(type(main.get_settings().resume.path), "exists", lambda _: True)
    login = AsyncMock()
    apply = AsyncMock(side_effect=AssertionError("Must not submit"))
    monkeypatch.setattr(LinkedInClient, "login", login)
    monkeypatch.setattr(LinkedInClient, "apply", apply)
    await main.run_agent(rank=rank)
    assert "https://example.com/jobs/1" in capsys.readouterr().out
    login.assert_not_called()
    apply.assert_not_called()
    assert searcher.match_jobs.await_count == int(rank)


def test_default_command_opens_dashboard(monkeypatch):
    from src import main

    calls = []
    monkeypatch.setattr("sys.argv", ["job-hunter"])
    monkeypatch.setattr(main, "serve", lambda: calls.append("serve"))
    monkeypatch.setattr(main, "run_agent", AsyncMock(side_effect=AssertionError("Unexpected collection")))
    main.main()
    assert calls == ["serve"]


def test_linkedin_collection_includes_external_application_jobs():
    from urllib.parse import parse_qs, urlsplit
    from src.config.config_loader import get_settings
    from src.portals.linkedin import LinkedInClient

    query = parse_qs(urlsplit(LinkedInClient()._build_search_url("data engineer", "Hyderabad")).query)
    assert "f_AL" not in query
    assert query["f_TPR"] == [f"r{get_settings().job_search.days_back * 86400}"]


def test_import_prepare_download_and_manual_status(db, monkeypatch, tmp_path):
    from src.api import app as api
    from src.db.repository import list_applications
    from src.db.session import session_scope

    monkeypatch.setattr(api, "_resume_text", lambda: "Python engineer. Built SQL pipelines at Example.")
    monkeypatch.setattr(api.get_settings().llm, "api_key", "")
    monkeypatch.chdir(tmp_path)
    client = TestClient(api.create_app())
    payload = {"title": "Data Engineer", "company": "Example", "location": "Hyderabad",
               "description": "Python and SQL pipelines", "job_url": "https://careers.example.com/jobs/1"}
    response = client.post("/jobs/import", data=payload, follow_redirects=False)
    assert response.status_code == 303
    detail_url = response.headers["location"]
    assert client.post("/jobs/import", data={**payload, "job_url": "javascript:alert(1)"}).status_code == 400
    # Adding a listing or following the legacy prepare route must not create an application.
    prepared = client.post(detail_url + "/prepare").json()
    assert prepared["status"] == "manual_application"
    assert prepared["job_url"] == payload["job_url"]
    with session_scope() as session:
        assert not list_applications(session)
    assert client.post(detail_url + "/tailor", follow_redirects=False).status_code == 303
    draft = client.get(detail_url + "/documents/resume")
    assert draft.status_code == 200
    assert "Built SQL pipelines at Example." in draft.text
    assert "attachment" in draft.headers["content-disposition"]
    assert client.post(detail_url + "/cover-letter", follow_redirects=False).status_code == 303
    assert client.get(detail_url + "/documents/cover").status_code == 200
    page = client.get(detail_url)
    assert page.status_code == 200
    assert "Open application link" in page.text
    assert "Prepare in browser" not in page.text
    with session_scope() as session:
        application = list_applications(session)[0]
        assert application.status == "review"
        assert application.applied_at is None
        application_id = application.id
    assert client.post(f"/applications/{application_id}/status", data={"status": "applied"}, follow_redirects=False).status_code == 303
    with session_scope() as session:
        assert list_applications(session)[0].applied_at is not None


def test_tailoring_requires_base_resume(db, monkeypatch):
    from src.api import app as api

    monkeypatch.setattr(api, "_resume_text", lambda: "")
    client = TestClient(api.create_app())
    assert client.post("/jobs/1/tailor").status_code == 400
