"""Naukri portal integration."""

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
from src.portals.selectors import NAUKRI_SELECTORS
from src.portals.ats_handler import ATSDetector, UniversalApplicant
from src.utils.profile_builder import ProfileBuilder

logger = get_logger(__name__)


class NaukriPortal(BasePortal):
    """Naukri job portal implementation."""

    portal_name = "naukri"
    portal_source = JobSource.NAUKRI

    def __init__(
        self,
        context: Optional[BrowserContext] = None,
        page: Optional[Page] = None,
        credentials: Optional[dict] = None,
    ):
        super().__init__(context, page, credentials)
        self.selectors = NAUKRI_SELECTORS
        if not self.credentials:
            settings = get_settings()
            self.credentials = {
                "username": settings.linkedin.username,  # reuse if same email
                "password": "",  # would need separate config
            }

    async def login(self) -> LoginStatus:
        """Login to Naukri."""
        if not self.context:
            logger.error("No browser context available")
            return LoginStatus.FAILED

        if not self.page:
            self.page = await self.context.new_page()

        try:
            logger.info("Navigating to Naukri login")
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
                logger.warning("Naukri credentials not configured")
                return LoginStatus.FAILED

            # Fill login form
            await self.page.fill(self.selectors.username_field, username)
            await self.page.fill(self.selectors.password_field, password)
            await self.page.click(self.selectors.login_button)
            await self.page.wait_for_load_state("networkidle", timeout=30000)

            # Check for CAPTCHA
            if self.is_captcha_required():
                logger.warning("CAPTCHA detected on Naukri login")
                return LoginStatus.CAPTCHA_REQUIRED

            # Verify login
            logged_in = await self.page.query_selector(self.selectors.logged_in_indicator)
            error = await self.page.query_selector(self.selectors.login_error)

            if error:
                logger.error("Naukri login failed", error=await error.inner_text())
                return LoginStatus.FAILED

            if logged_in:
                self.is_logged_in = True
                logger.info("Naukri login successful")
                return LoginStatus.SUCCESS

            logger.warning("Could not confirm Naukri login")
            return LoginStatus.FAILED

        except Exception as e:
            logger.error("Naukri login error", error=str(e))
            return LoginStatus.FAILED

    async def search_jobs(self, params: SearchParams) -> list[Job]:
        """Search for jobs on Naukri."""
        if not self.page:
            status = await self.login()
            if status not in (LoginStatus.SUCCESS, LoginStatus.ALREADY_LOGGED_IN):
                return []

        jobs: list[Job] = []

        for keyword in params.keywords:
            for location in (params.locations or [""]):
                try:
                    url = self.selectors.search_url_template.format(
                        keyword=quote(keyword.replace(" ", "-")),
                        location=quote(location.replace(" ", "-")),
                        days=params.posted_within_days or 7,
                    )
                    logger.info("Searching Naukri", keyword=keyword, location=location)

                    await self.page.goto(url, wait_until="domcontentloaded")
                    await self.page.wait_for_timeout(2000)

                    job_cards = await self.page.query_selector_all(self.selectors.job_card)

                    for card in job_cards[: params.max_results]:
                        try:
                            job = await self._parse_job_card(card)
                            if job:
                                jobs.append(job)
                        except Exception as e:
                            logger.debug("Failed to parse Naukri job card", error=str(e))
                            continue

                    # If not enough results from the simple URL, try the search interface
                    if len(jobs) < params.max_results:
                        await self._search_via_interface(keyword, location, params)

                except Exception as e:
                    logger.error("Naukri search failed", keyword=keyword, error=str(e))
                    continue

        # Deduplicate
        unique = {}
        for job in jobs:
            if job.key not in unique:
                unique[job.key] = job

        return list(unique.values())

    async def _search_via_interface(self, keyword: str, location: str, params: SearchParams) -> None:
        """Search using the Naukri search interface."""
        try:
            await self.page.goto("https://www.naukri.com/", wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)

            search_input = await self.page.query_selector(self.selectors.search_input)
            if search_input:
                await search_input.fill(keyword)

            if location and self.selectors.location_input:
                loc_input = await self.page.query_selector(self.selectors.location_input)
                if loc_input:
                    await loc_input.fill(location)

            search_btn = await self.page.query_selector(self.selectors.search_button)
            if search_btn:
                await search_btn.click()
                await self.page.wait_for_load_state("networkidle", timeout=15000)

        except Exception as e:
            logger.debug("Interface search failed", error=str(e))

    async def _parse_job_card(self, card) -> Optional[Job]:
        """Parse a Naukri job card."""
        try:
            title_el = await card.query_selector(self.selectors.job_title)
            company_el = await card.query_selector(self.selectors.job_company)
            location_el = await card.query_selector(self.selectors.job_location)
            exp_el = await card.query_selector(self.selectors.job_experience)
            salary_el = await card.query_selector(self.selectors.job_salary)
            link_el = await card.query_selector(self.selectors.job_link)

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            location = (await location_el.inner_text()).strip() if location_el else ""
            experience = (await exp_el.inner_text()).strip() if exp_el else ""
            salary = (await salary_el.inner_text()).strip() if salary_el else None
            url = await link_el.get_attribute("href") if link_el else None

            if not title or not company:
                return None

            if url and url.startswith("/"):
                url = f"https://www.naukri.com{url}"

            # Parse experience years
            experience_years = None
            if experience:
                match = re.search(r"(\d+)\s*-\s*(\d+)", experience)
                if match:
                    experience_years = int(match.group(2))
                elif re.search(r"(\d+)", experience):
                    experience_years = int(re.search(r"(\d+)", experience).group(1))

            return Job(
                title=title,
                company=company,
                location=location,
                description="",
                url=url,
                source=JobSource.NAUKRI,
                salary_range=salary,
                experience_required=experience_years,
            )

        except Exception as e:
            logger.debug("Naukri job card parse failed", error=str(e))
            return None

    async def extract_job(self, job_url: str) -> Optional[Job]:
        """Extract full job details from a job URL."""
        if not self.page:
            status = await self.login()
            if status not in (LoginStatus.SUCCESS, LoginStatus.ALREADY_LOGGED_IN):
                return None

        try:
            await self.page.goto(job_url, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)

            title = ""
            company = ""
            location = ""
            description = ""
            salary = None
            experience = None
            employment_type = None

            # Try detail container selectors
            title_el = await self.page.query_selector(self.selectors.job_title)
            if title_el:
                title = (await title_el.inner_text()).strip()

            company_el = await self.page.query_selector(self.selectors.job_company)
            if company_el:
                company = (await company_el.inner_text()).strip()

            location_el = await self.page.query_selector(self.selectors.job_location)
            if location_el:
                location = (await location_el.inner_text()).strip()

            desc_el = await self.page.query_selector(self.selectors.job_description)
            if desc_el:
                description = (await desc_el.inner_text()).strip()

            salary_el = await self.page.query_selector(self.selectors.job_salary)
            if salary_el:
                salary = (await salary_el.inner_text()).strip()

            exp_el = await self.page.query_selector(self.selectors.job_experience)
            if exp_el:
                exp_text = (await exp_el.inner_text()).strip()
                match = re.search(r"(\d+)", exp_text)
                if match:
                    experience = int(match.group(1))

            type_el = await self.page.query_selector(self.selectors.job_employment_type)
            if type_el:
                employment_type = (await type_el.inner_text()).strip()

            return Job(
                title=title,
                company=company,
                location=location,
                description=description,
                url=job_url,
                source=JobSource.NAUKRI,
                salary_range=salary,
                experience_required=experience,
                employment_type=employment_type,
            )

        except Exception as e:
            logger.error("Failed to extract Naukri job", url=job_url, error=str(e))
            return None

    async def apply(
        self,
        job: Job,
        resume_path: str,
        cover_letter_path: str = "",
        profile: Optional[dict] = None,
    ) -> ApplicationResult:
        """Apply to a job on Naukri."""
        if not self.page:
            status = await self.login()
            if status not in (LoginStatus.SUCCESS, LoginStatus.ALREADY_LOGGED_IN):
                return ApplicationResult(success=False, error="Not logged in")

        try:
            if not job.url:
                return ApplicationResult(success=False, error="No job URL")

            await self.page.goto(job.url, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2000)

            # Check if redirected to external ATS
            current_url = self.page.url
            ats_type = ATSDetector.detect(self.page, current_url)
            if ats_type not in ("unknown", "naukri") or (ats_type == "unknown" and "naukri" not in current_url):
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
                # Check for easy apply
                easy_apply = await self.page.query_selector(self.selectors.easy_apply_button)
                if easy_apply:
                    apply_btn = easy_apply

            if not apply_btn:
                logger.warning("Apply button not found on Naukri", job=job.title)
                return ApplicationResult(success=False, method=ApplyMethod.MANUAL_REQUIRED)

            # Check if external application
            external = await self.page.query_selector(self.selectors.not_easy_apply_indicator)
            if external:
                href = await external.get_attribute("href") if await external.evaluate("el => el.tagName.toLowerCase() == 'a'") else None
                if href and not href.startswith("/") and "naukri.com" not in href:
                    logger.info("External application detected", url=href)
                    return ApplicationResult(
                        success=False,
                        method=ApplyMethod.EXTERNAL_REDIRECT,
                        application_url=href,
                        requires_manual=True,
                    )

            await apply_btn.click()
            await self.page.wait_for_timeout(3000)

            # Use adaptive form filler for the application form
            from src.portals.ats_handler import AdaptiveFormFiller
            profile = profile or ProfileBuilder().build()
            filler = AdaptiveFormFiller(self.page)
            results = await filler.fill_form(profile)

            # Submit
            submit_btn = await self.page.query_selector(self.selectors.submit_button)
            if submit_btn:
                await submit_btn.click()
                await self.page.wait_for_timeout(3000)

            # Check for success
            success = await self.page.query_selector(self.selectors.success_message)
            if success:
                logger.info("Naukri application submitted", job=job.title, company=job.company)
                return ApplicationResult(
                    success=True,
                    method=ApplyMethod.EASY_APPLY,
                    application_url=self.page.url,
                )

            return ApplicationResult(
                success=True,
                method=ApplyMethod.STANDARD,
                application_url=self.page.url,
            )

        except Exception as e:
            logger.error("Naukri application failed", job=job.title, error=str(e))
            return ApplicationResult(success=False, error=str(e))