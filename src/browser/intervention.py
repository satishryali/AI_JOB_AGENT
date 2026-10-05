"""Pause the agent until the user finishes a security or form step."""

from __future__ import annotations

import asyncio
import sys

from src.config.logging import get_logger

logger = get_logger(__name__)


class HumanInterventionRequired(RuntimeError):
    """A browser task cannot continue without an interactive user."""


async def wait_for_human(reason: str) -> None:
    """Block until the user presses Enter. Does not bypass CAPTCHA, MFA, or checkpoints."""
    if sys.stdin is None or not sys.stdin.isatty():
        raise HumanInterventionRequired(reason)
    message = (
        f"\nHuman intervention needed: {reason}\n"
        "Complete it in the open browser (do not close the window).\n"
        "Press Enter here when the page is ready to continue...\n"
    )
    logger.warning("Waiting for human intervention", reason=reason)
    try:
        await asyncio.to_thread(input, message)
    except EOFError as e:
        raise HumanInterventionRequired(reason) from e
