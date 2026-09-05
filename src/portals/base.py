"""Base portal interface that all job portals and ATS platforms must implement."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from playwright.async_api import BrowserContext, Page

from src.models.job import Job


class LoginStatus(str, Enum):
    """Status of login attempts."""
    SUCCESS = "success"
    FAILED = "failed"
    ALREADY_LOGGED_IN = "already_logged_in"
    CAPTCHA_REQUIRED = "captcha_required"
    TWO_FA_REQUIRED = "two_fa_required"
    EXPIRED_SESSION = "expired_session"


class ApplyMethod(str, Enum):
    """How the application is submitted."""
    EASY_APPLY = "easy_apply"
    QUICK_APPLY = "quick_apply"
    STANDARD = "standard"
    EXTERNAL_REDIRECT = "external_redirect"
    MANUAL_REQUIRED = "manual_required"


@dataclass
class SearchParams:
    """Parameters for job search."""
    keywords: list[str]
    locations: list[str] = field(default_factory=list)
    experience_levels: list[str] = field(default_factory=list)
    job_types: list[str] = field(default_factory=list)  # full-time, part-time, contract
    work_modes: list[str] = field(default_factory=list)  # remote, hybrid, onsite
    salary_range: Optional[str] = None
    posted_within_days: Optional[int] = 7
    max_results: int = 25
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApplicationResult:
    """Result of an application attempt."""
    success: bool
    method: ApplyMethod = ApplyMethod.STANDARD
    application_url: str = ""
    confirmation_message: str = ""
    requires_manual: bool = False
    error: Optional[str] = None
    screenshot_path: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class BasePortal(ABC):
    """Common interface for all job portal implementations.

    Every new portal must implement these methods.
    """

    portal_name: str = "base"
    portal_source: Any = None  # JobSource enum value

    def __init__(
        self,
        context: Optional[BrowserContext] = None,
        page: Optional[Page] = None,
        credentials: Optional[dict] = None,
    ):
        self.context = context
        self.page = page
        self.credentials = credentials or {}
        self.is_logged_in = False

    @abstractmethod
    async def login(self) -> LoginStatus:
        """Login to the portal. Returns login status."""
        ...

    @abstractmethod
    async def search_jobs(self, params: SearchParams) -> list[Job]:
        """Search for jobs on the portal."""
        ...

    @abstractmethod
    async def extract_job(self, job_url: str) -> Optional[Job]:
        """Extract job details from a job URL."""
        ...

    @abstractmethod
    async def apply(
        self,
        job: Job,
        resume_path: str,
        cover_letter_path: str = "",
        profile: Optional[dict] = None,
    ) -> ApplicationResult:
        """Apply to a job."""
        ...

    async def logout(self) -> None:
        """Logout from the portal. Optional."""
        pass

    async def close(self) -> None:
        """Close portal session. Optional cleanup."""
        pass

    def is_captcha_required(self) -> bool:
        """Check if CAPTCHA is blocking the page."""
        if not self.page:
            return False

        try:
            captcha_selectors = [
                "iframe[src*='recaptcha']",
                "iframe[src*='captcha']",
                "[class*='captcha']",
                "[id*='captcha']",
                "iframe[title*='captcha']",
                "iframe[src*='hcaptcha']",
                "[data-sitekey]",
            ]
            for selector in captcha_selectors:
                el = self.page.query_selector(selector)
                if el:
                    return True
        except Exception:
            pass
        return False


class BaseATS(BasePortal):
    """Base class specifically for ATS (Applicant Tracking Systems).

    ATS platforms handle applications redirected from job portals.
    """

    ats_name: str = "base_ats"

    @abstractmethod
    async def detect(self, url: str) -> bool:
        """Detect if this ATS handles the given URL."""
        ...

    @abstractmethod
    async def submit_application(
        self,
        job_url: str,
        profile: dict,
        resume_path: str,
        cover_letter_path: str = "",
    ) -> ApplicationResult:
        """Submit an application directly to the ATS."""
        ...