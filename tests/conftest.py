"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from src.config.config_loader import reset_settings
from src.db.session import init_db, reset_engine


@pytest.fixture
def db():
    reset_settings()
    reset_engine()
    init_db("sqlite:///:memory:")
    yield
    reset_engine()
    reset_settings()
