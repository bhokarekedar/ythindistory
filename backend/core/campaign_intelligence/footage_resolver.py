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

    def _run_ytdlp_flat(self, target: str, max_items: int = 4) -> List[Dict[str, Any]]:
        """Extracts flat video listings without downloading media."""
        cmd = [
            self.ytdlp_bin,
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
            "--playlist-end", str(max_items),
            target
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
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

                    videos.append({
                        "video_id": v_id,
                        "url": video_url,
                        "title": data.get("title") or "Untitled Video",
                        "duration": duration_sec,
                        "duration_formatted": self._format_duration(duration_sec),
                        "thumbnail": thumb,
                        "channel": data.get("uploader") or data.get("channel") or "",
                        "view_count": data.get("view_count")
                    })
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

        # Priority D: Clean search based on campaign title / keywords
        if not resolved_videos and not drive_links:
            clean_title = campaign.title
            # Strip pool amounts and boilerplate
            clean_title = re.sub(r'[\$,\d]+(?:k)?\s*(?:pool|campaign)?', '', clean_title, flags=re.IGNORECASE).strip()
            clean_title = re.sub(r'\(.*?\)', '', clean_title).strip()
            if len(clean_title) > 4:
                search_query = f"ytsearch4:{clean_title} stream highlights"
                resolved_videos = self._run_ytdlp_flat(search_query, max_items=4)
                if resolved_videos:
                    source_type = "search_matches"

        result = {
            "campaign_id": campaign.campaign_id,
            "campaign_title": campaign.title,
            "source_type": source_type,
            "channel_url": channel_detected,
            "videos": resolved_videos,
            "drive_links": [{"url": d, "label": "Google Drive Footage Folder"} for d in drive_links],
            "total_videos_found": len(resolved_videos)
        }

        # Cache result
        self.cache[campaign.campaign_id] = {
            "timestamp": now,
            "data": result
        }

        return result
