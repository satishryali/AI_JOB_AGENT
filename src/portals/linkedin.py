"""LinkedIn portal integration for job search and applications."""

import re
from typing import Optional

from playwright.async_api import BrowserContext, Page

from src.config.settings import LinkedInSettings
from src.config.config_loader import get_settings
from src.config.logging import get_logger
from src.browser.intervention import wait_for_human
from src.browser.manager import BrowserManager, get_browser_manager
from src.models.job import Job, JobSource
from src.portals.base import ApplicationResult, ApplyMethod, LoginStatus, SearchParams

logger = get_logger(__name__)

_JOB_ID_RE = re.compile(r"(\d{8,})")


def _linkedin_job_id(*candidates: Optional[str]) -> str:
    """Extract a LinkedIn numeric job id from URLs, URNs, or data attributes."""
    for raw in candidates:
        if not raw:
            continue
        match = _JOB_ID_RE.search(str(raw))
        if match:
            return match.group(1)
    return ""


def _linkedin_view_url(job_id: str) -> str:
    """Logged-in search pane. Direct /jobs/view/{id} often returns HTTP 999 to automation."""
    return f"https://www.linkedin.com/jobs/search/?currentJobId={job_id}&f_AL=true"


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
        """Login to LinkedIn. Pauses for checkpoint / CAPTCHA / 2FA."""
        if self.is_logged_in and self._page:
            return LoginStatus.ALREADY_LOGGED_IN

        browser = await self._ensure_browser()
        if self._context is None:
            self._context = await browser.new_context()
        if self._page is None:
            self._page = await self._context.new_page()

        logger.info("Navigating to LinkedIn login")
        await self._page.goto(self.LOGIN_URL, wait_until="domcontentloaded")

        current_url = self._page.url
        if "feed" in current_url or "/jobs" in current_url:
            logger.info("Already logged in to LinkedIn")
            self.is_logged_in = True
            return LoginStatus.ALREADY_LOGGED_IN

        username = self._settings.username or self.credentials.get("username", "")
        password = self._settings.password or self.credentials.get("password", "")
        if not username or not password:
            logger.warning("LinkedIn credentials missing")
            await wait_for_human("Log into LinkedIn in the browser")
            self.is_logged_in = True
            return LoginStatus.ALREADY_LOGGED_IN

        try:
            await self._page.fill("#username", username)
            await self._page.fill("#password", password)
            await self._page.click("button[type='submit']")
            await self._page.wait_for_load_state("domcontentloaded", timeout=self._settings.login_timeout * 1000)
        except Exception as e:
            logger.error("LinkedIn login failed", error=str(e))
            if self._browser:
                await self._browser.screenshot_on_error(self._page, "linkedin_login_error")
            await wait_for_human("Login failed or timed out — finish login in the browser")

        blocked = await self._security_block_reason()
        if blocked:
            await wait_for_human(blocked)

        logger.info("LinkedIn login successful")
        self.is_logged_in = True
        return LoginStatus.SUCCESS

    async def _security_block_reason(self) -> str | None:
        if not self._page:
            return None
        url = self._page.url.lower()
        if any(token in url for token in ("checkpoint", "challenge", "add-phone", "two-step", "captcha", "security")):
            return f"LinkedIn security page ({self._page.url})"
        try:
            captcha = await self._page.query_selector(
                "iframe[src*='recaptcha'], iframe[src*='captcha'], iframe[src*='hcaptcha']"
            )
            if captcha:
                return "CAPTCHA on the page"
        except Exception:
            pass
        return None

    async def _continue_after_blocks(self) -> None:
        reason = await self._security_block_reason()
        if reason:
            await wait_for_human(reason)

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
            logger.error("LinkedIn page unavailable after login")
            return []

        jobs: list[Job] = []
        seen_ids: set[str] = set()
        query = " OR ".join(keywords[:5]) if keywords else "python"
        search_locations = self._dedupe_search_locations(locations)

        for index, location in enumerate(search_locations):
            if len(jobs) >= max_results:
                break
            try:
                logger.info(f"Searching LinkedIn keywords={query!r} location={location!r}")
                opened = await self._open_jobs_search(page, query, location, first=(index == 0))
                if not opened:
                    logger.warning(f"Could not open LinkedIn search for {location}")
                    continue

                list_ready = False
                for selector in (
                    ".jobs-search-results-list",
                    ".scaffold-layout__list",
                    "ul.scaffold-layout__list-container",
                    ".jobs-search__results-list",
                    "div.job-card-container",
                ):
                    try:
                        await page.wait_for_selector(selector, timeout=8000)
                        list_ready = True
                        break
                    except Exception:
                        continue
                if not list_ready:
                    logger.warning(f"LinkedIn results list not found for {location}")
                    continue

                await self._scroll_results(page, max_results)
                job_cards = await page.query_selector_all(
                    "div.job-card-container, li.jobs-search-results__list-item, li.scaffold-layout__list-item"
                )
                logger.info(f"LinkedIn found {len(job_cards)} cards in {location}")

                for card in job_cards:
                    if len(jobs) >= max_results:
                        break
                    try:
                        job = await self._parse_job_card(page, card)
                        if job and job.key not in seen_ids:
                            seen_ids.add(job.key)
                            jobs.append(job)
                    except Exception as e:
                        logger.debug(f"Failed to parse job card: {e}")
                        continue
            except Exception as e:
                logger.error(f"LinkedIn search failed for {location}: {e}")
                continue

        logger.info(f"LinkedIn search complete, total_jobs={len(jobs)}")
        return jobs

    def _dedupe_search_locations(self, locations: list[str] | None) -> list[str]:
        aliases = {"bengaluru": "bangalore", "bengalooru": "bangalore"}
        seen: set[str] = set()
        out: list[str] = []
        for loc in locations or [""]:
            raw = (loc or "").strip()
            key = aliases.get(raw.lower(), raw.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(raw)
        return out or [""]

    async def _open_jobs_search(self, page: Page, query: str, location: str, first: bool) -> bool:
        """Open a jobs search without relying on /jobs/search full reloads (LinkedIn often returns HTTP 999)."""
        if not first:
            if await self._change_search_location(page, location):
                return True
            await page.wait_for_timeout(4000)
        url = self._build_search_url(query, location)
        if await self._goto_soft(url):
            await self._continue_after_blocks()
            return True
        await wait_for_human(
            f"LinkedIn blocked the {location} jobs search. "
            "Open that city in the jobs search box, then press Enter."
        )
        return "linkedin.com/jobs" in (page.url or "")

    async def _change_search_location(self, page: Page, location: str) -> bool:
        """Change city on the current jobs page instead of a new goto."""
        box = page.locator(
            "input[aria-label*='City' i], input[aria-label*='Location' i], "
            ".jobs-search-box__input--location input"
        ).first
        try:
            await box.wait_for(state="visible", timeout=4000)
            await box.click()
            await box.fill(location)
            await page.wait_for_timeout(600)
            await box.press("Enter")
            await page.wait_for_timeout(2500)
            await self._continue_after_blocks()
            return True
        except Exception:
            return False

    def _build_search_url(self, keyword: str, location: str) -> str:
        """Build a search URL for listings with either internal or external applications."""
        from urllib.parse import urlencode

        params = {
            "keywords": keyword,
            "location": location,
            "f_TPR": f"r{get_settings().job_search.days_back * 86400}",
        }
        return f"{self.JOBS_URL}/?{urlencode(params)}"

    async def _scroll_results(self, page: Page, max_results: int) -> None:
        """Scroll through job results to load more cards."""
        for _ in range(min(5, max_results // 5)):
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(500)
            count = len(
                await page.query_selector_all(
                    "div.job-card-container, li.jobs-search-results__list-item"
                )
            )
            if count >= max_results:
                break

    async def _parse_job_card(self, page: Page, card) -> Optional[Job]:
        """Parse a single job card from search results."""
        try:
            await card.click()

            title_el = await card.query_selector(
                "a.job-card-list__title--link, a.job-card-container__link, "
                ".job-card-list__title, .artdeco-entity-lockup__title"
            )
            company_el = await card.query_selector(
                ".job-card-container__primary-description, "
                ".job-card-container__company-name, .artdeco-entity-lockup__subtitle"
            )
            location_el = await card.query_selector(
                ".job-card-container__metadata-item, .job-card-container__metadata-wrapper li"
            )

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            location = (await location_el.inner_text()).strip() if location_el else ""

            if not title:
                return None
            if not company:
                company = "Unknown"

            href = None
            link = await card.query_selector(
                "a[href*='/jobs/view/'], a.job-card-list__title--link, "
                "a.job-card-container__link, a[href*='currentJobId=']"
            )
            if link:
                href = await link.get_attribute("href")
            if not href and title_el:
                href = await title_el.get_attribute("href")
            if href and href.startswith("/"):
                href = f"https://www.linkedin.com{href}"

            card_id = None
            for attr in ("data-job-id", "data-occludable-job-id", "data-entity-urn"):
                card_id = await card.get_attribute(attr)
                if card_id:
                    break

            description = ""
            try:
                await card.click()
                await page.wait_for_timeout(800)
                description_el = await page.query_selector(
                    ".jobs-description__content, .jobs-search__job-details--container, "
                    "#job-details, .jobs-box__html-content"
                )
                if description_el:
                    description = (await description_el.inner_text())[:8000]
            except Exception:
                pass

            job_id = _linkedin_job_id(card_id, href, page.url)
            url = None
            if job_id:
                url = _linkedin_view_url(job_id)
            elif href and "/jobs/view/" in href:
                url = href.split("?")[0]
            elif href and "currentJobId=" in href:
                url = href

            return Job(
                title=title,
                company=company,
                location=location,
                description=description,
                url=url or None,
                source=JobSource.LINKEDIN,
                external_job_id=job_id,
            )

        except Exception as e:
            logger.debug("Job card parse failed", error=str(e))
            return None

    def _resolve_apply_url(self, job: Job) -> str:
        """Build a LinkedIn job URL the browser can open for Easy Apply."""
        raw = (job.url or "").strip()
        if raw.startswith("/"):
            raw = f"https://www.linkedin.com{raw}"
        job_id = _linkedin_job_id(job.external_job_id, raw)
        if job_id:
            return _linkedin_view_url(job_id)
        if "linkedin.com" in raw:
            return raw
        return ""

    async def _goto_soft(self, url: str) -> bool:
        """Navigate without failing the apply if LinkedIn returns 999/403."""
        try:
            response = await self._page.goto(url, wait_until="domcontentloaded", timeout=25000)
            status = response.status if response else 0
            if status >= 400:
                logger.warning("LinkedIn navigation HTTP error", status=status, url=url)
                return False
            await self._page.wait_for_timeout(1500)
            await self._continue_after_blocks()
            return True
        except Exception as e:
            logger.warning("LinkedIn navigation failed", error=str(e)[:180], url=url)
            return False

    async def _open_job_for_apply(self, job: Job, apply_url: str) -> bool:
        """Open the listing so Easy Apply is on the current page."""
        if await self._page_shows_job(job):
            return True
        if await self._select_job_on_results(job):
            return True

        job_id = _linkedin_job_id(job.external_job_id, apply_url, job.url)
        candidates: list[str] = []
        if job_id:
            candidates.append(_linkedin_view_url(job_id))
            candidates.append(
                f"https://www.linkedin.com/jobs/collections/recommended/?currentJobId={job_id}"
            )
        if apply_url and apply_url not in candidates:
            candidates.append(apply_url)

        for url in candidates:
            if not await self._goto_soft(url):
                continue
            if await self._page_shows_job(job):
                return True
            if await self._select_job_on_results(job):
                return True
            if await self._easy_apply_locator_visible():
                return True
        return False

    async def _easy_apply_locator_visible(self) -> bool:
        try:
            loc = self._page.get_by_role("button", name=re.compile(r"Easy Apply", re.I))
            return await loc.first.is_visible()
        except Exception:
            return False

    async def _page_shows_job(self, job: Job) -> bool:
        title = (job.title or "").strip().lower()
        if not title or not self._page:
            return False
        try:
            heading = await self._page.query_selector(
                "h1, .job-details-jobs-unified-top-card__job-title, "
                ".jobs-unified-top-card__job-title"
            )
            shown = ((await heading.inner_text()).strip().lower() if heading else "")
        except Exception:
            shown = ""
        return bool(shown) and (title[:24] in shown or shown[:24] in title)

    async def _select_job_on_results(self, job: Job) -> bool:
        """Click the matching search-result card so Easy Apply appears in the detail pane."""
        title_key = (job.title or "").strip().lower()[:28]
        company_key = (job.company or "").strip().lower()[:16]
        if not title_key:
            return False
        cards = await self._page.query_selector_all(
            "div.job-card-container, li.jobs-search-results__list-item, "
            "li.scaffold-layout__list-item"
        )
        for card in cards:
            try:
                text = (await card.inner_text()).lower()
            except Exception:
                continue
            if title_key[:18] not in text:
                continue
            if company_key and company_key[:10] not in text and job.company.lower() != "unknown":
                continue
            await card.click()
            await self._page.wait_for_timeout(1200)
            return True
        return False

    async def _already_applied_on_page(self) -> bool:
        try:
            loc = self._page.get_by_text(re.compile(r"^Applied$", re.I))
            if await loc.count():
                return await loc.first.is_visible()
        except Exception:
            pass
        applied = await self._page.query_selector(
            "button.jobs-apply-button[disabled], span.artdeco-inline-feedback__message"
        )
        if not applied:
            return False
        try:
            text = (await applied.inner_text()).lower()
        except Exception:
            text = ""
        return "applied" in text

    async def _click_easy_apply(self) -> bool:
        """Click the visible Easy Apply button (not Apply on company website)."""
        locators = [
            self._page.get_by_role("button", name=re.compile(r"Easy Apply", re.I)),
            self._page.locator("button.jobs-apply-button").filter(
                has_text=re.compile(r"Easy Apply", re.I)
            ),
            self._page.locator("[aria-label*='Easy Apply']"),
        ]
        for loc in locators:
            try:
                btn = loc.first
                await btn.wait_for(state="visible", timeout=4000)
                label = ((await btn.inner_text()) or "") + " " + ((await btn.get_attribute("aria-label")) or "")
                if "easy apply" not in label.lower():
                    continue
                if re.search(r"\bapplied\b", label, re.I):
                    continue
                await btn.click()
                logger.info("Clicked Easy Apply")
                return True
            except Exception:
                continue
        return False

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
        """Return a link for manual application; never open or submit a form."""
        return ApplicationResult(
            success=False, method=ApplyMethod.MANUAL_REQUIRED, requires_manual=True,
            application_url=str(job.url or self._resolve_apply_url(job) or ""),
            confirmation_message="Review and submit the application yourself using this link.",
        )

    async def _easy_apply_modal(self):
        return self._page.locator(
            ".jobs-easy-apply-modal, div[data-test-modal-id='easy-apply-modal']"
        ).first

    async def _easy_apply_modal_text(self) -> str:
        try:
            modal = await self._easy_apply_modal()
            if await modal.is_visible():
                return await modal.inner_text()
        except Exception:
            pass
        return ""

    async def _easy_apply_in_progress(self) -> bool:
        text = await self._easy_apply_modal_text()
        if not text:
            return False
        lowered = text.lower()
        if "application sent" in lowered or "application was sent" in lowered:
            return False
        if re.search(r"\d+\s*/\s*\d+\s*pages", text, re.I):
            return True
        if any(w in lowered for w in ("contact info", "resume", "additional questions", "review")):
            return True
        try:
            modal = await self._easy_apply_modal()
            return await modal.is_visible()
        except Exception:
            return False

    async def _application_succeeded(self) -> bool:
        """True only on LinkedIn's post-submit confirmation, not '100 applicants'."""
        if not self._page:
            return False
        if await self._easy_apply_in_progress():
            return False
        chunks: list[str] = []
        modal_text = await self._easy_apply_modal_text()
        if modal_text:
            chunks.append(modal_text)
        try:
            toast = self._page.locator(".artdeco-toast-item, [data-test-artdeco-toast]")
            if await toast.count():
                chunks.append(await toast.first.inner_text())
        except Exception:
            pass
        blob = "\n".join(chunks).lower()
        if not blob:
            return False
        markers = (
            "application submitted",
            "your application was sent",
            "application was sent",
            "application sent",
        )
        return any(m in blob for m in markers)

    async def _click_easy_apply_step(self) -> str:
        """Legacy entry point: application navigation is now user controlled."""
        return "manual"

    async def _complete_easy_apply(self, job: Job) -> ApplicationResult:
        """Legacy entry point: return the link instead of completing a form."""
        return await self.apply(job)

    async def _fill_application_form(self, job: Job) -> bool:
        """Fill the current Easy Apply page from profile/.env, using DeepSeek when needed."""
        from src.ai.easy_apply_form import fill_easy_apply_page

        try:
            return await fill_easy_apply_page(self._page, job)
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
