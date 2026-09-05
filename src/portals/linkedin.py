"""LinkedIn portal integration for job search and applications."""

from typing import Optional

from playwright.async_api import BrowserContext, Page

from src.config.settings import LinkedInSettings
from src.config.config_loader import get_settings
from src.config.logging import get_logger
from src.browser.manager import BrowserManager, get_browser_manager
from src.models.job import Job, JobSource
from src.portals.ats_handler import ATSDetector, UniversalApplicant
from src.portals.base import ApplicationResult, ApplyMethod, LoginStatus, SearchParams
from src.utils.profile_builder import ProfileBuilder

logger = get_logger(__name__)


class LinkedInClient:
    """LinkedIn-specific automation for job search and applications."""

    portal_name = "linkedin"
    portal_source = JobSource.LINKEDIN


    LOGIN_URL = "https://www.linkedin.com/login"
    JOBS_URL = "https://www.linkedin.com/jobs/search"

    def __init__(
        self,
        settings: Optional[LinkedInSettings] = None,
        browser: Optional[BrowserManager] = None,
        context: Optional[BrowserContext] = None,
        credentials: Optional[dict] = None,
    ):
        self._settings = settings or get_settings().linkedin
        self._browser = browser
        self._context = context
        self._page: Optional[Page] = None
        self.is_logged_in = False
        self.credentials = credentials or {}
        self.portal_name = "linkedin"
        self.portal_source = JobSource.LINKEDIN

    async def _ensure_browser(self) -> BrowserManager:
        """Ensure browser is initialized."""
        if self._browser is None:
            self._browser = await get_browser_manager()
        if self._browser._browser is None:
            await self._browser.launch()
        return self._browser

    async def login(self) -> LoginStatus:
        """Login to LinkedIn. Returns LoginStatus."""
        browser = await self._ensure_browser()
        self._context = await browser.new_context()
        self._page = await self._context.new_page()

        logger.info("Navigating to LinkedIn login")
        await self._page.goto(self.LOGIN_URL, wait_until="domcontentloaded")

        # Check if already logged in
        current_url = self._page.url
        if "feed" in current_url or "jobs" in current_url:
            logger.info("Already logged in to LinkedIn")
            self.is_logged_in = True
            return LoginStatus.ALREADY_LOGGED_IN

        username = self._settings.username or self.credentials.get("username", "")
        password = self._settings.password or self.credentials.get("password", "")
        if not username or not password:
            logger.warning("LinkedIn credentials missing; search/apply require manual login")
            return LoginStatus.FAILED

        # Fill credentials
        try:
            await self._page.fill("#username", username)
            await self._page.fill("#password", password)
            await self._page.click("button[type='submit']")
            await self._page.wait_for_load_state("networkidle", timeout=self._settings.login_timeout * 1000)

            # Handle security checkpoint if present
            if "checkpoint" in self._page.url:
                logger.warning("LinkedIn security checkpoint detected - manual intervention required")
                await self._page.wait_for_timeout(30000)  # 30s for manual verification

        except Exception as e:
            logger.error("LinkedIn login failed", error=str(e))
            await self._browser.screenshot_on_error(self._page, "linkedin_login_error")
            return LoginStatus.FAILED

        logger.info("LinkedIn login successful")
        self.is_logged_in = True
        return LoginStatus.SUCCESS

    async def search_jobs(
        self,
        keywords: list[str] | None = None,
        locations: list[str] | None = None,
        max_results: int = 25,
        params: SearchParams | None = None,
    ) -> list[Job]:
        """Search for jobs on LinkedIn."""
        if isinstance(keywords, SearchParams):
            params = keywords
            keywords = None
        if params is not None:
            keywords = params.keywords
            locations = params.locations
            max_results = params.max_results
        keywords = keywords or []
        locations = locations or [""]

        login_status = await self.login()
        page = self._page
        if page is None:
            logger.error("LinkedIn page unavailable", status=getattr(login_status, "value", login_status))
            return []

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        for keyword in keywords:
            for location in locations:
                try:
                    url = self._build_search_url(keyword, location)
                    logger.info("Searching LinkedIn for jobs", keyword=keyword, location=location)

                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_selector(".jobs-search-results-list", timeout=10000)

                    # Scroll to load more results
                    await self._scroll_results(page, max_results)

                    # Parse job cards
                    job_cards = await page.query_selector_all(".job-card-container")

                    for card in job_cards:
                        if len(jobs) >= max_results:
                            break

                        try:
                            job = await self._parse_job_card(page, card)
                            if job and job.key not in seen_ids:
                                seen_ids.add(job.key)
                                jobs.append(job)
                        except Exception as e:
                            logger.debug("Failed to parse job card", error=str(e))
                            continue

                except Exception as e:
                    logger.error("LinkedIn search failed", keyword=keyword, location=location, error=str(e))
                    continue

        logger.info("LinkedIn search complete", total_jobs=len(jobs))
        return jobs

    async def _build_search_url(self, keyword: str, location: str) -> str:
        """Build LinkedIn jobs search URL."""
        params = {
            "keywords": keyword,
            "location": location,
            "f_TPR": "r604800",  # Past 7 days
        }
        query = "&".join(f"{k}={v.replace(' ', '%20')}" for k, v in params.items())
        return f"{self.JOBS_URL}?{query}"

    async def _scroll_results(self, page: Page, max_results: int) -> None:
        """Scroll through job results to load more cards."""
        for _ in range(min(5, max_results // 5)):
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(500)
            count = len(await page.query_selector_all(".job-card-container"))
            if count >= max_results:
                break

    async def _parse_job_card(self, page: Page, card) -> Optional[Job]:
        """Parse a single job card from search results."""
        try:
            await card.click()

            title_el = await card.query_selector(".job-card-list__title")
            company_el = await card.query_selector(".job-card-container__company-name")
            location_el = await card.query_selector(".job-card-container__metadata-item")

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            location = (await location_el.inner_text()).strip() if location_el else ""

            if not title or not company:
                return None

            # Click to open job details
            await page.wait_for_selector(".jobs-search__job-details--container", timeout=5000)
            description_el = await page.query_selector(".jobs-description__content")
            description = ""
            if description_el:
                description = await description_el.inner_text()

            # Extract URL from card
            url = await card.get_attribute("href")
            if url and url.startswith("/"):
                url = f"https://www.linkedin.com{url}"

            return Job(
                title=title,
                company=company,
                location=location,
                description=description,
                url=url,
                source=JobSource.LINKEDIN,
            )

        except Exception as e:
            logger.debug("Job card parse failed", error=str(e))
            return None

    async def extract_job(self, job_url: str) -> Optional[Job]:
        """Extract full job details from a LinkedIn job URL."""
        if not self._page:
            await self.login()

        try:
            await self._page.goto(job_url, wait_until="domcontentloaded")
            await self._page.wait_for_timeout(2000)

            title_el = await self._page.query_selector(".jobs-unified-top-card__job-title, .job-details-jobs-unified-top-card__job-title")
            company_el = await self._page.query_selector(".jobs-unified-top-card__company-name, .job-details-jobs-unified-top-card__company-name")
            location_el = await self._page.query_selector(".jobs-unified-top-card__bullet, .job-details-jobs-unified-top-card__bullet")
            desc_el = await self._page.query_selector(".jobs-description__content, .jobs-box__html-content")

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            location = (await location_el.inner_text()).strip() if location_el else ""
            description = (await desc_el.inner_text()).strip() if desc_el else ""

            return Job(
                title=title,
                company=company,
                location=location,
                description=description,
                url=job_url,
                source=JobSource.LINKEDIN,
            )

        except Exception as e:
            logger.error("Failed to extract LinkedIn job", url=job_url, error=str(e))
            return None

    async def apply(self, job: Job, resume_path: str = "", cover_letter_path: str = "", profile: Optional[dict] = None) -> ApplicationResult:
        """Apply to a job via LinkedIn or any redirect target."""
        if not self._page:
            await self.login()

        try:
            logger.info(
                "Starting application",
                job=job.title,
                company=job.company,
            )

            if not job.url:
                logger.warning("No job URL available - cannot apply")
                return ApplicationResult(success=False, error="No job URL")

            await self._page.goto(str(job.url), wait_until="domcontentloaded")
            await self._page.wait_for_timeout(2000)

            # Check if we were redirected to a non-LinkedIn platform
            current_url = self._page.url
            platform = ATSDetector.detect(self._page, current_url)

            if platform != "linkedin" and platform != "unknown":
                logger.info(
                    "Detected redirect to external careers page - using universal applicant",
                    platform=platform,
                    url=current_url[:100],
                )
                profile = profile or ProfileBuilder().build()
                universal = UniversalApplicant(self._page)
                result = await universal.apply_to_job(
                    job_url=str(job.url),
                    profile=profile,
                    job_title=job.title,
                    company=job.company,
                )
                return ApplicationResult(
                    success=result,
                    method=ApplyMethod.EXTERNAL_REDIRECT,
                    application_url=current_url,
                )

            # If unknown, detect if it's still LinkedIn-like or something else
            if "linkedin.com" not in current_url:
                logger.info(
                    "Navigated away from LinkedIn - using universal applicant",
                    url=current_url[:100],
                )
                profile = profile or ProfileBuilder().build()
                universal = UniversalApplicant(self._page)
                result = await universal.apply_to_job(
                    job_url=str(job.url),
                    profile=profile,
                    job_title=job.title,
                    company=job.company,
                )
                return ApplicationResult(
                    success=result,
                    method=ApplyMethod.EXTERNAL_REDIRECT,
                    application_url=current_url,
                )

            # Continue with LinkedIn-specific application flow
            apply_button = await self._page.query_selector(
                "button.jobs-apply-button, button[aria-label*='Apply']"
            )

            if not apply_button:
                # Check if already applied
                applied_indicator = await self._page.query_selector(
                    "button.jobs-apply-button[disabled], span[aria-label='Applied']"
                )
                if applied_indicator:
                    logger.info("Already applied to this job", job=job.title)
                    return ApplicationResult(success=False, error="Already applied")
                logger.warning("Apply button not found on LinkedIn", job=job.title)
                return ApplicationResult(
                    success=False,
                    method=ApplyMethod.MANUAL_REQUIRED,
                    error="Apply button not found",
                )

            await apply_button.click()
            await self._page.wait_for_timeout(2000)

            await self._fill_application_form(job)
            await self._upload_resume()

            screenshot = None
            if self._browser:
                screenshot = await self._browser.screenshot_on_error(self._page, f"review_{job.company}")

            logger.info(
                "Application prepared for user review — submit was not clicked",
                job=job.title,
            )
            return ApplicationResult(
                success=False,
                method=ApplyMethod.MANUAL_REQUIRED,
                requires_manual=True,
                application_url=self._page.url,
                screenshot_path=str(screenshot) if screenshot else "",
                confirmation_message="Form filled. Review in the browser and submit yourself.",
            )

        except Exception as e:
            logger.error("Application failed", job=job.title, error=str(e))
            if self._browser:
                await self._browser.screenshot_on_error(self._page, f"apply_{job.company}")
            return ApplicationResult(success=False, error=str(e))

    async def _fill_application_form(self, job: Job) -> bool:
        """Fill out LinkedIn application form if it appears."""
        try:
            # Wait for form container
            await self._page.wait_for_selector(
                ".jobs-easy-apply-modal, form.ember-view",
                timeout=5000,
            )

            # Fill text inputs
            text_inputs = await self._page.query_selector_all("input[type='text']")
            for input_el in text_inputs:
                placeholder = await input_el.get_attribute("placeholder") or ""
                if "phone" in placeholder.lower():
                    phone = get_settings().user.phone
                    if phone:
                        await input_el.fill(phone)

            # Check radio buttons / checkboxes
            radio_inputs = await self._page.query_selector_all("input[type='radio']")
            for radio in radio_inputs:
                label = await radio.get_attribute("value") or ""
                if "yes" in label.lower() or label.lower() in ["1", "true"]:
                    await radio.check(force=True)

            return True

        except Exception as e:
            logger.debug("No application form to fill", error=str(e))
            return False

    async def _upload_resume(self) -> None:
        """Upload resume file if file input is present."""
        try:
            resume_path = get_settings().resume.path
            file_input = await self._page.query_selector(
                "input[type='file'], input[name='resume'], input[accept*='.pdf'], input[accept*='.doc']"
            )

            if file_input:
                await file_input.set_input_files(str(resume_path))
                logger.info("Resume uploaded", path=str(resume_path))
                await self._page.wait_for_timeout(2000)

        except Exception as e:
            logger.error("Resume upload failed", error=str(e))

    async def close(self) -> None:
        """Close LinkedIn session and browser context."""
        if self._context:
            await self._context.close()
            self._context = None
            self._page = None