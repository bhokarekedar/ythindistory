import os
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any
import yt_dlp


def extract_video_id(url: str) -> Optional[str]:
    """
    Extracts the standard 11-character YouTube video ID from various URL formats:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    - VIDEO_ID directly
    """
    if not url:
        return None
    url = url.strip()
    
    # Direct 11-char ID
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
        
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        
        if any(h in hostname for h in ['youtube.com', 'm.youtube.com', 'music.youtube.com']):
            if parsed.path == '/watch':
                v_param = parse_qs(parsed.query).get('v')
                if v_param:
                    return v_param[0]
            elif parsed.path.startswith(('/embed/', '/v/', '/shorts/')):
                parts = [p for p in parsed.path.split('/') if p]
                if len(parts) >= 2:
                    return parts[1]
        elif 'youtu.be' in hostname:
            parts = [p for p in parsed.path.split('/') if p]
            if parts:
                return parts[0]
    except Exception:
        pass
        
    # Regex fallback
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    return match.group(1) if match else None


class YouTubeDownloader:
    def __init__(self, output_dir: str = "temp"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """
        Extracts video metadata (title, duration, thumbnail, author, views) without downloading.
        Runs high-speed query first, with automatic cookie fallback if needed.
        """
        vid_id = extract_video_id(url)
        canonical_url = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else url

        base_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": False,
        }

        info = None
        # Fast extraction without cookies
        try:
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
        except Exception as e_nocookies:
            # Fallback with Chrome cookies
            try:
                cookie_opts = dict(base_opts)
                cookie_opts["cookiesfrombrowser"] = ("chrome", "Default")
                with yt_dlp.YoutubeDL(cookie_opts) as ydl:
                    info = ydl.extract_info(canonical_url, download=False)
            except Exception:
                raise Exception(f"Unable to extract video information from YouTube: {str(e_nocookies)}")

        if not info:
            raise Exception("Unable to extract video information")

        dur = int(info.get("duration") or 0)
        mins, secs = divmod(dur, 60)
        hrs, mins = divmod(mins, 60)
        dur_fmt = f"{hrs:d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}"

        # Check local cache for downloaded video
        actual_id = info.get("id") or vid_id
        is_cached = False
        cached_path = None
        if actual_id:
            for ext in ["mp4", "webm", "mkv"]:
                p = os.path.join(self.output_dir, f"{actual_id}.{ext}")
                if os.path.exists(p) and os.path.getsize(p) >= 1024 * 1024:
                    is_cached = True
                    cached_path = p
                    break

        return {
            "video_id": actual_id,
            "title": info.get("title", "Unknown Title"),
            "uploader": info.get("uploader") or info.get("channel") or "Unknown Channel",
            "uploader_url": info.get("uploader_url") or info.get("channel_url"),
            "duration": dur,
            "duration_formatted": dur_fmt,
            "thumbnail": info.get("thumbnail"),
            "view_count": info.get("view_count") or 0,
            "webpage_url": info.get("webpage_url") or canonical_url,
            "description": (info.get("description") or "")[:300],
            "is_cached": is_cached,
            "cached_path": cached_path
        }

    def download(self, url: str) -> str:
        """
        Download a YouTube video and return the downloaded file path.
        Automatically handles cookie retries and fallback to avoid errors.
        """
        def _get_opts(use_cookies: bool = True):
            opts = {
                "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "outtmpl": os.path.join(
                    self.output_dir,
                    "%(id)s.%(ext)s"
                ),
                "quiet": False,
                "no_warnings": False,
                "ignoreerrors": False,
            }
            if use_cookies:
                opts["cookiesfrombrowser"] = ("chrome", "Default")
            return opts

        info = None
        try:
            # Attempt with browser cookies
            with yt_dlp.YoutubeDL(_get_opts(use_cookies=True)) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as e_cookie:
            print(f"[YouTubeDownloader] Attempt with cookies encountered error: {e_cookie}. Retrying without browser cookies...")
            try:
                with yt_dlp.YoutubeDL(_get_opts(use_cookies=False)) as ydl:
                    info = ydl.extract_info(url, download=True)
            except Exception as e_nocookie:
                raise Exception(f"yt-dlp download failed: {str(e_nocookie)}") from e_nocookie

        if not info:
            raise Exception("Unable to extract video information during download")

        filepath = ydl.prepare_filename(info)

        # Normal output
        if os.path.exists(filepath):
            return filepath

        # Check if the final extension changed
        base_path = os.path.splitext(filepath)[0]
        for ext in ["mp4", "webm", "mkv", "m4a"]:
            possible_path = f"{base_path}.{ext}"
            if os.path.exists(possible_path):
                return possible_path

        raise Exception(f"Downloaded file could not be found: {filepath}")
