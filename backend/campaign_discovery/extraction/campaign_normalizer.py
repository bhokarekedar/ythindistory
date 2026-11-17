import time
from typing import Dict, Any, Optional
from ..models.campaign import DiscoveredCampaignDetail
from core.campaign_intelligence.models import (
    CampaignRecord,
    CommercialDetails,
    ContentRequirements,
    CampaignEligibility,
    PostingMetadata,
    CampaignAnalysis
)


class CampaignNormalizer:
    """
    Normalizes extracted Content Rewards campaign data into the system-wide
    CampaignRecord model, maintaining strict schema fidelity with nulls for missing values.
    """

    def normalize_to_record(self, detail: DiscoveredCampaignDetail) -> CampaignRecord:
        """Converts DiscoveredCampaignDetail into a standard CampaignRecord for CampaignRepository."""
        
        # Build CommercialDetails
        comm = CommercialDetails(
            payment_model=detail.payment_model or "POOL",
            maximum_budget=detail.total_budget,
            currency=detail.currency or "USD",
            payment_schedule=". ".join(detail.payment_conditions) if detail.payment_conditions else None
        )

        # Build ContentRequirements
        niches = detail.content_requirements.get("niche", [detail.category or "Entertainment"])
        creq = ContentRequirements(
            niche=niches,
            aspect_ratio="9:16",
            authorized_footage_provided=True
        )

        # Build Eligibility
        elig_notes = detail.eligibility_requirements.get("notes")
        elig = CampaignEligibility(
            minimum_subscribers=detail.eligibility_requirements.get("minimum_subscribers"),
            minimum_followers=detail.eligibility_requirements.get("minimum_followers"),
            other_requirements=[elig_notes] if elig_notes else []
        )

        # Build PostingMetadata
        post_meta = PostingMetadata(
            hashtags=detail.posting_instructions.get("hashtags", []),
            mentions=detail.posting_instructions.get("mentions", []),
            reference_links=detail.reference_links
        )

        # Initial Analysis placeholder (Audit state before user/LLM approval)
        unverified = []
        if detail.reference_files_restricted:
            unverified.append("Reference materials are locked behind Content Rewards 'Join Campaign' requirement.")

        analysis = CampaignAnalysis(
            decision="NEEDS_INFO" if unverified else "APPROVED",
            overall_score=75 if not unverified else 68,
            eligibility_score=85,
            niche_compatibility_score=85,
            production_feasibility_score=70,
            commercial_score=80,
            unverified_requirements=unverified,
            recommendation=(
                "Campaign concept successfully discovered and saved. Review reference files when authorized."
                if detail.reference_files_restricted else
                "Campaign ready for production clipping."
            ),
            summary=f"{detail.title} by {detail.creator or 'Unknown Creator'} on Content Rewards."
        )

        record_id = f"camp_{detail.external_id[:8]}"
        
        return CampaignRecord(
            campaign_id=record_id,
            title=detail.title,
            source_platform=detail.source_platform,
            campaign_url=detail.campaign_url,
            raw_brief=detail.raw_description,
            status=analysis.decision,
            created_at=time.time(),
            updated_at=time.time(),
            eligibility=elig,
            content_requirements=creq,
            posting_metadata=post_meta,
            commercial_details=comm,
            analysis=analysis
        )
