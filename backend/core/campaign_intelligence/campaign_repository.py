import os
import json
import hashlib
import time
from typing import List, Optional, Dict, Any
from .models import CampaignRecord, ChannelProfile


class CampaignRepository:
    """Persistent storage for ViralLoop campaigns and channel profile."""

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            # Anchor to backend/data relative to this file
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.data_dir = os.path.join(base_dir, "data")
        else:
            self.data_dir = data_dir

        os.makedirs(self.data_dir, exist_ok=True)
        self.campaigns_file = os.path.join(self.data_dir, "campaigns.json")
        self.profile_file = os.path.join(self.data_dir, "channel_profile.json")

    def _hash_brief(self, brief: str) -> str:
        """Normalized hash of brief text to quickly detect duplicate submissions."""
        normalized = "".join(brief.lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _read_all(self) -> Dict[str, Any]:
        if not os.path.exists(self.campaigns_file):
            return {}
        try:
            with open(self.campaigns_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CampaignRepository] Failed to read {self.campaigns_file}: {e}")
            return {}

    def _write_all(self, data: Dict[str, Any]) -> None:
        with open(self.campaigns_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save(self, campaign: CampaignRecord) -> CampaignRecord:
        """Saves or updates a campaign record."""
        data = self._read_all()
        campaign.updated_at = time.time()
        data[campaign.campaign_id] = campaign.model_dump()
        self._write_all(data)
        return campaign

    def get(self, campaign_id: str) -> Optional[CampaignRecord]:
        data = self._read_all()
        raw = data.get(campaign_id)
        if raw:
            return CampaignRecord(**raw)
        return None

    def find_duplicate(
        self,
        raw_brief: str,
        title: Optional[str] = None,
        campaign_url: Optional[str] = None
    ) -> Optional[CampaignRecord]:
        """
        Checks if a campaign has already been analyzed by comparing brief hash,
        exact URL, or identical title.
        """
        data = self._read_all()
        incoming_hash = self._hash_brief(raw_brief)
        norm_title = (title or "").strip().lower()
        norm_url = (campaign_url or "").strip().lower()

        for c_id, c_data in data.items():
            existing_brief = c_data.get("raw_brief", "")
            if self._hash_brief(existing_brief) == incoming_hash:
                return CampaignRecord(**c_data)

            if norm_url and c_data.get("campaign_url") and c_data.get("campaign_url", "").strip().lower() == norm_url:
                return CampaignRecord(**c_data)

            if norm_title and c_data.get("title", "").strip().lower() == norm_title and len(norm_title) > 6:
                return CampaignRecord(**c_data)

        return None

    def list(
        self,
        status: Optional[str] = None,
        platform: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[CampaignRecord]:
        """Lists campaigns with optional filters."""
        data = self._read_all()
        results: List[CampaignRecord] = []

        status_filter = status.upper() if status else None
        platform_filter = platform.lower() if platform else None
        search_term = search.lower() if search else None

        for c_data in data.values():
            rec = CampaignRecord(**c_data)

            # Status filter
            if status_filter and status_filter != "ALL":
                if status_filter == "ARCHIVED":
                    if rec.status != "ARCHIVED":
                        continue
                else:
                    # Ignore archived unless specifically requested
                    if rec.status == "ARCHIVED" or rec.status != status_filter:
                        continue
            else:
                # Default view excludes archived
                if rec.status == "ARCHIVED" and status_filter != "ARCHIVED":
                    continue

            # Platform filter (Content Rewards, Vyro, Whop, etc.)
            if platform_filter and platform_filter != "all":
                if platform_filter not in rec.source_platform.lower():
                    continue

            # Search term
            if search_term:
                searchable = f"{rec.title} {rec.raw_brief} {rec.source_platform}".lower()
                if search_term not in searchable:
                    continue

            results.append(rec)

        # Sort descending by updated_at
        results.sort(key=lambda x: x.updated_at, reverse=True)
        return results

    def update_verdict(
        self,
        campaign_id: str,
        verdict: str,
        reason: Optional[str] = None
    ) -> Optional[CampaignRecord]:
        """Applies manual human editorial verdict override."""
        rec = self.get(campaign_id)
        if not rec:
            return None

        verdict_upper = verdict.strip().upper()
        if verdict_upper in ["APPROVED", "REJECTED"]:
            rec.status = verdict_upper
            rec.manual_override = True
            rec.manual_verdict = verdict_upper
            rec.manual_override_reason = reason or f"Manually set to {verdict_upper} by channel editor."
        elif verdict_upper == "RESET":
            # Revert to original AI decision
            rec.status = rec.analysis.decision
            rec.manual_override = False
            rec.manual_verdict = None
            rec.manual_override_reason = None

        return self.save(rec)

    def update_metadata(self, campaign_id: str, posting_metadata: Dict[str, Any]) -> Optional[CampaignRecord]:
        """Updates editable posting metadata for publishing prep."""
        rec = self.get(campaign_id)
        if not rec:
            return None

        current = rec.posting_metadata.model_dump()
        current.update(posting_metadata)
        from .models import PostingMetadata
        rec.posting_metadata = PostingMetadata(**current)
        return self.save(rec)

    def archive(self, campaign_id: str) -> bool:
        """Sets campaign status to ARCHIVED."""
        rec = self.get(campaign_id)
        if not rec:
            return False
        rec.status = "ARCHIVED"
        self.save(rec)
        return True

    def get_channel_profile(self) -> ChannelProfile:
        """Loads known ViralLoop profile or initializes default."""
        if os.path.exists(self.profile_file):
            try:
                with open(self.profile_file, "r", encoding="utf-8") as f:
                    return ChannelProfile(**json.load(f))
            except Exception as e:
                print(f"[CampaignRepository] Failed to read {self.profile_file}: {e}")

        default_profile = ChannelProfile()
        self.save_channel_profile(default_profile)
        return default_profile

    def save_channel_profile(self, profile: ChannelProfile) -> ChannelProfile:
        profile.last_updated = time.time()
        with open(self.profile_file, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(), f, indent=2)
        return profile

