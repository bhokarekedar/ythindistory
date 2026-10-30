import os
import json
from groq import Groq
from core.providers.base import LLMProvider

class GroqProvider(LLMProvider):
    def __init__(self, model: str = "qwen/qwen3.8-27b", api_key: str = None, api_keys: list = None):
        self.model = model
        
        # Collect all valid, unique Groq keys into a rotation pool
        keys = []
        if api_keys:
            keys.extend([k for k in api_keys if k])
        if api_key and api_key not in keys:
            keys.append(api_key)
            
        env_keys = [
            os.environ.get("GROQ_API_KEY"),
            os.environ.get("GROQ_API_KEY_TWO"),
            os.environ.get("GROQ_API_KEY_THREE"),
            os.environ.get("GROQ_API_KEY_FOUR")
        ]
        for ek in env_keys:
            if ek and ek not in keys:
                keys.append(ek)
                
        self.api_keys = keys
        self.current_idx = 0
        if self.api_keys:
            self.client = Groq(api_key=self.api_keys[0])
            print(f"  [Groq Pool] 🔑 Initialized GroqProvider with {len(self.api_keys)} API key(s) in active rotation pool.")
        else:
            self.client = None
            print("  [Groq Pool] ⚠️ Initialized GroqProvider without valid API keys.")

    def translate_segments(self, segments, system_prompt: str, context: str = "", target_language: str = "hindi") -> list:
        if not self.client or not self.api_keys:
            print("  [Groq Provider] Error: No Groq API keys available to process request.")
            return []
        user_content = f"Context (do not translate this): {context}\n\nSegments to translate/rewrite:\n"
        user_content += json.dumps([{"id": s["id"], "text": s.get("text", "")} for s in segments], ensure_ascii=False)
        
        system_prompt += f"\n\nIMPORTANT: You must output ONLY a valid JSON object with a single key 'translations', containing a list of objects with 'id' and 'translated_text'. Exactly {len(segments)} objects must be returned, corresponding 1-to-1 to each input id. NEVER skip, combine, or omit any segment ID. Do not output markdown code blocks or any other text."

        last_exception = None
        # Attempt across available keys if rate limits are hit
        for attempt in range(len(self.api_keys)):
            try:
                response = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    model=self.model,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )

                content = response.choices[0].message.content
                data = json.loads(content)
                translations = data.get("translations", [])
                if not translations:
                    print(f"Warning: Groq returned valid JSON but no 'translations' list. Raw: {content}")
                return translations
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate_limit" in err_str or "tokens per day" in err_str or "tpd" in err_str
                
                if is_rate_limit and len(self.api_keys) > 1:
                    prev_idx = self.current_idx
                    self.current_idx = (self.current_idx + 1) % len(self.api_keys)
                    next_key = self.api_keys[self.current_idx]
                    print(f"\n  [Groq Pool] ⚠️ Key #{prev_idx + 1} reached token quota (429)! Automatically rotating to Key #{self.current_idx + 1} of {len(self.api_keys)}...")
                    self.client = Groq(api_key=next_key)
                    last_exception = e
                    continue
                else:
                    raise e
                    
        if last_exception:
            raise last_exception
        return []
