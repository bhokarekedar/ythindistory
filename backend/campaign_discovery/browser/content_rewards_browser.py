import time
import logging
from typing import List, Optional, Dict, Any
from playwright.sync_api import Page
from .browser_manager import BrowserManager
from ..extraction.campaign_listing import CampaignListingExtractor
from ..extraction.campaign_detail import CampaignDetailExtractor
from ..models.campaign import DiscoveredCampaignCard, DiscoveredCampaignDetail

logger = logging.getLogger("CampaignDiscovery.ContentRewardsBrowser")


class ContentRewardsBrowser:
    """
    Automated browser service for navigating Content Rewards,
    discovering campaign listings with infinite scrolling/pagination,
    and navigating to individual campaign pages for detailed extraction.
    """

    DISCOVER_URL = "https://contentrewards.com/c/discover"

    def __init__(
        self,
        browser_manager: Optional[BrowserManager] = None,
        listing_extractor: Optional[CampaignListingExtractor] = None,
        detail_extractor: Optional[CampaignDetailExtractor] = None
    ):
        self.browser_manager = browser_manager or BrowserManager()
        self.listing_extractor = listing_extractor or CampaignListingExtractor()
        self.detail_extractor = detail_extractor or CampaignDetailExtractor()

    def discover_campaign_listings(
        self,
        max_scroll_passes: int = 2,
        page: Optional[Page] = None
    ) -> List[DiscoveredCampaignCard]:
        """
        Navigates to Content Rewards Discover page, handles scrolling,
        and extracts all unique campaign listing cards.
        """
        created_local_page = False
        target_page = page

        if target_page is None:
            created_local_page = True
            target_page = self.browser_manager.new_page()

        try:
            logger.info(f"Navigating to Content Rewards Discover: {self.DISCOVER_URL}")
            target_page.goto(self.DISCOVER_URL, timeout=35000, wait_until="domcontentloaded")
            target_page.wait_for_timeout(2500)

            # Scroll passes to trigger any lazy-loaded cards
            for pass_idx in range(max_scroll_passes):
                target_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                target_page.wait_for_timeout(1500)

            html = target_page.content()
            cards = self.listing_extractor.extract_cards(html)
            logger.info(f"Successfully discovered {len(cards)} unique campaign cards.")
            return cards

        except Exception as e:
            logger.error(f"Error during campaign discovery: {e}")
            raise
        finally:
            if created_local_page and target_page:
                try:
                    target_page.close()
                except Exception:
                    pass

    def extract_campaign_by_url(
        self,
        campaign_url: str,
        page: Optional[Page] = None
    ) -> DiscoveredCampaignDetail:
        """
        Navigates to an individual campaign page and extracts full campaign details.
        """
        created_local_page = False
        target_page = page

        if target_page is None:
            created_local_page = True
            target_page = self.browser_manager.new_page()

        try:
            logger.info(f"Opening campaign detail page: {campaign_url}")
            target_page.goto(campaign_url, timeout=35000, wait_until="domcontentloaded")
            target_page.wait_for_timeout(2500)

            html = target_page.content()
            detail = self.detail_extractor.extract_detail(html, campaign_url)
            logger.info(f"Extracted campaign '{detail.title}' (ID: {detail.external_id})")
            return detail

        except Exception as e:
            logger.error(f"Error extracting campaign at {campaign_url}: {e}")
            raise
        finally:
            if created_local_page and target_page:
                try:
                    target_page.close()
                except Exception:
                    pass

