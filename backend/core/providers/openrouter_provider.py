import os
import json
import httpx
from core.providers.base import LLMProvider

class OpenRouterProvider(LLMProvider):
    def __init__(self, model: str = "openrouter/auto"):
        self.model = model
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def translate_segments(self, segments, system_prompt: str, context: str = "") -> list:
        if not self.api_key:
            print("Warning: OPENROUTER_API_KEY not set.")
            return []

        user_content = f"Context (do not translate this): {context}\n\nSegments to translate:\n"
        user_content += json.dumps([{"id": s["id"], "text": s["text"]} for s in segments], ensure_ascii=False)
        
        system_prompt += "\n\nIMPORTANT: You must output ONLY a valid JSON object with a single key 'translations', containing a list of objects with 'id' and 'hindi'. Do not output markdown code blocks or any other text."

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:8000",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "response_format": {"type": "json_object"}
        }

        try:
            with httpx.Client() as client:
                response = client.post(self.url, headers=headers, json=payload, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return parsed.get("translations", [])
        except Exception as e:
            print("Failed to call OpenRouter:", str(e))
            return []
