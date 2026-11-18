import os
import re
import json
import shutil
import subprocess
import time
from typing import Dict, Any, List, Optional
from .models import CampaignRecord

class CampaignFootageResolver:
    """
    Intelligently extracts and resolves source footage (YouTube videos, channels, 
    Drive folders) associated with a campaign so the user doesn't have to leave
    the app to search for videos manually.
    """

    def __init__(self, cache_ttl_seconds: int = 600):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = cache_ttl_seconds

        # Locate yt-dlp binary (prefer backend venv)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        venv_ytdlp = os.path.join(base_dir, "venv", "bin", "yt-dlp")
        if os.path.exists(venv_ytdlp):
            self.ytdlp_bin = venv_ytdlp
        else:
            self.ytdlp_bin = shutil.which("yt-dlp") or "yt-dlp"

    def _format_duration(self, seconds: Optional[int]) -> str:
        if not seconds or seconds < 0:
            return ""
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"

    def _run_ytdlp_flat(self, target: str, max_items: int = 8, required_keywords: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Extracts flat video listings without downloading media, applying strict Tier-1 and relevance filters."""
        cmd = [
            self.ytdlp_bin,
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
            "--playlist-end", str(max_items * 2),  # Pull extra to allow filtering
            target
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=18)
            if res.returncode != 0:
                print(f"[FootageResolver] yt-dlp warning/error for '{target}': {res.stderr[:200]}")
            
            videos = []
            for line in res.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    v_id = data.get("id") or ""
                    # Handle possible direct URL or ID
                    video_url = data.get("url") or (f"https://www.youtube.com/watch?v={v_id}" if len(v_id) == 11 else None)
                    if not video_url and len(v_id) == 11:
                        video_url = f"https://www.youtube.com/watch?v={v_id}"
                    
                    if not video_url:
                        continue

                    duration_sec = data.get("duration")
                    thumb = data.get("thumbnail")
                    if not thumb and data.get("thumbnails"):
                        thumb = data["thumbnails"][-1].get("url")
                    if not thumb and len(v_id) == 11:
                        thumb = f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"

                    v_title = data.get("title") or "Untitled Video"
                    v_channel = data.get("uploader") or data.get("channel") or ""
                    combined_meta = f"{v_title} {v_channel}".lower()

                    # 1. Reject non-Latin scripts (Devanagari, Arabic/Urdu, Cyrillic, CJK, etc.)
                    if re.search(r'[\u0900-\u097F\u0A00-\u0A7F\u0600-\u06FF\u0400-\u04FF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]', combined_meta):
                        continue

                    # 2. Comprehensive Tier-1 / Non-English filter (Bollywood, Indian labels, regional music)
                    non_tier1_keywords = [
                        # Indian music labels & film channels
                        "t-series", "tseries", "zee music", "sony music india", "yrf", "saregama",
                        "tips official", "speed records", "geet mp3", "white hill", "desi music factory",
                        "venus", "eros now", "aditya music", "lahari music", "rajshri", "times music",
                        # Languages & Indian regional film industries
                        "hindi", "punjabi", "bhojpuri", "haryanvi", "tamil", "telugu", "malayalam",
                        "kannada", "marathi", "bengali", "gujarati", "bollywood", "tollywood", "kollywood",
                        "desidesi", "desi", "indian", "india", "pakistan", "bangladesh", "urdu",
                        # Common Bollywood / Hindi words in Latin script
                        "ghar kab aaoge", "sandese aate hai", "border 2", "gaana", "geet", "bhajan",
                        "aarti", "dj remix", "bhojpuri song", "punjabi song", "hindi song", "full movie hindi",
                        # Prominent Indian creators
                        "carryminati", "fukra insaan", "triggered insaan", "round2hell",
                        "bb ki vines", "ashish chanchlani", "mortal", "scout", "techno gamerz",
                        "total gaming", "sourav joshi", "mythpat"
                    ]
                    if any(bad in combined_meta for bad in non_tier1_keywords):
                        continue

                    # 3. Relevance verification (if required keywords provided)
                    if required_keywords:
                        # At least one core subject keyword must appear in video title or channel name
                        has_relevance = any(kw.lower() in combined_meta for kw in required_keywords if len(kw) >= 3)
                        if not has_relevance:
                            continue

                    videos.append({
                        "video_id": v_id,
                        "url": video_url,
                        "title": v_title,
                        "duration": duration_sec,
                        "duration_formatted": self._format_duration(duration_sec),
                        "thumbnail": thumb,
                        "channel": v_channel,
                        "view_count": data.get("view_count")
                    })

                    if len(videos) >= max_items:
                        break
                except Exception as parse_err:
                    print(f"[FootageResolver] Parse error for line: {parse_err}")
            return videos
        except subprocess.TimeoutExpired:
            print(f"[FootageResolver] Timeout running yt-dlp on {target}")
            return []
        except Exception as e:
            print(f"[FootageResolver] Failed to run yt-dlp: {e}")
            return []

    def resolve_footage(self, campaign: CampaignRecord) -> Dict[str, Any]:
        """
        Extracts relevant video candidates, channel feeds, and drive links for a campaign.
        Uses in-memory cache to stay fast and responsive.
        """
        now = time.time()
        cached = self.cache.get(campaign.campaign_id)
        if cached and (now - cached.get("timestamp", 0) < self.cache_ttl):
            return cached["data"]

        brief = campaign.raw_brief or ""
        ref_links = []
        if campaign.content_requirements and campaign.content_requirements.allowed_source_urls:
            ref_links.extend(campaign.content_requirements.allowed_source_urls)

        combined_text = f"{brief}\n" + "\n".join(ref_links)

        # 1. Look for direct YouTube video URLs
        yt_video_urls = re.findall(
            r'(https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[a-zA-Z0-9_-]{11})',
            combined_text
        )

        # 2. Look for YouTube channel URLs
        yt_channel_urls = re.findall(
            r'(https?://(?:www\.)?youtube\.com/(?:@[a-zA-Z0-9_.-]+|channel/[a-zA-Z0-9_-]+|c/[a-zA-Z0-9_-]+))',
            combined_text
        )

        # 3. Look for Google Drive folders or files
        drive_links = re.findall(
            r'(https?://drive\.google\.com/[^\s\)\"\'>]+)',
            combined_text
        )

        # Deduplicate found links
        yt_video_urls = list(dict.fromkeys(yt_video_urls))
        yt_channel_urls = list(dict.fromkeys(yt_channel_urls))
        drive_links = list(dict.fromkeys(drive_links))

        resolved_videos: List[Dict[str, Any]] = []
        source_type = "manual"
        channel_detected = None

        # Priority A: Channel found in campaign brief
        if yt_channel_urls:
            source_type = "channel"
            raw_channel = yt_channel_urls[0]
            channel_detected = raw_channel
            # Fetch /videos tab for most recent uploads
            target = raw_channel.rstrip("/") + "/videos"
            resolved_videos = self._run_ytdlp_flat(target, max_items=4)

        # Priority B: Direct video links in campaign brief
        elif yt_video_urls:
            source_type = "direct_video"
            for v_url in yt_video_urls[:4]:
                single_v = self._run_ytdlp_flat(v_url, max_items=1)
                if single_v:
                    resolved_videos.extend(single_v)

        # Priority C: Check mentions (e.g. @MinecraftClippers or creator handle)
        if not resolved_videos and campaign.posting_metadata and campaign.posting_metadata.required_mentions:
            for mention in campaign.posting_metadata.required_mentions:
                clean_handle = mention.strip("@")
                if clean_handle and not clean_handle.lower().endswith("clippers"):
                    channel_url = f"https://www.youtube.com/@{clean_handle}/videos"
                    vids = self._run_ytdlp_flat(channel_url, max_items=4)
                    if vids:
                        resolved_videos = vids
                        source_type = "channel"
                        channel_detected = f"https://www.youtube.com/@{clean_handle}"
                        break

        # Priority D: Targeted smart search based on campaign type and subject
        if not resolved_videos:
            title_raw = campaign.title
            # Strip dollar amounts ($25,000, $8,000+, ,000)
            clean_title = re.sub(r'\$\s*[\d,]+[kKmMbB]?\+?', '', title_raw)
            clean_title = re.sub(r'^\s*,[\d,]+\s*', '', clean_title)
            # Strip brackets [ROBLOX], (Content Rewards)
            clean_title = re.sub(r'\[.*?\]|\(.*?\)', '', clean_title)
            # Strip marketing buzzwords
            clean_title = re.sub(r'\b(?:\d+\s+)?(?:live\s+)?music\s+campaigns?\b', '', clean_title, flags=re.IGNORECASE)
            clean_title = re.sub(r'\bclipping\s+campaigns?\b|\bpool\s+campaigns?\b|\bclipping\b|\bcampaigns?\b', '', clean_title, flags=re.IGNORECASE)
            clean_title = re.sub(r'\b(?:mv\s+)?edits\b', '', clean_title, flags=re.IGNORECASE)
            clean_title = re.sub(r'[\s\|\-\:\_]+$', '', clean_title).strip(" |-:_")

            # Extract subject words for relevance checking
            subject_words = [w for w in re.split(r'[\s\-_|/]+', clean_title) if len(w) >= 3 and w.lower() not in ("the", "and", "for", "with", "from", "stream", "live")]

            # Determine content category
            brief_lower = combined_text.lower()
            is_music = any(m in brief_lower or m in title_raw.lower() for m in ["sound campaign", "music", "song", "track", "audio", "single", "album", "mv"])
            is_podcast = any(p in brief_lower or p in title_raw.lower() for p in ["podcast", "interview", "episode"])
            is_trailer = any(t in brief_lower or t in title_raw.lower() for t in ["trailer", "teaser", "announcement"])

            if is_music:
                # Look for specific track names in quotes in the brief
                quoted_tracks = re.findall(r'[\"“\']([^\"”\']{3,30})[\"”\']', brief)
                valid_tracks = [t for t in quoted_tracks if not any(w in t.lower() for w in ["content", "http", "view", "cpm", "rule", "guideline"])]
                if valid_tracks:
                    # Search for artist + official video/audio
                    search_query = f"ytsearch10:{clean_title} official"
                    subject_words.extend([w for t in valid_tracks for w in t.split() if len(w) >= 3])
                else:
                    search_query = f"ytsearch10:{clean_title} official music video"
            elif is_podcast:
                search_query = f"ytsearch10:{clean_title} podcast full episode"
            elif is_trailer:
                search_query = f"ytsearch10:{clean_title} official trailer"
            else:
                search_query = f"ytsearch10:{clean_title}"

            if len(clean_title) >= 3:
                resolved_videos = self._run_ytdlp_flat(search_query, max_items=4, required_keywords=subject_words)
                if resolved_videos:
                    source_type = "search_matches"

        # Check for Content Bank / Asset Pack mention
        has_content_bank = bool(re.search(r'\b(?:content\s+bank|asset\s+pack|google\s+drive|drive\s+folder|assets?\s+folder)\b', combined_text, flags=re.IGNORECASE))

        # Build clean labeled reference/drive links
        labeled_links = []
        if campaign.guidelines_metadata and campaign.guidelines_metadata.get("reference_links"):
            for r in campaign.guidelines_metadata["reference_links"]:
                if isinstance(r, dict) and r.get("url"):
                    labeled_links.append({"url": r["url"], "label": r.get("label") or "Campaign Asset Folder"})
        
        existing_u = {l["url"] for l in labeled_links}
        for idx, d in enumerate(drive_links):
            if d not in existing_u:
                lbl = "Google Drive Footage Folder" if ("folder" in d or idx > 0) else "Campaign Guidelines Document"
                labeled_links.append({"url": d, "label": lbl})
                existing_u.add(d)

        result = {
            "campaign_id": campaign.campaign_id,
            "campaign_title": campaign.title,
            "source_type": source_type,
            "channel_url": channel_detected,
            "videos": resolved_videos,
            "drive_links": labeled_links,
            "has_content_bank": has_content_bank,
            "content_bank_note": "Official content bank / asset folder referenced in campaign brief." if has_content_bank else None,
            "total_videos_found": len(resolved_videos)
        }

        # Cache result
        self.cache[campaign.campaign_id] = {
            "timestamp": now,
            "data": result
        }

        return result
