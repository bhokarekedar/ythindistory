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
        # 1. Strip comic sound effects, onomatopoeia, speech bubbles, question marks, and floating graphic symbols
        refined_prompt = re.sub(r'(?i)\b(thought|speech|dialogue)\s+bubbles?\b[^,.;]*', '', refined_prompt)
        refined_prompt = re.sub(r'(?i)\b(question\s+marks?|\?|heart\s+icons?|exclamation\s+marks?)\b[^,.;]*', '', refined_prompt)
        refined_prompt = re.sub(r'(?i)\b(?:with\s+)?(?:a\s+)?(?:big\s+|loud\s+)?(?:snap|crack|boom|pow|bang|crunch|splat|whoosh|sound|pop)\s*(?:lines?|words?|effects?|text|symbols?|bubbles?)?\b', '', refined_prompt)

        # 2. Universal "stick" sanitization:
        # Keep human stick figures as stick figures. Automatically convert any other "stick <subject>" (animal, creature, vehicle, object)
        # into "simple 2D cartoon <subject>" so diffusion models never draw human circular heads or stick limbs on non-humans.
        refined_prompt = re.sub(
            r'(?i)\bstick\s+(?!(?:figures?|humans?|persons?|people|men|man|women|woman|boys?|girls?|guys?|characters?|narrators?|bodies|body|limbs|arms|legs)\b)([a-zA-Z]+)',
            r'simple 2D cartoon \1',
            refined_prompt
        )
        # Sanitize bare "stick humans" to ensure clothed figures instead of naked mannequins
        refined_prompt = re.sub(r'(?i)\bstick humans?\b', 'stick figures wearing plain shirts', refined_prompt)
        p_lower = refined_prompt.lower()
        if any(k in p_lower for k in ["stick figure", "stick-figure", "stick-comic", "ms paint", "basically primitive", "webcomic"]):
            # Universal, high-impact constraints applicable across any topic, script, or genre
            rules = []
            if "zero shading" not in p_lower:
                rules.append("Low-effort 2D MS Paint style, thick black outlines, flat bucket-fill colors. ABSOLUTELY NO SHADING, NO GRADIENTS, NO 3D DEPTH.")
            rules.append("HUMAN CHARACTERS ONLY: Human stick figures MUST have an uncolored, pure blank white circular head (#FFFFFF) with two tiny black dot eyes, wearing a plain white shirt and long black stick legs. The figure stands upright on two straight black stick legs. ABSOLUTELY ZERO UNDERWEAR, ZERO UNDERPANTS, ZERO NAKED PELVIS, ZERO BROKEN LIMBS.")
            rules.append("ANIMALS & CREATURES: All non-human creatures, animals, pets, and wildlife MUST have authentic animal heads and bodies (proper snout, muzzle, whiskers, ears, beak, fur, paws, flippers, or hooves). ANIMALS NEVER HAVE CIRCULAR HUMAN STICK HEADS, NEVER HAVE HUMAN MOUTHS, AND NEVER WEAR SHIRTS. Zero human-animal hybrids, zero centaurs.")
            rules.append("PHYSICAL GRAVITY & PERCHING: All subjects obey gravity. Land creatures must have feet/paws on solid ground. Any creature in mid-air MUST be actively flying with wings spread wide. Non-flying birds must be perched with claws gripping a shoulder, branch, or ground. ABSOLUTELY ZERO HOVERING IN MID-AIR, ZERO STANDING ON NOTHING.")
            rules.append("DISTANCED 16:9 FRAMING: Camera at a distance, subjects vertically centered on ground with generous 30% empty sky headroom above, full bodies visible in frame. Never draw tall subjects touching borders.")
            rules.append("ABSOLUTELY ZERO TEXT, ZERO WORDS, ZERO LETTERS, ZERO ONOMATOPOEIA, ZERO SOUND EFFECTS, ZERO COMIC LETTERING, ZERO SPEECH BUBBLES, ZERO FLOATING SYMBOLS.")

            suffix = " " + " ".join(rules)
            # Ensure total prompt stays safely under Cloudflare's 2048 character limit
            if len(refined_prompt) + len(suffix) > 2000:
                avail = 2000 - len(suffix)
                refined_prompt = refined_prompt[:avail].rsplit(' ', 1)[0]
            refined_prompt += suffix

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
                    if hasattr(e, "read"):
                        try:
                            err_str += f" - Response: {e.read().decode('utf-8')[:300]}"
                        except Exception:
                            pass
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

            arr = np.array(img.convert("RGB"))

            # 1. Detect Character / Subject Presence
            # Human characters in webcomic style have uncolored paper-white heads/shirts and/or orange hair
            white = np.all(arr > 230, axis=-1)
            orange = (arr[:, :, 0] > 175) & (arr[:, :, 1] < 135) & (arr[:, :, 2] < 85)
            char_mask = white | orange

            # Exclude rows where white covers > 50% of width (pure white background)
            row_char_counts = np.sum(char_mask, axis=1)
            char_rows = np.where((row_char_counts > 10) & (row_char_counts < 0.50 * w))[0]

            if len(char_rows) > 0:
                # Subject detected!
                char_top = int(char_rows[0])
                char_bottom = int(char_rows[-1])
                # Character head/hair starts slightly above detected torso/face
                head_top = max(0, char_top - 40)
                # Legs and ground contact extend below torso
                feet_bottom = min(h, char_bottom + 180)

                # Center the 16:9 crop window vertically around the character
                center_y = (head_top + feet_bottom) // 2
                top = center_y - crop_h // 2

                # Enforce headroom: NEVER scalp the head
                if top > max(0, head_top - 25):
                    top = max(0, head_top - 25)

                # Enforce ground/feet: if there is headroom to spare, shift down to preserve feet
                if feet_bottom > top + crop_h and top < max(0, head_top - 25):
                    shift = min(feet_bottom - (top + crop_h), (head_top - 25) - top)
                    top += max(0, shift)
            else:
                # 2. General Scenery / Animal Detection
                # Measure content divergence from top-corner background
                gray = np.array(img.convert("L"))
                bg_val = float(np.mean(gray[:25, :25]))
                diff = np.abs(gray.astype(float) - bg_val)
                row_density = np.sum(diff > 25, axis=1)
                content_rows = np.where(row_density > 20)[0]

                if len(content_rows) > 0 and content_rows[0] > 60:
                    # Clear empty sky exists at top: honor headroom
                    desired_top = max(0, int(content_rows[0]) - 35)
                    center_y = (int(content_rows[0]) + int(content_rows[-1])) // 2
                    top = center_y - crop_h // 2
                    if top > desired_top:
                        top = desired_top
                else:
                    # Full environment scene (trees, room, forest, landscape touching top):
                    # Natural cinematic crop positioned to frame the lower-middle action/ground
                    top = int(0.50 * (h - crop_h))

            # Clamp securely within [0, h - crop_h]
            top = max(0, min(h - crop_h, int(top)))
            cropped = img.crop((0, top, crop_w, top + crop_h))
            final_img = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
        else:
            # Image is wider than 16:9. Crop sides to center fit.
            crop_w = int(h * target_aspect)
            left = (w - crop_w) // 2
            cropped = img.crop((left, 0, left + crop_w, h))
            final_img = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

        final_img.save(output_path, "JPEG", quality=95)
