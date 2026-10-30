import json
import os
import re
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
            groq_keys = []
            if api_key: groq_keys.append(api_key)
            k1 = os.environ.get("GROQ_API_KEY")
            if k1 and k1 not in groq_keys: groq_keys.append(k1)
            k2 = os.environ.get("GROQ_API_KEY_TWO")
            if k2 and k2 not in groq_keys: groq_keys.append(k2)
            k3 = os.environ.get("GROQ_API_KEY_THREE")
            if k3 and k3 not in groq_keys: groq_keys.append(k3)

            self.providers.append(GroqProvider(model=translation_model, api_keys=groq_keys))
            if k2:
                self.validator_provider = GroqProvider(model=translation_model, api_keys=[k2] + [k for k in groq_keys if k != k2])
        
        if fallback_provider == "openrouter":
            self.providers.append(OpenRouterProvider(model=fallback_model))

    def get_system_prompt(self, target_language: str, glossary: str = "", channel_type: str = "movie_recap") -> str:
        lang = target_language.lower()
        is_real_story = channel_type in ["thriller_story", "real_story"]
        
        if is_real_story:
            # ─────────────────────────────────────────────────────────────
            # CHANNEL 2: REAL STORIES (JAPAN/KOREA TRUE INCIDENTS & MYSTERIES)
            # NOT MOVIES! Real-life incidents, true crime, eerie investigations.
            # ─────────────────────────────────────────────────────────────
            if lang == "hindi":
                base_prompt = """You are a master Hindi true-story and real-incident documentary narrator (specializing in chilling Japanese, Korean, and Asian real-life mysteries, true crime, and real incidents).
Your task is NOT to translate word-for-word, but to RE-SCRIPT and ELEVATE the narrative into an intense, eerie, and captivating spoken Hindi documentary with a personal storyteller touch!

CRITICAL CORE RULE — THIS IS A REAL INCIDENT, NOT A FICTIONAL MOVIE:
1. STRICTLY FORBIDDEN TO USE MOVIE TERMINOLOGY:
   - NEVER use words like 'movie', 'film', 'filmy', 'cinema', 'actor', 'actress', 'director', 'scene', 'climax', 'shooting', 'kahaani ka hero/villain'.
   - NEVER say 'Iss movie mein...' or 'Film ki shuruat mein...'!
   - ALWAYS treat this as a REAL LIFE INCIDENT that actually happened to real people:
     * 'दोस्तों, यह कोई काल्पनिक कहानी नहीं, बल्कि Japan/South Korea की एक ऐसी रोंगटे खड़े कर देने वाली सच्ची घटना है...'
     * 'घटना की शुरुआत होती है जब...'
     * 'जांच में पुलिस और फॉरेंसिक टीम को जो पता चला, उसने सबके रोंगटे खड़े कर दिए...'
     * 'इस खौफनाक मामले ने पूरे इलाके को हिलाकर रख दिया था...'
     * 'सोचिए, उस वक्त उस बेकसूर इंसान पर क्या बीती होगी...'
2. TOTAL BRANDING & FILLER PURGE:
   - STRICTLY FORBIDDEN: NEVER mention any third-party channel names (e.g. 'Filmi Cheeti', 'Mystery Recapped', 'Binge Lab', 'Cinema Mirage') or original YouTuber handles!
   - Remove all YouTube meta-chatter ('Subscribe karein', 'Bell icon dabayein', 'Video like karein', 'Link in description').
   - If the first segment contains a channel greeting, open immediately with a chilling true-incident hook (e.g., 'दोस्तों, आज हम बात करने वाले हैं Japan/South Korea की एक ऐसी रोंगटे खड़े कर देने वाली सच्ची घटना की, जिसके बारे में जानकर आपके होश उड़ जाएंगे. घटना की शुरुआत होती है...').
   - Remove creator personal anecdotes ('Maine pichhle saal dekha tha'). Focus 100% on the real case, victims, and events.
3. COMPLETE STANDALONE DIALOGUES:
   - Every single segment MUST be a complete, grammatically sound, finished sentence.
   - If an input fragment starts or ends abruptly mid-sentence (caused by subtitle chunking), reconstruct the complete intended thought using the surrounding story context.
   - NEVER end a segment on a dangling conjunction, postposition, or unfinished verb (e.g., 'और...', 'लेकिन...', 'कि...', 'की वजह से...', 'तभी...', 'होता...'). Always resolve and complete the sentence cleanly.
4. INVESTIGATIVE TENSION & HUMAN CADENCE:
   - Make sentences punchy, tense, and atmospheric when spoken aloud by a voice narrator.
   - Use commas (,) naturally where a human narrator takes a brief breath between clauses. End every complete statement with a period (.).
   - Do NOT use colons, semicolons, question marks, or dashes as they confuse the TTS.
5. CONVERSATIONAL HINDUSTANI:
   - Avoid overly formal or archaic Hindi. Use conversational, serious investigative Hindi mixed naturally with familiar English words.
6. ENGLISH WORDS IN LATIN SCRIPT:
   - Keep character/victim/detective names, Japanese/Korean city names (Tokyo, Seoul, Osaka, Busan, Kyoto, Gangnam), and everyday modern terms (police, apartment, hospital, hotel, phone, cctv, forensic, car, room, bag) in English Latin alphabet for accurate TTS pronunciation.
   CORRECT example: 'Police ने Tokyo के एक apartment से जांच शुरू की.'
   WRONG example: 'पुलिस ने टोक्यो के एक अपार्टमेंट से जांच शुरू की.'
7. PRESERVE SEGMENT IDS: Return exactly one translation object for every input ID."""
            else:
                base_prompt = """You are a master true-crime and Asian real-incident documentary narrator (like Explore With Us, JCS, or Dark Asian Files).
Your task is NOT to translate word-for-word, but to RE-SCRIPT the narrative into an intense, chilling, and highly personal investigative true-story documentary.

CRITICAL CORE RULE — THIS IS A REAL INCIDENT, NOT A FICTIONAL MOVIE:
1. STRICTLY FORBIDDEN TO USE MOVIE TERMINOLOGY:
   - NEVER refer to this as a 'movie', 'film', 'fictional story', 'director', or 'actor'.
   - Treat this 100% as a REAL-LIFE EVENT, police investigation, or eerie real-world mystery that occurred to real people.
   - Use investigative language ('Investigators discovered...', 'What happened next shocked the entire city...', 'According to police records...', 'Little did anyone know what was about to happen.').
2. TOTAL BRANDING & FILLER PURGE:
   - NEVER mention third-party channel names (e.g. 'Mystery Recapped', 'Binge Lab', 'Cinema Mirage') or original creator names/handles.
   - NEVER include YouTube meta-chatter ('Welcome back', 'Subscribe', 'Like', 'Patreon link', 'Comment below').
   - If the first segment contains a channel greeting, immediately replace it with an ominous, chilling opening hook about the real case.
3. COMPLETE STANDALONE DIALOGUES:
   - Every segment MUST be a complete, grammatically sound, finished thought.
   - If a fragment is cut mid-sentence by subtitle chunking, use the surrounding context to reconstruct it into a polished, self-contained statement.
   - NEVER end a segment on a dangling word or conjunction ('and...', 'but...', 'because...', 'which...'). Always conclude the thought cleanly.
4. AUDIO-FIRST STORYTELLING & NATURAL CHRONOLOGY:
   - AUDIO IS KING: Deliver the full story with complete emotional weight, suspense, and investigative detail. NEVER summarize or compress the narrative into a dry summary.
   - STRICT CHRONOLOGY: Focus strictly on the events belonging to this segment. Do NOT prematurely narrate future plot revelations that belong to later segments.
5. INVESTIGATIVE TENSION & CADENCE:
   - Make sentences punchy, atmospheric, and gripping when spoken aloud by a voice narrator.
   - Use commas (,) naturally where a speaker takes a brief breath between clauses. End every complete statement with a period (.).
   - Do NOT use colons, semicolons, or dashes as they confuse the TTS.
6. PRESERVE SEGMENT IDS: Return exactly one translation object for every input ID."""

        else:
            # ─────────────────────────────────────────────────────────────
            # CHANNEL 1: MOVIE RECAPS (FILM BREAKDOWNS & EXPLANATIONS)
            # ─────────────────────────────────────────────────────────────
            if lang == "hindi":
                base_prompt = """You are a master Hindi YouTube movie-recap and film storytelling narrator (like top Hindi recap creators).
Your task is NOT to translate word-for-word, but to RE-SCRIPT and ELEVATE the story into an engaging, emotional, and captivating spoken Hindi dialogue with a strong personal touch!

CRITICAL RULES FOR NARRATIVE EXCELLENCE:
1. BE A MASTER STORYTELLER (NEVER TRANSLATE WORD-FOR-WORD):
   - Never translate literally like a sterile textbook. Re-script the narrative with personal narrator flair, excitement, curiosity, and emotion!
   - Talk directly to your audience of movie lovers ('दोस्तों', 'अब देखिए आगे क्या होता है...', 'लेकिन कहानी में असली ट्विस्ट तो अब आने वाला था...', 'सोचिए, उस वक्त उस पर क्या बीती होगी...', 'तभी एक ऐसा सच सामने आता है जो सबके होश उड़ा देता है...').
   - Build suspense during thrilling scenes, express emotion during tragedy, and deliver twists with maximum impact!
2. TOTAL BRANDING & CHATTER PURGE:
   - STRICTLY FORBIDDEN: NEVER mention any third-party channel names (e.g., 'Filmi Cheeti', 'Mystery Recapped', 'Binge Lab', 'Cinema Mirage', 'Movie Recaps', etc.) or original YouTuber names/handles!
   - STRICTLY FORBIDDEN: NEVER include YouTube meta-chatter ('Subscribe karein', 'Bell icon dabayein', 'Video ko like karein', 'Comment mein batayein', 'Link in description').
   - If the opening segment contains an original channel greeting/intro, DO NOT translate their channel name! Instead, open with an energetic, captivating story hook (e.g., 'दोस्तों, आज हम बात करने वाले हैं एक ऐसी जबरदस्त सस्पेंस थ्रिलर फिल्म की, जो आपको शुरू से लेकर अंत तक कुर्सी से बांधे रखेगी. कहानी की शुरुआत में...').
   - Remove creator personal anecdotes ('Maine pichhle saal dekha tha'). Focus 100% on the movie plot and characters.
3. COMPLETE STANDALONE THOUGHTS:
   - Every single segment MUST be a complete, grammatically sound, finished sentence or dialogue.
   - If an input fragment starts or ends abruptly mid-sentence (caused by subtitle chunking), reconstruct the complete intended thought using the surrounding story context.
   - NEVER end a segment on a dangling conjunction, postposition, or unfinished verb (e.g., 'और...', 'लेकिन...', 'कि...', 'की वजह से...', 'तभी...', 'होता...'). Always resolve and complete the sentence within the segment.
4. AUDIO-FIRST STORYTELLING & NATURAL CHRONOLOGY:
   - AUDIO IS KING: Deliver the full story with complete emotional weight, drama, and personal flair. NEVER summarize or compress the narrative into a dry summary.
   - STRICT CHRONOLOGY: Focus strictly on the events belonging to this segment. Do NOT prematurely narrate future plot points that belong to later segments!
5. NATURAL HUMAN CADENCE & BREATHING:
   - Make Hindi sound natural and conversational when spoken aloud by a voice narrator.
   - Use commas (,) naturally where a human narrator takes a brief breath between clauses.
   - End every sentence with a period (.). Do NOT use question marks, colons, semicolons, or dashes.
6. CONVERSATIONAL HINDUSTANI:
   - Avoid overly formal or archaic Hindi. Use conversational Hindi mixed naturally with familiar English words, exactly as modern YouTube movie narrators speak.
7. ENGLISH WORDS IN LATIN SCRIPT: Keep character names, place names, movie titles, and common English loanwords in English Latin alphabet:
   - Character/person names (e.g., Jennifer, Hercule, Alex, Sarah)
   - Place names (e.g., New York, London, Jerusalem, Mumbai)
   - Everyday terms: police, hotel, hospital, doctor, station, train, office, cabin, coat, room, bag.
   CORRECT example: 'Hercule ने train manager को सारी बात समझाई.'
   WRONG example: 'हरकुल ने ट्रेन मैनेजर को सारी बात समझाई.'
8. PRESERVE SEGMENT IDS: Return exactly one translation object for every input ID."""
            else:
                base_prompt = """You are a master YouTube movie-recap and storytelling narrator.
Your task is NOT to translate word-for-word, but to RE-SCRIPT and ELEVATE the narrative into an engaging, polished, and personal storytelling experience!

CRITICAL RULES FOR NARRATIVE EXCELLENCE:
1. BE A MASTER STORYTELLER (NEVER TRANSLATE WORD-FOR-WORD):
   - Do NOT translate literally. Re-script the text with personal storytelling flair, enthusiasm, and tension.
   - Use natural storytelling beats and audience engagement ('Now, this is where things take a bizarre turn...', 'Imagine being in his shoes...', 'Suddenly, an unexpected revelation changes everything.').
   - Keep the pace lively, engaging, and atmospheric.
2. TOTAL BRANDING & CHATTER PURGE:
   - NEVER mention any third-party channel names (e.g., 'Filmi Cheeti', 'Mystery Recapped', 'Binge Lab', 'Cinema Mirage') or original creator names/handles.
   - Remove all YouTube meta-chatter ('Subscribe now', 'Like the video', 'Hit the bell', 'Patreon link').
   - If the first segment contains a channel greeting, replace it immediately with a captivating story hook about the film itself.
   - Remove personal anecdotes ('I watched this last week'). Focus 100% on the movie plot and characters.
3. COMPLETE STANDALONE THOUGHTS & ZERO DANGLING FRAGMENTS:
   - Every single segment MUST be a complete, grammatically sound, finished sentence or dialogue.
   - If an input fragment starts or ends abruptly mid-sentence (caused by subtitle chunking), reconstruct the complete intended thought using the surrounding story context.
   - NEVER end a segment on an incomplete thought, dangling preposition, or trailing conjunction like 'to', 'then', 'and', 'but', 'because', 'which', 'so', or 'the door'. Always conclude the statement cleanly.
4. SEAMLESS BOUNDARY HARMONIZATION (NO DUPLICATE REPETITIONS):
   - When an input segment begins with a fragment carried over from an earlier sentence, DO NOT repeat what the previous segment already narrated.
   - Seamlessly advance the narrative without stuttering or duplicating lines across adjacent segments.
5. STRICT ZERO-DEVANAGARI GUARANTEE:
   - Under NO circumstances should any Devanagari or Hindi characters (e.g., हिन्दी अक्षर) appear anywhere in the output!
   - The entire output MUST be 100% fluent, idiomatic English. Never copy source Hindi into the English field.
6. IDENTITY & ACTION LOGIC (BODY SWAPS / THRILLERS):
   - In thrillers involving body-swapping, possession, or disguise, maintain strict logical distinction between the physical body and the soul/consciousness inside it.
   - Ensure that actions (who kidnaps whom, who attacks whom, and who is trapped in whose body) reflect the narrative reality without reversing roles!
7. GENDER & CANON ENTITY LOCK:
   - Always maintain correct character pronouns, names, and titles according to the Story Glossary.
   - E.g., 'Mama Cecile' is female (never translate 'Mama' as 'Uncle'), 'Jill' is female, and locations like 'Terrebonne Parish' must be spelled accurately.
8. AUDIO-FIRST STORYTELLING & NATURAL CHRONOLOGY:
   - AUDIO IS KING: Deliver the full story with complete emotional weight, tension, and storytelling nuance. NEVER summarize or compress the narrative into a dry summary.
   - STRICT CHRONOLOGY: Focus strictly on the events belonging to this segment. Do NOT pull in or narrate future plot points that belong to later segments!
9. NATURAL SPOKEN RHYTHM & PACING:
   - Write sentences that sound natural, rhythmic, and captivating when read aloud by a Text-to-Speech narrator.
   - Use commas (,) naturally where a speaker takes a brief breath. End every complete sentence with a period (.).
   - Do NOT use complex punctuation like colons, semicolons, or dashes.
10. FIX TRANSCRIPTION TYPOS: The original text is generated from audio and may contain phonetic errors. Use the story context to correct them.
11. PRESERVE SEGMENT IDS: Return exactly one translation object for every input ID."""
        
        if glossary:
            base_prompt += f"\n\nCRITICAL STORY GLOSSARY (Use these to resolve typos, character genders, and ambiguous terms):\n{glossary}"
            
        return base_prompt

    def _extract_glossary(self, segments) -> str:
        groq_keys = []
        if self.api_key: groq_keys.append(self.api_key)
        for k in [os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_API_KEY_TWO"), os.environ.get("GROQ_API_KEY_THREE")]:
            if k and k not in groq_keys:
                groq_keys.append(k)
                
        if not groq_keys:
            return ""
            
        full_text = " ".join([s.get("text", "") for s in segments])
        full_text = full_text[:8000] # Provide ample context
        
        prompt = """You are an expert Hollywood screenplay and movie recap script editor. Read the following story transcript and extract a definitive reference glossary:
1. Movie Identification: If this is an established film (e.g., 'The Skeleton Key', 'Murder on the Orient Express'), name it.
2. Standard Character Names, Genders (Male/Female), and Exact Roles:
   - Resolve phonetic transcription errors (e.g., 'Mama Cecile (Female Hoodoo Sorceress - NEVER Uncle Cecil)', 'Papa Justify (Male Hoodoo Sorcerer)', 'Caroline Ellis (Female Hospice Nurse)', 'Ben Devereaux (Elderly Paralyzed Man)', 'Violet Devereaux (Elderly Woman)', 'Luke Marshall (Young Male Lawyer)', 'Jill (Female Best Friend)').
3. Canonical Locations, Spells, and Key Props:
   - Specific place names (e.g., 'Terrebonne Parish, Louisiana', 'New Orleans', 'Orient Express').
   - Specific props/terms (e.g., 'Conjure of Sacrifice (Ritual)', 'Red Brick Dust', 'Skeleton Key', 'Conjugation / Conjuration of Protection').

Return ONLY a clear, concise bulleted list of standard names, genders, roles, and terms to ensure 100% consistency across all translated segments."""
        
        for k_idx, key in enumerate(groq_keys):
            try:
                from groq import Groq
                client = Groq(api_key=key)
                completion = client.chat.completions.create(
                    model=self.model if hasattr(self, 'model') else "qwen/qwen3.8-27b",
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": full_text}
                    ],
                    temperature=0.3
                )
                glossary = completion.choices[0].message.content.strip()
                print(f"--- Extracted Glossary (using Key #{k_idx+1}): {glossary} ---")
                return glossary
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate_limit" in err_str:
                    print(f"  [Glossary] Key #{k_idx+1} hit rate limit (429). Trying next key...")
                    continue
                print(f"Glossary extraction failed on Key #{k_idx+1}: {e}")
        return ""

    def get_validator_prompt(self, target_language: str) -> str:
        return f"""You are a strict QA Editor for a YouTube movie recap channel.
Review and fix the provided {target_language.capitalize()} script segments.
Rules:
1. ZERO UNTRANSLATED CHARACTERS: If target is English, ensure ZERO Hindi/Devanagari characters remain. Translate any missed text completely.
2. ELIMINATE WORD-FOR-WORD TRANSLATION: Ensure the dialogue sounds like a captivating, natural story told by an engaging human narrator.
3. STRICT 3RD PARTY BRANDING PURGE: Ensure NO third-party channel names (like Filmi Cheeti, Mystery Recapped, etc.), creator names, or subscribe/like pleas remain.
4. COMPLETE STANDALONE THOUGHTS: Ensure each segment is a complete, finished thought with proper punctuation and NO dangling words (e.g. 'to', 'then.', 'and').
5. NO DUPLICATE REPETITIONS: If two adjacent segments repeat the same statement, harmonize them seamlessly.
6. CRITICAL: You MUST return a JSON object with a single key 'translations' containing EXACTLY the same 'id's as provided.
7. Do not merge segments. Do not delete IDs. Return ALL provided IDs.
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

        groq_keys = []
        if self.api_key: groq_keys.append(self.api_key)
        for k in [os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_API_KEY_TWO"), os.environ.get("GROQ_API_KEY_THREE"), os.environ.get("GROQ_API_KEY_FOUR")]:
            if k and k not in groq_keys:
                groq_keys.append(k)

        for k_idx, key in enumerate(groq_keys if groq_keys else [None]):
            try:
                from groq import Groq
                client = Groq(api_key=key)
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

                print(f"  [AI Director] ✅ Tagged {tagged_count}/{len(segments)} segments for Cloudflare FLUX.1 generation (using Key #{k_idx+1}).")
                return segments
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate_limit" in err_str:
                    print(f"  [AI Director] Key #{k_idx+1} hit rate limit (429). Trying next key...")
                    continue
                print(f"  [AI Director] Warning: Failed to tag AI segments on Key #{k_idx+1} ({e}). Falling back to 100% video.")
                break

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
                    if lang_key == "english" and seg.get("text") and re.search(r'[\u0900-\u097F]', seg.get("text")):
                        # NEVER put raw Hindi into an English transcript!
                        print(f"  [Safety Fallback] Segment {seg_id} missed English translation. Translating single fragment...")
                        try:
                            recov = self._execute_translation([seg], system_prompt, context="", target_language="english")
                            final_text = recov[0].get("english", recov[0].get("translated_text", "")) if recov else ""
                        except:
                            final_text = ""
                        if not final_text:
                            final_text = f"The story continues with event {seg_id}."
                    else:
                        print(f"  [Fallback] Segment {seg_id} had no valid translation. Falling back to original text.")
                        final_text = seg.get("text", "").strip()

                translated_segments.append({
                    "id": seg["id"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "original_text": seg["text"],
                    lang_key: final_text
                })
            
        # Post-process and sanitize all segments for QA, zero-Devanagari, anti-dangling, and boundary smoothness
        # 1. Automated self-review and improvement loop
        reviewed_segments = self.self_review_and_improve(translated_segments, target_language=lang_key)
        translated_segments = self.post_process_script(reviewed_segments, target_language=lang_key)

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

    def self_review_and_improve(self, segments: list, target_language: str = "english") -> list:
        """
        Automated self-review and narrative elevation loop:
        1. Analyzes the drafted script for dangling thoughts, fragmented cutoffs, leaked characters,
           repetition, and awkward pacing.
        2. Targets flagged segments along with their immediate narrative neighbors.
        3. Prompts the LLM (using the multi-key pool) to refine and elevate these segments into
           flawless, captivating audio narrations while preserving segment IDs and timing.
        """
        if not segments:
            return segments

        lang = target_language.lower()
        print(f"\n  [Self-Review] 🧐 Scanning {len(segments)} segments for narrative flow, cutoffs, and quality defects...")
        
        # 1. Flag segments with defects
        flagged_ids = set()
        dangling_pattern = re.compile(r'[,;\s]+(?:and|but|or|so|to|then|which|that|because|the door|waiting for)\.?$', re.IGNORECASE)
        meta_pattern = re.compile(r'\b(subscribe|like the video|filmi cheeti|mystery recapped|binge lab|bell icon|welcome back)\b', re.IGNORECASE)

        for i, seg in enumerate(segments):
            text = seg.get(lang, "").strip()
            if not text:
                flagged_ids.add(int(seg["id"]))
                continue

            # Check 1: Leaked Devanagari in English
            if lang == "english" and re.search(r'[\u0900-\u097F]', text):
                flagged_ids.add(int(seg["id"]))
                continue

            # Check 2: Dangling words at end of segment
            if dangling_pattern.search(text) or text.endswith((" to.", " to")):
                flagged_ids.add(int(seg["id"]))
                continue

            # Check 3: Short unfinished fragments (< 4 words)
            if len(text.split()) < 4:
                flagged_ids.add(int(seg["id"]))
                continue

            # Check 4: Unwanted channel branding / meta phrases
            if meta_pattern.search(text):
                flagged_ids.add(int(seg["id"]))
                continue

            # Check 5: Stutter / duplicate sentences between adjacent segments
            if i > 0:
                prev_text = segments[i-1].get(lang, "").strip()
                if prev_text and (prev_text.lower() in text.lower() or text.lower() in prev_text.lower()):
                    if len(text.split()) > 4:
                        flagged_ids.add(int(seg["id"]))
                        flagged_ids.add(int(segments[i-1]["id"]))

        if not flagged_ids:
            print("  [Self-Review] ✨ All segments passed quality screening! No issues detected.")
            return segments

        print(f"  [Self-Review] ⚠️ Flagged {len(flagged_ids)} segment(s) needing narrative refinement: {sorted(list(flagged_ids))[:15]}...")

        # 2. Expand flagged set to include neighboring segments for narrative context
        expanded_ids = set()
        seg_id_to_idx = {int(s["id"]): idx for idx, s in enumerate(segments)}
        for fid in flagged_ids:
            idx = seg_id_to_idx.get(fid)
            if idx is not None:
                expanded_ids.add(fid)
                if idx > 0:
                    expanded_ids.add(int(segments[idx-1]["id"]))
                if idx < len(segments) - 1:
                    expanded_ids.add(int(segments[idx+1]["id"]))

        # Group into contiguous review chunks of at most 8 segments
        sorted_review_ids = sorted(list(expanded_ids))
        chunks = []
        current_chunk = []
        for sid in sorted_review_ids:
            if not current_chunk:
                current_chunk.append(sid)
            else:
                if sid - current_chunk[-1] <= 2 and len(current_chunk) < 8:
                    current_chunk.append(sid)
                else:
                    chunks.append(current_chunk)
                    current_chunk = [sid]
        if current_chunk:
            chunks.append(current_chunk)

        review_prompt = f"""You are a master YouTube script doctor and high-retention audio editor.
Your task is to REVIEW and ELEVATE the provided {lang.capitalize()} story segments into compelling, professional narration.

CRITICAL INSTRUCTIONS:
1. STANDALONE & COMPLETE THOUGHTS: Fix all dangling word cutoffs (e.g. 'and', 'to', 'then', 'because'). Every segment must be a complete, grammatically sound sentence.
2. SEAMLESS NARRATIVE FLOW: Ensure natural transitions between segments. The narration should feel like an engaging storyteller speaking naturally.
3. PURGE JUNK & REPETITION: Remove any stuttering, duplicate phrasing, channel branding, or untranslated characters.
4. STRICT TIMING INTEGRITY: Do NOT combine or remove segments. You MUST return a JSON object with a single key 'translations' containing EXACTLY the same segment IDs with polished text.
"""

        # 3. Process review chunks using the multi-key pool / execute translation
        result_map = {}
        for chunk_idx, chunk_ids in enumerate(chunks):
            chunk_segments = [{"id": sid, "text": segments[seg_id_to_idx[sid]].get(lang, "")} for sid in chunk_ids]
            print(f"  [Self-Review] 🔄 Refining chunk {chunk_idx + 1}/{len(chunks)} (Segments {chunk_ids})...")
            try:
                # Use validator provider if available, or fall back to primary provider
                provider = self.validator_provider or (self.providers[0] if self.providers else None)
                if provider:
                    refined = provider.translate_segments(chunk_segments, review_prompt, context="Self-review script enhancement", target_language=lang)
                    for item in refined:
                        try:
                            rid = int(item["id"])
                            text_val = item.get("translated_text") or item.get(lang) or item.get("text")
                            if text_val and text_val.strip():
                                result_map[rid] = text_val.strip()
                        except:
                            pass
            except Exception as e:
                print(f"  [Self-Review] Warning: Chunk {chunk_idx + 1} refinement failed ({e}). Keeping original text.")

        # 4. Apply refined text back to segments
        improved_count = 0
        for seg in segments:
            sid = int(seg["id"])
            if sid in result_map and result_map[sid]:
                seg[lang] = result_map[sid]
                improved_count += 1

        print(f"  [Self-Review] ✅ Successfully polished {improved_count} segments with automated review loop.")
        return segments

    def post_process_script(self, segments: list, target_language: str = "english") -> list:
        """
        Final safety and QA sweep across the completed script:
        1. Purges any leaked Devanagari/Hindi characters from English narrations.
        2. Fixes dangling word cutoffs at segment boundaries (e.g. 'to', 'then.', 'The door', 'and', 'waiting for').
        3. Cleans boundary stuttering / duplicate sentences between adjacent segments.
        4. Standardizes canonical naming (e.g. 'Mama Cecile', 'Terrebonne Parish').
        """
        import re
        lang = target_language.lower()
        if not segments:
            return segments

        for seg in segments:
            text = seg.get(lang, "").strip()
            if not text:
                continue

            if lang == "english":
                # 1. Purge any Devanagari text leaking into English
                if re.search(r'[\u0900-\u097F]', text):
                    cleaned = re.sub(r'[\u0900-\u097F\s।॥]+', ' ', text).strip()
                    if len(cleaned.split()) >= 4:
                        text = cleaned
                    else:
                        print(f"  [QA Fix] Purged raw Hindi from segment {seg.get('id')}")
                        text = cleaned if cleaned else text

                # 2. Fix dangling word cutoffs at the end of segments
                text = re.sub(r'[,;\s]+(?:and|but|or|so|to|then|which|that|because|the door|waiting for|Conjugation of)\.?$', '.', text, flags=re.IGNORECASE)
                text = re.sub(r'\.\s*Luke then\.?$', '.', text, flags=re.IGNORECASE)
                text = re.sub(r'\.\s*Once Violet had left the room\.?$', '.', text, flags=re.IGNORECASE)
                text = re.sub(r'\s+to$', '.', text)

                # 3. Canonical terms and entity corrections
                text = re.sub(r'\bUncle Cecil\b', 'Mama Cecile', text)
                text = re.sub(r'\bUncle Cecile\b', 'Mama Cecile', text)
                text = re.sub(r'\bTerabon\b', 'Terrebonne', text)
                text = re.sub(r'\bCanjar of Sacrifice\b', 'Conjure of Sacrifice', text, flags=re.IGNORECASE)
                text = re.sub(r'\bConjugation of Supreme Protection\b', 'Conjuration of Supreme Protection', text, flags=re.IGNORECASE)

            # Ensure proper punctuation at the end of every segment
            text = text.strip()
            if text and not text.endswith(('.', '!', '"', "'")):
                text += '.'
            
            # Remove any double spaces, comma-periods, or awkward punctuation
            text = re.sub(r'[,;]\s*\.', '.', text)
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\s+\.', '.', text)
            seg[lang] = text

        # 4. Anti-stutter boundary pass across adjacent segments
        for i in range(len(segments) - 1):
            curr_text = segments[i].get(lang, "").strip()
            next_text = segments[i+1].get(lang, "").strip()
            if not curr_text or not next_text:
                continue

            curr_sentences = [s.strip() for s in curr_text.split('.') if s.strip()]
            next_sentences = [s.strip() for s in next_text.split('.') if s.strip()]

            # If next segment repeats the exact last sentence of current segment, trim it
            if curr_sentences and next_sentences:
                last_curr = curr_sentences[-1].lower()
                first_next = next_sentences[0].lower()
                if last_curr and (last_curr == first_next or (len(last_curr) > 25 and (last_curr in first_next or first_next in last_curr))):
                    trimmed_next = ". ".join(next_sentences[1:])
                    if trimmed_next:
                        segments[i+1][lang] = trimmed_next + ('.' if not trimmed_next.endswith('.') else '')

        return segments

