import os
import json
import time
from typing import Dict, Any, List, Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

class YouTubePublisher:
    """
    Automated YouTube Shorts publisher supporting direct Google OAuth2 Data API v3.
    """

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.data_dir = os.path.join(base_dir, "data")
        else:
            self.data_dir = data_dir

        os.makedirs(self.data_dir, exist_ok=True)
        self.token_file = os.path.join(self.data_dir, "youtube_token.json")
        self.client_secrets_file = os.path.join(self.data_dir, "client_secrets.json")

    def authenticate_local(self, port: int = 8088) -> Dict[str, Any]:
        """
        Launches local server OAuth flow to authorize and connect the YouTube channel.
        Opens Google's sign-in page in the browser and saves youtube_token.json.
        """
        if not os.path.exists(self.client_secrets_file):
            return {
                "success": False,
                "error": "client_secrets_file_missing",
                "message": f"client_secrets.json not found. Please place your Google OAuth file into {self.data_dir}/client_secrets.json"
            }

        try:
            flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=port, prompt="consent", access_type="offline")

            with open(self.token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

            status = self.get_auth_status()
            status["success"] = True
            return status
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"OAuth authorization failed: {str(e)}"
            }

    def get_auth_status(self) -> Dict[str, Any]:
        """Checks if there is an active authenticated YouTube session."""
        if not os.path.exists(self.token_file):
            return {
                "connected": False,
                "has_client_secrets": os.path.exists(self.client_secrets_file),
                "message": "YouTube not connected. Add client_secrets.json to connect your channel."
            }

        try:
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self.token_file, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())

            if creds and creds.valid:
                youtube = build("youtube", "v3", credentials=creds)
                # Fetch channel info
                ch_req = youtube.channels().list(part="snippet", mine=True)
                ch_res = ch_req.execute()
                items = ch_res.get("items", [])
                if items:
                    snippet = items[0].get("snippet", {})
                    return {
                        "connected": True,
                        "channel_id": items[0].get("id"),
                        "channel_title": snippet.get("title"),
                        "channel_thumb": snippet.get("thumbnails", {}).get("default", {}).get("url"),
                        "message": f"Connected to YouTube channel '{snippet.get('title')}'"
                    }
                return {
                    "connected": True,
                    "channel_title": "Authorized Channel",
                    "message": "Connected to YouTube channel."
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "has_client_secrets": os.path.exists(self.client_secrets_file),
                "message": f"Authentication check failed: {str(e)}"
            }

        return {
            "connected": False,
            "has_client_secrets": os.path.exists(self.client_secrets_file),
            "message": "Credentials expired or invalid."
        }

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy_status: str = "unlisted",
        category_id: str = "24"  # Entertainment
    ) -> Dict[str, Any]:
        """
        Uploads a vertical short video to YouTube.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found at: {video_path}")

        # Ensure #Shorts is in the title for vertical shorts algorithmic shelf
        formatted_title = title.strip()
        if "#shorts" not in formatted_title.lower():
            if len(formatted_title) <= 90:
                formatted_title = f"{formatted_title} #Shorts"

        clean_tags = [t.strip("# ") for t in (tags or []) if t.strip("# ")]
        if "Shorts" not in clean_tags:
            clean_tags.append("Shorts")

        # Check authentication
        if not os.path.exists(self.token_file):
            # Development fallback / test mode if credentials not configured yet
            print(f"[YouTubePublisher] Notice: YouTube OAuth credentials not found at {self.token_file}.")
            return {
                "success": False,
                "requires_auth": True,
                "message": "YouTube channel not connected. Please provide Google OAuth client_secrets.json to enable direct publishing.",
                "video_file": os.path.basename(video_path),
                "preview_metadata": {
                    "title": formatted_title,
                    "description": description,
                    "tags": clean_tags,
                    "privacy": privacy_status
                }
            }

        try:
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self.token_file, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())

            youtube = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "title": formatted_title[:100],
                    "description": description,
                    "tags": clean_tags[:30],
                    "categoryId": category_id
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(
                video_path,
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024*1024*5
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            print(f"[YouTubePublisher] Uploading '{formatted_title}' ({os.path.getsize(video_path)} bytes)...")
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"[YouTubePublisher] Upload progress: {int(status.progress() * 100)}%")

            uploaded_id = response.get("id")
            video_url = f"https://www.youtube.com/watch?v={uploaded_id}"
            shorts_url = f"https://www.youtube.com/shorts/{uploaded_id}"

            print(f"[YouTubePublisher] Video uploaded successfully: {shorts_url}")
            return {
                "success": True,
                "video_id": uploaded_id,
                "video_url": video_url,
                "shorts_url": shorts_url,
                "title": formatted_title,
                "privacy_status": privacy_status
            }
        except Exception as e:
            print(f"[YouTubePublisher] Upload failed: {e}")
            raise RuntimeError(f"YouTube upload error: {str(e)}")

