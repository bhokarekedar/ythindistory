import time
import logging
import threading
from typing import Dict, Any, List, Optional
from ..browser.browser_manager import BrowserManager
from ..browser.session_manager import SessionManager
from ..browser.content_rewards_browser import ContentRewardsBrowser
from ..extraction.campaign_normalizer import CampaignNormalizer
from ..models.campaign import DiscoveredCampaignDetail
from core.campaign_intelligence.campaign_repository import CampaignRepository
from core.campaign_intelligence.models import CampaignRecord

logger = logging.getLogger("CampaignDiscovery.DiscoveryService")


class CampaignDiscoveryService:
    """
    High-level orchestration service for discovering, extracting,
    normalizing, and persisting Content Rewards campaigns into ViralLoop.
    """

    _lock = threading.Lock()
    _is_running: bool = False
    _current_run_info: Dict[str, Any] = {}

    @classmethod
    def is_busy(cls) -> bool:
        return cls._is_running

    @classmethod
    def get_run_status(cls) -> Dict[str, Any]:
        return {
            "is_busy": cls._is_running,
            "current_run": dict(cls._current_run_info) if cls._is_running else None
        }

    def __init__(
        self,
        repository: Optional[CampaignRepository] = None,
        browser_manager: Optional[BrowserManager] = None
    ):
        self.repository = repository or CampaignRepository()
        self.browser_manager = browser_manager or BrowserManager()
        self.session_manager = SessionManager(self.browser_manager)
        self.browser = ContentRewardsBrowser(browser_manager=self.browser_manager)
        self.normalizer = CampaignNormalizer()

    def discover_and_sync(
        self,
        max_campaigns: int = 5,
        refresh_existing: bool = False
    ) -> Dict[str, Any]:
        """
        Executes a complete discovery run:
        1. Discovers all listing cards from Content Rewards discover page.
        2. Filters out duplicates already present in the CampaignRepository.
        3. Navigates to individual campaign pages up to `max_campaigns`.
        4. Extracts full campaign details and saves them to the repository.
        """
        if not self._lock.acquire(blocking=False):
            msg = "A campaign discovery run is already in progress. Concurrent runs are rejected to protect browser profile."
            logger.warning(msg)
            raise RuntimeError(msg)

        CampaignDiscoveryService._is_running = True
        CampaignDiscoveryService._current_run_info = {
            "started_at": time.time(),
            "max_campaigns": max_campaigns,
            "refresh_existing": refresh_existing
        }

        try:
            start_time = time.time()
            logger.info(f"Starting discovery sync (max_campaigns={max_campaigns}, refresh={refresh_existing})...")

            # Check existing campaigns in repository
            existing_records = self.repository.list(status="ALL")
            existing_urls = {r.campaign_url for r in existing_records if r.campaign_url}
            existing_ids = {r.campaign_id for r in existing_records}

            # 1. Discover listings
            cards = self.browser.discover_campaign_listings()
            discovered_count = len(cards)

            new_saved = 0
            skipped = 0
            failed = 0
            processed = 0
            saved_records: List[Dict[str, Any]] = []

            # 2. Process campaigns sequentially
            for card in cards:
                if processed >= max_campaigns:
                    break

                target_id = f"camp_{card.external_id[:8]}"
                is_duplicate = card.campaign_url in existing_urls or target_id in existing_ids

                if is_duplicate and not refresh_existing:
                    skipped += 1
                    continue

                processed += 1
                try:
                    # Open individual page and extract
                    detail = self.browser.extract_campaign_by_url(card.campaign_url)
                    
                    # Normalize and persist
                    record = self.normalizer.normalize_to_record(detail)
                    saved_record = self.repository.save(record)

                    existing_urls.add(card.campaign_url)
                    existing_ids.add(saved_record.campaign_id)
                    new_saved += 1

                    saved_records.append({
                        "campaign_id": saved_record.campaign_id,
                        "title": saved_record.title,
                        "url": saved_record.campaign_url,
                        "status": saved_record.status,
                        "payment_model": saved_record.commercial_details.payment_model,
                        "total_budget": saved_record.commercial_details.maximum_budget,
                        "restricted_materials": detail.reference_files_restricted
                    })

                except Exception as e:
                    logger.error(f"Failed to process campaign {card.campaign_url}: {e}")
                    failed += 1

            elapsed = round(time.time() - start_time, 2)
            logger.info(f"Sync complete in {elapsed}s: Discovered={discovered_count}, Processed={processed}, Saved={new_saved}, Skipped={skipped}, Failed={failed}")

            # Overall status: COMPLETED or PARTIAL_FAILURE
            overall_status = "COMPLETED"
            if failed > 0 and new_saved == 0:
                overall_status = "FAILED"
            elif failed > 0:
                overall_status = "PARTIAL_FAILURE"

            return {
                "status": overall_status,
                "elapsed_seconds": elapsed,
                "metrics": {
                    "discovered_total": discovered_count,
                    "processed_count": processed,
                    "new_saved_count": new_saved,
                    "duplicates_skipped": skipped,
                    "failed_count": failed
                },
                "saved_campaigns": saved_records
            }
        finally:
            CampaignDiscoveryService._is_running = False
            CampaignDiscoveryService._current_run_info = {}
            self._lock.release()

    def extract_and_save_single_url(self, campaign_url: str) -> Dict[str, Any]:
        """
        Directly navigates to a specific campaign URL, extracts details,
        normalizes, and saves to the repository.
        """
        logger.info(f"Extracting single campaign: {campaign_url}")
        detail = self.browser.extract_campaign_by_url(campaign_url)
        record = self.normalizer.normalize_to_record(detail)
        saved = self.repository.save(record)

        return {
            "status": "SUCCESS",
            "campaign_id": saved.campaign_id,
            "title": saved.title,
            "url": saved.campaign_url,
            "detail": detail.model_dump(),
            "record": saved.model_dump()
        }

    def close(self):
        """Closes underlying browser resources."""
        self.browser_manager.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
