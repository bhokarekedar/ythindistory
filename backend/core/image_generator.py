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

    def generate_image(self, prompt: str, output_path: str, max_retries: int = 3, target_width: int = 1920, target_height: int = 1080, force: bool = False) -> Optional[str]:
        """
        Generates an image from prompt and writes it directly to output_path
        in true 16:9 widescreen YouTube longform resolution (1920x1080).
        Automatically rotates across Cloudflare accounts when rate limits / daily quotas are reached.
        Returns output_path on success, None on failure.
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # If not forcing regeneration and image already exists at target resolution, return it
        if not force and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
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

        # Pipeline Auto-Enforcement for Stick-Comic & MS Paint Style
        import re
        refined_prompt = prompt
        # Clean out speech/thought bubble requests that cause garbled text hallucinations
        refined_prompt = re.sub(r'(?i)\b(thought|speech|dialogue)\s+bubbles?\b[^,.;]*', '', refined_prompt)
        p_lower = refined_prompt.lower()
        if any(k in p_lower for k in ["stick figure", "stick-figure", "stick-comic", "ms paint", "basically primitive", "webcomic"]):
            # 1. Enforce strict MS Paint aesthetics (Kill FLUX's 3D/Shading bias)
            if "zero shading" not in p_lower:
                refined_prompt += " ABSOLUTELY NO SHADING, NO GRADIENTS, NO 3D DEPTH. Must look like a low-effort MS Paint drawing with thick, unpolished black outlines and flat bucket-fill colors."

            # 2. Enforce stick figure anatomy strictly
            if "zero realistic" not in p_lower:
                refined_prompt += " All characters MUST be basic 2D minimalist stick figures with pure white circular heads, black dot eyes, and single-line stick limbs. Zero realistic human anatomy, zero flesh tones, zero extra people."

            # 3. Enforce wide camera framing
            if "headroom" not in p_lower and "wide shot" not in p_lower:
                refined_prompt += " Extreme wide long shot, centered 16:9 composition with ample empty headroom above and wide ground below, entire bodies visible in middle vertical third."

            # 4. Enforce flat animal style & full bodies (no severed heads)
            refined_prompt += " All characters and animals MUST be drawn full body with complete head, torso, and legs. Zero floating or severed heads."

            # 5. Strict negative constraint: Zero text, zero speech bubbles
            refined_prompt += " ABSOLUTELY ZERO TEXT, ZERO WORDS, ZERO LETTERS, ZERO SPEECH BUBBLES, ZERO THOUGHT BUBBLES. Pure visual drawing with no written text."

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

        if current_aspect < target_aspect:
            # Image is taller than 16:9 (e.g. 1024x1024 square from FLUX).
            # Crop vertically to a pristine 16:9 widescreen frame without any edge smears.
            crop_h = int(w / target_aspect)
            crop_w = w

            # Detect content bounds
            x_margin = int(0.10 * w)
            gray = np.array(img.convert("L"))
            inner_gray = gray[:, x_margin:w - x_margin]

            bg_val = float(np.mean(gray[:25, :25]))
            diff = np.abs(inner_gray.astype(float) - bg_val)
            content_rows = np.where(np.max(diff, axis=1) > 25)[0]

            if len(content_rows) > 0:
                top_content_y = content_rows[0]
                bottom_content_y = content_rows[-1]
                subject_height = bottom_content_y - top_content_y

                # If subject fits inside 16:9 crop height with margins, preserve headroom & center
                if subject_height + 50 <= crop_h:
                    desired_top = max(0, top_content_y - 40)
                    center_y = (top_content_y + bottom_content_y) // 2
                    top = center_y - crop_h // 2
                    if top > desired_top:
                        top = desired_top
                    top = max(0, min(h - crop_h, top))
                else:
                    # Full environment scene (trees, room, city) or tall character:
                    # Natural cinematic center crop
                    top = (h - crop_h) // 2
                    # If there is clear empty sky/headroom at the top, respect it
                    if top_content_y > 30 and top < top_content_y - 30:
                        top = min(top_content_y - 30, h - crop_h)
                    top = max(0, min(h - crop_h, top))
            else:
                top = (h - crop_h) // 2

            cropped = img.crop((0, top, crop_w, top + crop_h))
            final_img = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
        else:
            # Image is wider than 16:9. Crop sides to center fit.
            crop_w = int(h * target_aspect)
            left = (w - crop_w) // 2
            cropped = img.crop((left, 0, left + crop_w, h))
            final_img = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

        final_img.save(output_path, "JPEG", quality=95)
