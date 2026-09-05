"""Foundit (Monster) portal integration."""

import re
from typing import Optional
from urllib.parse import quote

from playwright.async_api import BrowserContext, Page

from src.config.logging import get_logger
from src.config.config_loader import get_settings
from src.models.job import Job, JobSource
from src.portals.base import (
    ApplicationResult,
    ApplyMethod,
    BasePortal,
    LoginStatus,
    SearchParams,
)
from src.portals.selectors import FOUNDIT_SELECTORS
from src.portals.ats_handler import ATSDetector, UniversalApplicant
from src.utils.profile_builder import ProfileBuilder

logger = get_logger(__name__)


class FounditPortal(BasePortal):
    """Foundit (formerly Monster) job portal implementation."""

    portal_name = "foundit"
    portal_source = JobSource.FOUNDIT

    def __init__(
        self,
        context: Optional[BrowserContext] = None,
        page: Optional[Page] = None,
        credentials: Optional[dict] = None,
    ):
        super().__init__(context, page, credentials)
        self.selectors = FOUNDIT_SELECTORS
        if not self.credentials:
            settings = get_settings()
            self.credentials = {
                "username": settings.linkedin.username,
                "password": "",
            }

    async def login(self) -> LoginStatus:
        """Login to Foundit."""
        if not self.context:
            logger.error("No browser context available")
            return LoginStatus.FAILED

        if not self.page:
            self.page = await self.context.new_page()

        try:
            logger.info("Navigating to Foundit login")
            await self.page.goto(self.selectors.login_url, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)

            logged_in = await self.page.query_selector(self.selectors.logged_in_indicator)
            if logged_in:
                self.is_logged_in = True
                return LoginStatus.ALREADY_LOGGED_IN

            username = self.credentials.get("username", "")
            password = self.credentials.get("password", "")

            if not username or not password:
                logger.warning("Foundit credentials not configured")
                return LoginStatus.FAILED

            await self.page.fill(self.selectors.username_field, username)
            await self.page.fill(self.selectors.password_field, password)
            await self.page.click(self.selectors.login_button)
            await self.page.wait_for_load_state("networkidle", timeout=30000)

            if self.is_captcha_required():
                logger.warning("CAPTCHA detected on Foundit login")
                return LoginStatus.CAPTCHA_REQUIRED

            logged_in = await self.page.query_selector(self.selectors.logged_in_indicator)
            if logged_in:
                self.is_logged_in = True
                logger.info("Foundit login successful")
                return LoginStatus.SUCCESS

            return LoginStatus.FAILED

        except Exception as e:
            logger.error("Foundit login error", error=str(e))
            return LoginStatus.FAILED

    async def search_jobs(self, params: SearchParams) -> list[Job]:
        """Search for jobs on Foundit."""
        if not self.page:
            await self.login()

        jobs: list[Job] = []

        for keyword in params.keywords:
            for location in (params.locations or [""]):
                try:
                    url = self.selectors.search_url_template.format(
                        keyword=quote(keyword),
                        location=quote(location) if location else "",
                    )
                    logger.info("Searching Foundit", keyword=keyword, location=location)

                    await self.page.goto(url, wait_until="domcontentloaded")
                    await self.page.wait_for_timeout(2000)

                    job_cards = await self.page.query_selector_all(self.selectors.job_card)

                    for card in job_cards[: params.max_results]:
                        try:
                            job = await self._parse_job_card(card)
                            if job:
                                jobs.append(job)
                        except Exception as e:
                            logger.debug("Failed to parse Foundit job card", error=str(e))
                            continue

                except Exception as e:
                    logger.error("Foundit search failed", keyword=keyword, error=str(e))
                    continue

        unique = {}
        for job in jobs:
            if job.key not in unique:
                unique[job.key] = job
        return list(unique.values())

    async def _parse_job_card(self, card) -> Optional[Job]:
        """Parse a Foundit job card."""
        try:
            title_el = await card.query_selector(self.selectors.job_title)
            company_el = await card.query_selector(self.selectors.job_company)
            location_el = await card.query_selector(self.selectors.job_location)
            link_el = await card.query_selector(self.selectors.job_link)

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            location = (await location_el.inner_text()).strip() if location_el else ""
            url = await link_el.get_attribute("href") if link_el else None

            if not title or not company:
                return None

            if url and url.startswith("/"):
                url = f"https://www.foundit.in{url}"

            return Job(
                title=title,
                company=company,
                location=location,
                description="",
                url=url,
                source=JobSource.FOUNDIT,
            )

        except Exception as e:
            logger.debug("Foundit job card parse failed", error=str(e))
            return None

    async def extract_job(self, job_url: str) -> Optional[Job]:
        """Extract full job details from a Foundit job URL."""
        if not self.page:
            await self.login()

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
                source=JobSource.FOUNDIT,
                salary_range=salary,
            )

        except Exception as e:
            logger.error("Failed to extract Foundit job", url=job_url, error=str(e))
            return None

    async def apply(
        self,
        job: Job,
        resume_path: str,
        cover_letter_path: str = "",
        profile: Optional[dict] = None,
    ) -> ApplicationResult:
        """Apply to a job on Foundit."""
        if not self.page:
            await self.login()

        try:
            if not job.url:
                return ApplicationResult(success=False, error="No job URL")

            await self.page.goto(job.url, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)

            current_url = self.page.url
            ats_type = ATSDetector.detect(self.page, current_url)
            if ats_type not in ("unknown", "foundit") or (ats_type == "unknown" and "foundit" not in current_url):
                logger.info("Redirected to ATS - using universal applicant", ats=ats_type)
                universal = UniversalApplicant(self.page)
                profile = profile or ProfileBuilder().build()
                result = await universal.apply_to_job(
                    job_url=job.url,
                    profile=profile,
                    job_title=job.title,
                    company=job.company,
                )
                return ApplicationResult(
                    success=result,
                    method=ApplyMethod.EXTERNAL_REDIRECT,
                    application_url=current_url,
                )

            apply_btn = await self.page.query_selector(self.selectors.apply_button)
            if not apply_btn:
                easy_apply = await self.page.query_selector(self.selectors.easy_apply_button)
                if easy_apply:
                    apply_btn = easy_apply

            if not apply_btn:
                logger.warning("Apply button not found on Foundit", job=job.title)
                return ApplicationResult(success=False, method=ApplyMethod.MANUAL_REQUIRED)

            await apply_btn.click()
            await self.page.wait_for_timeout(3000)

            from src.portals.ats_handler import AdaptiveFormFiller
            profile = profile or ProfileBuilder().build()
            filler = AdaptiveFormFiller(self.page)
            await filler.fill_form(profile)

            submit_btn = await self.page.query_selector(self.selectors.submit_button)
            if submit_btn:
                await submit_btn.click()
                await self.page.wait_for_timeout(3000)

            success = await self.page.query_selector(self.selectors.success_message)
            if success:
                logger.info("Foundit application submitted", job=job.title, company=job.company)
                return ApplicationResult(success=True, method=ApplyMethod.EASY_APPLY)

            return ApplicationResult(success=True, method=ApplyMethod.STANDARD)

        except Exception as e:
            logger.error("Foundit application failed", job=job.title, error=str(e))
            return ApplicationResult(success=False, error=str(e))