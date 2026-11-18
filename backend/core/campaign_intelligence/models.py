from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import time
import uuid


class ChannelProfile(BaseModel):
    """ViralLoop's known account and channel state."""
    channel_name: str = "ViralLoop"
    tagline: str = "The Best Moments. All in One Loop."
    channel_status: str = "NEW"  # NEW, GROWING, ESTABLISHED
    youtube_subscribers: int = 0
    instagram_followers: int = 0
    tiktok_followers: int = 0
    account_age_days: int = 1
    previous_viral_videos_count: int = 0
    historical_views_total: int = 0
    primary_language: str = "en"
    target_tier1: bool = True
    audience_geography: List[str] = Field(default_factory=lambda: ["US", "GB", "CA", "AU", "NZ"])
    tier1_audience_percentage: Optional[float] = 100.0
    face_camera_available: bool = False  # Faceless production workflow
    content_niches: List[str] = Field(
        default_factory=lambda: [
            "gaming", "streamers", "minecraft", "roblox", "fortnite",
            "mrbeast_challenges", "extreme_competitions", "unexpected_events",
            "crazy_experiments", "funny_moments", "viral_entertainment"
        ]
    )
    supported_aspect_ratios: List[str] = Field(default_factory=lambda: ["9:16"])
    captions_supported: bool = True
    ai_clip_detection_supported: bool = True
    last_updated: float = Field(default_factory=time.time)


class CampaignEligibility(BaseModel):
    """Eligibility criteria required by the campaign marketplace."""
    platforms_targeted: List[str] = Field(default_factory=lambda: ["youtube_shorts", "instagram_reels", "tiktok"])
    minimum_subscribers: Optional[int] = None
    minimum_followers: Optional[int] = None
    minimum_account_age_days: Optional[int] = None
    minimum_previous_views: Optional[int] = None
    viral_video_urls_required: bool = False
    required_viral_video_count: Optional[int] = None
    required_audience_countries: List[str] = Field(default_factory=list)
    minimum_tier1_audience_percentage: Optional[float] = None
    account_verification_required: bool = False
    all_eligibility_requirements: List[str] = Field(default_factory=list)


class ContentRequirements(BaseModel):
    """Content creation & formatting requirements."""
    niche: List[str] = Field(default_factory=list)
    allowed_source_urls: List[str] = Field(default_factory=list)
    authorized_footage_provided: bool = True
    original_footage_required: bool = False
    face_camera_required: bool = False
    voiceover_required: bool = False
    ai_content_allowed: Optional[bool] = True
    minimum_duration_seconds: Optional[int] = None
    maximum_duration_seconds: Optional[int] = None
    aspect_ratio: str = "9:16"
    captions_required: bool = False
    logo_required: bool = False
    creator_credit_required: bool = False
    other_requirements: List[str] = Field(default_factory=list)


class PostingMetadata(BaseModel):
    """Publishing instructions to be used by social uploaders."""
    platforms: List[str] = Field(default_factory=lambda: ["youtube_shorts", "instagram_reels", "tiktok"])
    caption_template: Optional[str] = None
    hashtags: List[str] = Field(default_factory=list)
    required_mentions: List[str] = Field(default_factory=list)
    cta: Optional[str] = None
    pinned_comment: Optional[str] = None
    required_disclosures: List[str] = Field(default_factory=list)
    required_title_format: Optional[str] = None
    posting_frequency_limit: Optional[str] = None
    submission_deadline_minutes: Optional[int] = None
    other_posting_instructions: List[str] = Field(default_factory=list)


class CommercialDetails(BaseModel):
    """Payout model, CPM, and budget limits."""
    payment_model: Optional[str] = "CPM"  # CPM, FIXED_PER_VIDEO, REVENUE_SHARE, PERFORMANCE
    cpm_min: Optional[float] = None
    cpm_max: Optional[float] = None
    minimum_payable_views: Optional[int] = None
    maximum_budget: Optional[float] = None
    maximum_payout_per_video: Optional[float] = None
    payment_schedule: Optional[str] = None
    currency: Optional[str] = "USD"


class CampaignAnalysis(BaseModel):
    """Multi-dimensional evaluation results and decision."""
    decision: str  # APPROVED, REJECTED, NEEDS_INFO
    overall_score: int  # 0 to 100
    eligibility_score: int  # 0 to 100
    niche_compatibility_score: int  # 0 to 100
    production_feasibility_score: int  # 0 to 100
    commercial_score: int  # 0 to 100
    mandatory_requirements: List[str] = Field(default_factory=list)
    satisfied_requirements: List[str] = Field(default_factory=list)
    failed_requirements: List[str] = Field(default_factory=list)
    unverified_requirements: List[str] = Field(default_factory=list)
    rejection_reasons: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    recommendation: str
    summary: str


class CampaignRecord(BaseModel):
    """Complete campaign entity stored in repository."""
    campaign_id: str = Field(default_factory=lambda: f"camp_{str(uuid.uuid4())[:8]}")
    title: str
    source_platform: str = "Content Rewards"  # Content Rewards, Whop, Vyro, Other
    campaign_url: Optional[str] = None
    raw_brief: str
    status: str = "NEEDS_INFO"  # APPROVED, REJECTED, NEEDS_INFO, ARCHIVED
    manual_override: bool = False
    manual_verdict: Optional[str] = None
    manual_override_reason: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    eligibility: CampaignEligibility = Field(default_factory=CampaignEligibility)
    content_requirements: ContentRequirements = Field(default_factory=ContentRequirements)
    posting_metadata: PostingMetadata = Field(default_factory=PostingMetadata)
    commercial_details: CommercialDetails = Field(default_factory=CommercialDetails)
    guidelines_metadata: Optional[Dict[str, Any]] = None
    analysis: CampaignAnalysis
