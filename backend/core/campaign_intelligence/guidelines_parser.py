import os
import re
import json
from typing import Dict, Any, List, Optional, Union
from groq import Groq
from core.api_keys import ApiKeyManager

class GuidelinesParser:
    """
    Evaluates campaign guidelines with a strict binary verdict: APPROVED or REJECTED.
    Stores full metadata in the backend while returning only essential publishing details
    for a clean, uncluttered frontend.
    """

    def __init__(self):
        self.key_manager = ApiKeyManager()

    def parse_guidelines(
        self,
        raw_text: str,
        guidelines_urls: Optional[Union[List[str], str]] = None
    ) -> Dict[str, Any]:
        if not raw_text or len(raw_text.strip()) < 10:
            return {"error": "Guidelines text too short or empty."}

        # Normalize URL input
        url_list: List[str] = []
        if isinstance(guidelines_urls, str) and guidelines_urls.strip():
            url_list = [u.strip() for u in re.split(r'[\n,]+', guidelines_urls) if u.strip().startswith("http")]
        elif isinstance(guidelines_urls, list):
            url_list = [u.strip() for u in guidelines_urls if u.strip().startswith("http")]

        in_text_drives = re.findall(r'(https?://(?:drive|docs)\.google\.com/[^\s\)\"\'>]+|https?://(?:www\.)?dropbox\.com/[^\s\)\"\'>]+)', raw_text)
        for d in in_text_drives:
            if d not in url_list:
                url_list.append(d)

        # Groq evaluation
        api_key = self.key_manager.get_next_key()
        if api_key:
            try:
                parsed = self._evaluate_with_groq(raw_text, api_key, url_list)
                if parsed and isinstance(parsed, dict) and "status" in parsed:
                    return parsed
            except Exception as e:
                print(f"[GuidelinesParser] Groq error: {e}, using fallback.")

        return self._evaluate_fallback(raw_text, url_list)

    def _evaluate_with_groq(self, text: str, api_key: str, url_list: List[str]) -> Dict[str, Any]:
        client = Groq(api_key=api_key)

        system_prompt = """You are an automated campaign eligibility gate for ViralLoop, an automated video clipper.
ViralLoop takes video footage from YouTube or Google Drive and automatically extracts clips, adds captions, and publishes vertical video (YouTube Shorts, Instagram Reels, TikTok).

RULES FOR EVALUATION:
1. "status": MUST be either "APPROVED" or "REJECTED".
   - REJECT ONLY IF:
     a) The user/clipper is STRICTLY MANDATED to record their OWN face / personal selfie webcam reaction on camera, with ZERO alternatives. (Note: If reaction videos are suggested as one option among other allowed edit formats like lyric bars, caption edits, or performance cuts, it is APPROVED!).
     b) The campaign is non-English only.
     c) The campaign explicitly prohibits clipping/editing tools.
   - APPROVE IF:
     The user can clip footage of the artist/creator (e.g. 8lanco, streamer, podcaster) using edit formats like performance cuts, lyric bars, B-roll cuts, or stream highlights.
     (Note: Platforms like YouTube Shorts, Instagram Reels, or TikTok are ALL supported and 100% OK).
2. "rejection_reason": Concise 1-sentence reason ONLY if REJECTED (e.g. "Requires personal on-camera selfie/facecam reaction video."), otherwise null.
3. "mandatory_caption": Exact required caption text (e.g. "EVERY LITTLE THING BY 8LANCO. OUT NOW. #8lanco #everylittlething").
4. "required_hashtags": Array of hashtags.
5. "required_mentions": Array of account mentions/tags.
6. "critical_rule": Single most important 1-sentence disqualification rule (e.g. "Creator must be on screen for 50%+ of clip, official sound at 1% volume, always end on creator.").
7. "allowed_platforms": Array of allowed platforms (e.g. ["YouTube Shorts", "Instagram Reels", "TikTok"]).
8. "reference_links": Array of objects [{"label": "...", "url": "..."}].

Return ONLY valid JSON.
"""

        user_content = f"Guidelines Text:\n{text[:6500]}"
        if url_list:
            user_content += "\nReference URLs:\n" + "\n".join(url_list)

        response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )

        data = json.loads(response.choices[0].message.content)
        
        # Ensure status is uppercase
        data["status"] = (data.get("status") or "APPROVED").upper()
        if data["status"] not in ["APPROVED", "REJECTED"]:
            data["status"] = "APPROVED"

        # Build clean labeled reference links
        existing_urls = {r.get("url") for r in data.get("reference_links", []) if isinstance(r, dict)}
        if not data.get("reference_links"):
            data["reference_links"] = []

        for idx, u in enumerate(url_list):
            if u not in existing_urls:
                lbl = "Guidelines Doc" if idx == 0 else f"Asset Folder #{idx+1}"
                data["reference_links"].append({"label": lbl, "url": u})
                existing_urls.add(u)

        return data

    def _evaluate_fallback(self, text: str, url_list: List[str]) -> Dict[str, Any]:
        is_reaction_only = bool(re.search(r'\bonly\s+reaction\s+videos?\b|\bmust\s+show\s+your\s+face\b', text, re.I))
        
        hashtags = [f"#{h}" for h in list(dict.fromkeys(re.findall(r'#([a-zA-Z0-9_]+)', text)))]
        mentions = [f"@{m}" for m in list(dict.fromkeys(re.findall(r'@([a-zA-Z0-9_.-]+)', text)))]
        caption_match = re.search(r'Caption:\s*([^\n\r]+)', text, re.I)

        return {
            "status": "REJECTED" if is_reaction_only else "APPROVED",
            "rejection_reason": "Personal on-camera face reaction required." if is_reaction_only else None,
            "mandatory_caption": caption_match.group(1).strip() if caption_match else None,
            "required_hashtags": hashtags,
            "required_mentions": mentions,
            "critical_rule": "Ensure creator is visible on screen and official sound is used as instructed.",
            "allowed_platforms": ["YouTube Shorts", "Instagram Reels", "TikTok"],
            "reference_links": [{"label": "Reference Folder", "url": u} for u in url_list]
        }
