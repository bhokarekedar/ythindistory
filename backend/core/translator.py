import json
import os
import time
from core.providers import GroqProvider, OpenRouterProvider

class StoryTranslator:
    def __init__(self, primary_provider: str = "groq", fallback_provider: str = "none",
                 translation_model: str = "qwen/qwen3.8-27b",
                 fallback_model: str = "openrouter/auto",
                 batch_size: int = 20, max_retries: int = 2,
                 api_key: str = None):
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.providers = []
        self.validator_provider = None
        
        if primary_provider == "groq":
            self.providers.append(GroqProvider(model=translation_model, api_key=api_key))
            validator_key = os.environ.get("GROQ_API_KEY_TWO")
            if validator_key:
                self.validator_provider = GroqProvider(model=translation_model, api_key=validator_key)
        
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
7. CRITICAL — CONCISENESS: Keep translations as brief and concise as possible. The spoken Hindi should not be longer in duration than the original English. Use short, punchy sentences.
8. CRITICAL — NO mid-sentence commas: Do NOT use commas (,) inside a Hindi sentence. Commas cause the TTS engine to add an unnatural pause mid-sentence. Only use a period (.) to end a complete sentence.
9. Do NOT add any punctuation other than a single period (.) at the end of a sentence.
10. STORYTELLING TONE: Narrate this as a captivating, immersive story. Build suspense in thrilling moments, express sadness in emotional scenes, and engage the listener as if you are telling a gripping story to a friend.
11. DO NOT DELETE THE INTRO: If the script starts with an introduction (like 'Welcome to the channel' or 'Today we are explaining...'), you MUST translate and keep it! Do not delete it.
12. Return ONLY the requested translations for the current segments.
13. Preserve the segment IDs exactly."""
        else:
            return """You are a professional English YouTube movie-recap narrator.
Translate and refine the provided movie explanation into natural, spoken English.
Rules:
1. If the original text is broken or fragmented, reconstruct the correct intended meaning into fluent English.
2. Make it sound natural when spoken aloud — it will be read by a Text-to-Speech engine.
3. Keep sentences short and engaging.
4. CRITICAL: DO NOT LEAK CONTEXT. Translate ONLY the text provided for each specific segment ID. Do not borrow sentences from the next or previous segment.
5. Return ONLY the requested rewritten text for the current segments.
6. Preserve the segment IDs exactly.
7. Do not use complex punctuation like colons, semicolons, or dashes as they confuse the TTS. Use commas (,) and periods (.).
8. CRITICAL RULES - FILTERING CONTENT:
    - Remove intros/outros ("Welcome to my channel").
    - Remove promotions/sponsorships.
    - Remove personal anecdotes ("I haven't watched this", "I just saw the trailer").
    - IMPORTANT: If a segment contains BOTH an anecdote AND important movie plot information (e.g., "I just saw the trailer. The story is about a village..."), DO NOT delete the whole segment! Only remove the anecdote and translate the story part.
    - Only return an empty string ("") if the ENTIRE segment is purely useless filler.
9. STORYTELLING TONE: Narrate this as a captivating, immersive story."""

    def get_validator_prompt(self, target_language: str) -> str:
        return f"""You are a strict QA Editor for a YouTube movie recap channel.
Review and fix the provided {target_language.capitalize()} translations.
Rules:
1. Fix any unnatural flow, bad grammar, or robotic phrasing.
2. Ensure it sounds like a captivating story told by a human.
3. Keep sentences short and punchy.
4. CRITICAL: You MUST return a JSON object with a single key 'translations' containing EXACTLY the same 'id's as provided.
5. Do not merge segments. Do not delete IDs. Return ALL provided IDs.
"""

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
            
            batch_ids = {int(seg["id"]) for seg in batch}
            valid_results = []
            
            # --- Pass 1: Translation with retry loop for missing IDs ---
            for attempt in range(self.max_retries + 1):
                print(f"Generating {lang_key} script for batch {i // self.batch_size + 1} (Attempt {attempt+1})...")
                results = self._execute_translation(batch, system_prompt, context, lang_key)
                
                returned_ids = set()
                for item in results:
                    try:
                        returned_ids.add(int(item["id"]))
                    except:
                        pass
                
                if batch_ids.issubset(returned_ids):
                    valid_results = results
                    break
                else:
                    missing = batch_ids - returned_ids
                    print(f"Warning: LLM missed IDs {missing}. Retrying batch...")
                    time.sleep(2)
            
            if not valid_results:
                valid_results = results
                
            # --- Pass 2: Validation/Editing with GROQ_API_KEY_TWO ---
            if self.validator_provider and valid_results:
                print(f"Validating batch {i // self.batch_size + 1} with second API key...")
                validator_prompt = self.get_validator_prompt(lang_key)
                
                # Format for the validator (it expects 'text' to translate/fix)
                validator_input = []
                for r in valid_results:
                    val_text = r.get("translated_text", r.get(lang_key, r.get("text", "")))
                    validator_input.append({"id": r["id"], "text": val_text})
                
                for attempt in range(self.max_retries):
                    try:
                        val_results = self.validator_provider.translate_segments(validator_input, validator_prompt, context="", target_language=lang_key)
                        val_returned_ids = set()
                        for item in val_results:
                            try:
                                val_returned_ids.add(int(item["id"]))
                            except:
                                pass
                        
                        if batch_ids.issubset(val_returned_ids):
                            valid_results = val_results
                            break
                        else:
                            missing = batch_ids - val_returned_ids
                            print(f"Warning: Validator missed IDs {missing}. Retrying validation...")
                    except Exception as e:
                        print(f"Validator failed: {e}")
                    time.sleep(2)
            
            # Map results back by ID (convert to int in case LLM outputs strings)
            result_map = {}
            for item in valid_results:
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
