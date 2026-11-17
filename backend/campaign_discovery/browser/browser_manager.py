import os
import logging
from typing import Optional
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page

logger = logging.getLogger("CampaignDiscovery.BrowserManager")


class BrowserManager:
    """
    Manages Playwright lifecycle with a persistent Chromium context.
    Stores browser state, cookies, and local storage locally in backend/data/browser_profile/.
    """

    def __init__(
        self,
        profile_dir: Optional[str] = None,
        headless: bool = True,
        default_timeout_ms: int = 30000
    ):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if profile_dir is None:
            self.profile_dir = os.path.join(base_dir, "data", "browser_profile")
        else:
            self.profile_dir = profile_dir

        self.headless = headless
        self.default_timeout_ms = default_timeout_ms
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None

    def initialize(self) -> BrowserContext:
        """Launches Chromium with persistent storage context."""
        os.makedirs(self.profile_dir, exist_ok=True)
        
        if self._context is not None:
            return self._context

        logger.info(f"Launching Chromium (headless={self.headless}, profile={self.profile_dir})")
        self._playwright = sync_playwright().start()

        # Launch persistent context
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US"
        )
        self._context.set_default_timeout(self.default_timeout_ms)
        return self._context

    def new_page(self) -> Page:
        """Returns a new page from the persistent context."""
        ctx = self.initialize()
        return ctx.new_page()

    def close(self):
        """Closes browser context and Playwright gracefully."""
        try:
            if self._context:
                logger.info("Closing browser persistent context...")
                self._context.close()
                self._context = None
        except Exception as e:
            logger.warning(f"Error closing browser context: {e}")

        try:
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
        except Exception as e:
            logger.warning(f"Error stopping Playwright: {e}")

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

