import os
import json
from groq import Groq

class MetadataGenerator:
    def __init__(self, api_key: str = None):
        # Using Qwen 27B since it's available on Groq and great for JSON generation
        self.model_name = "qwen/qwen3.8-27b"
        self.client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"))

    def generate(self, script_path: str, output_path: str, target_lang: str):
        print("Generating SEO-optimized YouTube metadata...")
        
        with open(script_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
            
        # Combine the text to get a summary of the story
        # We prioritize the translated text since it's more concise
        full_text = " ".join([s.get(target_lang, s.get("text", "")) for s in segments])
        
        # If it's too long, truncate it to the first 4000 characters to save context and speed up generation
        full_text = full_text[:4000]
        
        prompt = """You are an expert YouTube SEO strategist.
Based on the following movie recap story, generate:
1. An engaging, click-worthy YouTube title that generates immense curiosity. Do NOT use emojis in the title.
2. An SEO-optimized description that clearly tells YouTube's algorithm who to show this video to (area of interest, genre, target audience).
3. A list of 15-20 high-volume, relevant SEO keywords/tags.

Return STRICTLY a JSON object with this format:
{
    "title": "Your Title Here",
    "description": "Your SEO description here",
    "keywords": ["tag1", "tag2", "tag3"]
}
"""
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": full_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            
            response_text = completion.choices[0].message.content
            metadata = json.loads(response_text)
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)
                
            print(f"Metadata saved to: {output_path}")
            return output_path
        except Exception as e:
            print(f"Metadata generation failed: {e}")
            return None
