import os
import requests
import json
import time

class FacebookUploader:
    def __init__(self, page_id: str = None, page_token: str = None):
        self.page_id = page_id or os.getenv("FB_PAGE_ID", "561214384321132")
        self.page_token = page_token or os.getenv("FB_PAGE_ACCESS_TOKEN")
        self.base_url = f"https://graph.facebook.com/v21.0/{self.page_id}/videos"

    def upload_video(self, video_path: str, title: str, description: str, chunk_size_mb: int = 25) -> dict:
        """
        Uploads long-form videos to a Facebook Page using Meta's Resumable Chunked Upload API.
        Handles videos of any file size without hitting HTTP 413 Payload Too Large limits.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size = os.path.getsize(video_path)
        print(f"\n[Facebook Uploader] 🚀 Initializing Resumable Upload for: {os.path.basename(video_path)}")
        print(f"  Page ID   : {self.page_id}")
        print(f"  File Size : {file_size / (1024 * 1024):.2f} MB")
        print(f"  Title     : {title}")

        # ── Step 1: Start Upload Session ──────────────────────────────────
        start_payload = {
            "upload_phase": "start",
            "file_size": file_size,
            "access_token": self.page_token
        }
        res = requests.post(self.base_url, data=start_payload, timeout=30)
        if res.status_code != 200:
            raise RuntimeError(f"Failed to start Facebook upload session: {res.status_code} - {res.text}")

        session_data = res.json()
        video_id = session_data.get("video_id")
        upload_session_id = session_data.get("upload_session_id")
        start_offset = int(session_data.get("start_offset", 0))
        end_offset = int(session_data.get("end_offset", file_size))

        print(f"  [Session Started] Video ID: {video_id} | Session ID: {upload_session_id}")

        # ── Step 2: Transfer Chunks ───────────────────────────────────────
        chunk_size_bytes = chunk_size_mb * 1024 * 1024
        with open(video_path, "rb") as f:
            while start_offset < file_size:
                # Meta suggests an end_offset, but we can send up to chunk_size_bytes
                send_len = min(chunk_size_bytes, file_size - start_offset)
                f.seek(start_offset)
                chunk_data = f.read(send_len)

                pct = (start_offset / file_size) * 100
                print(f"  [Uploading] {pct:.1f}% ({start_offset / (1024*1024):.1f}MB / {file_size / (1024*1024):.1f}MB)...")

                transfer_data = {
                    "upload_phase": "transfer",
                    "upload_session_id": upload_session_id,
                    "start_offset": start_offset,
                    "access_token": self.page_token
                }
                files = {
                    "video_file_chunk": ("chunk.mp4", chunk_data, "application/octet-stream")
                }

                retries = 3
                success = False
                for attempt in range(retries):
                    try:
                        t_res = requests.post(self.base_url, data=transfer_data, files=files, timeout=120)
                        if t_res.status_code == 200:
                            t_json = t_res.json()
                            start_offset = int(t_json.get("start_offset"))
                            end_offset = int(t_json.get("end_offset"))
                            success = True
                            break
                        else:
                            print(f"  [Chunk Warning] Attempt {attempt+1} failed: {t_res.status_code} {t_res.text}")
                            time.sleep(3)
                    except Exception as e:
                        print(f"  [Chunk Error] Attempt {attempt+1} exception: {e}")
                        time.sleep(3)

                if not success:
                    raise RuntimeError(f"Failed to transfer chunk at offset {start_offset}")

        print("  [Transfer Complete] 100% of video bytes uploaded successfully!")

        # ── Step 3: Finish Upload & Publish ───────────────────────────────
        finish_payload = {
            "upload_phase": "finish",
            "upload_session_id": upload_session_id,
            "title": title,
            "description": description,
            "access_token": self.page_token
        }
        f_res = requests.post(self.base_url, data=finish_payload, timeout=30)
        if f_res.status_code != 200:
            raise RuntimeError(f"Failed to finish Facebook video publish: {f_res.status_code} - {f_res.text}")

        finish_data = f_res.json()
        print(f"  [Published] ✅ Success! Facebook Video ID: {video_id}")
        return {
            "success": True,
            "video_id": video_id,
            "page_id": self.page_id,
            "url": f"https://www.facebook.com/{self.page_id}/videos/{video_id}"
        }

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    video_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/output/yFNP-yfIBlE/yFNP-yfIBlE_final.mp4"
    meta_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/output/yFNP-yfIBlE/yFNP-yfIBlE_metadata.json"
    
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
        
    uploader = FacebookUploader()
    result = uploader.upload_video(
        video_path=video_path,
        title=meta.get("title"),
        description=meta.get("description")
    )
    print("\nResult:", result)
