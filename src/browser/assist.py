"""Browser assistance: fill known fields and stop before submit."""

from __future__ import annotations

from src.browser.manager import BrowserManager
from src.config.logging import get_logger
from src.portals.ats_handler import UniversalApplicant
from src.utils.profile_builder import ProfileBuilder

logger = get_logger(__name__)


async def prepare_application(job_url: str) -> str:
    """Open the job posting, fill what we know, leave submit to the user."""
    manager = BrowserManager()
    page = None
    try:
        await manager.launch()
        context = await manager.new_context()
        page = await manager.new_page(context)
        profile = ProfileBuilder().build()
        applicant = UniversalApplicant(page)
        await applicant.apply_to_job(job_url, profile, submit=False)
        path = await manager.screenshot_on_error(page, "prepare_review")
        logger.info("Application prepared; waiting for user submit", url=job_url)
        return str(path)
    except Exception as e:
        logger.error("browser error", error=str(e))
        if page is not None:
            try:
                await manager.screenshot_on_error(page, "prepare_error")
            except Exception:
                pass
        raise
    finally:
        await manager.close()
