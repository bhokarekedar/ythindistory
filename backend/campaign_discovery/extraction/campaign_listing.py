import re
from typing import List, Dict, Set
from bs4 import BeautifulSoup
from ..models.campaign import DiscoveredCampaignCard


class CampaignListingExtractor:
    """
    Parses campaign cards from the Content Rewards discover page DOM.
    Extracts URLs, titles, creators, categories, and payment summaries.
    Handles deduplication based on external campaign UUIDs.
    """

    UUID_REGEX = re.compile(r'/c/campaigns/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', re.I)

    def extract_cards(self, html: str, base_url: str = "https://contentrewards.com") -> List[DiscoveredCampaignCard]:
        """Parses HTML DOM of discover page and returns unique DiscoveredCampaignCard items."""
        soup = BeautifulSoup(html, "html.parser")
        discovered_cards: List[DiscoveredCampaignCard] = []
        seen_ids: Set[str] = set()

        links = soup.find_all("a", href=True)

        for a in links:
            href = a["href"]
            match = self.UUID_REGEX.search(href)
            if not match:
                continue

            ext_id = match.group(1).lower()
            if ext_id in seen_ids:
                continue

            seen_ids.add(ext_id)

            full_url = href if href.startswith("http") else f"{base_url.rstrip('/')}/{href.lstrip('/')}"
            
            # Extract card container text
            card_text = " ".join(a.get_text(separator=" ").split())
            
            # Extract title if present in link
            title = None
            creator = None
            category = None
            payment_summary = None

            # Look for heading or bold inside card
            h_tag = a.find(["h2", "h3", "h4", "p", "span"])
            if h_tag:
                title_cand = h_tag.get_text().strip()
                if len(title_cand) > 3:
                    title = title_cand

            # Search for pool or CPM in card text
            pay_match = re.search(r'(\$[\d,]+(?:\.\d+)?(?:\s*(?:k|pool|cpm|total))?)', card_text, re.I)
            if pay_match:
                payment_summary = pay_match.group(1).strip()

            # Identify common categories
            for cat in ["Gaming", "Entertainment", "Comedy", "Sports", "Challenge", "Music", "Tech"]:
                if re.search(rf'\b{cat}\b', card_text, re.I):
                    category = cat
                    break

            discovered_cards.append(
                DiscoveredCampaignCard(
                    external_id=ext_id,
                    campaign_url=full_url,
                    title=title or f"Campaign {ext_id[:8]}",
                    creator=creator,
                    category=category,
                    payment_summary=payment_summary,
                    status="active"
                )
            )

        return discovered_cards

