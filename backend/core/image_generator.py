import os
import json
import urllib.request
from typing import Optional

class CloudflareImageGenerator:
    """
    Generates high-quality AI images using Cloudflare Workers AI with multi-account rotation.
    Model: @cf/black-forest-labs/flux-1-schnell
    """
    def __init__(self, api_key: Optional[str] = None, account_id: Optional[str] = None):
        self.model = "@cf/black-forest-labs/flux-1-schnell"
        self.accounts = []

        # Account 1 (Primary)
        k1 = api_key or os.getenv("CLOUDFARE_API_KEY")
        a1 = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID")
        if k1 and a1:
            self.accounts.append({"key": k1, "account_id": a1, "name": "Cloudflare Account #1"})

        # Account 2 (Secondary rotation)
        k2 = os.getenv("CLOUDFARE_API_KEY_TWO")
        a2 = os.getenv("CLOUDFLARE_ACCOUNT_ID_TWO")
        if k2 and a2:
            self.accounts.append({"key": k2, "account_id": a2, "name": "Cloudflare Account #2"})

        # Additional Accounts (if added)
        acc_nums = {"THREE": 3, "FOUR": 4, "FIVE": 5}
        for suffix, num in acc_nums.items():
            ks = os.getenv(f"CLOUDFARE_API_KEY_{suffix}")
            as_ = os.getenv(f"CLOUDFLARE_ACCOUNT_ID_{suffix}")
            if ks and as_:
                self.accounts.append({"key": ks, "account_id": as_, "name": f"Cloudflare Account #{num}"})

        self.active_idx = 0
        print(f"  [Cloudflare Image Pool] 🔑 Initialized with {len(self.accounts)} active Cloudflare account(s).")

    def generate_image(self, prompt: str, output_path: str, max_retries: int = 3, target_width: int = 1920, target_height: int = 1080) -> Optional[str]:
        """
        Generates an image from prompt and writes it directly to output_path
        in true 16:9 widescreen YouTube longform resolution (1920x1080).
        Automatically rotates across Cloudflare accounts when rate limits / daily quotas are reached.
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

        if not self.accounts:
            print("  [Cloudflare] Error: No Cloudflare accounts configured in .env")
            return None

        # Enforce stick-comic consistency for animals if in stick-figure MS Paint mode
        refined_prompt = prompt
        p_lower = prompt.lower()
        if any(k in p_lower for k in ["stick figure", "stick-figure", "stick-comic", "ms paint"]):
            animal_keywords = ["animal", "elephant", "dog", "cat", "monkey", "horse", "bear", "lion", "tiger", "bird", "rabbit", "creature", "pet"]
            if any(ak in p_lower for ak in animal_keywords):
                if "zero gray shading" not in p_lower and "pure solid flat white body" not in p_lower:
                    refined_prompt += " Crucially, all animals must be drawn in the same stick comic style: pure flat solid white body fill, thin black stick legs, bold black outlines, zero 3D shading, zero gray color, zero fur texture, completely flat 2D MS Paint webcomic."

        payload = json.dumps({"prompt": refined_prompt}).encode("utf-8")

        # Try across all available accounts in rotation
        for _ in range(len(self.accounts)):
            acc = self.accounts[self.active_idx]
            key = acc["key"]
            acc_id = acc["account_id"]
            acc_name = acc["name"]
            url = f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/ai/run/{self.model}"

            for attempt in range(max_retries):
                try:
                    req = urllib.request.Request(
                        url,
                        data=payload,
                        headers={
                            "Authorization": f"Bearer {key}",
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
                            print(f"  [Cloudflare AI] ✅ Image generated ({acc_name}) in 1920x1080: {output_path}")
                            return output_path
                        else:
                            print(f"  [Cloudflare AI] API error ({acc_name}): {data.get('errors')}")
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "4006" in err_str or "Too Many Requests" in err_str:
                        print(f"  [Cloudflare AI] ⚠️ {acc_name} reached quota / 429 rate limit. Rotating to next account...")
                        self.active_idx = (self.active_idx + 1) % len(self.accounts)
                        break  # Break retry loop to try next account immediately
                    print(f"  [Cloudflare AI] Attempt {attempt+1} failed on {acc_name}: {e}")
                    import time
                    time.sleep(2)

        return None

    def _save_as_16_9(self, img, output_path: str, target_width: int = 1920, target_height: int = 1080):
        from PIL import Image
        import numpy as np

        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        target_aspect = target_width / target_height
        current_aspect = w / h

        # If image is squarish or taller than 16:9 (common for 1024x1024 AI outputs)
        # fit vertically so NO heads or feet get cropped off, and extend background horizontally
        if current_aspect < target_aspect:
            scale = target_height / h
            new_w = int(w * scale)
            scaled = img.resize((new_w, target_height), Image.Resampling.LANCZOS)
            scaled_arr = np.array(scaled)

            canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
            x_offset = (target_width - new_w) // 2

            # Place image in horizontal center
            canvas[:, x_offset:x_offset + new_w] = scaled_arr

            # Seamlessly extend left and right background edges
            left_edge = scaled_arr[:, 0:1, :]
            canvas[:, :x_offset] = np.repeat(left_edge, x_offset, axis=1)

            right_edge = scaled_arr[:, -1:, :]
            r_width = target_width - (x_offset + new_w)
            if r_width > 0:
                canvas[:, x_offset + new_w:] = np.repeat(right_edge, r_width, axis=1)

            final_img = Image.fromarray(canvas)
        else:
            # If image is wider than 16:9, crop sides
            new_w = int(h * target_aspect)
            left = (w - new_w) // 2
            cropped = img.crop((left, 0, left + new_w, h))
            final_img = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

        final_img.save(output_path, "JPEG", quality=95)
