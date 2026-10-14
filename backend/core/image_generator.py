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

    def generate_image(self, prompt: str, output_path: str, max_retries: int = 3) -> Optional[str]:
        """
        Generates an image from prompt and writes it directly to output_path.
        Returns output_path on success, None on failure.
        """
        if not self.api_key or not self.account_id:
            print("  [Cloudflare] Error: Missing CLOUDFARE_API_KEY or CLOUDFLARE_ACCOUNT_ID")
            return None

        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # If image already generated, return cached path
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return output_path

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
                        image_bytes = base64.b64decode(data["result"]["image"])
                        with open(output_path, "wb") as f:
                            f.write(image_bytes)
                        print(f"  [Cloudflare AI] ✅ Image generated: {output_path}")
                        return output_path
                    else:
                        print(f"  [Cloudflare AI] API error: {data.get('errors')}")
            except Exception as e:
                print(f"  [Cloudflare AI] Attempt {attempt+1} failed: {e}")
                import time
                time.sleep(2)

        return None
