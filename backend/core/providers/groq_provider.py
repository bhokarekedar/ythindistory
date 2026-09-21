import os
import json
from groq import Groq
from core.providers.base import LLMProvider

class GroqProvider(LLMProvider):
    def __init__(self, model: str = "llama-3.1-70b-versatile"):
        self.model = model
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    def translate_segments(self, segments, system_prompt: str, context: str = "") -> list:
        # We need to construct a robust JSON prompt to ensure Groq outputs clean JSON
        user_content = f"Context (do not translate this): {context}\n\nSegments to translate:\n"
        user_content += json.dumps([{"id": s["id"], "text": s["text"]} for s in segments], ensure_ascii=False)
        
        system_prompt += "\n\nIMPORTANT: You must output ONLY a valid JSON object with a single key 'translations', containing a list of objects with 'id' and 'hindi'. Do not output markdown code blocks or any other text."

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
