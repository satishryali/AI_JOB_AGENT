"""Configuration settings models using Pydantic."""

from pathlib import Path
from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    provider: Literal["deepseek", "openai", "anthropic", "gemini"] = "deepseek"
    model: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4000, gt=0)
    timeout: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=8)
    enable_explanations: bool = False


class BrowserSettings(BaseSettings):
    """Browser automation configuration."""

    model_config = SettingsConfigDict(env_prefix="BROWSER_")

    headless: bool = False
    timeout: int = Field(default=30000, gt=0)
    viewport_width: int = Field(default=1920, gt=0)
    viewport_height: int = Field(default=1080, gt=0)
    user_agent: str = ""
    slow_mo: int = Field(default=0, ge=0)


class JobSearchSettings(BaseSettings):
    """Job search configuration."""

    model_config = SettingsConfigDict(env_prefix="JOB_")

    keywords: list[str] = Field(default_factory=lambda: ["python", "ai", "machine learning"])
    locations: list[str] = Field(default_factory=lambda: ["remote"])
    portals: list[str] = Field(default_factory=lambda: ["linkedin", "indeed"])
    max_results_per_portal: int = Field(default=50, gt=0)
    days_back: int = Field(default=7, gt=0)
    min_match_score: float = Field(default=50.0, ge=0.0, le=100.0)

    @field_validator("min_match_score", mode="before")
    @classmethod
    def scale_legacy_score(cls, v):
        if v is None or v == "":
            return 50.0
        value = float(v)
        if 0 < value <= 1:
            return value * 100.0
        return value


class ResumeSettings(BaseSettings):
    """Resume configuration."""

    model_config = SettingsConfigDict(env_prefix="RESUME_")

    path: Path = Path("data/resumes/Satyanarayana_Ryali.pdf")
    skills_path: Path = Path("data/resumes/skills.yaml")
    experience_years: int = Field(default=4, ge=0)

    @field_validator("path", "skills_path", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve()


class ApplicationSettings(BaseSettings):
    """Application automation configuration."""

    model_config = SettingsConfigDict(env_prefix="APP_")

    auto_apply: bool = False
    max_applications_per_day: int = Field(default=10, gt=0)
    delay_between_applications: int = Field(default=30, ge=0)
    cover_letter_template: Path = Path("data/templates/cover_letter.txt")

    @field_validator("cover_letter_template", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve()


class LinkedInSettings(BaseSettings):
    """LinkedIn-specific configuration."""

    model_config = SettingsConfigDict(env_prefix="LINKEDIN_")

    username: str = ""
    password: str = ""
    login_timeout: int = Field(default=30, gt=0)
    search_timeout: int = Field(default=60, gt=0)


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="DB_")

    url: str = ""
    path: Path = Path("data/job_hunter.db")

    @field_validator("path", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve()

    def sqlalchemy_url(self) -> str:
        import os

        env_url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL") or self.url
        if env_url:
            return env_url
        sqlite_path = self.path.as_posix()
        return f"sqlite:///{sqlite_path}"


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: Path = Path("data/logs/agent.log")
    format: str = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}"
    rotation: str = "10 MB"
    retention: str = "7 days"

    @field_validator("file", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve()


class UserProfileSettings(BaseSettings):
    """User identity and preferences. Never hard-code personal data in source."""

    model_config = SettingsConfigDict(env_prefix="USER_")

    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    salary_expectations: str = ""


class Settings(BaseSettings):
    """Main application settings aggregator."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    job_search: JobSearchSettings = Field(default_factory=JobSearchSettings)
    resume: ResumeSettings = Field(default_factory=ResumeSettings)
    application: ApplicationSettings = Field(default_factory=ApplicationSettings)
    linkedin: LinkedInSettings = Field(default_factory=LinkedInSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    user: UserProfileSettings = Field(default_factory=UserProfileSettings)
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent.parent
