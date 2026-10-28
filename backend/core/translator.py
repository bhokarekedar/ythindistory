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
        self.api_key = api_key
        self.model = translation_model
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

    def get_system_prompt(self, target_language: str, glossary: str = "", channel_type: str = "movie_recap") -> str:
        lang = target_language.lower()
        if channel_type == "thriller_story":
            base_prompt = """You are a master true-crime and psychological mystery documentary narrator (like JCS or Explore With Us).
Translate and rewrite the provided script into an intense, suspenseful, and chilling English story.

CRITICAL RULES FOR NATURAL STORYTELLING & DIALOGUES:
1. COMPLETE STANDALONE DIALOGUES: Every segment MUST be a complete, grammatically sound, finished thought.
   - If an input fragment is cut mid-sentence by subtitle chunking, use the surrounding context to reconstruct it into a polished, self-contained sentence.
   - NEVER end a segment on a dangling word or hanging conjunction (e.g. 'and...', 'but...', 'because...', 'which...'). Always resolve and close the thought cleanly.
2. INVESTIGATIVE TENSION & PACING:
   - Make sentences punchy, atmospheric, and gripping when spoken aloud.
   - Use commas (,) naturally where a human narrator takes a brief breath between clauses. End every complete statement with a period (.).
   - Do NOT use colons, semicolons, or dashes as they confuse the TTS.
3. STORY INTEGRITY:
   - Remove intros/outros ("Welcome to my channel", "Subscribe") and sponsorships.
   - Keep all dark, gripping, and psychological details intact.
4. PRESERVE SEGMENT IDS: Return exactly one translation object for every input ID."""
        elif lang == "hindi":
            base_prompt = """You are a master Hindi YouTube movie-recap and storytelling narrator.
Convert the provided movie explanation into natural, engaging, and fluent spoken Hindi dialogues.

CRITICAL RULES FOR NATURAL STORYTELLING & COMPLETE DIALOGUES:
1. COMPLETE STANDALONE THOUGHTS: Every single segment MUST be a complete, grammatically sound, finished sentence or dialogue.
   - If an input fragment starts or ends abruptly mid-sentence (caused by subtitle chunking), reconstruct the complete intended thought using the surrounding story context.
   - NEVER end a segment on a dangling conjunction, postposition, or unfinished verb (e.g., 'और...', 'लेकिन...', 'कि...', 'की वजह से...', 'तभी...', 'होता...'). Always resolve and complete the sentence within the segment.
2. NATURAL HUMAN CADENCE & BREATHING:
   - Make Hindi sound natural and conversational when spoken aloud by a voice narrator.
   - Use commas (,) naturally where a human narrator would take a brief breath between clauses.
   - End every sentence with a period (.). Do NOT use question marks, colons, semicolons, or dashes.
3. CONVERSATIONAL HINDUSTANI:
   - Avoid overly formal or archaic Hindi. Use conversational Hindi mixed naturally with familiar English words, exactly as modern YouTube movie narrators speak.
4. ENGLISH WORDS IN LATIN SCRIPT: Keep character names, place names, movie titles, and common English loanwords in English Latin alphabet:
   - Character/person names (e.g., Jennifer, Hercule, Alex, Sarah)
   - Place names (e.g., New York, London, Jerusalem, Mumbai)
   - Everyday terms: police, hotel, hospital, doctor, station, train, office, cabin, coat, room, bag.
   Reason: Google/Kokoro TTS pronounces English Latin script accurately. Writing them in Devanagari distorts pronunciation.
   CORRECT example: 'Hercule ने train manager को सारी बात समझाई.'
   WRONG example: 'हरकुल ने ट्रेन मैनेजर को सारी बात समझाई.'
5. CONCISE & ENGAGING: Keep sentences short, punchy, and atmospheric. The narration should feel like a gripping story told to a friend.
6. PRESERVE INTRODUCTIONS: If the script begins with an intro or greeting ('Welcome to the channel' or 'Today we explain...'), keep and translate it naturally.
7. PRESERVE SEGMENT IDS: Return exactly one translation object for every input ID."""
        else:
            base_prompt = """You are a master YouTube movie-recap and storytelling narrator.
Translate and rewrite the provided script into engaging, polished, and natural spoken English.

CRITICAL RULES FOR NATURAL STORYTELLING & COMPLETE DIALOGUES:
1. COMPLETE STANDALONE THOUGHTS: Every single segment MUST be a complete, grammatically sound, finished sentence or dialogue.
   - If an input fragment starts or ends abruptly mid-sentence, use the surrounding story context to reconstruct it into a complete, polished thought.
   - NEVER end a segment on an incomplete thought or dangling word like 'and', 'but', 'because', 'which', 'so', or 'then'. Always complete the sentence cleanly.
2. NATURAL SPOKEN RHYTHM & PACING:
   - Write sentences that sound natural, rhythmic, and captivating when read aloud by a Text-to-Speech narrator.
   - Use commas (,) naturally where a speaker takes a brief breath. End every complete sentence with a period (.).
   - Do NOT use complex punctuation like colons, semicolons, or dashes.
3. FIX TRANSCRIPTION TYPOS: The original text is generated from audio and may contain phonetic errors. Use the story context to correct them.
4. FILTER USELESS FILLER: Remove creator sponsorships and channel intros/outros ('Subscribe now'). But if a segment contains story details, keep and polish the story information.
5. PRESERVE SEGMENT IDS: Return exactly one translation object for every input ID."""
        
        if glossary:
            base_prompt += f"\n\nCRITICAL STORY GLOSSARY (Use these to resolve typos or ambiguous terms):\n{glossary}"
            
        return base_prompt

    def _extract_glossary(self, segments) -> str:
        if not self.api_key and not os.environ.get("GROQ_API_KEY"):
            return ""
            
        full_text = " ".join([s["text"] for s in segments])
        full_text = full_text[:6000] # Truncate to save context
        
        prompt = """You are an expert script editor. Read the following story and extract a glossary of:
1. Character Names
2. Important Objects or Locations

Return ONLY a comma-separated list of these terms in English, like: "Maharaja (Character), Jyoti (Character), The Warehouse (Location)". Do not add any other text."""
        
        try:
            from groq import Groq
            client = Groq(api_key=self.api_key or os.environ.get("GROQ_API_KEY"))
            completion = client.chat.completions.create(
                model=self.model if hasattr(self, 'model') else "qwen/qwen3.8-27b",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": full_text}
                ],
                temperature=0.3
            )
            glossary = completion.choices[0].message.content.strip()
            print(f"--- Extracted Glossary: {glossary} ---")
            return glossary
        except Exception as e:
            print(f"Glossary extraction failed: {e}")
            return ""

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

    def tag_ai_visual_segments(self, segments: list, target_lang: str = "english", max_ratio: float = 0.30) -> list:
        """
        Uses LLM to select up to 30% of segments representing the most dramatic/visual
        moments and generate cinematic image prompts for Cloudflare FLUX.1.
        """
        if not segments:
            return segments

        target_count = max(1, int(len(segments) * max_ratio))
        print(f"  [AI Director] Smartly selecting up to {target_count} cinematic AI moments (~{int(max_ratio*100)}%)...")

        summary_items = []
        for s in segments:
            text = s.get(target_lang, s.get("english", s.get("original_text", ""))).strip()
            if text:
                summary_items.append({"id": s["id"], "text": text[:150]})

        if not summary_items:
            return segments

        prompt = f"""You are an elite cinematic documentary director.
Analyze the following sequential story segments. Select at most {target_count} segments (approx 25-30% of total) that describe the most visually shocking, suspenseful, or cinematic moments (e.g. crime scenes, dramatic discoveries, eerie locations, tense confrontations).

RULES:
1. NEVER select consecutive/back-to-back IDs! Always leave at least 1-2 segments between AI visuals so real video can play.
2. Select between {max(1, target_count - 3)} and {target_count} total segments.
3. For each chosen segment ID, generate a vivid 'image_prompt' suitable for FLUX.1:
   - Style: Cinematic 35mm film still, photorealistic, atmospheric, moody noir lighting, 4K, high detail.
   - Example: "Cinematic 35mm film still of a dark rain-soaked abandoned house at 3 AM, single flickering yellow light in window, misty atmosphere, 4K"
4. Output strictly a JSON object with a single key 'ai_segments':
{{
  "ai_segments": [
    {{"id": 3, "prompt": "..."}},
    {{"id": 7, "prompt": "..."}}
  ]
}}"""

        try:
            from groq import Groq
            client = Groq(api_key=self.api_key or os.environ.get("GROQ_API_KEY"))
            completion = client.chat.completions.create(
                model=self.model if hasattr(self, 'model') else "qwen/qwen3.8-27b",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(summary_items, ensure_ascii=False)}
                ],
                response_format={"type": "json_object"},
                temperature=0.4
            )
            data = json.loads(completion.choices[0].message.content)
            ai_map = {item["id"]: item.get("prompt", "") for item in data.get("ai_segments", [])}
            
            tagged_count = 0
            for seg in segments:
                if seg["id"] in ai_map and ai_map[seg["id"]]:
                    seg["use_ai_image"] = True
                    seg["image_prompt"] = ai_map[seg["id"]]
                    tagged_count += 1
                else:
                    seg["use_ai_image"] = False

            print(f"  [AI Director] ✅ Tagged {tagged_count}/{len(segments)} segments for Cloudflare FLUX.1 generation.")
        except Exception as e:
            print(f"  [AI Director] Warning: Failed to tag AI segments ({e}). Falling back to 100% video.")
            for seg in segments:
                seg["use_ai_image"] = False

        return segments

    def translate_transcript(self, transcript_path: str, target_language: str = "hindi", output_dir: str = "temp", channel_type: str = "movie_recap") -> str:
        with open(transcript_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
            
        translated_segments = []
        lang_key = target_language.lower()
        
        print(f"Extracting contextual glossary for {lang_key} translation...")
        glossary = self._extract_glossary(segments)
        
        system_prompt = self.get_system_prompt(lang_key, glossary, channel_type=channel_type)
        
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

            # Targeted single-segment recovery for any still-missing IDs
            existing_ids = {int(item["id"]) for item in valid_results if "id" in item and str(item["id"]).isdigit()}
            still_missing = batch_ids - existing_ids
            if still_missing:
                print(f"Attempting single-segment recovery for missing IDs: {still_missing}...")
                for missing_id in sorted(still_missing):
                    missing_seg = next((s for s in batch if int(s["id"]) == missing_id), None)
                    if missing_seg:
                        try:
                            recovered = self._execute_translation([missing_seg], system_prompt, context="", target_language=lang_key)
                            for r in recovered:
                                if int(r.get("id", missing_id)) == missing_id:
                                    valid_results.append(r)
                                    print(f"  -> Successfully recovered translation for missing segment {missing_id}")
                        except Exception as e:
                            print(f"  -> Single-segment recovery failed for ID {missing_id}: {e}")
                
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
                    seg_id = int(item["id"])
                    text_val = item.get("translated_text") or item.get(lang_key) or item.get("text")
                    if text_val and text_val.strip().lower() not in ["translation/rewrite failed", "error"]:
                        result_map[seg_id] = text_val.strip()
                except (KeyError, ValueError):
                    pass
            
            for seg in batch:
                seg_id = int(seg["id"])
                final_text = result_map.get(seg_id)
                if not final_text:
                    # Fall back to original text so TTS speaks valid story text, NOT an error string!
                    print(f"  [Fallback] Segment {seg_id} had no valid translation. Falling back to original text.")
                    final_text = seg.get("text", "").strip()

                translated_segments.append({
                    "id": seg["id"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "original_text": seg["text"],
                    lang_key: final_text
                })
            
        # If thriller story channel, smartly tag 30% AI visual moments
        if channel_type == "thriller_story":
            translated_segments = self.tag_ai_visual_segments(translated_segments, target_lang=lang_key, max_ratio=0.30)
            
        base_name = os.path.splitext(os.path.basename(transcript_path))[0].replace("_transcript", "")
        suffix = f"_{channel_type}" if channel_type == "thriller_story" else ""
        output_path = os.path.join(output_dir, f"{base_name}_{lang_key}{suffix}_transcript.json")
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(translated_segments, f, indent=4, ensure_ascii=False)
            
        print(f"{lang_key.capitalize()} script saved to {output_path}")
        return output_path
