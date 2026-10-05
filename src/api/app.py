"""FastAPI dashboard and JSON API."""

from __future__ import annotations

from pathlib import Path
import asyncio
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from src.ai.matcher import group_by_score_band
from src.ai.matcher import load_user_skills, score_job
from src.ai.resume_tailor import tailor_resume
from src.ai.cover_letter import generate_cover_letter
from src.ai.document_export import export_document_versions
from src.config.config_loader import get_settings
from src.config.logging import get_logger, setup_logging
from src.db.repository import (
    create_or_get_application,
    get_job,
    get_active_application,
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
from src.jobs.export import jobs_csv, save_jobs_csv
from src.jobs.importer import fetch_job_details, JobImportError
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
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    app.state.collection_results = []
    app.state.collection_task = None
    app.state.collection_error = None

    @app.get("/", response_class=HTMLResponse)
    async def overview(request: Request):
        with session_scope() as session:
            counts = overview_counts(session)
            jobs = [job_to_dict(j) for j in list_jobs(session, limit=80)]
            jobs = [j for j in jobs if j.get("match_score") is None or j["match_score"] >= 10]
            bands = group_by_score_band(jobs, lambda j: j.get("match_score"))
        return templates.TemplateResponse(
            request,
            "overview.html",
            {"counts": counts, "jobs": jobs, "bands": bands, "statuses": STATUSES},
        )

    @app.get("/jobs", response_class=HTMLResponse)
    async def jobs_page(request: Request):
        with session_scope() as session:
            jobs = [job_to_dict(j) for j in list_jobs(session, limit=None)]
            scored = [j for j in jobs if j.get("match_score") is not None]
            unscored = [j for j in jobs if j.get("match_score") is None]
            bands = group_by_score_band(scored, lambda j: j.get("match_score"))
        return templates.TemplateResponse(
            request, "jobs.html", {"jobs": jobs, "bands": bands, "unscored": unscored,
                                   "sources": app.state.collection_results,
                                   "keywords": ", ".join(settings.job_search.keywords),
                                   "locations": ", ".join(settings.job_search.locations),
                                   "collecting": app.state.collection_task is not None and not app.state.collection_task.done(),
                                   "collection_error": app.state.collection_error}
        )

    @app.get("/jobs/export.csv")
    async def export_jobs():
        return Response(jobs_csv(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="jobs.csv"'})

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
    async def collect_jobs(keywords: str = Form(""), locations: str = Form("")):
        if app.state.collection_task is None or app.state.collection_task.done():
            app.state.collection_error = None

            async def collect():
                searcher = JobSearcher()
                try:
                    options = {}
                    if keywords.strip():
                        options["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]
                    if locations.strip():
                        options["locations"] = [loc.strip() for loc in locations.split(",") if loc.strip()]
                    jobs = await searcher.search_jobs(**options)
                    save_jobs_csv(Path("data/exports/jobs.csv"))
                    logger.info(f"Collection complete: {len(jobs)} jobs; CSV saved")
                except Exception as e:
                    app.state.collection_error = str(e)
                    logger.exception("Collection failed")
                finally:
                    app.state.collection_results = searcher.collection_results

            app.state.collection_task = asyncio.create_task(collect())
        return RedirectResponse("/jobs", status_code=303)

    @app.get("/api/collection")
    async def collection_status():
        running = app.state.collection_task is not None and not app.state.collection_task.done()
        return {"running": running, "error": app.state.collection_error,
                "sources": [{"source": r.source, "count": len(r.jobs), "error": r.error,
                             "skipped": r.skipped} for r in app.state.collection_results]}

    @app.post("/jobs/import")
    async def import_job(
        title: str = Form(""), company: str = Form(""),
        job_url: str = Form(...), location: str = Form(""),
        description: str = Form(""),
    ):
        url = job_url.strip()
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise HTTPException(400, "Invalid job link")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise HTTPException(400, "Use an HTTP or HTTPS application link")
        details = {}
        if not description.strip():
            try:
                fetched = await fetch_job_details(url)
                details = fetched.model_dump()
            except JobImportError as e:
                raise HTTPException(400, str(e)) from e
        for key, value in {"title": title, "company": company, "location": location,
                           "description": description}.items():
            if value.strip():
                details[key] = value
        if not details.get("title") or not details.get("company") or not details.get("description"):
            raise HTTPException(400, "Title, company, and description could not all be fetched; fill missing details manually")
        details["job_url"] = details.get("job_url") or url
        details["source"] = details.get("source") or parsed.hostname.removeprefix("www.")
        job = to_normalized(details)
        with session_scope() as session:
            record, _ = upsert_job(session, job)
            job_id = record.id
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    @app.post("/jobs/match")
    async def match_jobs():
        settings = get_settings()
        searcher = JobSearcher()
        resume = _resume_text()
        if not resume.strip():
            raise HTTPException(400, "Add a readable base resume before ranking jobs")
        with session_scope() as session:
            records = list_jobs(session, limit=500)
            jobs = [to_job(to_normalized(job_to_dict(r))) for r in records]
        await searcher.match_jobs(jobs, resume, settings.job_search.min_match_score)
        return RedirectResponse("/jobs", status_code=303)

    @app.post("/jobs/{job_id}/tailor")
    async def tailor(job_id: int):
        settings = get_settings()
        resume = _resume_text()
        if not resume.strip():
            raise HTTPException(400, "Add a readable base resume before tailoring")
        with session_scope() as session:
            job_row = get_job(session, job_id)
            if not job_row:
                raise HTTPException(404, "Job not found")
            existing = get_active_application(session, job_id)
            if existing and existing.status == ApplicationStatus.APPLIED.value:
                existing.warning = "This job is already marked APPLIED. Its submitted documents were preserved."
                return RedirectResponse(f"/jobs/{job_id}", status_code=303)
            job = to_job(to_normalized(job_to_dict(job_row)))
            skills = load_user_skills(settings.resume.skills_path)
            match = score_job(job, skills, resume_text=resume)
            matched = match.matched_skills
        out = Path("data/applications") / f"resume_{job_id}.txt"
        result = await tailor_resume(
            resume,
            job,
            skills,
            matched,
            use_llm=bool(settings.llm.api_key),
            output_path=out,
        )
        export_document_versions(out)
        with session_scope() as session:
            app, _, warning = create_or_get_application(session, job_id, ApplicationStatus.REVIEW.value)
            if warning:
                return RedirectResponse(f"/jobs/{job_id}", status_code=303)
            app.resume_version = str(out.with_suffix(".docx"))
            app.status = ApplicationStatus.REVIEW.value
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    @app.get("/jobs/{job_id}/documents/{kind}")
    async def download_document(job_id: int, kind: str, format: str = "txt"):
        if kind not in {"resume", "cover"}:
            raise HTTPException(404, "Document not found")
        media_types = {"txt": "text/plain", "pdf": "application/pdf",
                       "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        if format not in media_types:
            raise HTTPException(400, "Choose txt, pdf, or docx")
        with session_scope() as session:
            if not get_job(session, job_id):
                raise HTTPException(404, "Job not found")
        path = Path("data/applications") / f"{kind}_{job_id}.{format}"
        if not path.is_file():
            raise HTTPException(404, "Prepare this document first")
        return FileResponse(path, media_type=media_types[format], filename=path.name)

    @app.post("/jobs/{job_id}/cover-letter")
    async def cover_letter(job_id: int):
        settings = get_settings()
        with session_scope() as session:
            job_row = get_job(session, job_id)
            if not job_row:
                raise HTTPException(404, "Job not found")
            existing = get_active_application(session, job_id)
            if existing and existing.status == ApplicationStatus.APPLIED.value:
                existing.warning = "This job is already marked APPLIED. Its submitted documents were preserved."
                return RedirectResponse(f"/jobs/{job_id}", status_code=303)
            job = to_job(to_normalized(job_to_dict(job_row)))
        out = Path("data/applications") / f"cover_{job_id}.txt"
        text = await generate_cover_letter(
            job,
            _resume_text(),
            template_path=settings.application.cover_letter_template,
            use_llm=bool(settings.llm.api_key),
            output_path=out,
        )
        export_document_versions(out)
        with session_scope() as session:
            app, _, warning = create_or_get_application(session, job_id, ApplicationStatus.REVIEW.value)
            if warning:
                return RedirectResponse(f"/jobs/{job_id}", status_code=303)
            app.cover_letter_version = str(out.with_suffix(".docx"))
            app.status = ApplicationStatus.REVIEW.value
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    @app.post("/jobs/{job_id}/prepare")
    async def prepare(job_id: int):
        """Legacy route: return the application link without browser automation."""
        with session_scope() as session:
            job = get_job(session, job_id)
            if not job:
                raise HTTPException(404, "Job not found")
            url = job.job_url
        if not url:
            raise HTTPException(400, "Job has no application link")
        return {"status": "manual_application", "job_url": url,
                "message": "Open this link, review your resume, and apply yourself."}

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
    if path.suffix.lower() == ".docx":
        from docx import Document

        return "\n".join(p.text for p in Document(str(path)).paragraphs if p.text)
    return path.read_text(encoding="utf-8", errors="ignore")


app = create_app()
