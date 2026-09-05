"""Configuration loader for YAML and environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.config.settings import Settings


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
            result[env_key] = ",".join(str(v) for v in value)
        elif value is not None:
            result[env_key] = str(value)

    return result


def _apply_yaml_defaults(yaml_config: dict[str, Any]) -> None:
    """Set YAML values into os.environ only when the key is not already set.

    Priority: existing environment / .env > YAML > code defaults.
    Nested settings classes use prefixes such as LLM_, JOB_, DB_, LOG_.
    """
    mapping_prefixes = {
        "llm": "LLM_",
        "browser": "BROWSER_",
        "job_search": "JOB_",
        "resume": "RESUME_",
        "application": "APP_",
        "linkedin": "LINKEDIN_",
        "database": "DB_",
        "logging": "LOG_",
        "user": "USER_",
    }
    for section, data in yaml_config.items():
        if section in mapping_prefixes and isinstance(data, dict):
            flat = _flatten_config(data, mapping_prefixes[section])
            for key, value in flat.items():
                os.environ.setdefault(key, value)
        elif not isinstance(data, dict):
            os.environ.setdefault(section.upper(), str(data))


def create_settings(config_path: Path | None = None) -> Settings:
    """Create settings from YAML, .env, and environment variables."""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config.yaml"

    load_dotenv()
    yaml_config = load_yaml_config(config_path)
    _apply_yaml_defaults(yaml_config)
    return Settings()


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
