import time
import logging
from typing import Dict, Any, Optional
from playwright.sync_api import Page
from .browser_manager import BrowserManager

logger = logging.getLogger("CampaignDiscovery.SessionManager")


class SessionManager:
    """
    Manages user authentication state and headed manual login workflows
    for Content Rewards without storing or exposing credentials.
    """

    def __init__(self, browser_manager: Optional[BrowserManager] = None):
        self.browser_manager = browser_manager or BrowserManager()

    def check_auth_status(self, page: Optional[Page] = None) -> Dict[str, Any]:
        """
        Inspects page DOM to determine whether the user session is authenticated.
        Public pages on Content Rewards display 'Sign in' / 'Create Account' when unauthenticated.
        """
        created_local_page = False
        target_page = page

        if target_page is None:
            created_local_page = True
            target_page = self.browser_manager.new_page()
            target_page.goto("https://contentrewards.com/c/discover", timeout=30000, wait_until="domcontentloaded")
            target_page.wait_for_timeout(2000)

        try:
            content = target_page.content().lower()
            url = target_page.url

            # Unauthenticated indicators
            has_signin = "sign in" in content or "create account" in content or "/sign-in" in url
            # Authenticated indicators (user avatar, dashboard, account settings, logout/signout)
            has_auth_markers = (
                "log out" in content or
                "sign out" in content or
                "dashboard" in content or
                bool(target_page.query_selector("button[aria-label*='user'], button[aria-label*='profile'], img[alt*='avatar']"))
            )

            is_authenticated = has_auth_markers and not has_signin

            return {
                "is_authenticated": is_authenticated,
                "status": "AUTHENTICATED" if is_authenticated else "UNAUTHENTICATED",
                "current_url": url,
                "details": "Active logged-in session detected." if is_authenticated else "Unauthenticated session (public discover view)."
            }
        except Exception as e:
            logger.error(f"Error checking session status: {e}")
            return {
                "is_authenticated": False,
                "status": "ERROR",
                "current_url": getattr(target_page, "url", ""),
                "details": str(e)
            }
        finally:
            if created_local_page and target_page:
                try:
                    target_page.close()
                except Exception:
                    pass

    def launch_manual_login(self, timeout_seconds: int = 180) -> Dict[str, Any]:
        """
        Launches a headed Chromium browser window to allow the user to log in manually.
        Stores persistent cookies in backend/data/browser_profile/.
        Polls until login succeeds or timeout is reached.
        """
        logger.info(f"Launching headed browser for manual login (timeout: {timeout_seconds}s)...")
        # Ensure any existing headless context is closed first
        self.browser_manager.close()

        headed_mgr = BrowserManager(
            profile_dir=self.browser_manager.profile_dir,
            headless=False,
            default_timeout_ms=timeout_seconds * 1000
        )
        
        try:
            page = headed_mgr.new_page()
            page.goto("https://contentrewards.com/", timeout=45000, wait_until="domcontentloaded")
            
            start_time = time.time()
            logger.info("Headed browser open. Waiting for user to complete manual login...")

            while time.time() - start_time < timeout_seconds:
                time.sleep(3)
                try:
                    status = self.check_auth_status(page)
                    if status.get("is_authenticated"):
                        logger.info("User login successfully detected!")
                        return {
                            "status": "SUCCESS",
                            "message": "Authentication successful. Browser profile updated.",
                            "authenticated": True
                        }
                except Exception:
                    pass

            return {
                "status": "TIMEOUT",
                "message": f"Manual login did not complete within {timeout_seconds} seconds.",
                "authenticated": False
            }
        finally:
            headed_mgr.close()

