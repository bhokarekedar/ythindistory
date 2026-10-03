import os
import json
from groq import Groq
from core.providers.base import LLMProvider

class GroqProvider(LLMProvider):
    def __init__(self, model: str = "llama-3.1-70b-versatile", api_key: str = None):
        self.model = model
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.client = Groq(api_key=self.api_key)

    def translate_segments(self, segments, system_prompt: str, context: str = "", target_language: str = "hindi") -> list:
        # We need to construct a robust JSON prompt to ensure Groq outputs clean JSON
        user_content = f"Context (do not translate this): {context}\n\nSegments to translate/rewrite:\n"
        user_content += json.dumps([{"id": s["id"], "text": s["text"]} for s in segments], ensure_ascii=False)
        
        system_prompt += "\n\nIMPORTANT: You must output ONLY a valid JSON object with a single key 'translations', containing a list of objects with 'id' and 'translated_text'. Do not output markdown code blocks or any other text."

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
        try:
            data = json.loads(content)
            translations = data.get("translations", [])
            if not translations:
                print(f"Warning: Groq returned valid JSON but no 'translations' list. Raw: {content}")
            return translations
        except json.JSONDecodeError:
            print("Failed to parse Groq response:", content)
            return []
