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
        
        prompt = """You are an elite YouTube growth hacker and SEO strategist.
Based on the following movie recap story, you must generate metadata designed to maximize Click-Through Rate (CTR).

1. TITLE RULES:
   - Make it ultra click-worthy and "thumbnail-worthy".
   - It MUST create an irresistible "information gap" (e.g., "He Messed With The Wrong Father", "She Thought She Was Safe Until...").
   - DO NOT just write the name of the movie. 
   - Keep it under 70 characters so it doesn't get truncated on mobile.
   - DO NOT use emojis.
   - Use high-emotion trigger words (Revenge, Betrayal, Shocking, Genius, Psycho).

2. DESCRIPTION RULES:
   - The first 2 lines MUST be an incredible hook that makes them want to watch immediately.
   - The rest should be an SEO-optimized summary packed with natural keywords to tell the YouTube algorithm exactly who to show this to (genre, audience interest).

3. KEYWORDS:
   - Provide 15-20 high-volume, relevant tags.

Return STRICTLY a JSON object with this format:
{
    "title": "Your Irresistible Title Here",
    "description": "Your hooked SEO description here",
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
