"""FastAPI dashboard and JSON API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.ai.cover_letter import generate_cover_letter
from src.ai.matcher import load_user_skills, score_job
from src.ai.resume_tailor import tailor_resume
from src.config.config_loader import get_settings
from src.config.logging import get_logger, setup_logging
from src.db.repository import (
    create_or_get_application,
    get_job,
    get_or_create_profile,
    job_to_dict,
    list_applications,
    list_jobs,
    overview_counts,
    set_application_status,
    update_match,
    upsert_job,
)
from src.db.session import init_db, session_scope
from src.jobs.normalize import to_job, to_normalized
from src.jobs.searcher import JobSearcher
from src.models.job import ApplicationStatus

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATUSES = [s.value for s in ApplicationStatus]


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.logging)
    init_db()

    app = FastAPI(title="AI Job Hunter", version="1.0.0")

    @app.get("/", response_class=HTMLResponse)
    async def overview(request: Request):
        with session_scope() as session:
            counts = overview_counts(session)
            jobs = [job_to_dict(j) for j in list_jobs(session, limit=15)]
        return templates.TemplateResponse(
            request,
            "overview.html",
            {"counts": counts, "jobs": jobs, "statuses": STATUSES},
        )

    @app.get("/jobs", response_class=HTMLResponse)
    async def jobs_page(request: Request):
        with session_scope() as session:
            jobs = [job_to_dict(j) for j in list_jobs(session)]
        return templates.TemplateResponse(request, "jobs.html", {"jobs": jobs})

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def job_detail(request: Request, job_id: int):
        with session_scope() as session:
            job = get_job(session, job_id)
            if not job:
                raise HTTPException(404, "Job not found")
            data = job_to_dict(job)
            apps = [
                {
                    "id": a.id,
                    "status": a.status,
                    "resume_version": a.resume_version,
                    "cover_letter_version": a.cover_letter_version,
                    "notes": a.notes,
                    "applied_at": a.applied_at.isoformat() if a.applied_at else None,
                    "warning": a.warning,
                }
                for a in job.applications
            ]
        return templates.TemplateResponse(
            request,
            "job_detail.html",
            {"job": data, "applications": apps, "statuses": STATUSES},
        )

    @app.post("/jobs/collect")
    async def collect_jobs():
        searcher = JobSearcher()
        jobs = await searcher.search_jobs()
        logger.info("number of jobs collected", count=len(jobs))
        return RedirectResponse("/jobs", status_code=303)

    @app.post("/jobs/match")
    async def match_jobs():
        settings = get_settings()
        searcher = JobSearcher()
        resume = _resume_text()
        with session_scope() as session:
            records = list_jobs(session, limit=500)
            jobs = [to_job(to_normalized(job_to_dict(r))) for r in records]
        await searcher.match_jobs(jobs, resume, settings.job_search.min_match_score)
        return RedirectResponse("/jobs", status_code=303)

    @app.post("/jobs/{job_id}/tailor")
    async def tailor(job_id: int):
        settings = get_settings()
        resume = _resume_text()
        with session_scope() as session:
            job_row = get_job(session, job_id)
            if not job_row:
                raise HTTPException(404, "Job not found")
            job = to_job(to_normalized(job_to_dict(job_row)))
            skills = load_user_skills(settings.resume.skills_path)
            matched = [s for s in (job_row.matched_skills or "").split(",") if s.strip()]
        out = Path("data/applications") / f"resume_{job_id}.txt"
        result = await tailor_resume(
            resume,
            job,
            skills,
            matched,
            use_llm=bool(settings.llm.api_key),
            output_path=out,
        )
        with session_scope() as session:
            app, _, warning = create_or_get_application(session, job_id, ApplicationStatus.REVIEW.value)
            if warning:
                return {"warning": warning, "path": str(out), "summary": result.summary}
            app.resume_version = str(out)
            app.status = ApplicationStatus.REVIEW.value
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    @app.post("/jobs/{job_id}/cover-letter")
    async def cover_letter(job_id: int):
        settings = get_settings()
        with session_scope() as session:
            job_row = get_job(session, job_id)
            if not job_row:
                raise HTTPException(404, "Job not found")
            job = to_job(to_normalized(job_to_dict(job_row)))
        out = Path("data/applications") / f"cover_{job_id}.txt"
        text = await generate_cover_letter(
            job,
            _resume_text(),
            template_path=settings.application.cover_letter_template,
            use_llm=bool(settings.llm.api_key),
            output_path=out,
        )
        with session_scope() as session:
            app, _, warning = create_or_get_application(session, job_id, ApplicationStatus.REVIEW.value)
            if warning:
                return {"warning": warning, "path": str(out), "letter": text}
            app.cover_letter_version = str(out)
            app.status = ApplicationStatus.REVIEW.value
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    @app.post("/jobs/{job_id}/prepare")
    async def prepare(job_id: int):
        """Open the job in a browser, fill known fields, and stop before submit."""
        logger.info("application preparation started", job_id=job_id)
        with session_scope() as session:
            job_row = get_job(session, job_id)
            if not job_row:
                raise HTTPException(404, "Job not found")
            existing = None
            if job_row.applications:
                existing = job_row.applications[-1]
            if existing and existing.status == ApplicationStatus.APPLIED.value:
                return {"warning": "This job is already marked APPLIED.", "job_url": job_row.job_url}
            url = job_row.job_url
            app, _, _ = create_or_get_application(session, job_id, ApplicationStatus.READY.value)
            app.status = ApplicationStatus.READY.value
        if not url:
            raise HTTPException(400, "Job has no URL to open")
        try:
            from src.browser.assist import prepare_application

            screenshot = await prepare_application(url)
            return {
                "status": "ready_for_review",
                "message": "Browser opened and known fields filled. Submit the form yourself.",
                "screenshot": screenshot,
                "job_url": url,
            }
        except Exception as e:
            logger.error("browser error", error=str(e))
            raise HTTPException(500, f"Browser assistance failed: {e}")

    @app.get("/applications", response_class=HTMLResponse)
    async def applications_page(request: Request):
        with session_scope() as session:
            rows = list_applications(session)
            apps = [
                {
                    "id": a.id,
                    "company": a.job.company if a.job else "",
                    "role": a.job.title if a.job else "",
                    "applied_at": a.applied_at.isoformat() if a.applied_at else "",
                    "status": a.status,
                    "resume_version": a.resume_version,
                    "notes": a.notes,
                    "job_id": a.job_id,
                }
                for a in rows
            ]
        return templates.TemplateResponse(
            request,
            "applications.html",
            {"applications": apps, "statuses": STATUSES},
        )

    @app.post("/applications/{application_id}/status")
    async def update_status(
        application_id: int,
        status: str = Form(...),
        notes: str = Form(""),
    ):
        if status not in STATUSES:
            raise HTTPException(400, "Invalid status")
        try:
            with session_scope() as session:
                updated = set_application_status(
                    session,
                    application_id,
                    status,
                    notes=notes or None,
                    mark_applied=(status == ApplicationStatus.APPLIED.value),
                )
                if not updated:
                    raise HTTPException(404, "Application not found")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return RedirectResponse("/applications", status_code=303)

    @app.get("/api/overview")
    async def api_overview():
        with session_scope() as session:
            return overview_counts(session)

    @app.get("/health")
    async def health():
        try:
            with session_scope() as session:
                get_or_create_profile(session)
            return {"status": "ok"}
        except Exception as e:
            logger.error("database error", error=str(e))
            return {"status": "error", "detail": "database unavailable"}

    return app


def _resume_text() -> str:
    path = get_settings().resume.path
    if not path.exists():
        return ""
    if path.suffix.lower() == ".pdf":
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


app = create_app()
