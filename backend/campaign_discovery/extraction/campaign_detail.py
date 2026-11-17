import re
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from ..models.campaign import DiscoveredCampaignDetail, ExtractionReport


class CampaignDetailExtractor:
    """
    Extracts complete campaign information from individual Content Rewards campaign pages.
    Parses titles, creators, payments, platforms, eligibility, reference materials, and raw text.
    Correctly flags restricted resources without attempting to bypass join barriers.
    """

    UUID_REGEX = re.compile(r'/c/campaigns/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', re.I)

    def extract_detail(self, html: str, url: str) -> DiscoveredCampaignDetail:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ")
        normalized_text = " ".join(text.split())

        warnings: List[str] = []
        missing_sections: List[str] = []

        # 1. External ID
        uuid_match = self.UUID_REGEX.search(url)
        ext_id = uuid_match.group(1).lower() if uuid_match else "unknown_id"

        # 2. Title & Creator
        h1 = soup.find("h1")
        title = h1.get_text().strip() if h1 else None
        if not title:
            # Fallback to page title
            if soup.title and soup.title.string:
                title = soup.title.string.split("|")[0].split("by")[0].strip()
            else:
                title = f"Content Rewards Campaign {ext_id[:8]}"
                warnings.append("H1 title element not found; used title fallback.")

        # Creator / Organization
        creator = None
        # On Content Rewards, creator appears above H1 or in "More from <Creator>"
        creator_match = re.search(r'More from\s+([A-Za-z0-9_\-\s]+?)(?:\d+\s+campaigns|View profile)', normalized_text, re.I)
        if creator_match:
            creator = creator_match.group(1).strip()
        else:
            # Try finding creator before H1 in navigation
            back_match = re.search(r'Back\s+(?:Join Campaign\s+)?([A-Za-z0-9_\-]+)\s+\$', normalized_text)
            if back_match:
                creator = back_match.group(1).strip()

        # Category
        category = None
        for cat in ["Gaming", "Entertainment", "Comedy", "Sports", "Challenge", "Music", "Tech", "Lifestyle"]:
            if re.search(rf'\b{cat}\b', normalized_text, re.I):
                category = cat
                break

        # Status
        campaign_status = "ACTIVE"
        if "accepting clips" in normalized_text.lower():
            campaign_status = "ACTIVE"
        elif "ended" in normalized_text.lower() or "closed" in normalized_text.lower():
            campaign_status = "CLOSED"

        # 3. Payment Information
        payment_model = None
        total_budget = None
        rate = None
        payment_conditions = []

        if "pool" in normalized_text.lower():
            payment_model = "POOL"
        elif "cpm" in normalized_text.lower():
            payment_model = "CPM"
        elif "fixed" in normalized_text.lower():
            payment_model = "FIXED"

        # Extract dollar amounts for budget
        budget_match = re.search(r'\$([\d,]+(?:\.\d{2})?)', normalized_text)
        if budget_match:
            try:
                num_str = budget_match.group(1).replace(",", "")
                total_budget = float(num_str)
            except Exception:
                pass

        if "split by views" in normalized_text.lower():
            payment_conditions.append("Split by Views")
        if "when the pool ends" in normalized_text.lower():
            payment_conditions.append("Paid when the pool ends")

        if not payment_model:
            missing_sections.append("payment_model")
            warnings.append("Payment model could not be unambiguously determined.")

        # 4. Social & Reference Links
        social_links: List[str] = []
        # Find explicit links
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if any(dom in href.lower() for dom in ["youtube.com", "twitch.tv", "tiktok.com", "instagram.com", "twitter.com", "x.com"]):
                if href not in social_links and not href.startswith("https://contentrewards.com"):
                    social_links.append(href)

        # Regex match text handles in raw description (e.g. twitch.tv/username)
        raw_urls = re.findall(
            r'(?:https?://(?:www\.)?|www\.)?(?:youtube\.com/@[a-zA-Z0-9_-]+|twitch\.tv/[a-zA-Z0-9_-]+|tiktok\.com/@[a-zA-Z0-9_\.-]+|instagram\.com/[a-zA-Z0-9_\.-]+)',
            html
        )
        for u in raw_urls:
            full_u = u if u.startswith("http") else f"https://{u}"
            if full_u not in social_links and not full_u.startswith("https://contentrewards.com"):
                social_links.append(full_u)

        # 5. Platforms Supported & Mandatory
        supported_platforms: List[str] = []
        if any("youtube" in s.lower() for s in social_links) or "youtube" in normalized_text.lower():
            supported_platforms.append("YouTube Shorts")
        if any("tiktok" in s.lower() for s in social_links) or "tiktok" in normalized_text.lower():
            supported_platforms.append("TikTok")
        if any("instagram" in s.lower() for s in social_links) or "instagram" in normalized_text.lower():
            supported_platforms.append("Instagram Reels")

        # 6. Reference Materials & Permissions
        files_count = None
        count_match = re.search(r'Reference materials\s+(\d+)\s+files?', normalized_text, re.I)
        if count_match:
            try:
                files_count = int(count_match.group(1))
            except Exception:
                pass

        is_restricted = (
            "visible once you join" in normalized_text.lower() or
            "join to unlock" in normalized_text.lower() or
            "join campaign" in normalized_text.lower()
        )

        # 7. Raw Description Snippet
        desc_start = normalized_text.find(title) if title and title in normalized_text else 0
        raw_description = normalized_text[desc_start:desc_start + 1200]

        # 8. Extraction Audit Report
        status = "SUCCESS"
        if len(missing_sections) >= 2 or not title:
            status = "PARTIAL_EXTRACTION"

        report = ExtractionReport(
            status=status,
            missing_sections=missing_sections,
            warnings=warnings,
            restricted_resources=is_restricted
        )

        return DiscoveredCampaignDetail(
            external_id=ext_id,
            source_platform="Content Rewards",
            campaign_url=url,
            title=title,
            creator=creator,
            brand=None,
            category=category,
            campaign_status=campaign_status,
            payment_model=payment_model,
            total_budget=total_budget,
            rate=rate,
            currency="USD",
            payment_conditions=payment_conditions,
            supported_platforms=supported_platforms,
            mandatory_platforms=[],  # Unknown unless explicitly mandated
            eligibility_requirements={
                "minimum_subscribers": None,
                "minimum_followers": None,
                "notes": "Reference materials locked behind campaign join requirement." if is_restricted else None
            },
            content_requirements={
                "niche": [category] if category else ["Entertainment"],
                "aspect_ratio": "9:16",
                "authorized_footage_provided": True
            },
            posting_instructions={
                "hashtags": [f"#{creator.lower().replace(' ', '')}"] if creator else [],
                "mentions": []
            },
            reference_links=social_links,
            reference_files_count=files_count,
            reference_files_restricted=is_restricted,
            raw_description=raw_description,
            raw_rules=None,
            extraction_report=report
        )

