"""Regression coverage for the reported job-assistant defects."""

import asyncio
import io
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from src.ai.deepseek_client import DeepSeekClient, DeepSeekResponseError
from src.ai.matcher import _salary_score
from src.config.settings import LLMSettings
from src.db.models import ApplicationRecord
from src.db.repository import job_to_dict, overview_counts, upsert_job
from src.db.session import session_scope, get_engine
from src.jobs.normalize import _parse_datetime
from src.models.job import Job, NormalizedJob


@pytest.mark.parametrize("model", ["deepseek-chat", "deepseek-reasoner"])
async def test_json_requests_handle_legacy_reasoner(model):
    client = DeepSeekClient(LLMSettings(model=model))
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"answer": "Python"}'))]))
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert await client.generate_json("JSON please") == {"answer": "Python"}
    kwargs = create.call_args.kwargs
    assert ("response_format" in kwargs) == (model == "deepseek-chat")
    assert ("temperature" in kwargs) == (model == "deepseek-chat")


async def test_json_arrays_raise_client_error():
    client = DeepSeekClient()
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="[]"))]))
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(DeepSeekResponseError, match="JSON object"):
        await client.generate_json("JSON please")


async def test_linkedin_legacy_methods_never_touch_browser():
    from src.portals.linkedin import LinkedInClient

    class ForbiddenPage:
        def __getattr__(self, attr):
            raise AssertionError(f"Browser access forbidden: {attr}")

    client = LinkedInClient()
    client._page = ForbiddenPage()
    job = Job(title="Engineer", company="Example", url="https://linkedin.com/jobs/view/123456789")
    result = await client.apply(job)
    assert result.requires_manual and not result.success
    assert result.application_url == job.url
    assert await client._click_easy_apply_step() == "manual"
    assert (await client._complete_easy_apply(job)).requires_manual


def test_yaml_reload_and_environment_precedence(monkeypatch, tmp_path):
    from src.config.config_loader import create_settings

    isolated_env = dict(os.environ)
    for key in ["JOB_MIN_MATCH_SCORE", "RESUME_EXPERIENCE_YEARS"]:
        isolated_env.pop(key, None)
    monkeypatch.setattr(os, "environ", isolated_env)
    config = tmp_path / "config.yaml"
    config.write_text("job_search:\n  min_match_score: 61\nresume:\n  experience_years: 3\n")
    assert create_settings(config).job_search.min_match_score == 61
    config.write_text("job_search:\n  min_match_score: 82\nresume:\n  experience_years: 6\n")
    assert create_settings(config).job_search.min_match_score == 82
    assert "JOB_MIN_MATCH_SCORE" not in os.environ
    (tmp_path / ".env").write_text("JOB_MIN_MATCH_SCORE=73\nRESUME_EXPERIENCE_YEARS=7\n")
    assert create_settings(config).job_search.min_match_score == 73
    os.environ["JOB_MIN_MATCH_SCORE"] = "91"
    assert create_settings(config).job_search.min_match_score == 91


def test_defaults_agree_with_yaml_and_env_example():
    from pathlib import Path
    import yaml
    from dotenv import dotenv_values
    from src.config.settings import JobSearchSettings, ResumeSettings, DatabaseSettings

    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "config.yaml").read_text())
    example = dotenv_values(root / ".env.example")
    assert config["job_search"]["min_match_score"] == JobSearchSettings.model_fields["min_match_score"].default == float(example["JOB_MIN_MATCH_SCORE"])
    assert config["resume"]["experience_years"] == ResumeSettings.model_fields["experience_years"].default == int(example["RESUME_EXPERIENCE_YEARS"])
    assert config["database"]["path"] == str(DatabaseSettings.model_fields["path"].default).replace("\\", "/")
    assert example["DATABASE_URL"] == "sqlite:///" + config["database"]["path"]


def test_documents_redirect_preserve_applied_and_download_formats(db, monkeypatch, tmp_path):
    from docx import Document
    from src.api import app as api

    monkeypatch.setattr(api, "_resume_text", lambda: "Built Python and SQL pipelines at Example.")
    monkeypatch.setattr(api.get_settings().llm, "api_key", "")
    monkeypatch.chdir(tmp_path)
    with session_scope() as session:
        job, _ = upsert_job(session, NormalizedJob(source="test", external_job_id="1", title="Data Engineer", company="Example", description="Python SQL"))
        job_id = job.id
    with TestClient(api.create_app()) as client:
        for action, kind in [("tailor", "resume"), ("cover-letter", "cover")]:
            url = f"/jobs/{job_id}/{action}"
            for _ in range(2):
                response = client.post(url, follow_redirects=False)
                assert response.status_code == 303
                assert response.headers["location"] == f"/jobs/{job_id}"
            pdf = client.get(f"/jobs/{job_id}/documents/{kind}?format=pdf")
            docx = client.get(f"/jobs/{job_id}/documents/{kind}?format=docx")
            assert pdf.status_code == docx.status_code == 200
            assert pdf.content.startswith(b"%PDF")
            assert Document(io.BytesIO(docx.content)).paragraphs
        assert client.get(f"/jobs/{job_id}/documents/resume?format=exe").status_code == 400
        with session_scope() as session:
            app = session.query(ApplicationRecord).first()
            app.status = "applied"
            app.applied_at = datetime.now(timezone.utc)
        before = (tmp_path / "data/applications" / f"resume_{job_id}.docx").read_bytes()
        for action in ["tailor", "cover-letter"]:
            assert client.post(f"/jobs/{job_id}/{action}", follow_redirects=False).status_code == 303
        assert (tmp_path / "data/applications" / f"resume_{job_id}.docx").read_bytes() == before
        with session_scope() as session:
            assert session.query(ApplicationRecord).first().status == "applied"


def test_overview_aggregates_without_loading_records(db):
    with session_scope() as session:
        job, _ = upsert_job(session, NormalizedJob(source="test", external_job_id="1", title="Engineer", company="Example"))
        job.match_score = 80
        session.add(ApplicationRecord(job_id=job.id, status="review"))
    statements = []
    def capture(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(get_engine(), "before_cursor_execute", capture)
    try:
        with session_scope() as session:
            counts = overview_counts(session)
            assert not session.identity_map
        assert counts["jobs_collected"] == counts["relevant_jobs"] == counts["jobs_requiring_review"] == 1
        assert len(statements) == 2
    finally:
        event.remove(get_engine(), "before_cursor_execute", capture)


def test_latest_application_does_not_depend_on_list_order(db):
    with session_scope() as session:
        job, _ = upsert_job(session, NormalizedJob(source="test", external_job_id="1", title="Engineer", company="Example"))
        first = ApplicationRecord(job=job, status="applied")
        second = ApplicationRecord(job=job, status="interview")
        session.add_all([first, second])
        session.flush()
        job.applications[:] = [second, first]
        assert job_to_dict(job)["application_status"] == "interview"


async def test_matching_uses_one_batch_transaction(db, monkeypatch):
    from src.jobs import searcher as module

    calls = []
    original = module.session_scope
    def record_scope():
        calls.append(1)
        return original()
    monkeypatch.setattr(module, "session_scope", record_scope)
    jobs = [Job(title="Python Engineer", company=f"Example {i}") for i in range(4)]
    results = await module.JobSearcher().match_jobs(jobs, "Python engineer")
    assert len(results) == 4
    assert len(calls) == 1


@pytest.mark.parametrize("text,delta", [("2 days ago", timedelta(days=2)), ("Posted 3 hours ago", timedelta(hours=3)),
    ("1 week ago", timedelta(weeks=1)), ("yesterday", timedelta(days=1)), ("today", timedelta()), ("30+ days ago", timedelta(days=30))])
def test_relative_dates(text, delta):
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    assert _parse_datetime(text, now) == now - delta


@pytest.mark.parametrize("pay,expected,score", [
    ("USD 25/hour", "USD 52,000 annually", 100),
    ("INR 100,000/month", "12 LPA", 100),
    ("20 - 25 LPA", "INR 2,000,000 yearly", 100),
    ("USD 30 per hour", "INR 100,000 monthly", 70),
    ("INR 50,000 monthly", "INR 1,200,000 annually", 30),
    ("USD 100000", "USD 100000 yearly", 70),
])
def test_salary_period_and_currency(pay, expected, score):
    assert _salary_score(pay, expected) == score


async def test_noninteractive_human_intervention_fails_promptly(monkeypatch):
    from src.browser.intervention import wait_for_human, HumanInterventionRequired

    monkeypatch.setattr("sys.stdin", io.StringIO())
    with pytest.raises(HumanInterventionRequired, match="Login required"):
        await asyncio.wait_for(wait_for_human("Login required"), timeout=0.1)


async def test_remotive_logs_one_summary(monkeypatch):
    from src.collectors import remotive

    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, *args, **kwargs):
            return httpx.Response(200, request=httpx.Request("GET", "https://example.com"), json={"jobs": [
                {"id": i, "title": "Python Engineer", "company_name": "Example", "url": f"https://example.com/{i}"} for i in range(3)]})
    monkeypatch.setattr(remotive.httpx, "AsyncClient", FakeClient)
    logger = Mock()
    monkeypatch.setattr(remotive, "logger", logger)
    assert len(await remotive.RemotiveCollector().collect(["python"], [], 10)) == 3
    logger.info.assert_called_once()
