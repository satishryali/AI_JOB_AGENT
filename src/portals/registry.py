"""Portal and ATS registry with factory pattern for easy extensibility."""

from typing import Optional, Type, TypeVar

from src.config.logging import get_logger
from src.models.job import JobSource
from src.portals.base import BaseATS, BasePortal

logger = get_logger(__name__)

P = TypeVar("P", bound=BasePortal)
A = TypeVar("A", bound=BaseATS)


class PortalRegistry:
    """Registry for all job portals and ATS platforms.

    New portals/ATS can be registered by calling register_portal() or
    by adding them to the appropriate dictionary during class definition.
    """

    _portals: dict[str, Type[BasePortal]] = {}
    _ats_platforms: dict[str, Type[BaseATS]] = {}
    _instances: dict[str, BasePortal] = {}

    @classmethod
    def register_portal(cls, name: str, portal_class: Type[BasePortal]) -> None:
        """Register a job portal."""
        cls._portals[name.lower()] = portal_class
        logger.debug("Registered job portal", name=name, class_name=portal_class.__name__)

    @classmethod
    def register_ats(cls, name: str, ats_class: Type[BaseATS]) -> None:
        """Register an ATS platform."""
        cls._ats_platforms[name.lower()] = ats_class
        logger.debug("Registered ATS platform", name=name, class_name=ats_class.__name__)

    @classmethod
    def get_portal(cls, name: str, **kwargs) -> Optional[BasePortal]:
        """Get a portal instance by name."""
        portal_cls = cls._portals.get(name.lower())
        if not portal_cls:
            logger.error("Portal not registered", name=name)
            return None
        return portal_cls(**kwargs)

    @classmethod
    def get_ats(cls, name: str, **kwargs) -> Optional[BaseATS]:
        """Get an ATS instance by name."""
        ats_cls = cls._ats_platforms.get(name.lower())
        if not ats_cls:
            logger.error("ATS not registered", name=name)
            return None
        return ats_cls(**kwargs)

    @classmethod
    def get_all_portals(cls) -> dict[str, Type[BasePortal]]:
        """Get all registered portals."""
        return cls._portals.copy()

    @classmethod
    def get_all_ats(cls) -> dict[str, Type[BaseATS]]:
        """Get all registered ATS platforms."""
        return cls._ats_platforms.copy()

    @classmethod
    def available_portals(cls) -> list[str]:
        """List all registered portal names."""
        return sorted(cls._portals.keys())

    @classmethod
    def available_ats(cls) -> list[str]:
        """List all registered ATS names."""
        return sorted(cls._ats_platforms.keys())

    @classmethod
    def get_portal_for_source(cls, source: JobSource) -> Optional[Type[BasePortal]]:
        """Get portal class for a JobSource enum value."""
        for name, portal_cls in cls._portals.items():
            if portal_cls.portal_source == source:
                return portal_cls
        return None


# ==============================================================================
# ATS Detection Registry
# ==============================================================================

# ATS domain patterns for detection
ATS_DOMAIN_PATTERNS: dict[str, list[str]] = {
    "workday": [
        "workday.com", "wd5.myworkday.com", "myworkday.com", "wd1.myworkday.com",
        "wd2.myworkday.com", "wd3.myworkday.com", "workdayjobs.com",
    ],
    "greenhouse": ["greenhouse.io", "boards.greenhouse.io", "app.greenhouse.io"],
    "lever": ["lever.co", "jobs.lever.co"],
    "ashby": ["ashbyhq.com", "jobs.ashbyhq.com"],
    "smartrecruiters": ["smartrecruiters.com", "jobs.smartrecruiters.com"],
    "icims": ["icims.com", "jobs.icims.com"],
    "taleo": ["taleo.net", "oraclecloud.com", "tbe.taleo.net", "taleo.com"],
    "successfactors": ["successfactors.com", "sapsf.com", "sapsf.eu", "sapcloudform.com"],
    "bamboohr": ["bamboohr.com", "apply.workable.com"],
    "jobvite": ["jobvite.com", "jobs.jobvite.com"],
}


def detect_ats_from_url(url: str) -> str:
    """Detect ATS platform from URL."""
    from urllib.parse import urlparse

    domain = urlparse(url).netloc.lower()
    full_url = url.lower()

    for ats_name, domains in ATS_DOMAIN_PATTERNS.items():
        for d in domains:
            if d in domain or d in full_url:
                return ats_name

    return "unknown"


def register_builtin_portals() -> None:
    """Register all built-in portals and ATS platforms."""
    # Import here to avoid circular imports
    from src.portals.linkedin import LinkedInClient

    # Register LinkedIn (existing client, adapted to BasePortal interface)
    PortalRegistry.register_portal("linkedin", LinkedInClient)

    # Register Naukri
    try:
        from src.portals.naukri import NaukriPortal
        PortalRegistry.register_portal("naukri", NaukriPortal)
    except ImportError as e:
        logger.debug("Naukri portal not available", error=str(e))

    # Register Indeed
    try:
        from src.portals.indeed import IndeedPortal
        PortalRegistry.register_portal("indeed", IndeedPortal)
    except ImportError as e:
        logger.debug("Indeed portal not available", error=str(e))

    # Register Foundit
    try:
        from src.portals.foundit import FounditPortal
        PortalRegistry.register_portal("foundit", FounditPortal)
    except ImportError as e:
        logger.debug("Foundit portal not available", error=str(e))

    # Register ATS platforms
    try:
        from src.portals.ats_implementations import (
            AshbyATS, BambooHRATS, GreenhouseATS, ICIMSATS, JobviteATS,
            LeverATS, SmartRecruitersATS, SuccessFactorsATS, TaleoATS,
            WorkdayATS,
        )
        PortalRegistry.register_ats("workday", WorkdayATS)
        PortalRegistry.register_ats("greenhouse", GreenhouseATS)
        PortalRegistry.register_ats("lever", LeverATS)
        PortalRegistry.register_ats("ashby", AshbyATS)
        PortalRegistry.register_ats("smartrecruiters", SmartRecruitersATS)
        PortalRegistry.register_ats("icims", ICIMSATS)
        PortalRegistry.register_ats("taleo", TaleoATS)
        PortalRegistry.register_ats("successfactors", SuccessFactorsATS)
        PortalRegistry.register_ats("bamboohr", BambooHRATS)
        PortalRegistry.register_ats("jobvite", JobviteATS)
    except ImportError as e:
        logger.debug("ATS implementations not available", error=str(e))

    logger.info(
        "Built-in portals registered",
        portals=PortalRegistry.available_portals(),
        ats=PortalRegistry.available_ats(),
    )