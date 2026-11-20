"""YouTube Upload Module for English Shadowing Videos.

Uses YouTube Data API v3 (videos.insert, thumbnails.set, playlists, commentThreads).
Features:
- OAuth credentials loaded from local file (default: backend/data/youtube_token.json).
- Resumable upload for large MP4 video files with exponential backoff on transient errors.
- Privacy control: 'private', 'unlisted', 'public', or scheduled publishing via publish_at (ISO 8601).
- Automatically adds video to designated playlist (creating playlist if needed).
- Sets video thumbnail if provided.
- Posts pinned_comment text as top-level comment and logs manual pinning reminder.
- Strict confirmation requirement (--yes / confirm=True) to prevent accidental uploads.
- Keeps title_alternatives in video_metadata.json only (never uploaded).
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("youtube_uploader")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[YouTubeUploader] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# Standard YouTube Category IDs
CATEGORY_MAP = {
    "education": "27",
    "entertainment": "24",
    "howto": "26",
    "news": "25",
    "people": "22",
    "film": "1",
    "music": "10",
}


def resolve_token_file(token_path: Optional[str] = None) -> Path:
    """Resolves which token file to use, preferring shadow english specific token."""
    base_data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    if token_path:
        return Path(token_path)
    
    shadow_token = base_data_dir / "youtube_token_shadow_english.json"
    if shadow_token.exists():
        return shadow_token
    
    default_token = base_data_dir / "youtube_token.json"
    if default_token.exists():
        return default_token
        
    return shadow_token


def get_channel_status(token_path: Optional[str] = None) -> Dict[str, Any]:
    """Returns the authenticated YouTube channel details or connection failure info."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    base_data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    token_file = resolve_token_file(token_path)
    secrets_file = base_data_dir / "client_secrets.json"

    if not token_file.exists():
        return {
            "connected": False,
            "has_client_secrets": secrets_file.exists(),
            "token_file": str(token_file),
            "message": f"Channel token not found at {token_file.name}. Please connect the channel."
        }

    try:
        creds = Credentials.from_authorized_user_file(str(token_file))
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

        if creds and creds.valid:
            service = build("youtube", "v3", credentials=creds)
            ch_res = service.channels().list(part="snippet,statistics", mine=True).execute()
            items = ch_res.get("items", [])
            if items:
                ch = items[0]
                snippet = ch.get("snippet", {})
                stats = ch.get("statistics", {})
                custom_url = snippet.get("customUrl", "")
                title = snippet.get("title", "")
                is_target_channel = "@shadowenglishdaily" in custom_url.lower() or "shadow english" in title.lower()

                return {
                    "connected": True,
                    "channel_id": ch.get("id"),
                    "channel_title": title,
                    "custom_url": custom_url,
                    "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url"),
                    "subscriber_count": stats.get("subscriberCount", "0"),
                    "video_count": stats.get("videoCount", "0"),
                    "is_target_channel": is_target_channel,
                    "token_file": str(token_file),
                    "message": f"Connected to {title} ({custom_url})"
                }
            return {
                "connected": True,
                "token_file": str(token_file),
                "message": "Authorized, but no channel found for this Google account."
            }
    except Exception as e:
        return {
            "connected": False,
            "token_file": str(token_file),
            "error": str(e),
            "message": f"Authentication check failed: {e}"
        }


def authenticate_channel(
    token_path: Optional[str] = None,
    client_secrets_path: Optional[str] = None,
    port: int = 8089,
) -> Dict[str, Any]:
    """Runs interactive local OAuth flow in the browser to connect a YouTube channel."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    base_data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    token_file = Path(token_path) if token_path else (base_data_dir / "youtube_token_shadow_english.json")
    secrets_file = Path(client_secrets_path) if client_secrets_path else (base_data_dir / "client_secrets.json")

    if not secrets_file.exists():
        return {
            "success": False,
            "error": "client_secrets_missing",
            "message": f"OAuth client_secrets.json not found at {secrets_file}."
        }

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)
        creds = flow.run_local_server(port=port, prompt="consent", access_type="offline")

        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        status = get_channel_status(token_path=str(token_file))
        status["success"] = True
        return status
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"OAuth flow failed: {e}"
        }


def get_authenticated_service(
    token_path: Optional[str] = None,
    client_secrets_path: Optional[str] = None,
):
    """Builds and returns an authenticated googleapiclient YouTube resource."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    base_data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    token_file = resolve_token_file(token_path)
    secrets_file = Path(client_secrets_path) if client_secrets_path else (base_data_dir / "client_secrets.json")

    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file))
        except Exception as e:
            logger.warning(f"Error reading existing token file: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired YouTube OAuth access token...")
            creds.refresh(Request())
            token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        else:
            if not secrets_file.exists():
                raise FileNotFoundError(
                    f"Neither valid token ({token_file}) nor client_secrets.json ({secrets_file}) were found. "
                    "Please provide OAuth client_secrets.json to connect your YouTube channel."
                )
            logger.info("Initiating browser OAuth flow for YouTube channel authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)
            creds = flow.run_local_server(port=8089, prompt="consent", access_type="offline")
            token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(
    video_path: str,
    metadata_path: str,
    thumbnail_path: Optional[str] = None,
    publish_at: Optional[str] = None,
    privacy: str = "private",
    confirm: bool = False,
    token_path: Optional[str] = None,
    client_secrets_path: Optional[str] = None,
    max_retries: int = 5,
) -> Dict[str, Any]:
    """Uploads a video to YouTube with full metadata, playlist, thumbnail, and comment.

    Args:
        video_path: Path to MP4 video file.
        metadata_path: Path to video_metadata.json.
        thumbnail_path: Optional path to thumbnail image file.
        publish_at: Optional ISO 8601 UTC timestamp for scheduled publishing (e.g. '2026-11-25T15:00:00Z').
        privacy: 'private', 'unlisted', or 'public'. Defaults to 'private'.
        confirm: Must be True to execute upload. Safety flag preventing accidental uploads.
        token_path: Optional path to stored OAuth token.
        client_secrets_path: Optional path to Google client_secrets.json.
        max_retries: Maximum exponential backoff retries for transient HTTP errors.
    """
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    v_file = Path(video_path).resolve()
    m_file = Path(metadata_path).resolve()

    if not v_file.exists():
        raise FileNotFoundError(f"Video file not found: {v_file}")
    if not m_file.exists():
        raise FileNotFoundError(f"Metadata file not found: {m_file}")

    with open(m_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Required confirmation check
    if not confirm:
        msg = (
            "⚠️ Confirmation required: YouTube upload aborted because confirm=False. "
            "Please pass confirm=True (or --yes in CLI) to publish."
        )
        logger.warning(msg)
        return {
            "success": False,
            "requires_confirmation": True,
            "message": msg,
            "preview": {
                "title": meta.get("title"),
                "privacy": privacy,
                "video_file": str(v_file),
                "playlist": meta.get("playlist"),
            },
        }

    # Validate privacy & scheduled publish
    privacy_status = privacy.lower().strip()
    if privacy_status not in ("private", "unlisted", "public"):
        raise ValueError(f"Invalid privacy status '{privacy}'. Must be 'private', 'unlisted', or 'public'.")

    status_body: Dict[str, Any] = {
        "privacyStatus": privacy_status,
        "selfDeclaredMadeForKids": bool(meta.get("made_for_kids", False)),
    }

    if publish_at:
        # YouTube requires privacyStatus to be 'private' when publishAt is set
        status_body["privacyStatus"] = "private"
        status_body["publishAt"] = publish_at
        logger.info(f"Video scheduled to publish at: {publish_at} (status forced to private until release)")

    # Category ID resolution
    cat_name = meta.get("category", "Education").lower().strip()
    category_id = CATEGORY_MAP.get(cat_name, "27")

    # Map fields (note: title_alternatives is intentionally omitted from snippet)
    # YouTube Data API rules:
    # 1. Total tags length including quotes around multi-word tags and separating commas must not exceed 500 chars (safe ceiling: 420 chars).
    # 2. No quotes, brackets, or invalid characters.
    raw_tags = meta.get("tags", [])
    safe_tags = []
    curr_quoted_len = 0
    for t in raw_tags:
        t_clean = re.sub(r'["\'<>/]', '', str(t)).strip().lower()
        if not t_clean:
            continue
        tag_cost = len(t_clean) + (2 if " " in t_clean else 0) + (1 if safe_tags else 0)
        if curr_quoted_len + tag_cost <= 420:
            safe_tags.append(t_clean)
            curr_quoted_len += tag_cost
        else:
            logger.info(f"Omitted tag '{t_clean}' to stay strictly within YouTube 500-char quota (currently {curr_quoted_len} chars).")
            break

    snippet_body = {
        "title": meta.get("title", "Untitled Shadowing Lesson")[:100],
        "description": meta.get("description", "")[:5000],
        "tags": safe_tags,
        "categoryId": category_id,
        "defaultLanguage": meta.get("language", "en"),
    }

    body = {
        "snippet": snippet_body,
        "status": status_body,
    }

    youtube = get_authenticated_service(token_path, client_secrets_path)

    media = MediaFileUpload(
        str(v_file),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 8,  # 8MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    file_size_mb = v_file.stat().st_size / (1024 * 1024)
    logger.info(f"Starting resumable upload for '{snippet_body['title']}' ({file_size_mb:.1f} MB)...")

    response = None
    retry_count = 0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info(f"Upload progress: {pct}%")
            retry_count = 0  # reset on successful chunk
        except (HttpError, OSError) as err:
            retry_count += 1
            if retry_count > max_retries:
                logger.error(f"Exceeded max retries ({max_retries}). Upload failed.")
                raise err
            sleep_sec = 2 ** retry_count
            logger.warning(f"Transient error: {err}. Retrying chunk in {sleep_sec}s (retry {retry_count}/{max_retries})...")
            time.sleep(sleep_sec)

    video_id = response.get("id")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info(f"🎉 Video uploaded successfully! Video ID: {video_id} -> {video_url}")

    # 1. Set Thumbnail
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            logger.info(f"Setting custom thumbnail: {thumbnail_path}")
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path),
            ).execute()
            logger.info("✅ Thumbnail applied successfully.")
        except Exception as e:
            logger.warning(f"Could not set thumbnail: {e}")

    # 2. Add to Playlist (create playlist if needed)
    playlist_name = meta.get("playlist", "").strip()
    if playlist_name:
        try:
            playlist_id = _get_or_create_playlist(youtube, playlist_name)
            if playlist_id:
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id,
                            },
                        }
                    },
                ).execute()
                logger.info(f"✅ Added video to playlist '{playlist_name}' (ID: {playlist_id}).")
        except Exception as e:
            logger.warning(f"Could not add to playlist '{playlist_name}': {e}")

    # 3. Post Pinned Comment
    comment_text = meta.get("pinned_comment", "").strip()
    comment_id = None
    if comment_text:
        try:
            c_resp = youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": comment_text,
                            }
                        },
                    }
                },
            ).execute()
            comment_id = c_resp.get("id")
            logger.info(f"✅ Comment posted successfully (Comment ID: {comment_id}).")
            logger.info(
                "📌 REMINDER: YouTube Data API v3 does not permit automated comment pinning. "
                "Please open YouTube Studio and pin this comment manually to the top of your video."
            )
        except Exception as e:
            logger.warning(f"Could not post comment: {e}")

    return {
        "success": True,
        "video_id": video_id,
        "video_url": video_url,
        "privacy": privacy_status,
        "playlist": playlist_name,
        "comment_id": comment_id,
    }


def _get_or_create_playlist(youtube, playlist_title: str) -> Optional[str]:
    """Finds an existing playlist by title or creates a new one."""
    try:
        req = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
        while req:
            res = req.execute()
            for item in res.get("items", []):
                if item["snippet"]["title"].strip().lower() == playlist_title.strip().lower():
                    return item["id"]
            req = youtube.playlists().list_next(req, res)

        # Create if not found
        logger.info(f"Playlist '{playlist_title}' not found. Creating new public playlist...")
        create_res = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {"title": playlist_title},
                "status": {"privacyStatus": "public"},
            },
        ).execute()
        return create_res.get("id")
    except Exception as e:
        logger.warning(f"Error querying/creating playlist: {e}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload English Shadowing video to YouTube.")
    parser.add_argument("--video", required=True, help="Path to MP4 video file")
    parser.add_argument("--metadata", required=True, help="Path to video_metadata.json")
    parser.add_argument("--thumbnail", default=None, help="Optional thumbnail image path")
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"], help="Privacy status")
    parser.add_argument("--publish-at", default=None, help="Scheduled publish UTC ISO 8601 string")
    parser.add_argument("--yes", action="store_true", help="Confirmation flag required to execute upload")

    args = parser.parse_args()

    try:
        res = upload_to_youtube(
            video_path=args.video,
            metadata_path=args.metadata,
            thumbnail_path=args.thumbnail,
            publish_at=args.publish_at,
            privacy=args.privacy,
            confirm=args.yes,
        )
        if res.get("success"):
            print(f"Upload complete: {res['video_url']}")
        else:
            print(res.get("message"))
    except Exception as err:
        print(f"Error during upload: {err}", file=sys.stderr)
        sys.exit(1)
