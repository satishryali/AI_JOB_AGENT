"""Indeed portal integration."""

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
from src.portals.selectors import INDEED_SELECTORS
from src.portals.ats_handler import ATSDetector, UniversalApplicant
from src.utils.profile_builder import ProfileBuilder

logger = get_logger(__name__)


class IndeedPortal(BasePortal):
    """Indeed job portal implementation."""

    portal_name = "indeed"
    portal_source = JobSource.INDEED

    def __init__(
        self,
        context: Optional[BrowserContext] = None,
        page: Optional[Page] = None,
        credentials: Optional[dict] = None,
    ):
        super().__init__(context, page, credentials)
        self.selectors = INDEED_SELECTORS
        self.domain = "in.indeed.com"  # Default to India, configurable

    async def login(self) -> LoginStatus:
        """Login to Indeed."""
        if not self.context:
            logger.error("No browser context available")
            return LoginStatus.FAILED

        if not self.page:
            self.page = await self.context.new_page()

        try:
            logger.info("Navigating to Indeed login")
            await self.page.goto(self.selectors.login_url, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)

            # Check if already logged in
            logged_in = await self.page.query_selector(self.selectors.logged_in_indicator)
            if logged_in:
                self.is_logged_in = True
                return LoginStatus.ALREADY_LOGGED_IN

            username = self.credentials.get("username", "")
            password = self.credentials.get("password", "")

            if not username or not password:
                logger.warning("Indeed credentials not configured")
                return LoginStatus.FAILED

            await self.page.fill(self.selectors.username_field, username)
            await self.page.fill(self.selectors.password_field, password)
            await self.page.click(self.selectors.login_button)
            await self.page.wait_for_load_state("networkidle", timeout=30000)

            if self.is_captcha_required():
                logger.warning("CAPTCHA detected on Indeed login")
                return LoginStatus.CAPTCHA_REQUIRED

            logged_in = await self.page.query_selector(self.selectors.logged_in_indicator)
            if logged_in:
                self.is_logged_in = True
                logger.info("Indeed login successful")
                return LoginStatus.SUCCESS

            return LoginStatus.FAILED

        except Exception as e:
            logger.error("Indeed login error", error=str(e))
            return LoginStatus.FAILED

    async def search_jobs(self, params: SearchParams) -> list[Job]:
        """Search for jobs on Indeed."""
        if not self.page:
            await self.login()

        jobs: list[Job] = []

        for keyword in params.keywords:
            for location in (params.locations or [""]):
                try:
                    url = self.selectors.search_url_template.format(
                        domain=self.domain,
                        keyword=quote(keyword),
                        location=quote(location),
                        days=params.posted_within_days or 7,
                    )
                    logger.info("Searching Indeed", keyword=keyword, location=location)

                    await self.page.goto(url, wait_until="domcontentloaded")
                    await self.page.wait_for_timeout(2000)

                    await self._scroll_results(params.max_results)

                    job_cards = await self.page.query_selector_all(self.selectors.job_card)

                    for card in job_cards[: params.max_results]:
                        try:
                            job = await self._parse_job_card(card)
                            if job:
                                jobs.append(job)
                        except Exception as e:
                            logger.debug("Failed to parse Indeed job card", error=str(e))
                            continue

                except Exception as e:
                    logger.error("Indeed search failed", keyword=keyword, error=str(e))
                    continue

        # Deduplicate
        unique = {}
        for job in jobs:
            if job.key not in unique:
                unique[job.key] = job

        return list(unique.values())

    async def _scroll_results(self, max_results: int) -> None:
        """Scroll to load more job results."""
        for _ in range(min(5, max_results // 5)):
            count = len(await self.page.query_selector_all(self.selectors.job_card))
            if count >= max_results:
                break
            await self.page.mouse.wheel(0, 800)
            await self.page.wait_for_timeout(500)

    async def _parse_job_card(self, card) -> Optional[Job]:
        """Parse an Indeed job card."""
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
                url = f"https://{self.domain}{url}"

            return Job(
                title=title,
                company=company,
                location=location,
                description="",
                url=url,
                source=JobSource.INDEED,
            )

        except Exception as e:
            logger.debug("Indeed job card parse failed", error=str(e))
            return None

    async def extract_job(self, job_url: str) -> Optional[Job]:
        """Extract full job details from an Indeed job URL."""
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
                source=JobSource.INDEED,
                salary_range=salary,
            )

        except Exception as e:
            logger.error("Failed to extract Indeed job", url=job_url, error=str(e))
            return None

    async def apply(
        self,
        job: Job,
        resume_path: str,
        cover_letter_path: str = "",
        profile: Optional[dict] = None,
    ) -> ApplicationResult:
        """Apply to a job on Indeed."""
        if not self.page:
            await self.login()

        try:
            if not job.url:
                return ApplicationResult(success=False, error="No job URL")

            await self.page.goto(job.url, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)

            # Check if redirected to external ATS
            current_url = self.page.url
            ats_type = ATSDetector.detect(self.page, current_url)
            if ats_type not in ("unknown", "indeed") or (ats_type == "unknown" and "indeed.com" not in current_url):
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

            # Find apply button
            apply_btn = await self.page.query_selector(self.selectors.apply_button)
            if not apply_btn:
                return ApplicationResult(success=False, method=ApplyMethod.MANUAL_REQUIRED)

            # Check if external redirect
            external_link = await self.page.query_selector(self.selectors.not_easy_apply_indicator)
            if external_link:
                href = await external_link.get_attribute("href") if await external_link.evaluate("el => el.tagName.toLowerCase() == 'a'") else None
                if href and "indeed.com" not in href:
                    return ApplicationResult(
                        success=False,
                        method=ApplyMethod.EXTERNAL_REDIRECT,
                        application_url=href,
                        requires_manual=True,
                    )

            await apply_btn.click()
            await self.page.wait_for_timeout(3000)

            # Use adaptive form filler
            from src.portals.ats_handler import AdaptiveFormFiller
            profile = profile or ProfileBuilder().build()
            filler = AdaptiveFormFiller(self.page)
            results = await filler.fill_form(profile)

            # Submit
            submit_btn = await self.page.query_selector(self.selectors.submit_button)
            if submit_btn:
                await submit_btn.click()
                await self.page.wait_for_timeout(3000)

            success = await self.page.query_selector(self.selectors.success_message)
            if success:
                logger.info("Indeed application submitted", job=job.title, company=job.company)
                return ApplicationResult(
                    success=True,
                    method=ApplyMethod.EASY_APPLY,
                    application_url=self.page.url,
                )

            return ApplicationResult(success=True, method=ApplyMethod.STANDARD)

        except Exception as e:
            logger.error("Indeed application failed", job=job.title, error=str(e))
            return ApplicationResult(success=False, error=str(e))