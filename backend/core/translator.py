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
1. Do not translate word-for-word. Preserve exact meaning.
2. Make Hindi sound natural when spoken aloud.
3. Keep character names unchanged.
4. Avoid overly formal Hindi. Use conversational Hindi.
5. Keep sentences reasonably short.
6. Do not add introductions, conclusions, or commentary.
7. Return ONLY the requested Hindi translations for the current segments.
8. Preserve the segment IDs exactly."""

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
