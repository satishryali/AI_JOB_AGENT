"""Job collectors: public APIs plus isolated portal wrappers."""

from src.collectors.base import BaseCollector, CollectorResult
from src.collectors.runner import run_collectors

__all__ = ["BaseCollector", "CollectorResult", "run_collectors"]
