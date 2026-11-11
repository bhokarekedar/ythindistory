import os
import json
import urllib.request
from typing import Optional

class CloudflareImageGenerator:
    """
    Generates high-quality AI images using Cloudflare Workers AI
    Model: @cf/black-forest-labs/flux-1-schnell
    """
    def __init__(self, api_key: Optional[str] = None, account_id: Optional[str] = None):
        self.api_key = api_key or os.getenv("CLOUDFARE_API_KEY")
        self.account_id = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.model = "@cf/black-forest-labs/flux-1-schnell"
        
        if not self.account_id and self.api_key:
            self.account_id = self._auto_discover_account_id()

    def _auto_discover_account_id(self) -> Optional[str]:
        try:
            req = urllib.request.Request(
                "https://api.cloudflare.com/client/v4/accounts",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("result"):
                    return data["result"][0]["id"]
        except Exception as e:
            print(f"  [Cloudflare] Failed to auto-discover account ID: {e}")
        return None

    def generate_image(self, prompt: str, output_path: str, max_retries: int = 3, target_width: int = 1920, target_height: int = 1080) -> Optional[str]:
        """
        Generates an image from prompt and writes it directly to output_path
        in true 16:9 widescreen YouTube longform resolution (1920x1080).
        Returns output_path on success, None on failure.
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # If image already generated, check if it's already target resolution
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            try:
                from PIL import Image
                with Image.open(output_path) as chk:
                    if chk.size == (target_width, target_height):
                        return output_path
                    else:
                        # Existing image was square (e.g. 1024x1024), convert it now!
                        self._save_as_16_9(chk, output_path, target_width, target_height)
                        print(f"  [Image Processor] 🔄 Upgraded existing image to 1920x1080: {output_path}")
                        return output_path
            except Exception:
                pass

        if not self.api_key or not self.account_id:
            print("  [Cloudflare] Error: Missing CLOUDFARE_API_KEY or CLOUDFLARE_ACCOUNT_ID")
            return None

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
        payload = json.dumps({"prompt": prompt}).encode("utf-8")

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=40) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("success") and "result" in data and "image" in data["result"]:
                        import base64
                        import io
                        from PIL import Image
                        image_bytes = base64.b64decode(data["result"]["image"])
                        raw_img = Image.open(io.BytesIO(image_bytes))
                        self._save_as_16_9(raw_img, output_path, target_width, target_height)
                        print(f"  [Cloudflare AI] ✅ Image generated in 1920x1080: {output_path}")
                        return output_path
                    else:
                        print(f"  [Cloudflare AI] API error: {data.get('errors')}")
            except Exception as e:
                print(f"  [Cloudflare AI] Attempt {attempt+1} failed: {e}")
                import time
                time.sleep(2)

        return None

    def _save_as_16_9(self, img, output_path: str, target_width: int = 1920, target_height: int = 1080):
        from PIL import Image
        w, h = img.size
        target_aspect = target_width / target_height
        current_aspect = w / h
        if current_aspect > target_aspect:
            new_w = int(h * target_aspect)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        else:
            new_h = int(w / target_aspect)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))
        
        resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        if resized.mode in ("RGBA", "P"):
            resized = resized.convert("RGB")
        resized.save(output_path, "JPEG", quality=95)
