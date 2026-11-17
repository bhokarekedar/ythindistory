import os
import sys
import unittest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from campaign_discovery import (
    BrowserManager,
    SessionManager,
    ContentRewardsBrowser,
    CampaignListingExtractor,
    CampaignDetailExtractor,
    CampaignNormalizer,
    CampaignDiscoveryService
)
from core.campaign_intelligence import CampaignRepository


class TestModularCampaignDiscovery(unittest.TestCase):

    def setUp(self):
        self.repo = CampaignRepository()

    def test_01_browser_manager_lifecycle(self):
        """Verify persistent Chromium launch, directory creation, and clean shutdown."""
        mgr = BrowserManager(headless=True)
        ctx = mgr.initialize()
        self.assertIsNotNone(ctx)
        self.assertTrue(os.path.exists(mgr.profile_dir))
        
        page = mgr.new_page()
        page.goto("https://example.com")
        self.assertIn("Example Domain", page.title())
        page.close()
        mgr.close()
        self.assertIsNone(mgr._context)

    def test_02_session_manager_unauthenticated_status(self):
        """Verify session check detects unauthenticated state on public discover view."""
        mgr = BrowserManager(headless=True)
        try:
            sess = SessionManager(mgr)
            status = sess.check_auth_status()
            self.assertIn("status", status)
            self.assertEqual(status["status"], "UNAUTHENTICATED")
            self.assertFalse(status["is_authenticated"])
        finally:
            mgr.close()

    def test_03_campaign_listing_extraction(self):
        """Verify discovery page extracts unique campaign cards without duplicates."""
        browser = ContentRewardsBrowser()
        try:
            cards = browser.discover_campaign_listings(max_scroll_passes=1)
            self.assertGreaterEqual(len(cards), 50)
            
            # Verify deduplication
            ext_ids = [c.external_id for c in cards]
            self.assertEqual(len(ext_ids), len(set(ext_ids)), "Duplicate external IDs found in listings!")
            
            first = cards[0]
            self.assertTrue(first.campaign_url.startswith("https://contentrewards.com/c/campaigns/"))
            self.assertIsNotNone(first.external_id)
        finally:
            browser.browser_manager.close()

    def test_04_individual_campaign_extraction_jasontheween(self):
        """Test extraction of the real JasonTheWeen campaign page."""
        target_url = "https://contentrewards.com/c/campaigns/0b178e3c-fbd3-4294-8ded-394e3da9c62f"
        browser = ContentRewardsBrowser()
        try:
            detail = browser.extract_campaign_by_url(target_url)
            self.assertEqual(detail.external_id, "0b178e3c-fbd3-4294-8ded-394e3da9c62f")
            self.assertIn("Jason", detail.title)
            self.assertEqual(detail.category, "Entertainment")
            self.assertEqual(detail.payment_model, "POOL")
            self.assertEqual(detail.total_budget, 9000.0)
            
            # Verify reference material restriction
            self.assertTrue(detail.reference_files_restricted, "Restricted reference materials must be detected!")
            self.assertEqual(detail.reference_files_count, 4)
            
            # Verify social channels
            has_yt = any("youtube.com" in s for s in detail.reference_links)
            has_twitch = any("twitch.tv" in s for s in detail.reference_links)
            self.assertTrue(has_yt or has_twitch, "Expected creator social links in reference links!")

            # Verify Normalizer to CampaignRecord
            normalizer = CampaignNormalizer()
            record = normalizer.normalize_to_record(detail)
            self.assertEqual(record.campaign_id, "camp_0b178e3c")
            self.assertEqual(record.commercial_details.maximum_budget, 9000.0)
            
            # Verify persistence into CampaignRepository
            saved = self.repo.save(record)
            reloaded = self.repo.get(saved.campaign_id)
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.title, detail.title)
            self.assertEqual(reloaded.commercial_details.payment_model, "POOL")
        finally:
            browser.browser_manager.close()

    def test_05_discovery_service_sync_and_deduplication(self):
        """Verify discovery service sync skips duplicates and respects limits."""
        with CampaignDiscoveryService(repository=self.repo) as service:
            # First pass: limit to 2 campaigns
            result = service.discover_and_sync(max_campaigns=2, refresh_existing=False)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertGreaterEqual(result["metrics"]["discovered_total"], 50)
            self.assertLessEqual(result["metrics"]["processed_count"], 2)
            
            # Second pass: identical limit with refresh_existing=False should skip
            result_skip = service.discover_and_sync(max_campaigns=2, refresh_existing=False)
            self.assertGreaterEqual(result_skip["metrics"]["duplicates_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
