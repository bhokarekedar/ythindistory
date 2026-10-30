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
        self.cooldowns = {i: 0.0 for i in range(len(self.api_keys))}
        if self.api_keys:
            self.client = Groq(api_key=self.api_keys[0])
            print(f"  [Groq Pool] 🔑 Initialized GroqProvider with {len(self.api_keys)} API key(s) in active rotation pool.")
        else:
            self.client = None
            print("  [Groq Pool] ⚠️ Initialized GroqProvider without valid API keys.")

    def _parse_cooldown_seconds(self, err_str: str) -> float:
        import re
        m_min_sec = re.search(r'try again in\s+(\d+(?:\.\d+)?)m\s*(\d+(?:\.\d+)?)s', err_str, re.IGNORECASE)
        if m_min_sec:
            return float(m_min_sec.group(1)) * 60 + float(m_min_sec.group(2))
        m_min = re.search(r'try again in\s+(\d+(?:\.\d+)?)m\b', err_str, re.IGNORECASE)
        if m_min:
            return float(m_min.group(1)) * 60
        m_sec = re.search(r'try again in\s+(\d+(?:\.\d+)?)s', err_str, re.IGNORECASE)
        if m_sec:
            return float(m_sec.group(1))
        return 30.0

    def translate_segments(self, segments, system_prompt: str, context: str = "", target_language: str = "hindi") -> list:
        import time
        if not self.client or not self.api_keys:
            print("  [Groq Provider] Error: No Groq API keys available to process request.")
            return []
            
        user_content = f"Context (do not translate this): {context}\n\nSegments to translate/rewrite:\n"
        user_content += json.dumps([{"id": s["id"], "text": s.get("text", "")} for s in segments], ensure_ascii=False)
        
        system_prompt += f"\n\nIMPORTANT: You must output ONLY a valid JSON object with a single key 'translations', containing a list of objects with 'id' and 'translated_text'. Exactly {len(segments)} objects must be returned, corresponding 1-to-1 to each input id. NEVER skip, combine, or omit any segment ID. Do not output markdown code blocks or any other text."

        last_exception = None
        max_total_attempts = len(self.api_keys) * 2  # Allows rotating and waiting for soonest unlock
        
        for attempt in range(max_total_attempts):
            now = time.time()
            
            # Check if current key is still on cooldown
            if self.cooldowns.get(self.current_idx, 0) > now:
                # Find an unlocked key if one is ready
                unlocked_keys = [i for i in range(len(self.api_keys)) if self.cooldowns.get(i, 0) <= now]
                if unlocked_keys:
                    self.current_idx = unlocked_keys[0]
                    self.client = Groq(api_key=self.api_keys[self.current_idx])
                else:
                    # All keys are on cooldown: wait for the one that unlocks soonest
                    soonest_idx = min(self.cooldowns, key=self.cooldowns.get)
                    wait_sec = max(1.0, self.cooldowns[soonest_idx] - now)
                    if wait_sec <= 600:  # Respect cooldown up to 10 minutes
                        print(f"\n  [Groq Pool] ⏳ All {len(self.api_keys)} keys are in cooldown. Waiting {int(wait_sec)}s for Key #{soonest_idx + 1} to unlock (all progress is safely saved on disk)...")
                        remaining = wait_sec + 1
                        while remaining > 0:
                            chunk = min(15.0, remaining)
                            time.sleep(chunk)
                            remaining -= chunk
                        self.current_idx = soonest_idx
                        self.client = Groq(api_key=self.api_keys[self.current_idx])
                    else:
                        print(f"\n  [Groq Pool] ⚠️ All keys on prolonged cooldown (>10m). Progress is safely saved on disk. You can restart anytime to resume.")
                        break

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
                last_exception = e
                
                if is_rate_limit:
                    cd_sec = self._parse_cooldown_seconds(str(e))
                    self.cooldowns[self.current_idx] = time.time() + cd_sec
                    print(f"\n  [Groq Pool] ⚠️ Key #{self.current_idx + 1} reached quota/limit (429). Cooldown: {int(cd_sec)}s.")
                    
                    # Search for any other key currently ready
                    now = time.time()
                    available = [i for i in range(len(self.api_keys)) if i != self.current_idx and self.cooldowns.get(i, 0) <= now]
                    if available:
                        self.current_idx = available[0]
                        self.client = Groq(api_key=self.api_keys[self.current_idx])
                        print(f"  [Groq Pool] 🔄 Switching to unlocked Key #{self.current_idx + 1} of {len(self.api_keys)} immediately.")
                        continue
                    else:
                        # In the next iteration, the pool will wait for the soonest unlocking key
                        continue
                else:
                    raise e
                    
        if last_exception:
            raise last_exception
        return []
