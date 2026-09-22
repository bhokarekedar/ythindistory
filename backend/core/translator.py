import json
import os
import time
from core.providers import GroqProvider, OpenRouterProvider

class HindiTranslator:
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

        self.system_prompt = """You are a professional Hindi YouTube movie-recap narrator.
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
8. Return ONLY the requested Hindi translations for the current segments.
9. Preserve the segment IDs exactly.
10. CRITICAL — NO mid-sentence commas: Do NOT use commas (,) inside a Hindi sentence. Commas cause the TTS engine to add an unnatural pause mid-sentence. For example: 'मार देती है' is correct. 'मार, देती है' is WRONG. Only use a period (.) to end a complete sentence.
11. Do NOT add any punctuation other than a single period (.) at the end of a sentence. No commas, no semicolons, no colons, no dashes, no ellipses.
12. If the speaker mentions their channel name, replace it with 'Movie Explained Hindi'. If they promote personal items or social media, replace with a generic engagement line like 'अगर वीडियो पसंद आ रहा है तो like जरूर करें' that fits naturally.
13. Gemini TTS supports inline audio tags. Add these tags in square brackets [] at appropriate places in the Hindi text based on the scene's emotion. Valid tags: [amused], [happy], [sad], [angry], [enthusiasm], [curiosity], [determination], [whispering], [laughs], [sigh], [gasp], [short pause], [long pause]. Example: '[amused] क्या बात है! [laughs] मैंने तो यह सोचा भी नहीं था.'"""

    def _execute_translation(self, segments, context: str) -> list:
        for provider in self.providers:
            for attempt in range(self.max_retries):
                try:
                    result = provider.translate_segments(segments, self.system_prompt, context)
                    if result and len(result) > 0:
                        return result
                except Exception as e:
                    print(f"Provider {provider.__class__.__name__} attempt {attempt+1} failed: {e}")
                time.sleep(2 * (attempt + 1)) # exponential backoff
        return []

    def translate_transcript(self, transcript_path: str, output_dir: str = "temp") -> str:
        with open(transcript_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
            
        translated_segments = []
        
        # Process in batches
        for i in range(0, len(segments), self.batch_size):
            batch = segments[i:i+self.batch_size]
            
            # Build context (1 sentence before and 1 after the batch)
            prev_context = segments[i-1]["text"] if i > 0 else ""
            next_idx = i + self.batch_size
            next_context = segments[next_idx]["text"] if next_idx < len(segments) else ""
            context = f"{prev_context} [...] {next_context}"
            
            print(f"Translating batch {i // self.batch_size + 1} ({len(batch)} segments)...")
            hindi_results = self._execute_translation(batch, context)
            
            # Map results back by ID (convert to int in case LLM outputs strings)
            result_map = {}
            for item in hindi_results:
                try:
                    result_map[int(item["id"])] = item.get("hindi", "अनुवाद विफल")
                except (KeyError, ValueError):
                    pass
            
            for seg in batch:
                translated_segments.append({
                    "id": seg["id"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "english": seg["text"],
                    "hindi": result_map.get(seg["id"], "अनुवाद विफल") # Fallback text if it fails
                })
            
        base_name = os.path.splitext(os.path.basename(transcript_path))[0].replace("_transcript", "")
        output_path = os.path.join(output_dir, f"{base_name}_hindi_transcript.json")
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(translated_segments, f, indent=4, ensure_ascii=False)
            
        print(f"Hindi transcript saved to {output_path}")
        return output_path
