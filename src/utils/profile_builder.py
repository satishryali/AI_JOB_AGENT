"""Build a user profile from resume and settings for form filling."""

import re
from pathlib import Path
from typing import Optional

from src.config.config_loader import get_settings
from src.config.logging import get_logger

logger = get_logger(__name__)


class ProfileBuilder:
    """Build a user profile from resume and configuration."""

    def __init__(self):
        self.settings = get_settings()
        self.profile: dict = {}

    def build(self) -> dict:
        """Build the complete user profile."""
        self.profile = {
            # Personal info from settings
            "first_name": self._extract_first_name(),
            "last_name": self._extract_last_name(),
            "email": self._extract_email(),
            "phone": self._extract_phone(),
            "linkedin": "",
            "github": "",
            "website": "",
            "city": "",
            "resume": str(self.settings.resume.path),
            "cover_letter": str(self.settings.application.cover_letter_template),
            "experience": str(self.settings.resume.experience_years),
            "salary": "",
            "notice_period": "",
            "work_authorization": "",
            "willing_to_relocate": "",
            "availability": "",
        }

        # Extract from resume if available
        resume_text = self._extract_resume_text(self.settings.resume.path)
        if resume_text:
            self._parse_resume(resume_text)

        # Extract from LinkedIn settings (if it's a username, not an email)
        linkedin_username = self.settings.linkedin.username
        if linkedin_username and "@" not in linkedin_username:
            self.profile["linkedin"] = f"https://www.linkedin.com/in/{linkedin_username}"

        # Validate and fill defaults
        self._fill_defaults()

        logger.info("Profile built", keys=list(self.profile.keys()))
        return self.profile

    def _extract_first_name(self) -> str:
        """Extract first name from settings, then resume filename."""
        if self.settings.user.first_name:
            return self.settings.user.first_name
        resume_name = self.settings.resume.path.stem
        parts = re.split(r"[._\- ]+", resume_name)
        if parts and parts[0] and parts[0].lower() not in {"resume", "cv"}:
            clean = re.sub(r"\d+", "", parts[0]).strip()
            if clean:
                return clean.capitalize()
        return ""

    def _extract_last_name(self) -> str:
        """Extract last name from settings, then resume filename."""
        if self.settings.user.last_name:
            return self.settings.user.last_name
        resume_name = self.settings.resume.path.stem
        parts = re.split(r"[._\- ]+", resume_name)
        if len(parts) > 1 and parts[1] and parts[1].lower() not in {"resume", "cv"}:
            clean = re.sub(r"\d+", "", parts[1]).strip()
            if clean:
                return clean.capitalize()
        return ""

    def _extract_email(self) -> str:
        if self.settings.user.email:
            return self.settings.user.email
        if "@" in self.settings.linkedin.username:
            return self.settings.linkedin.username
        return ""

    def _extract_phone(self) -> str:
        return self.settings.user.phone or ""

    def _extract_resume_text(self, path: Path) -> str:
        """Extract text from resume file."""
        if not path.exists():
            return ""

        try:
            if path.suffix.lower() == ".pdf":
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    return "\n".join(page.extract_text() or "" for page in pdf.pages)
            elif path.suffix.lower() in (".doc", ".docx"):
                from docx import Document
                doc = Document(str(path))
                return "\n".join(p.text for p in doc.paragraphs if p.text)
            elif path.suffix.lower() == ".txt":
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            elif path.suffix.lower() == ".tex":
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            logger.warning("Failed to extract resume text", error=str(e))

        return ""

    def _parse_resume(self, text: str) -> None:
        """Parse resume text to extract profile information."""
        # Extract email
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
        if email_match and not self.profile["email"]:
            self.profile["email"] = email_match.group(0)

        # Extract phone
        phone_match = re.search(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", text)
        if phone_match:
            self.profile["phone"] = phone_match.group(0)

        # Extract LinkedIn URL
        linkedin_match = re.search(r"linkedin\.com/in/[\w-]+", text, re.IGNORECASE)
        if linkedin_match:
            self.profile["linkedin"] = f"https://www.{linkedin_match.group(0).strip('.,')}"

        # Extract GitHub URL
        github_match = re.search(r"github\.com/[\w-]+", text, re.IGNORECASE)
        if github_match:
            self.profile["github"] = f"https://www.{github_match.group(0).strip('.,')}"

        # Extract city/location
        location_match = re.search(r"(?:Location|City|Based in|Address)[:;\s]*(\S+[\w\s]*?)\n", text, re.IGNORECASE)
        if location_match:
            self.profile["city"] = location_match.group(1).strip()

        # Extract years of experience
        exp_match = re.search(r"(\d+)\s*\+?\s*years?\s*(?:of)?\s*experience", text, re.IGNORECASE)
        if exp_match:
            self.profile["experience"] = exp_match.group(1)

        # Extract name from the beginning of resume
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines and not self.profile["first_name"]:
            # First line is usually the name
            name_parts = lines[0].split()
            if len(name_parts) >= 1:
                self.profile["first_name"] = name_parts[0].capitalize()
            if len(name_parts) >= 2:
                self.profile["last_name"] = name_parts[1].capitalize()

        # Extract salary expectation if mentioned
        salary_match = re.search(r"(?:Expected|Expected Salary|Salary Expectation)[:;\s]*(\S[\w\s,.-]*?)\n", text, re.IGNORECASE)
        if salary_match:
            self.profile["salary"] = salary_match.group(1).strip()

    def _fill_defaults(self) -> None:
        """Fill defaults from configuration only — do not invent personal data."""
        if not self.profile["availability"]:
            self.profile["availability"] = "Immediate"
