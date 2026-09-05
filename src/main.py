"""Main entry point for AI Job Hunter."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from src.config.config_loader import get_settings
from src.config.logging import setup_logging
from src.db.session import init_db
from src.jobs.searcher import JobSearcher
from src.jobs.tracker import ApplicationTracker


async def read_resume_text(path: Path) -> str:
    """Extract text from resume PDF or DOCX file."""
    if not path.exists():
        return ""

    if path.suffix.lower() == ".pdf":
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    if path.suffix.lower() in (".doc", ".docx"):
        from docx import Document

        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text)
    return path.read_text(encoding="utf-8", errors="ignore")


async def run_pipeline() -> None:
    """Collect and score jobs. Does not apply."""
    settings = get_settings()
    setup_logging(settings.logging)
    init_db()

    print("Starting AI Job Hunter (collect + match only)...")
    searcher = JobSearcher()
    tracker = ApplicationTracker()
    tracker.connect()
    resume_path = settings.resume.path
    resume_text = await read_resume_text(resume_path)
    print(f"Resume loaded: {bool(resume_text)} ({resume_path})")

    jobs = await searcher.search_jobs()
    print(f"Found {len(jobs)} jobs")
    if not jobs:
        tracker.close()
        return

    matched = await searcher.match_jobs(jobs, resume_text, settings.job_search.min_match_score)
    print(f"Scored {len(matched)} jobs (threshold {settings.job_search.min_match_score})")
    for result in matched[:15]:
        print(f"  {result.score:5.1f}  {result.job.title} @ {result.job.company}")
        if result.matched_skills:
            print(f"         matched: {', '.join(result.matched_skills[:8])}")
        if result.missing_skills:
            print(f"         missing: {', '.join(result.missing_skills[:8])}")
    print("Applications are never submitted automatically. Use the dashboard to review and apply.")
    tracker.close()


def serve() -> None:
    import uvicorn

    settings = get_settings()
    setup_logging(settings.logging)
    init_db()
    uvicorn.run("src.api.app:app", host=settings.host, port=settings.port, reload=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Job Hunter")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "collect", "pipeline"],
        help="serve = dashboard (default), pipeline = collect+match",
    )
    args = parser.parse_args()
    if args.command in {"collect", "pipeline"}:
        asyncio.run(run_pipeline())
    else:
        serve()


if __name__ == "__main__":
    main()
