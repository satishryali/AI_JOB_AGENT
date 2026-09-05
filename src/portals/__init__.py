# Portal integration module initialization

from src.portals.linkedin import LinkedInClient
from src.portals.base import BasePortal, BaseATS, ApplicationResult, ApplyMethod, LoginStatus, SearchParams
from src.portals.ats_handler import ATSDetector, AdaptiveFormFiller, UniversalApplicant
from src.portals.registry import PortalRegistry, detect_ats_from_url, register_builtin_portals

__all__ = [
    "LinkedInClient",
    "BasePortal", "BaseATS",
    "ApplicationResult", "ApplyMethod", "LoginStatus", "SearchParams",
    "ATSDetector", "AdaptiveFormFiller", "UniversalApplicant",
    "PortalRegistry", "detect_ats_from_url", "register_builtin_portals",
]
