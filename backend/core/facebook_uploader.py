import os
import requests
import json
import time

def is_valid_movie_title(t: str) -> bool:
    if not t or not isinstance(t, str):
        return False
    t_clean = t.strip().lower()
    invalid_keywords = [
        "", "none", "null", "unknown", "untitled", "n/a", "na",
        "extract the movie title from the story", "movie recap", "film recap",
        "movie name", "unnamed", "not mentioned", "not specified"
    ]
    if t_clean in invalid_keywords:
        return False
    if t_clean.startswith("unknown") or t_clean.startswith("[") or t_clean.endswith("]"):
        return False
    return True

class FacebookUploader:
    def __init__(self, page_id: str = None, page_token: str = None):
        self.page_id = page_id or os.getenv("FB_PAGE_ID", "561214384321132")
        self.page_token = page_token or os.getenv("FB_PAGE_ACCESS_TOKEN")
        self.base_url = f"https://graph.facebook.com/v21.0/{self.page_id}/videos"

    def optimize_seo(self, title: str, description: str, tags: list = None, movie_title: str = None) -> tuple:
        """
        Enhances Title & Description with high-retention keywords, explicit Movie Attribution,
        and hashtags tailored for Facebook algorithms. If movie is absent, skips cleanly.
        """
        # 1. Title SEO: Ensure strong genre keywords exist without keyword stuffing
        title_clean = title.strip()
        lower_t = title_clean.lower()
        if not any(k in lower_t for k in ["recap", "explained"]):
            optimized_title = f"{title_clean} | Movie Recap"
        else:
            optimized_title = title_clean

        # Clean placeholders from title if any
        for bad in ["| Unknown Recap", "| [Movie Name] Recap", "| None Recap"]:
            if bad in optimized_title:
                optimized_title = optimized_title.replace(bad, "| Movie Recap")

        has_movie = is_valid_movie_title(movie_title)

        # 2. Hashtag Generator: Curate top-ranking Facebook hashtags
        default_hashtags = ["#MovieRecap", "#ThrillerMovie", "#MovieExplained", "#CrimeThriller", "#MysteryRecap"]
        
        # Add movie-specific hashtag ONLY if valid movie name exists
        if has_movie:
            clean_movie = movie_title.strip()
            m_tag = "#" + "".join([w.capitalize() for w in clean_movie.split() if w.isalnum()])
            if m_tag not in default_hashtags and len(m_tag) > 2:
                default_hashtags.insert(0, m_tag)

        if tags:
            for tag in tags[:8]:
                cleaned = "#" + "".join([w.capitalize() for w in tag.split() if w.isalnum()])
                if cleaned not in default_hashtags and len(cleaned) > 2 and not any(bad in cleaned.lower() for bad in ["unknown", "moviename", "na"]):
                    default_hashtags.append(cleaned)

        hashtag_block = " ".join(default_hashtags[:10])
        
        # 3. Description formatting with prominent Movie Attribution
        desc_clean = description.strip() if description else ""
        if has_movie:
            clean_movie = movie_title.strip()
            if "Movie:" not in desc_clean and "Movie Name:" not in desc_clean and clean_movie.lower() not in desc_clean.lower():
                desc_clean = f"🎬 Movie Name: {clean_movie}\n\n{desc_clean}"

        # Clean any accidental placeholder lines from description
        filtered_lines = []
        for line in desc_clean.split("\n"):
            l_lower = line.lower()
            if ("🎬 movie" in l_lower or "movie name:" in l_lower) and any(bad in l_lower for bad in ["unknown", "[", "]", "n/a", "none"]):
                continue
            filtered_lines.append(line)
        desc_clean = "\n".join(filtered_lines).strip()

        if hashtag_block not in desc_clean:
            optimized_desc = f"{desc_clean}\n\n{hashtag_block}"
        else:
            optimized_desc = desc_clean

        return optimized_title, optimized_desc

    def upload_video(self, video_path: str, title: str, description: str, tags: list = None,
                     chunk_size_mb: int = 25, target_tier1: bool = True, movie_title: str = None) -> dict:
        """
        Uploads long-form videos to Facebook using Meta's Resumable Chunked Upload API.
        
        Features:
        - Feed Targeting: Prioritizes organic distribution to Tier-1 countries (US, UK, CA, AU) 
          WITHOUT blocking or restricting global viewers.
        - SEO Optimization: Automatically embeds keyword badges and high-volume hashtags.
        - Resumable Chunking: Safely uploads videos of any size (300MB - 5GB+).
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size = os.path.getsize(video_path)
        opt_title, opt_desc = self.optimize_seo(title, description, tags, movie_title=movie_title)

        print(f"\n[Facebook Uploader] 🚀 Initializing Resumable Upload for: {os.path.basename(video_path)}")
        print(f"  Page ID          : {self.page_id}")
        print(f"  File Size        : {file_size / (1024 * 1024):.2f} MB")
        print(f"  Optimized Title  : {opt_title}")
        print(f"  Target Demography: Tier 1 (US, GB, CA, AU) Feed-Prioritized")

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

        print(f"  [Session Started] Video ID: {video_id} | Session ID: {upload_session_id}")

        # ── Step 2: Transfer Chunks ───────────────────────────────────────
        chunk_size_bytes = chunk_size_mb * 1024 * 1024
        with open(video_path, "rb") as f:
            while start_offset < file_size:
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

        # ── Step 3: Finish Upload & Publish with Tier-1 Feed Targeting ─────
        finish_payload = {
            "upload_phase": "finish",
            "upload_session_id": upload_session_id,
            "title": opt_title,
            "description": opt_desc,
            "access_token": self.page_token
        }

        # Preferred Audience (News Feed & Watch tab priority) WITHOUT restricting global access
        if target_tier1:
            feed_targeting = {
                "geo_locations": {
                    "countries": ["US", "GB", "CA", "AU"]
                }
            }
            finish_payload["feed_targeting"] = json.dumps(feed_targeting)

        f_res = requests.post(self.base_url, data=finish_payload, timeout=30)
        if f_res.status_code != 200:
            raise RuntimeError(f"Failed to finish Facebook video publish: {f_res.status_code} - {f_res.text}")

        print(f"  [Published] ✅ Success! Facebook Video ID: {video_id}")
        return {
            "success": True,
            "video_id": video_id,
            "page_id": self.page_id,
            "url": f"https://www.facebook.com/reel/{video_id}/"
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
        description=meta.get("description"),
        tags=meta.get("keywords")
    )
    print("\nResult:", result)
