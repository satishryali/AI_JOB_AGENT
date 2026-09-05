"""Collector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.models.job import NormalizedJob


@dataclass
class CollectorResult:
    source: str
    jobs: list[NormalizedJob] = field(default_factory=list)
    error: str | None = None
    skipped: bool = False


class BaseCollector(ABC):
    name: str = "base"

    @abstractmethod
    async def collect(
        self,
        keywords: list[str],
        locations: list[str],
        max_results: int,
    ) -> list[NormalizedJob]:
        ...
