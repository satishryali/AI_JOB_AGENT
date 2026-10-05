"""Configuration loader for YAML and environment variables."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.config.settings import Settings

_LIST_ENV_KEYS = (
    "JOB_KEYWORDS",
    "JOB_LOCATIONS",
    "JOB_PORTALS",
    "JOB_COLLECTION_SITES",
    "USER_PREFERRED_ROLES",
    "USER_PREFERRED_LOCATIONS",
)


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Load configuration from YAML file."""
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _flatten_config(config: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten nested config dict to environment variable format."""
    result: dict[str, str] = {}

    for key, value in config.items():
        env_key = f"{prefix}{key.upper()}" if prefix else key.upper()

        if isinstance(value, dict):
            result.update(_flatten_config(value, f"{env_key}_"))
        elif isinstance(value, list):
            result[env_key] = json.dumps(value)
        elif value is not None:
            result[env_key] = str(value)

    return result


def _coerce_list_env_vars() -> None:
    """Accept comma-separated or JSON lists in .env for list settings."""
    for key in _LIST_ENV_KEYS:
        raw = os.environ.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if not value:
            continue
        if value.startswith("["):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    os.environ[key] = json.dumps(parsed)
                    continue
            except json.JSONDecodeError:
                pass
        parts = [p.strip().strip("\"'") for p in value.split(",") if p.strip()]
        os.environ[key] = json.dumps(parts)


def create_settings(config_path: Path | None = None) -> Settings:
    """Precedence: process environment > .env > YAML > model defaults.

    YAML is passed to the models instead of written into os.environ, so loading
    another config or resetting settings cannot inherit a previous YAML value.
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    load_dotenv(config_path.parent / ".env")
    yaml_config = load_yaml_config(config_path)
    _coerce_list_env_vars()
    prefixes = {"llm": "LLM_", "browser": "BROWSER_", "job_search": "JOB_",
                "resume": "RESUME_", "application": "APP_", "linkedin": "LINKEDIN_",
                "database": "DB_", "logging": "LOG_", "user": "USER_"}
    sections = {}
    for section, prefix in prefixes.items():
        model = Settings.model_fields[section].annotation
        defaults = {key: value for key, value in yaml_config.get(section, {}).items()
                    if f"{prefix}{key.upper()}" not in os.environ}
        sections[section] = model(**defaults)
    if os.environ.get("DATABASE_URL"):
        sections["database"].url = os.environ["DATABASE_URL"]
    root_defaults = {key: value for key, value in yaml_config.items()
                     if key not in prefixes and key.upper() not in os.environ}
    return Settings(_env_file=None, **root_defaults, **sections)


_settings: Settings | None = None


def get_settings(config_path: Path | None = None) -> Settings:
    """Get or create the global settings instance."""
    global _settings

    if _settings is None:
        _settings = create_settings(config_path)

    return _settings


def reset_settings() -> None:
    """Reset the global settings instance (useful for testing)."""
    global _settings
    _settings = None
