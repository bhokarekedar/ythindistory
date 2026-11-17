import os
import json
import re
import time
from typing import Dict, Any, Optional, List, Tuple
from groq import Groq
from dotenv import load_dotenv

from .models import (
    ChannelProfile,
    CampaignRecord,
    CampaignEligibility,
    ContentRequirements,
    PostingMetadata,
    CommercialDetails,
    CampaignAnalysis
)
from ..api_keys import ApiKeyManager

# Ensure .env is loaded
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()


class CampaignAnalyzer:
    """
    Intelligent analysis engine that inspects marketplace campaign briefs,
    evaluates eligibility against ViralLoop's profile, assesses niche & feasibility,
    and produces audit-proof approval decisions and structured posting metadata.
    """

    def __init__(self, model: str = "qwen/qwen3.8-27b"):
        self.model = model
        self.key_manager = ApiKeyManager()

    def _get_groq_client(self) -> Optional[Groq]:
        api_key = self.key_manager.get_next_key() or os.environ.get("GROQ_API_KEY")
        if not api_key:
            return None
        return Groq(api_key=api_key)

    def analyze_campaign(
        self,
        raw_brief: str,
        title: Optional[str] = None,
        source_platform: Optional[str] = None,
        campaign_url: Optional[str] = None,
        channel_profile: Optional[ChannelProfile] = None
    ) -> CampaignRecord:
        """
        Full end-to-end pipeline:
        1. Extract structured entities from unstructured brief using Groq LLM (or fallback).
        2. Execute deterministic audit checks against ChannelProfile.
        3. Formulate final decision (APPROVED, REJECTED, NEEDS_INFO) with human-readable rationale.
        4. Assemble CampaignRecord.
        """
        profile = channel_profile or ChannelProfile()
        brief_clean = raw_brief.strip()
        detected_platform = source_platform or self._detect_platform(brief_clean, campaign_url)

        # Step 1: LLM Extraction
        extracted_data = self._llm_extract(brief_clean, title, detected_platform)

        # Step 2: Deterministic Rule-Based Verification & Scoring
        eligibility, content_reqs, posting_meta, commercial, analysis = self._evaluate_campaign(
            extracted_data=extracted_data,
            raw_brief=brief_clean,
            profile=profile
        )

        final_title = title or extracted_data.get("title") or self._generate_fallback_title(brief_clean)

        return CampaignRecord(
            title=final_title,
            source_platform=detected_platform,
            campaign_url=campaign_url or extracted_data.get("campaign_url"),
            raw_brief=brief_clean,
            status=analysis.decision,
            eligibility=eligibility,
            content_requirements=content_reqs,
            posting_metadata=posting_meta,
            commercial_details=commercial,
            analysis=analysis
        )

    def _detect_platform(self, brief: str, url: Optional[str] = None) -> str:
        text = f"{brief} {url or ''}".lower()
        if "contentrewards" in text or "content rewards" in text:
            return "Content Rewards"
        elif "whop" in text:
            return "Whop"
        elif "vyro" in text:
            return "Vyro"
        return "Marketplace"

    def _generate_fallback_title(self, brief: str) -> str:
        first_line = brief.strip().split("\n")[0][:60]
        return first_line if len(first_line) > 5 else "Untitled Creator Campaign"

    def _llm_extract(self, brief: str, title: Optional[str], platform: str) -> Dict[str, Any]:
        """Calls Groq LLM with structured JSON extraction prompt."""
        system_prompt = """You are a Senior Campaign Intelligence Architect for ViralLoop, a short-form clipping channel.
Your task is to parse an unstructured campaign brief from creator monetization platforms (Content Rewards, Whop, Vyro) into a strictly validated JSON structure.

CRITICAL RULES:
1. Extract ONLY facts explicitly stated in the brief.
2. DO NOT invent or hallucinate hashtags, mentions, CTAs, subscriber thresholds, or payout rates.
3. If an item is not mentioned, use null for scalars and empty array [] for lists.
4. Distinguish between MANDATORY requirements vs OPTIONAL suggestions.

JSON SCHEMA TO RETURN:
{
  "title": "Clean concise campaign title",
  "campaign_url": null or string,
  "eligibility": {
    "platforms_targeted": ["youtube_shorts", "instagram_reels", "tiktok"],
    "minimum_subscribers": null or integer,
    "minimum_followers": null or integer,
    "minimum_account_age_days": null or integer,
    "minimum_previous_views": null or integer,
    "viral_video_urls_required": boolean,
    "required_viral_video_count": null or integer,
    "required_audience_countries": [],
    "minimum_tier1_audience_percentage": null or float,
    "account_verification_required": boolean,
    "all_eligibility_requirements": ["list of explicit eligibility rules"]
  },
  "content_requirements": {
    "niche": ["gaming", "minecraft", "challenges", etc.],
    "allowed_source_urls": [],
    "authorized_footage_provided": boolean,
    "original_footage_required": boolean,
    "face_camera_required": boolean,
    "voiceover_required": boolean,
    "ai_content_allowed": null or boolean,
    "minimum_duration_seconds": null or integer,
    "maximum_duration_seconds": null or integer,
    "aspect_ratio": "9:16",
    "captions_required": boolean,
    "logo_required": boolean,
    "creator_credit_required": boolean,
    "other_requirements": []
  },
  "posting_metadata": {
    "platforms": ["youtube_shorts", "instagram_reels", "tiktok"],
    "caption_template": null or string,
    "hashtags": ["#explicitHashtagsFromBrief"],
    "required_mentions": ["@creatorMention"],
    "cta": null or string,
    "pinned_comment": null or string,
    "required_disclosures": ["#ad", "#sponsored" if mentioned],
    "required_title_format": null or string,
    "posting_frequency_limit": null or string,
    "submission_deadline_minutes": null or integer,
    "other_posting_instructions": []
  },
  "commercial_details": {
    "payment_model": "CPM",
    "cpm_min": null or float,
    "cpm_max": null or float,
    "minimum_payable_views": null or integer,
    "maximum_budget": null or float,
    "maximum_payout_per_video": null or float,
    "payment_schedule": null or string,
    "currency": "USD"
  },
  "raw_observations": {
    "niche_summary": "1 sentence on content type",
    "potential_blockers": ["list any disqualifying demands"],
    "missing_critical_info": ["e.g. footage source link not specified"]
  }
}"""

        user_prompt = f"""CAMPAIGN SOURCE: {platform}
PROVIDED TITLE: {title or 'N/A'}

CAMPAIGN BRIEF TEXT TO PARSE:
{brief[:8000]}"""

        for attempt in range(2):
            try:
                client = self._get_groq_client()
                if not client:
                    break

                completion = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=850
                )
                raw_json = completion.choices[0].message.content.strip()
                if raw_json.startswith("```"):
                    raw_json = raw_json.split("\n", 1)[1].rsplit("```", 1)[0]
                return json.loads(raw_json)
            except Exception as e:
                print(f"[CampaignAnalyzer] LLM attempt {attempt + 1} error: {e}")
                time.sleep(1)

        # Fallback to deterministic regex extraction
        return self._rule_based_extraction(brief, title, platform)

    def _rule_based_extraction(self, brief: str, title: Optional[str], platform: str) -> Dict[str, Any]:
        """Deterministic heuristic extraction if LLM is unavailable."""
        text_lower = brief.lower()

        # Check subscriber requirements
        sub_match = re.search(r'(\d+[\d,]*)\+?\s*(?:subscribers|subs)', text_lower)
        min_subs = int(sub_match.group(1).replace(",", "")) if sub_match else None

        # Check follower requirements
        fol_match = re.search(r'(\d+[\d,]*)\+?\s*(?:followers)', text_lower)
        min_fol = int(fol_match.group(1).replace(",", "")) if fol_match else None

        # Viral links required?
        viral_req = bool(re.search(r'previous\s+viral|submit\s+viral\s+video|proof\s+of\s+views', text_lower))

        # Face cam required?
        face_cam = bool(re.search(r'face\s*cam|on\s*camera|show\s+your\s+face|film\s+yourself', text_lower))

        # Original filming required?
        original_film = bool(re.search(r'original\s+footage|film\s+original|record\s+yourself', text_lower))

        # Hashtags
        hashtags = list(set(re.findall(r'#\w+', brief)))

        # Mentions
        mentions = list(set(re.findall(r'@\w+', brief)))

        # CPM / Payout
        cpm_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(?:cpm|\/\s*1k|\/\s*1000)', text_lower)
        cpm_val = float(cpm_match.group(1)) if cpm_match else None

        # Niches
        niches = []
        for n in ["gaming", "minecraft", "roblox", "fortnite", "challenge", "streamer", "mrbeast", "tech", "entertainment"]:
            if n in text_lower:
                niches.append(n)

        return {
            "title": title or self._generate_fallback_title(brief),
            "campaign_url": None,
            "eligibility": {
                "platforms_targeted": ["youtube_shorts", "instagram_reels", "tiktok"],
                "minimum_subscribers": min_subs,
                "minimum_followers": min_fol,
                "minimum_account_age_days": None,
                "minimum_previous_views": None,
                "viral_video_urls_required": viral_req,
                "required_viral_video_count": 3 if viral_req else None,
                "required_audience_countries": [],
                "minimum_tier1_audience_percentage": None,
                "account_verification_required": False,
                "all_eligibility_requirements": []
            },
            "content_requirements": {
                "niche": niches or ["entertainment"],
                "allowed_source_urls": [],
                "authorized_footage_provided": True,
                "original_footage_required": original_film,
                "face_camera_required": face_cam,
                "voiceover_required": False,
                "ai_content_allowed": True,
                "minimum_duration_seconds": 15,
                "maximum_duration_seconds": 90,
                "aspect_ratio": "9:16",
                "captions_required": True,
                "logo_required": False,
                "creator_credit_required": False,
                "other_requirements": []
            },
            "posting_metadata": {
                "platforms": ["youtube_shorts", "instagram_reels", "tiktok"],
                "caption_template": None,
                "hashtags": hashtags,
                "required_mentions": mentions,
                "cta": None,
                "pinned_comment": None,
                "required_disclosures": [],
                "required_title_format": None,
                "posting_frequency_limit": None,
                "submission_deadline_minutes": None,
                "other_posting_instructions": []
            },
            "commercial_details": {
                "payment_model": "CPM",
                "cpm_min": cpm_val,
                "cpm_max": cpm_val,
                "minimum_payable_views": None,
                "maximum_budget": None,
                "maximum_payout_per_video": None,
                "payment_schedule": None,
                "currency": "USD"
            },
            "raw_observations": {
                "niche_summary": "Extracted via rule-based parser.",
                "potential_blockers": [],
                "missing_critical_info": []
            }
        }

    def _evaluate_campaign(
        self,
        extracted_data: Dict[str, Any],
        raw_brief: str,
        profile: ChannelProfile
    ) -> Tuple[CampaignEligibility, ContentRequirements, PostingMetadata, CommercialDetails, CampaignAnalysis]:
        """
        Executes strict audit comparing campaign demands against known ViralLoop capabilities.
        Generates 4 dimension scores, checklists, reasons, risks, and the final decision.
        """
        el_raw = extracted_data.get("eligibility", {})
        cr_raw = extracted_data.get("content_requirements", {})
        pm_raw = extracted_data.get("posting_metadata", {})
        cd_raw = extracted_data.get("commercial_details", {})
        if not cd_raw.get("currency"):
            cd_raw["currency"] = "USD"
        obs_raw = extracted_data.get("raw_observations", {})

        eligibility = CampaignEligibility(**el_raw)
        content_reqs = ContentRequirements(**cr_raw)
        posting_meta = PostingMetadata(**pm_raw)
        commercial = CommercialDetails(**cd_raw)

        mandatory_reqs: List[str] = []
        satisfied_reqs: List[str] = []
        failed_reqs: List[str] = []
        unverified_reqs: List[str] = []
        rejection_reasons: List[str] = []
        risks: List[str] = []
        missing_info: List[str] = []

        # -------------------------------------------------------------
        # DIMENSION 1: CHANNEL ELIGIBILITY
        # -------------------------------------------------------------
        # Check minimum subscribers
        if eligibility.minimum_subscribers is not None and eligibility.minimum_subscribers > 0:
            mandatory_reqs.append(f"Requires at least {eligibility.minimum_subscribers:,} YouTube subscribers.")
            if profile.youtube_subscribers < eligibility.minimum_subscribers:
                msg = f"Campaign requires {eligibility.minimum_subscribers:,} subscribers, but ViralLoop is a NEW channel with {profile.youtube_subscribers} subscribers."
                failed_reqs.append(msg)
                rejection_reasons.append(msg)
            else:
                satisfied_reqs.append(f"Subscribers requirement satisfied ({profile.youtube_subscribers:,} >= {eligibility.minimum_subscribers:,}).")

        # Check minimum followers
        if eligibility.minimum_followers is not None and eligibility.minimum_followers > 0:
            mandatory_reqs.append(f"Requires at least {eligibility.minimum_followers:,} social media followers.")
            max_followers = max(profile.instagram_followers, profile.tiktok_followers)
            if max_followers < eligibility.minimum_followers:
                msg = f"Campaign requires {eligibility.minimum_followers:,} followers, but ViralLoop currently has {max_followers} followers."
                failed_reqs.append(msg)
                rejection_reasons.append(msg)
            else:
                satisfied_reqs.append(f"Follower requirement satisfied ({max_followers:,} >= {eligibility.minimum_followers:,}).")

        # Check viral video URLs requirement
        if eligibility.viral_video_urls_required:
            count = eligibility.required_viral_video_count or 1
            mandatory_reqs.append(f"Requires submission of {count} previous viral video URLs for account qualification.")
            if profile.previous_viral_videos_count < count:
                msg = f"Campaign requires {count} previous viral video URLs, but ViralLoop currently has 0 qualifying historical videos."
                failed_reqs.append(msg)
                rejection_reasons.append(msg)
            else:
                satisfied_reqs.append(f"Viral video portfolio satisfied ({profile.previous_viral_videos_count} links available).")

        # Check account age
        if eligibility.minimum_account_age_days is not None and eligibility.minimum_account_age_days > 0:
            mandatory_reqs.append(f"Requires minimum account age of {eligibility.minimum_account_age_days} days.")
            if profile.account_age_days < eligibility.minimum_account_age_days:
                msg = f"Campaign requires {eligibility.minimum_account_age_days} days account age (ViralLoop is {profile.account_age_days} days old)."
                failed_reqs.append(msg)
                rejection_reasons.append(msg)
            else:
                satisfied_reqs.append(f"Account age requirement met ({profile.account_age_days} days).")

        # Check Tier 1 audience / country restrictions
        if eligibility.minimum_tier1_audience_percentage is not None and eligibility.minimum_tier1_audience_percentage > 0:
            mandatory_reqs.append(f"Requires at least {eligibility.minimum_tier1_audience_percentage}% Tier 1 audience.")
            if profile.tier1_audience_percentage is None:
                msg = f"Requires {eligibility.minimum_tier1_audience_percentage}% Tier 1 audience; ViralLoop audience demographics are currently unknown."
                unverified_reqs.append(msg)
                missing_info.append("Verified audience analytics / country demographics")
            elif profile.tier1_audience_percentage < eligibility.minimum_tier1_audience_percentage:
                msg = f"Tier 1 audience percentage ({profile.tier1_audience_percentage}%) is below required {eligibility.minimum_tier1_audience_percentage}%."
                failed_reqs.append(msg)
                rejection_reasons.append(msg)
            else:
                satisfied_reqs.append(f"Tier 1 audience requirement met ({profile.tier1_audience_percentage}%).")

        if eligibility.required_audience_countries:
            mandatory_reqs.append(f"Requires audience from: {', '.join(eligibility.required_audience_countries)}")
            if not profile.audience_geography:
                msg = f"Requires audience from {', '.join(eligibility.required_audience_countries)}; channel audience breakdown is currently unknown."
                unverified_reqs.append(msg)
                missing_info.append("Audience country verification")
            elif not any(c.lower() in [g.lower() for g in profile.audience_geography] for c in eligibility.required_audience_countries):
                msg = f"Channel geography does not match required countries: {', '.join(eligibility.required_audience_countries)}"
                failed_reqs.append(msg)
                rejection_reasons.append(msg)

        # Eligibility Score calculation
        if failed_reqs:
            eligibility_score = 15
        elif unverified_reqs:
            eligibility_score = 55
        else:
            eligibility_score = 95
            satisfied_reqs.append("No restrictive subscriber, follower, or portfolio barriers.")

        # -------------------------------------------------------------
        # DIMENSION 2: CONTENT NICHE COMPATIBILITY
        # -------------------------------------------------------------
        niche_score = 50
        niche_list = [n.lower() for n in content_reqs.niche]
        brief_lower = raw_brief.lower()

        # High-compatibility keywords
        high_fit = [
            "gaming", "streamer", "minecraft", "roblox", "fortnite",
            "mrbeast", "challenge", "experiment", "competition", "funny",
            "entertainment", "reaction", "creator highlight", "esports"
        ]
        # Medium-fit keywords
        med_fit = ["tech", "ai", "internet story", "demonstration", "sports highlight", "gadget"]
        # Incompatible / Low-fit keywords
        low_fit = [
            "beauty", "cosmetics", "skincare", "fashion", "crypto trading",
            "forex", "loan", "finance app", "insurance", "weight loss",
            "diet recipe", "lifestyle vlog", "relationship advice", "motivational"
        ]

        high_matches = [k for k in high_fit if any(k in n for n in niche_list) or k in brief_lower]
        med_matches = [k for k in med_fit if any(k in n for n in niche_list) or k in brief_lower]
        low_matches = [k for k in low_fit if any(k in n for n in niche_list) or k in brief_lower]

        if low_matches and not high_matches:
            niche_score = 20
            rejection_reasons.append(f"Content niche ({', '.join(low_matches)}) is incompatible with ViralLoop's gaming and challenge clipping strategy.")
        elif high_matches:
            niche_score = min(98, 80 + (len(high_matches) * 5))
            satisfied_reqs.append(f"Niche aligns strongly with ViralLoop audience: {', '.join(high_matches[:4])}.")
        elif med_matches:
            niche_score = 65
            satisfied_reqs.append(f"Moderate niche fit: {', '.join(med_matches[:3])}.")
        else:
            niche_score = 55
            risks.append("Generic or broad entertainment niche; monitor viewer retention.")

        # -------------------------------------------------------------
        # DIMENSION 3: CONTENT PRODUCTION FEASIBILITY
        # -------------------------------------------------------------
        feasibility_score = 85

        # Face camera requirement
        if content_reqs.face_camera_required:
            mandatory_reqs.append("Requires face-camera footage of creator.")
            msg = "Campaign requires live on-camera creator presence, which conflicts with ViralLoop's faceless short-form production model."
            failed_reqs.append(msg)
            rejection_reasons.append(msg)
            feasibility_score -= 50

        # Original filming requirement
        if content_reqs.original_footage_required:
            mandatory_reqs.append("Requires filming original physical footage.")
            msg = "Campaign requires filming original physical footage rather than clipping creator content."
            failed_reqs.append(msg)
            rejection_reasons.append(msg)
            feasibility_score -= 40

        # Source footage authorization
        if not content_reqs.authorized_footage_provided:
            msg = "Campaign does not explicitly provide authorized footage or usage permissions."
            unverified_reqs.append(msg)
            missing_info.append("Authorized creator footage links or usage license")
            feasibility_score -= 25

        # AI prohibited
        if content_reqs.ai_content_allowed is False:
            risks.append("Campaign restricts AI-assisted content tools; ensure human-in-the-loop review for all clips.")
            feasibility_score -= 10

        # 9:16 Vertical support
        if content_reqs.aspect_ratio in ["9:16", "vertical"]:
            satisfied_reqs.append("Vertical 9:16 format perfectly matches AI Smart Crop engine.")
        else:
            risks.append(f"Requested aspect ratio '{content_reqs.aspect_ratio}' differs from standard 9:16 shorts.")

        feasibility_score = max(10, min(100, feasibility_score))

        # -------------------------------------------------------------
        # DIMENSION 4: COMMERCIAL ATTRACTIVENESS
        # -------------------------------------------------------------
        commercial_score = 60
        if commercial.cpm_max:
            if commercial.cpm_max >= 5.0:
                commercial_score = 95
            elif commercial.cpm_max >= 2.0:
                commercial_score = 80
            elif commercial.cpm_max >= 0.80:
                commercial_score = 65
            else:
                commercial_score = 45
        elif commercial.payment_model == "FIXED_PER_VIDEO":
            commercial_score = 75

        # -------------------------------------------------------------
        # FINAL DECISION DETERMINATION
        # -------------------------------------------------------------
        if failed_reqs or niche_score < 40 or feasibility_score < 45:
            decision = "REJECTED"
            overall_score = min(48, int((eligibility_score * 0.4) + (niche_score * 0.3) + (feasibility_score * 0.3)))
            recommendation = (
                f"REJECT: Disqualifying conditions detected ({len(failed_reqs)} failed criteria). "
                f"Revisit when channel statistics meet the mandatory criteria or when suitable footage is provided."
            )
        elif unverified_reqs or not content_reqs.authorized_footage_provided:
            decision = "NEEDS_INFO"
            overall_score = int(
                (eligibility_score * 0.35) +
                (niche_score * 0.25) +
                (feasibility_score * 0.25) +
                (commercial_score * 0.15)
            )
            recommendation = (
                f"HOLD (NEEDS INFO): The campaign concept is promising, but {len(unverified_reqs)} requirement(s) cannot be confirmed "
                f"without additional channel analytics or explicit footage permissions."
            )
        else:
            decision = "APPROVED"
            overall_score = int(
                (eligibility_score * 0.35) +
                (niche_score * 0.25) +
                (feasibility_score * 0.25) +
                (commercial_score * 0.15)
            )
            overall_score = max(75, min(98, overall_score))
            recommendation = (
                "APPROVE: Strong niche alignment with gaming/challenge strategy, zero disqualifying barriers, "
                "and production requirements fully achievable with ViralLoop's faceless 9:16 workflow."
            )

        # Build clean executive summary
        summary = (
            f"Campaign evaluated for {profile.channel_name}. "
            f"Verdict: {decision} (Compatibility Score: {overall_score}/100). "
            f"Niche Fit: {niche_score}%, Production Feasibility: {feasibility_score}%, Eligibility: {eligibility_score}%."
        )

        analysis = CampaignAnalysis(
            decision=decision,
            overall_score=overall_score,
            eligibility_score=eligibility_score,
            niche_compatibility_score=niche_score,
            production_feasibility_score=feasibility_score,
            commercial_score=commercial_score,
            mandatory_requirements=mandatory_reqs,
            satisfied_requirements=satisfied_reqs,
            failed_requirements=failed_reqs,
            unverified_requirements=unverified_reqs,
            rejection_reasons=rejection_reasons,
            risks=risks + obs_raw.get("potential_blockers", []),
            missing_information=missing_info + obs_raw.get("missing_critical_info", []),
            recommendation=recommendation,
            summary=summary
        )

        return eligibility, content_reqs, posting_meta, commercial, analysis
