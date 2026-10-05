"""Main entry point for AI Job Hunter."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from src.config.config_loader import get_settings
from src.config.logging import setup_logging
from src.db.session import init_db
from src.jobs.searcher import JobSearcher
from src.jobs.export import save_jobs_csv


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


async def run_agent(rank: bool = True, include_linkedin: bool = False, csv_path: Path | None = None) -> None:
    """Collect listings and optionally rank them; the user applies via the links."""
    settings = get_settings()
    setup_logging(settings.logging)
    init_db()
    searcher = JobSearcher()
    linkedin = None
    try:
        if include_linkedin:
            from src.portals.linkedin import LinkedInClient

            linkedin = LinkedInClient()
            await linkedin.login()
        jobs = await searcher.search_jobs(linkedin_client=linkedin)
        print(f"Collected {len(jobs)} jobs")
        if rank:
            if not settings.resume.path.exists():
                print(f"Resume not found: {settings.resume.path}. Showing unranked listings.")
                rank = False
            else:
                resume_text = await read_resume_text(settings.resume.path)
                matched = await searcher.match_jobs(jobs, resume_text)
                for match in matched:
                    print(f"{match.score:5.1f}  {match.job.title} @ {match.job.company}")
                    print(f"  Application link: {match.job.url or 'Unavailable'}")
                    print(f"  {match.reasoning}")
        if not rank:
            for job in jobs:
                print(f"{job.title} @ {job.company} [{job.location}]")
                print(f"  Application link: {job.url or 'Unavailable'}")
        for source in searcher.collection_results:
            if source.error:
                print(f"{source.source}: {source.error}")
        if csv_path is not None:
            print(f"CSV saved: {save_jobs_csv(csv_path)}")
        print("Review listings and prepare resume drafts in the dashboard. Apply using the links.")
    finally:
        if linkedin is not None:
            await linkedin.close()


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
        choices=["apply", "serve", "collect", "pipeline"],
        help="serve = dashboard (default), collect = listings, pipeline = listings + ranking; apply is a legacy alias for pipeline",
    )
    parser.add_argument("--linkedin", action="store_true", help="Include LinkedIn browser collection; may require manual login")
    parser.add_argument("--csv", type=Path, default=Path("data/exports/jobs.csv"), help="CSV output for collection commands")
    args = parser.parse_args()
    if args.command == "serve":
        serve()
    else:
        asyncio.run(run_agent(rank=args.command != "collect", include_linkedin=args.linkedin, csv_path=args.csv))


if __name__ == "__main__":
    main()
