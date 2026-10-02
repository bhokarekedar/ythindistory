import json
import os
import time
from core.providers import GroqProvider, OpenRouterProvider

class StoryTranslator:
    def __init__(self, primary_provider: str = "groq", fallback_provider: str = "none",
                 translation_model: str = "qwen/qwen3.8-27b",
                 fallback_model: str = "openrouter/auto",
                 batch_size: int = 20, max_retries: int = 2):
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.providers = []
        
        if primary_provider == "groq":
            self.providers.append(GroqProvider(model=translation_model))
        
        if fallback_provider == "openrouter":
            self.providers.append(OpenRouterProvider(model=fallback_model))

    def get_system_prompt(self, target_language: str) -> str:
        lang = target_language.lower()
        if lang == "hindi":
            return """You are a professional Hindi YouTube movie-recap narrator.
Convert the provided English movie explanation into natural spoken Hindi.
Rules:
1. If the English text is broken, fragmented, or grammatically incorrect, first reconstruct the correct intended meaning, THEN translate it into fluent Hindi. Never translate broken English literally.
2. Do not translate word-for-word. Preserve exact meaning.
3. Make Hindi sound natural when spoken aloud — it will be read by a Text-to-Speech engine.
4. CRITICAL — English words in English script: Keep ALL of the following in their original English Latin alphabet (do NOT transliterate to Devanagari):
   - Character names, person names (e.g. Jennifer, Alex, Sarah)
   - Place names, city names (e.g. New York, London, Mumbai)
   - Movie/show titles
   - English technical terms or words commonly used in Hindi speech (e.g. police, hotel, hospital, doctor, college, bus, train, office)
   Reason: Google TTS pronounces English Latin script correctly. If you write them in Devanagari the pronunciation becomes distorted.
   CORRECT example: 'Jennifer एक writer थी जो New York में रहती थी'
   WRONG example: 'जेनिफर एक राइटर थी जो न्यू यॉर्क में रहती थी'
5. Avoid overly formal Hindi. Use conversational Hindi mixed with English words naturally (as Indians speak).
6. Keep sentences short — one idea per sentence.
7. Do not add introductions, conclusions, or commentary.
8. Return ONLY the requested translations for the current segments.
9. Preserve the segment IDs exactly.
10. CRITICAL — NO mid-sentence commas: Do NOT use commas (,) inside a Hindi sentence. Commas cause the TTS engine to add an unnatural pause mid-sentence. Only use a period (.) to end a complete sentence.
11. Do NOT add any punctuation other than a single period (.) at the end of a sentence.
12. CRITICAL RULES - DO NOT INCLUDE THE FOLLOWING:
    - No Intros/Outros: Remove any "Welcome to my channel", "Thanks for 1 million subscribers", or "Don't forget to subscribe/like/comment".
    - No Promotions/Sponsorships: Remove any mentions of sponsors, giveaways, merchandise, or brand deals.
    - No Personal Anecdotes: Remove any personal life updates that are unrelated to the core story of the video.
    - Start at the Core Story: Ignore the hook if it's promotional. Begin the script exactly where the actual educational/entertainment story begins.
    - If you encounter these, skip them completely and return an empty string ("") for that segment's translated_text. Do NOT bridge the gap.
13. STORYTELLING TONE: Narrate this as a captivating, immersive story. Build suspense in thrilling moments, express sadness in emotional scenes, and engage the listener as if you are telling a gripping story to a friend."""
        else:
            return """You are a professional English YouTube movie-recap narrator.
Refine and rewrite the provided English movie explanation into natural, spoken English.
Rules:
1. If the text is broken, fragmented, or grammatically incorrect, reconstruct the correct intended meaning into fluent English.
2. Make it sound natural when spoken aloud — it will be read by a Text-to-Speech engine.
3. Keep sentences short and engaging — one idea per sentence.
4. Do not add introductions, conclusions, or commentary outside of the story recap.
5. Return ONLY the requested rewritten text for the current segments.
6. Preserve the segment IDs exactly.
7. Do not use complex punctuation like colons, semicolons, or dashes as they confuse the TTS. Use commas (,) and periods (.).
8. CRITICAL RULES - DO NOT INCLUDE THE FOLLOWING:
    - No Intros/Outros: Remove any "Welcome to my channel", "Thanks for 1 million subscribers", or "Don't forget to subscribe/like/comment".
    - No Promotions/Sponsorships: Remove any mentions of sponsors, giveaways, merchandise, or brand deals.
    - No Personal Anecdotes: Remove any personal life updates that are unrelated to the core story of the video.
    - Start at the Core Story: Ignore the hook if it's promotional. Begin the script exactly where the actual educational/entertainment story begins.
    - If you encounter these, skip them completely and return an empty string ("") for that segment's translated_text. Do NOT bridge the gap.
9. STORYTELLING TONE: Narrate this as a captivating, immersive story. Build suspense in thrilling moments, express sadness in emotional scenes, and engage the listener as if you are telling a gripping story to a friend."""

    def _execute_translation(self, segments, system_prompt: str, context: str, target_language: str) -> list:
        for provider in self.providers:
            for attempt in range(self.max_retries):
                try:
                    # Pass target_language if provider supports it, otherwise provider needs to handle "translated_text"
                    result = provider.translate_segments(segments, system_prompt, context, target_language=target_language.lower())
                    if result and len(result) > 0:
                        return result
                except Exception as e:
                    print(f"Provider {provider.__class__.__name__} attempt {attempt+1} failed: {e}")
                time.sleep(2 * (attempt + 1)) # exponential backoff
        return []

    def translate_transcript(self, transcript_path: str, target_language: str = "hindi", output_dir: str = "temp") -> str:
        with open(transcript_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
            
        translated_segments = []
        lang_key = target_language.lower()
        system_prompt = self.get_system_prompt(lang_key)
        
        # Process in batches
        for i in range(0, len(segments), self.batch_size):
            batch = segments[i:i+self.batch_size]
            
            # Build context (1 sentence before and 1 after the batch)
            prev_context = segments[i-1]["text"] if i > 0 else ""
            next_idx = i + self.batch_size
            next_context = segments[next_idx]["text"] if next_idx < len(segments) else ""
            context = f"{prev_context} [...] {next_context}"
            
            print(f"Generating {lang_key} script for batch {i // self.batch_size + 1} ({len(batch)} segments)...")
            results = self._execute_translation(batch, system_prompt, context, lang_key)
            
            # Map results back by ID (convert to int in case LLM outputs strings)
            result_map = {}
            for item in results:
                try:
                    result_map[int(item["id"])] = item.get("translated_text", item.get("hindi", item.get("text", "Error")))
                except (KeyError, ValueError):
                    pass
            
            for seg in batch:
                translated_segments.append({
                    "id": seg["id"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "original_text": seg["text"],
                    lang_key: result_map.get(seg["id"], "Translation/Rewrite Failed")
                })
            
        base_name = os.path.splitext(os.path.basename(transcript_path))[0].replace("_transcript", "")
        output_path = os.path.join(output_dir, f"{base_name}_{lang_key}_transcript.json")
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(translated_segments, f, indent=4, ensure_ascii=False)
            
        print(f"{lang_key.capitalize()} script saved to {output_path}")
        return output_path
