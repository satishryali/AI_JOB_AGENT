"""Concrete ATS platform implementations.

Each ATS extends BaseATS and provides platform-specific behavior.
The UniversalApplicant from ats_handler.py handles the actual form filling.
"""

from typing import Optional

from playwright.async_api import BrowserContext, Page

from src.config.logging import get_logger
from src.portals.base import ApplicationResult, ApplyMethod, BaseATS, LoginStatus, SearchParams
from src.portals.selectors import (
    ASHBY_SELECTORS,
    BAMBOO_SELECTORS,
    GREENHOUSE_SELECTORS,
    ICIMS_SELECTORS,
    JOBVITE_SELECTORS,
    LEVER_SELECTORS,
    SMARTRECRUITERS_SELECTORS,
    SUCCESSFACTORS_SELECTORS,
    TALEO_SELECTORS,
    WORKDAY_SELECTORS,
    PortalSelectors,
)
from src.portals.ats_handler import ATSDetector, UniversalApplicant
from src.models.job import JobSource
from src.utils.profile_builder import ProfileBuilder

logger = get_logger(__name__)


class BaseATSImplementation(BaseATS):
    """Base class for all ATS implementations."""

    ats_name: str = "base_ats"
    selectors: Optional[PortalSelectors] = None
    portal_source = JobSource.COMPANY

    def __init__(
        self,
        context: Optional[BrowserContext] = None,
        page: Optional[Page] = None,
        credentials: Optional[dict] = None,
    ):
        super().__init__(context, page, credentials)
        self.selectors = self._get_selectors()

    def _get_selectors(self) -> PortalSelectors:
        """Return the platform-specific selectors."""
        return PortalSelectors()  # Override in subclasses

    async def login(self) -> LoginStatus:
        """Most ATS platforms don't require login to apply."""
        return LoginStatus.ALREADY_LOGGED_IN

    async def search_jobs(self, params: SearchParams) -> list:
        """ATS platforms don't search jobs - they're redirected from portals."""
        return []

    async def detect(self, url: str) -> bool:
        """Detect if this ATS handles the given URL."""
        import logging
        from urllib.parse import urlparse

        domain = urlparse(url).netloc.lower()

        # Check domain patterns
        domain_patterns = {
            "workday": ["workday.com", "wd5.myworkday.com", "myworkday.com"],
            "greenhouse": ["greenhouse.io", "boards.greenhouse.io"],
            "lever": ["lever.co", "jobs.lever.co"],
            "ashby": ["ashbyhq.com"],
            "smartrecruiters": ["smartrecruiters.com"],
            "icims": ["icims.com"],
            "taleo": ["taleo.net"],
            "successfactors": ["successfactors.com", "sapsf.com"],
            "bamboohr": ["bamboohr.com"],
            "jobvite": ["jobvite.com"],
        }

        patterns = domain_patterns.get(self.ats_name, [])
        for pattern in patterns:
            if pattern in domain:
                return True
        return False

    async def extract_job(self, job_url: str):
        """Extract job details from the ATS page."""
        from src.models.job import Job

        if not self.page:
            logger.error("No page available for extract_job")
            return None

        try:
            await self.page.goto(job_url, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)

            title_el = await self.page.query_selector(self.selectors.job_title)
            company_el = await self.page.query_selector(self.selectors.job_company)
            location_el = await self.page.query_selector(self.selectors.job_location)
            desc_el = await self.page.query_selector(self.selectors.job_description)
            salary_el = await self.page.query_selector(self.selectors.job_salary)

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            location = (await location_el.inner_text()).strip() if location_el else ""
            description = (await desc_el.inner_text()).strip() if desc_el else ""
            salary = (await salary_el.inner_text()).strip() if salary_el else None

            return Job(
                title=title,
                company=company,
                location=location,
                description=description,
                url=job_url,
                source=JobSource.COMPANY,
                salary_range=salary,
                raw_data={"ats_platform": self.ats_name},
            )

        except Exception as e:
            logger.error(f"Failed to extract job from {self.ats_name}", url=job_url, error=str(e))
            return None

    async def apply(
        self,
        job,
        resume_path: str,
        cover_letter_path: str = "",
        profile: Optional[dict] = None,
    ) -> ApplicationResult:
        """Apply to a job using the universal applicant."""
        if not self.page:
            logger.error("No page available for application")
            return ApplicationResult(success=False, error="No page")

        profile = profile or ProfileBuilder().build()
        universal = UniversalApplicant(self.page)

        result = await universal.apply_to_job(
            job_url=str(job.url) if job.url else "",
            profile=profile,
            job_title=job.title,
            company=job.company,
        )

        return ApplicationResult(
            success=result,
            method=ApplyMethod.STANDARD,
            application_url=str(job.url) if job.url else "",
            details={"ats_platform": self.ats_name},
        )

    async def submit_application(
        self,
        job_url: str,
        profile: dict,
        resume_path: str,
        cover_letter_path: str = "",
    ) -> ApplicationResult:
        """Submit application directly to the ATS."""
        universal = UniversalApplicant(self.page)
        result = await universal.apply_to_job(
            job_url=job_url,
            profile=profile,
            job_title="",
            company="",
        )

        return ApplicationResult(
            success=result,
            method=ApplyMethod.STANDARD,
            application_url=job_url,
            details={"ats_platform": self.ats_name},
        )

    async def logout(self) -> None:
        """Most ATS don't require logout."""
        pass


class WorkdayATS(BaseATSImplementation):
    """Workday ATS implementation."""

    ats_name = "workday"

    def _get_selectors(self) -> PortalSelectors:
        return WORKDAY_SELECTORS


class GreenhouseATS(BaseATSImplementation):
    """Greenhouse ATS implementation."""

    ats_name = "greenhouse"

    def _get_selectors(self) -> PortalSelectors:
        return GREENHOUSE_SELECTORS


class LeverATS(BaseATSImplementation):
    """Lever ATS implementation."""

    ats_name = "lever"

    def _get_selectors(self) -> PortalSelectors:
        return LEVER_SELECTORS


class AshbyATS(BaseATSImplementation):
    """Ashby ATS implementation."""

    ats_name = "ashby"

    def _get_selectors(self) -> PortalSelectors:
        return ASHBY_SELECTORS


class SmartRecruitersATS(BaseATSImplementation):
    """SmartRecruiters ATS implementation."""

    ats_name = "smartrecruiters"

    def _get_selectors(self) -> PortalSelectors:
        return SMARTRECRUITERS_SELECTORS


class ICIMSATS(BaseATSImplementation):
    """iCIMS ATS implementation."""

    ats_name = "icims"

    def _get_selectors(self) -> PortalSelectors:
        return ICIMS_SELECTORS


class TaleoATS(BaseATSImplementation):
    """Oracle Taleo ATS implementation."""

    ats_name = "taleo"

    def _get_selectors(self) -> PortalSelectors:
        return TALEO_SELECTORS


class SuccessFactorsATS(BaseATSImplementation):
    """SAP SuccessFactors ATS implementation."""

    ats_name = "successfactors"

    def _get_selectors(self) -> PortalSelectors:
        return SUCCESSFACTORS_SELECTORS


class BambooHRATS(BaseATSImplementation):
    """BambooHR ATS implementation."""

    ats_name = "bamboohr"

    def _get_selectors(self) -> PortalSelectors:
        return BAMBOO_SELECTORS


class JobviteATS(BaseATSImplementation):
    """Jobvite ATS implementation."""

    ats_name = "jobvite"

    def _get_selectors(self) -> PortalSelectors:
        return JOBVITE_SELECTORS