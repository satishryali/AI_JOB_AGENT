"""Browser automation manager using Playwright."""

import asyncio
from functools import wraps
from pathlib import Path
from typing import Callable, Any, Optional
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from src.config.settings import BrowserSettings
from src.config.config_loader import get_settings
from src.config.logging import get_logger

logger = get_logger(__name__)


class BrowserManager:
    """Manages Playwright browser lifecycle and provides high-level automation helpers."""

    def __init__(self, settings: Optional[BrowserSettings] = None):
        self._settings = settings or get_settings().browser
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: list[BrowserContext] = []

    async def launch(self) -> None:
        """Launch the browser instance."""
        if self._browser is not None:
            logger.warning("Browser already launched")
            return

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._settings.headless,
            slow_mo=self._settings.slow_mo,
        )
        logger.info("Browser launched", headless=self._settings.headless)

    async def new_context(self, **kwargs) -> BrowserContext:
        """Create a new isolated browser context."""
        if self._browser is None:
            await self.launch()

        context = await self._browser.new_context(
            viewport={
                "width": self._settings.viewport_width,
                "height": self._settings.viewport_height,
            },
            user_agent=self._settings.user_agent or None,
            **kwargs,
        )
        self._contexts.append(context)
        logger.debug("New browser context created")
        return context

    async def new_page(self, context: Optional[BrowserContext] = None) -> Page:
        """Create a new page in the given context (or default)."""
        if context is None:
            context = await self.new_context()
        page = await context.new_page()
        page.set_default_timeout(self._settings.timeout)
        return page

    async def navigate(
        self,
        page: Page,
        url: str,
        wait_until: str = "domcontentloaded",
        retries: int = 2,
    ) -> None:
        """Navigate to URL with retry logic."""
        last_error = None
        for attempt in range(retries + 1):
            try:
                logger.debug("Navigating", url=url, attempt=attempt + 1)
                await page.goto(url, wait_until=wait_until, timeout=self._settings.timeout)
                return
            except Exception as e:
                last_error = e
                logger.warning("Navigation failed", url=url, attempt=attempt + 1, error=str(e))
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
        raise last_error

    async def screenshot_on_error(self, page: Page, name: str) -> Path:
        """Take a screenshot for debugging."""
        screenshots_dir = Path("data/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        path = screenshots_dir / f"{name}_{int(asyncio.get_event_loop().time())}.png"
        await page.screenshot(path=str(path), full_page=True)
        logger.error("Screenshot saved", path=str(path))
        return path

    async def close_context(self, context: BrowserContext) -> None:
        """Close a specific context."""
        if context in self._contexts:
            await context.close()
            self._contexts.remove(context)
            logger.debug("Browser context closed")

    async def close(self) -> None:
        """Close all contexts and browser."""
        for context in self._contexts:
            await context.close()
        self._contexts.clear()

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        logger.info("Browser closed")

    async def __aenter__(self) -> "BrowserManager":
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


def with_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for retrying async operations with exponential backoff."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "Operation failed, retrying",
                            func=func.__name__,
                            attempt=attempt + 1,
                            delay=delay,
                            error=str(e),
                        )
                        await asyncio.sleep(delay)
            raise last_error

        return wrapper

    return decorator


_browser_manager: Optional[BrowserManager] = None


async def get_browser_manager(settings: Optional[BrowserSettings] = None) -> BrowserManager:
    """Get or create the global browser manager instance."""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager(settings)
    return _browser_manager


async def reset_browser_manager() -> None:
    """Reset the global browser manager (useful for testing)."""
    global _browser_manager
    if _browser_manager:
        await _browser_manager.close()
    _browser_manager = None
