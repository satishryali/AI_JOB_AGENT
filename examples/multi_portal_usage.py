"""Example: Using multiple portals and ATS platforms with the job agent.

This example demonstrates how to:
1. Register and use multiple job portals
2. Handle redirects to different ATS platforms
3. Apply to jobs across different portals
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.browser.manager import get_browser_manager
from src.config.logging import get_logger
from src.portals.base import SearchParams
from src.portals.registry import (
    PortalRegistry,
    detect_ats_from_url,
    register_builtin_portals,
)
from src.portals.selectors import get_selectors
from src.utils.profile_builder import ProfileBuilder

logger = get_logger(__name__)


async def search_across_portals(
    keywords: list[str],
    locations: list[str],
    portals: list[str] = None,
    max_results: int = 25,
) -> None:
    """Search for jobs across multiple portals."""
    register_builtin_portals()

    available = PortalRegistry.available_portals()
    if portals:
        portals_to_search = [p for p in portals if p in available]
    else:
        portals_to_search = available

    logger.info("Searching across portals", portals=portals_to_search)

    browser = await get_browser_manager()
    context = await browser.new_context()

    for portal_name in portals_to_search:
        try:
            portal_cls = PortalRegistry._portals.get(portal_name)
            if not portal_cls:
                continue

            profile = ProfileBuilder().build()

            portal = portal_cls(
                context=context,
                credentials={
                    "username": profile.get("email", ""),
                    "password": "",  # Set in .env or credentials
                },
            )

            params = SearchParams(
                keywords=keywords,
                locations=locations,
                max_results=max_results,
                posted_within_days=7,
            )

            jobs = await portal.search_jobs(params)
            logger.info(
                "Search complete",
                portal=portal_name,
                jobs_found=len(jobs),
            )

            for job in jobs[:5]:
                print(f"  [{portal_name}] {job.company}: {job.title} - {job.location}")
                print(f"    URL: {job.url}")
                print()

        except Exception as e:
            logger.error("Portal search failed", portal=portal_name, error=str(e))

    await browser.close()


async def apply_to_job_example(job_url: str, title: str, company: str) -> bool:
    """Example: Apply to a job, handling any ATS redirect."""
    register_builtin_portals()

    # Detect the ATS from the URL
    ats_type = detect_ats_from_url(job_url)
    logger.info("Detected ATS from URL", ats=ats_type, url=job_url[:100])

    # Get selectors for the platform
    selectors = get_selectors(ats_type)
    logger.info("Got selectors", platform=ats_type)

    # Use the UniversalApplicant to apply
    from src.browser.manager import get_browser_manager
    from src.portals.ats_handler import UniversalApplicant
    from src.utils.profile_builder import ProfileBuilder

    browser = await get_browser_manager()
    context = await browser.new_context()
    page = await context.new_page()

    profile = ProfileBuilder().build()
    applicant = UniversalApplicant(page)

    result = await applicant.apply_to_job(
        job_url=job_url,
        profile=profile,
        job_title=title,
        company=company,
    )

    logger.info("Application result", success=result, job=title, company=company)
    await browser.close()
    return result


async def main():
    print("=" * 60)
    print("AI Job Agent - Multi-Portal Example")
    print("=" * 60)
    print()

    # List available portals
    register_builtin_portals()
    print("Available portals:", PortalRegistry.available_portals())
    print("Available ATS platforms:", PortalRegistry.available_ats())
    print()

    # Example: Search across portals
    await search_across_portals(
        keywords=["python", "data engineer"],
        locations=["hyderabad", "remote"],
        max_results=5,
    )

    print()
    print("Note: To actually apply to a job, use apply_to_job_example()")
    print("e.g.: await apply_to_job_example('https://...', 'Python Developer', 'Company Name')")


if __name__ == "__main__":
    asyncio.run(main())