"""Job-related data models using Pydantic."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class JobSource(str, Enum):
    """Source portal for a job listing."""

    LINKEDIN = "linkedin"
    INDEED = "indeed"
    NAUKRI = "naukri"
    FOUNDIT = "foundit"
    WELLFOUND = "wellfound"
    GLASSDOOR = "glassdoor"
    REMOTIVE = "remotive"
    ADZUNA = "adzuna"
    COMPANY = "company"
    OTHER = "other"


class JobStatus(str, Enum):
    """Status of a collected job listing."""

    COLLECTED = "collected"
    FOUND = "found"
    MATCHED = "matched"
    MISMATCHED = "mismatched"
    ARCHIVED = "archived"


class ApplicationStatus(str, Enum):
    """Application pipeline statuses."""

    SAVED = "saved"
    REVIEW = "review"
    READY = "ready"
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    OFFER = "offer"
    WITHDRAWN = "withdrawn"
    FAILED = "failed"
    ALREADY_APPLIED = "already_applied"


class Job(BaseModel):
    """Represents a job listing scraped from a portal."""

    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    location: str = Field("", description="Job location")
    description: str = Field("", description="Full job description text")
    url: Optional[HttpUrl] = Field(None, description="Job listing URL")
    source: JobSource = Field(JobSource.OTHER, description="Source portal")
    employment_type: Optional[str] = Field(None, description="Full-time, Part-time, etc.")
    salary_range: Optional[str] = Field(None, description="Salary range if available")
    posted_date: Optional[datetime] = Field(None, description="Date job was posted")
    skills_required: list[str] = Field(default_factory=list, description="Skills mentioned in job")
    experience_required: Optional[int] = Field(None, ge=0, description="Years of experience required")
    remote: bool = Field(False, description="Whether job is remote")
    raw_data: dict = Field(default_factory=dict, description="Raw scraped data")
    external_job_id: str = Field("", description="Source-specific job id")
    collected_at: Optional[datetime] = Field(None)
    status: JobStatus = Field(JobStatus.COLLECTED)
    match_score: Optional[float] = Field(None, ge=0.0, le=100.0)

    @property
    def key(self) -> str:
        """Unique key for in-memory deduplication."""
        if self.external_job_id:
            return f"{self.source.value}:{self.external_job_id}"
        return f"{self.company.lower()}:{self.title.lower()}:{self.location.lower()}"

    def __hash__(self) -> int:
        return hash(self.key)


class NormalizedJob(BaseModel):
    """Canonical job payload produced by every collector."""

    source: str
    external_job_id: str
    title: str
    company: str
    location: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    salary: str = ""
    job_url: str = ""
    posted_date: Optional[datetime] = None


class MatchResult(BaseModel):
    """Result of resume matching."""

    job: Job
    score: float = Field(..., ge=0.0, le=100.0, description="Match score 0-100")
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    should_apply: bool = Field(False, description="Heuristic recommendation only")
    reasoning: str = Field("", description="Explanation for the score")
    applied_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When match was evaluated",
    )


class ApplicationResult(BaseModel):
    """Result of preparing or recording an application."""

    job: Job
    status: ApplicationStatus = Field(ApplicationStatus.FAILED)
    applied_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    portal: Optional[str] = Field(None, description="Portal where application was submitted")
    application_url: Optional[str] = Field(None, description="URL of submitted application")
    resume_path: Optional[str] = Field(None, description="Path to resume used")
    cover_letter_path: Optional[str] = Field(None, description="Path to cover letter used")
    error_message: Optional[str] = Field(None, description="Error if application failed")
    screenshot_path: Optional[str] = Field(None, description="Screenshot if error occurred")
