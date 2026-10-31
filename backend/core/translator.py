import json
import os
import re
import time

try:
    import dotenv
    dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

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
        self.movie_metadata = {}  # Dynamic entity metadata extracted in Layer 1
        
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

    def get_system_prompt(self, target_language: str, glossary: str = "", channel_type: str = "movie_recap", is_source_english: bool = False) -> str:
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
            elif is_source_english and lang == "english":
                base_prompt = """You are an elite Hollywood screenplay and YouTube movie recap script editor.
The input consists of raw auto-generated English captions from a YouTube movie breakdown. Because of subtitle timing and chunking, these captions are sliced mid-thought every 3-5 seconds, contain transcription errors, and include creator chatter.

Your mission is NOT to summarize, but to ELEVATE and POLISH these captions into a flawless, captivating English voiceover narration script.

CRITICAL EDITORIAL RULES:
1. STANDALONE & COMPLETE SENTENCES (KOKORO TTS AUDIO RULE):
   - Every single segment MUST be a self-contained, grammatically complete sentence ending strictly with a period (.), exclamation point (!), or question mark (?).
   - If an input fragment ends abruptly mid-thought (e.g., 'and then he went', 'because the killer was'), reconstruct the complete intended thought using the surrounding story context.
   - NEVER start a segment with lowercase continuation words (e.g. 'and her', 'began to clean'). Capitalize the first word.
   - NEVER end a segment on a trailing preposition or conjunction ('to', 'and', 'but', 'because', 'so').
2. TOTAL BRANDING, FILLER & CHATTER PURGE:
   - STRICTLY FORBIDDEN: NEVER mention third-party channel names (e.g. Filmi Cheeti, Mystery Recapped, Binge Lab, Cinema Mirage) or original creator handles!
   - Purge all YouTube meta-chatter ('Subscribe now', 'Hit the bell icon', 'Leave a like', 'Stay tuned', 'In the next episode', 'Link in description').
   - Purge stray non-story vocalizations or sign-offs (e.g., 'Om', 'Om.', 'Shanti').
   - If the first segment contains a channel greeting, open immediately with an intense story hook about the film itself.
3. PRESERVE ACCURACY, FACTS & CHRONOLOGY (NO SUMMARIZING):
   - AUDIO IS KING: Deliver the full story with complete emotional weight, mystery, and suspense.
   - NEVER compress multiple segments into a brief summary. Maintain 1-to-1 narrative progression.
   - Preserve all character names, dates (e.g., 1988), case facts, and sequence of events as described.
4. NATURAL SPOKEN RHYTHM & PACING:
   - Write sentences that sound punchy, tense, and captivating when read aloud by a Text-to-Speech narrator.
   - End declarative statements with a period (.). Never use malformed marks ('?.', '!.', '..').
5. STRICT TIMING & ID PRESERVATION:
   - Return exactly one polished translation object for every input ID. Do not merge, skip, or delete IDs."""
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
3. ABSOLUTE STANDALONE SENTENCES & KOKORO TTS AUDIO RULES:
   - CRITICAL: NEVER SLICE OR CHOP A SINGLE SENTENCE ACROSS MULTIPLE IDS!
   - Kokoro Text-to-Speech (TTS) makes bizarre glitched breathing noises when sentences end abruptly on clauses or conjunctions.
   - Every single segment MUST be a complete, grammatically sound, finished standalone sentence or dialogue ending strictly with a period (.), exclamation point (!), or question mark (?).
   - NEVER start a segment with a lowercase continuation word (e.g., 'inside to look', 'and her', 'began to clean'). Always capitalize the first word.
   - NEVER end a segment on a comma (,), an unfinished preposition, or a trailing conjunction (e.g., 'when she went', 'and her', 'it then', 'just then', 'and', 'but', 'because', 'so', 'to').
   - If the input Hindi subtitle chunk is short (3-5 words) or cut off mid-thought, DO NOT translate it literally as a half-sentence fragment. Use the story context to complete the full, independent thought cleanly within that segment!
4. SEAMLESS BOUNDARY HARMONIZATION (NO DUPLICATE REPETITIONS):
   - When an input segment begins with a fragment carried over from an earlier sentence, DO NOT repeat what the previous segment already narrated.
   - Seamlessly advance the narrative without stuttering or duplicating lines across adjacent segments.
5. STRICT ZERO-DEVANAGARI GUARANTEE:
   - Under NO circumstances should any Devanagari or Hindi characters (e.g., हिन्दी अक्षर) appear anywhere in the output!
   - The entire output MUST be 100% fluent, idiomatic English. Never copy source Hindi into the English field.
6. IDENTITY & ACTION LOGIC (BODY SWAPS / THRILLERS):
   - In thrillers involving body-swapping, possession, or disguise, maintain strict logical distinction between the physical body and the soul/consciousness inside it.
   - Ensure that actions reflect the narrative reality without reversing roles!
7. GENDER & CANON ENTITY LOCK:
   - Always maintain correct character pronouns, names, and titles according to the Story Glossary.
8. AUDIO-FIRST STORYTELLING & NATURAL CHRONOLOGY:
   - Deliver the full story with complete emotional weight, tension, and storytelling nuance. NEVER summarize into a dry summary.
   - Strictly narrate events belonging to this segment. Do not jump ahead.
9. NATURAL SPOKEN RHYTHM & PACING:
   - Write sentences that sound natural, rhythmic, and captivating for a voiceover narrator. End complete sentences with a period (.).
10. FIX TRANSCRIPTION TYPOS: Correct phonetic transcription errors using context.
11. PRESERVE SEGMENT IDS: Return exactly one translation object for every input ID."""

        if glossary:
            base_prompt += f"\n\nCRITICAL STORY GLOSSARY (Use these to resolve typos, character genders, and ambiguous terms):\n{glossary}"
            
        return base_prompt

    def _extract_glossary(self, segments, metadata_path: str = "", is_source_english: bool = False) -> str:
        """
        Layer 1: Generic Dynamic Structured Grounding.
        Extracts structured JSON metadata (movie_title, characters, key_terms) for ANY film/incident
        using Groq with response_format={"type": "json_object"}.
        Persists to metadata_path if provided, and stores in self.movie_metadata.
        Returns a rich Markdown glossary string for general prompt grounding.
        """
        # If metadata was already cached to disk for this video, load it instantly!
        if metadata_path and os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    self.movie_metadata = json.load(f)
                if self.movie_metadata and "characters" in self.movie_metadata:
                    print(f"  [Layer 1 Grounding] ⏩ Loaded cached entity metadata from: {metadata_path}")
                    return self._format_glossary_markdown(self.movie_metadata)
            except Exception as e:
                print(f"  [Layer 1 Grounding] Warning loading cached metadata: {e}")

        groq_keys = []
        if self.api_key: groq_keys.append(self.api_key)
        for k in [os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_API_KEY_TWO"), os.environ.get("GROQ_API_KEY_THREE")]:
            if k and k not in groq_keys:
                groq_keys.append(k)
                
        if not groq_keys:
            return ""
            
        full_text = " ".join([s.get("text", "") for s in segments[:120]])
        full_text = full_text[:8000] # Provide ample context
        
        lang_desc = "English YouTube" if is_source_english else "Hindi/Hinglish"
        prompt = f"""You are an expert Hollywood screenplay and movie recap script analyst.
Analyze the following {lang_desc} movie recap transcript and extract a definitive, structured JSON entity guide.

Return a STRICT JSON object with these exact keys:
{{
  "movie_title": "Title of the movie or real incident",
  "genre": "Genre (e.g. Horror, Mystery Thriller, True Crime)",
  "characters": [
    {{
      "canonical_name": "Full English Character Name (e.g. Caroline Ellis)",
      "aliases": ["Caroline", "Nurse"],
      "gender": "female" or "male",
      "role_summary": "Brief 1-line description of role in the story",
      "hindi_phonetic_spellings": ["Phonetic spellings if applicable, or []"]
    }}
  ],
  "key_terms": [
    {{
      "canonical_term": "English Term or Location (e.g. Terrebonne Parish)",
      "hindi_phonetic_spellings": ["Phonetic spellings if applicable, or []"],
      "meaning": "Brief explanation"
    }}
  ]
}}
Identify all characters, villains, victims, and crucial props/locations. Be thorough and accurate."""

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
                    response_format={"type": "json_object"},
                    temperature=0.2
                )
                raw_json = completion.choices[0].message.content.strip()
                data = json.loads(raw_json)
                self.movie_metadata = data
                print(f"  [Layer 1 Grounding] ✅ Identified Movie: '{data.get('movie_title')}' with {len(data.get('characters', []))} characters & {len(data.get('key_terms', []))} key terms.")

                if metadata_path:
                    try:
                        with open(metadata_path, "w", encoding="utf-8") as mf:
                            json.dump(data, mf, indent=2, ensure_ascii=False)
                    except Exception as e:
                        print(f"  [Layer 1 Grounding] Warning saving metadata: {e}")

                return self._format_glossary_markdown(data)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate_limit" in err_str:
                    print(f"  [Layer 1 Grounding] Key #{k_idx+1} hit rate limit (429). Trying next key...")
                    continue
                print(f"  [Layer 1 Grounding] Extraction failed on Key #{k_idx+1}: {e}")
        return ""

    def _format_glossary_markdown(self, metadata: dict) -> str:
        """Converts structured metadata into a rich Markdown prompt section."""
        lines = []
        if metadata.get("movie_title"):
            lines.append(f"Movie / Story Title: {metadata['movie_title']} ({metadata.get('genre', 'Drama')})")
        
        characters = metadata.get("characters", [])
        if characters:
            lines.append("\nStandard Character Names & Roles:")
            for c in characters:
                cname = c.get("canonical_name", "")
                gender = c.get("gender", "unknown")
                role = c.get("role_summary", "")
                spellings = ", ".join(c.get("hindi_phonetic_spellings", []))
                lines.append(f"- {cname} ({gender.capitalize()}, Role: {role}) | Hindi ASR spellings: [{spellings}]")

        terms = metadata.get("key_terms", [])
        if terms:
            lines.append("\nCanonical Locations & Story Elements:")
            for t in terms:
                tname = t.get("canonical_term", "")
                mean = t.get("meaning", "")
                spellings = ", ".join(t.get("hindi_phonetic_spellings", []))
                lines.append(f"- {tname}: {mean} | Hindi ASR spellings: [{spellings}]")

        return "\n".join(lines)

    def get_batch_entity_bindings(self, batch_segments: list) -> str:
        """
        Layer 2: Generic Dynamic In-Prompt Entity Binding (Per Batch).
        Scans the batch's Hindi text against self.movie_metadata.
        Dynamically constructs targeted entity anchoring rules strictly for the
        characters and terms present in this specific batch.
        Zero hardcoded names — 100% dynamically resolved from Layer 1.
        """
        if not self.movie_metadata:
            return ""

        batch_text = " ".join([s.get("text", "") for s in batch_segments])
        active_characters = []
        for char in self.movie_metadata.get("characters", []):
            spellings = char.get("hindi_phonetic_spellings", [])
            matched_spellings = [sp for sp in spellings if sp and sp in batch_text]
            if not matched_spellings:
                cname = char.get("canonical_name", "")
                aliases = char.get("aliases", [])
                for n in [cname] + aliases:
                    if len(n) > 2 and re.search(rf'\b{re.escape(n)}\b', batch_text, re.IGNORECASE):
                        matched_spellings.append(n)
                        break
            if matched_spellings:
                active_characters.append((char, matched_spellings))

        active_terms = []
        for term in self.movie_metadata.get("key_terms", []):
            spellings = term.get("hindi_phonetic_spellings", [])
            matched_spellings = [sp for sp in spellings if sp and sp in batch_text]
            if not matched_spellings:
                tname = term.get("canonical_term", "")
                if tname and re.search(rf'\b{re.escape(tname)}\b', batch_text, re.IGNORECASE):
                    matched_spellings.append(tname)
            if matched_spellings:
                active_terms.append((term, matched_spellings))

        if not active_characters and not active_terms:
            return ""

        binding_lines = ["\n### DYNAMIC ENTITY LOCKS FOR THIS SPECIFIC BATCH:"]
        binding_lines.append("The following story entities are actively mentioned in this batch's source text. Adhere strictly to these canonical names:")
        
        for char, spellings in active_characters:
            cname = char.get("canonical_name")
            gender = char.get("gender", "unknown").lower()
            pronouns = "he / him / his" if gender == "male" else ("she / her / hers" if gender == "female" else "they / them")
            spellings_str = ", ".join([f"'{s}'" for s in spellings])
            binding_lines.append(
                f"- Entity Reference: {spellings_str} -> CANONICAL CHARACTER: '{cname}' ({gender.capitalize()}, Pronouns: {pronouns}). Role: {char.get('role_summary', '')}."
                f"\n  STRICT: Maintain this character as '{cname}'. NEVER substitute unrelated phonetic words or confuse identities!"
            )

        for term, spellings in active_terms:
            tname = term.get("canonical_term")
            spellings_str = ", ".join([f"'{s}'" for s in spellings])
            binding_lines.append(
                f"- Term Reference: {spellings_str} -> CANONICAL TERM: '{tname}' ({term.get('meaning', '')}). Maintain strictly as '{tname}'."
            )

        return "\n".join(binding_lines)

    def check_entity_consistency(self, batch_source_segments: list, batch_translated_segments: list, target_language: str = "english") -> dict:
        """
        Layer 3: Generic Source-to-Target Entity Consistency Check (Automated QA).
        Algorithmic check across all segments in the batch:
        If any character from self.movie_metadata is found in the source text (via
        hindi_phonetic_spellings or English names), verifies that the character's
        canonical name, alias, or gender-appropriate pronoun is present in the output text.
        Zero hardcoded names — 100% dynamically resolved from Layer 1.
        Returns: dict mapping segment ID -> list of defect messages.
        """
        defects = {}
        if target_language.lower() != "english" or not self.movie_metadata:
            return defects

        characters = self.movie_metadata.get("characters", [])
        if not characters:
            return defects

        trans_map = {}
        for t in batch_translated_segments:
            try:
                sid = int(t.get("id"))
                text_val = t.get("translated_text") or t.get("english") or t.get("text") or ""
                trans_map[sid] = text_val
            except Exception:
                pass

        for src in batch_source_segments:
            try:
                sid = int(src.get("id"))
            except Exception:
                continue

            src_text = src.get("text", "")
            trans_text = trans_map.get(sid, "")
            if not trans_text:
                continue

            for char in characters:
                spellings = char.get("hindi_phonetic_spellings", [])
                cname = char.get("canonical_name", "")
                aliases = char.get("aliases", [])
                gender = char.get("gender", "").lower()

                # Check if character was mentioned in source
                matched_spellings = [sp for sp in spellings if sp and sp in src_text]
                if not matched_spellings and cname:
                    for n in [cname] + aliases:
                        if len(n) > 2 and re.search(rf'\b{re.escape(n)}\b', src_text, re.IGNORECASE):
                            matched_spellings.append(n)
                            break

                if matched_spellings:
                    # Check for canonical name or alias match
                    names_to_search = [cname.lower()] + [a.lower() for a in aliases if len(a) > 2]
                    name_present = any(n in trans_text.lower() for n in names_to_search if n)

                    # Pronoun fallback check
                    pronoun_pattern = r'\b(he|him|his)\b' if gender == "male" else (r'\b(she|her|hers)\b' if gender == "female" else r'\b(they|them)\b')
                    pronoun_present = bool(re.search(pronoun_pattern, trans_text, re.IGNORECASE))

                    if not name_present and not pronoun_present:
                        defect_desc = f"Source mentioned '{matched_spellings[0]}' ({cname}), but translation omitted or scrambled the character."
                        if sid not in defects:
                            defects[sid] = []
                        defects[sid].append(defect_desc)

        return defects

    @staticmethod
    def detect_punctuation_glitches(text: str) -> list:
        """
        Detects all malformed punctuation patterns that cause Kokoro TTS glitching:
        - Mixed terminal marks ('?.', '!.', '.?', '.!')
        - Double/triple marks ('??', '!!', '?!', '!?')
        - Ellipses or double periods ('..', '...', '....')
        - Comma/semicolon/dash collisions (',.', ';.', '.,', ':,')
        - Trailing commas, semicolons, colons, or dashes (',', ';', ':', '-', '—')
        - Space before terminal punctuation (' .', ' ?')
        """
        glitches = []
        if not text:
            return glitches
            
        if re.search(r'[\?!]+\s*\.+', text):
            glitches.append("Mixed question/exclamation with period (e.g. '?.', '!.')")
        if re.search(r'\.+\s*[\?!]+', text):
            glitches.append("Period followed by question/exclamation (e.g. '.?', '.!')")
        if re.search(r'[?!]{2,}', text):
            glitches.append("Repeated question/exclamation marks (e.g. '?!', '??')")
        if re.search(r'\.{2,}', text):
            glitches.append("Ellipsis or multiple periods (e.g. '..', '...')")
        if re.search(r'[,;:–—-]\s*[.!?]|[.!?,]\s*[,;:–—-]', text):
            glitches.append("Conflicting punctuation collision (e.g. ',.', '.,', '-.')")
        if re.search(r'[,;:–—-]\s*$', text):
            glitches.append("Trailing dangling punctuation mark at end of segment")
        if re.search(r'[,;]{2,}', text):
            glitches.append("Repeated commas or semicolons (e.g. ',,')")
        return glitches

    def get_validator_prompt(self, target_language: str, qa_defects: dict = None) -> str:
        prompt = f"""You are a strict QA Editor for a YouTube movie recap channel.
Review and fix the provided {target_language.capitalize()} script segments.
Rules:
1. ZERO UNTRANSLATED CHARACTERS: If target is English, ensure ZERO Hindi/Devanagari characters remain. Translate any missed text completely.
2. ELIMINATE WORD-FOR-WORD TRANSLATION: Ensure the dialogue sounds like a captivating, natural story told by an engaging human narrator.
3. STRICT 3RD PARTY BRANDING PURGE: Ensure NO third-party channel names (like Filmi Cheeti, Mystery Recapped, etc.), creator names, or subscribe/like pleas remain.
4. KOKORO TTS COMPLETION RULE (NO CHOPPED OR SLICED SENTENCES):
   - Every single segment MUST be a self-contained, grammatically complete sentence ending strictly with a period (.), exclamation point (!), or question mark (?).
   - NEVER allow a sentence to be sliced or chopped across two segments (e.g., segment A ending with 'and her', 'when she went', or 'it then', and segment B starting with lowercase).
   - If a segment is an incomplete fragment or clause, rewrite it into a full, finished, independent sentence.
5. NO MALFORMED PUNCTUATION PATTERNS:
   - NEVER combine marks like '?.', '!.', '.?', or '..'.
   - NEVER end a segment with an ellipsis ('...'), dangling comma (','), semicolon, or hyphen.
   - End declarative statements with a single clean period (.).
6. NO DUPLICATE REPETITIONS: If two adjacent segments repeat the same statement, harmonize them seamlessly.
7. CRITICAL: You MUST return a JSON object with a single key 'translations' containing EXACTLY the same 'id's as provided.
8. Do not merge segments. Do not delete IDs. Return ALL provided IDs.
"""
        if qa_defects:
            prompt += "\n\nCRITICAL IDENTIFIED DEFECTS TO FIX IN THIS BATCH:\n"
            for sid, msgs in qa_defects.items():
                prompt += f"- Segment ID {sid}: " + "; ".join(msgs) + "\n"
            prompt += "STRICT REQUIREMENT: Ensure all entity omissions and punctuation glitches in these flagged segments are fully corrected!\n"

        return prompt

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
            
        lang_key = target_language.lower()
        base_name = os.path.splitext(os.path.basename(transcript_path))[0].replace("_transcript", "")
        suffix = f"_{channel_type}" if channel_type == "thriller_story" else ""
        output_path = os.path.join(output_dir, f"{base_name}_{lang_key}{suffix}_transcript.json")
        checkpoint_path = os.path.join(output_dir, f"{base_name}_{lang_key}{suffix}_checkpoint.json")
        metadata_path = os.path.join(output_dir, f"{base_name}_metadata.json")
        
        # Load progress from checkpoint if a previous run was paused/interrupted
        translated_map = {}
        if os.path.exists(checkpoint_path):
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as cf:
                    saved_list = json.load(cf)
                    for s in saved_list:
                        val = s.get(lang_key, "").strip()
                        if val and val.lower() not in ["translation/rewrite failed", "error"]:
                            translated_map[int(s["id"])] = s
                if translated_map:
                    print(f"  [Resume] ⏩ Found checkpoint! Loaded {len(translated_map)}/{len(segments)} already translated segments from: {checkpoint_path}")
            except Exception as e:
                print(f"  [Resume] Warning reading checkpoint: {e}")
                translated_map = {}
        
        # Automatically detect if source transcript is already English
        sample_text = " ".join([s.get("text", "") for s in segments[:30]])
        has_devanagari = bool(re.search(r'[\u0900-\u097F]', sample_text))
        is_source_english = not has_devanagari and len(re.findall(r'[a-zA-Z]', sample_text)) > 50

        mode_desc = "English Script Elevation" if (is_source_english and lang_key == "english") else f"{lang_key.capitalize()} translation"
        print(f"Extracting contextual glossary for {mode_desc}...")
        glossary = self._extract_glossary(segments, metadata_path=metadata_path, is_source_english=is_source_english)
        
        system_prompt = self.get_system_prompt(lang_key, glossary, channel_type=channel_type, is_source_english=is_source_english)
        
        # Process in batches
        for i in range(0, len(segments), self.batch_size):
            batch = segments[i:i+self.batch_size]
            batch_ids = {int(seg["id"]) for seg in batch}
            
            # If every segment in this batch was already completed in the checkpoint, skip immediately!
            if batch_ids.issubset(translated_map.keys()):
                print(f"  [Resume] ⏩ Skipping batch {i // self.batch_size + 1} (Segments {min(batch_ids)}-{max(batch_ids)} already translated in checkpoint).")
                continue
            
            # Build context (1 sentence before and 1 after the batch)
            prev_context = segments[i-1]["text"] if i > 0 else ""
            next_idx = i + self.batch_size
            next_context = segments[next_idx]["text"] if next_idx < len(segments) else ""
            context = f"{prev_context} [...] {next_context}"
            
            # Layer 2: Dynamic in-prompt entity binding for this specific batch
            entity_bindings = self.get_batch_entity_bindings(batch)
            batch_system_prompt = system_prompt + ("\n\n" + entity_bindings if entity_bindings else "")

            valid_results = []
            
            # --- Pass 1: Translation with retry loop for missing IDs ---
            for attempt in range(self.max_retries + 1):
                print(f"Generating {lang_key} script for batch {i // self.batch_size + 1} (Attempt {attempt+1})...")
                results = self._execute_translation(batch, batch_system_prompt, context, lang_key)
                
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
                            recovered = self._execute_translation([missing_seg], batch_system_prompt, context="", target_language=lang_key)
                            for r in recovered:
                                if int(r.get("id", missing_id)) == missing_id:
                                    valid_results.append(r)
                                    print(f"  -> Successfully recovered translation for missing segment {missing_id}")
                        except Exception as e:
                            print(f"  -> Single-segment recovery failed for ID {missing_id}: {e}")
                
            # --- Pass 2: Smart Conditional Validation, Layer 3 QA & Punctuation Glitch Inspector ---
            needs_validation = False
            qa_defects = {}
            if valid_results:
                # 1. Layer 3: Generic source-to-target entity consistency check
                entity_defects = self.check_entity_consistency(batch, valid_results, target_language=lang_key)
                for sid, msgs in entity_defects.items():
                    qa_defects.setdefault(sid, []).extend(msgs)

                # 2. Punctuation & Syntax Glitch Inspection ('?.', '!.', '..', etc.)
                for r in valid_results:
                    sid = int(r.get("id", 0))
                    val_text = r.get("translated_text", r.get(lang_key, r.get("text", ""))).strip()
                    punct_glitches = self.detect_punctuation_glitches(val_text)
                    if punct_glitches:
                        qa_defects.setdefault(sid, []).extend(punct_glitches)

                if qa_defects:
                    needs_validation = True
                    print(f"  [QA Inspector] ⚠️ Flagged defects in batch {i // self.batch_size + 1} (IDs: {list(qa_defects.keys())})")

            if self.validator_provider and valid_results and not needs_validation:
                for r in valid_results:
                    val_text = r.get("translated_text", r.get(lang_key, r.get("text", ""))).strip()
                    if lang_key == "english" and re.search(r'[\u0900-\u097F]', val_text):
                        needs_validation = True
                        break
                    # Water-tight check for Kokoro TTS audio quality:
                    # 1. Missing terminal sentence punctuation or ending with a comma
                    if not re.search(r'[.!?]["\']?$', val_text) or val_text.endswith(','):
                        needs_validation = True
                        break
                    # 2. Dangling trailing conjunctions, prepositions, or cutoffs
                    if re.search(r'[,;\s]+(?:and|but|or|so|to|then|which|that|because|when|while|with|and her|as well as|the door|waiting for)\.?$', val_text, re.IGNORECASE):
                        needs_validation = True
                        break
                    # 3. Starting with lowercase continuation word
                    if val_text and val_text[0].islower():
                        needs_validation = True
                        break
                    if val_text.endswith("...") or len(val_text.split()) < 3:
                        needs_validation = True
                        break

            if needs_validation and self.validator_provider:
                print(f"Validating batch {i // self.batch_size + 1} with second API key (defects detected)...")
                validator_prompt = self.get_validator_prompt(lang_key, qa_defects=qa_defects)
                
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

                translated_map[seg_id] = {
                    "id": seg["id"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "original_text": seg["text"],
                    lang_key: final_text
                }

            # Incrementally persist checkpoint to disk after every batch
            try:
                sorted_checkpoint = [translated_map[s["id"]] for s in segments if s["id"] in translated_map]
                with open(checkpoint_path, "w", encoding="utf-8") as cf:
                    json.dump(sorted_checkpoint, cf, indent=2, ensure_ascii=False)
                print(f"  [Checkpoint] 💾 Saved progress: {len(sorted_checkpoint)}/{len(segments)} segments safely persisted.")
            except Exception as e:
                print(f"  [Checkpoint] Warning writing checkpoint: {e}")
            
        # Reconstruct full list in original segment order
        translated_segments = [translated_map[s["id"]] for s in segments if s["id"] in translated_map]
            
        # Post-process and sanitize all segments for QA, zero-Devanagari, anti-dangling, and boundary smoothness
        # 1. Automated self-review and improvement loop
        reviewed_segments = self.self_review_and_improve(translated_segments, target_language=lang_key)
        translated_segments = self.post_process_script(reviewed_segments, target_language=lang_key)

        # If thriller story channel, smartly tag 30% AI visual moments
        if channel_type == "thriller_story":
            translated_segments = self.tag_ai_visual_segments(translated_segments, target_lang=lang_key, max_ratio=0.30)
            
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(translated_segments, f, indent=4, ensure_ascii=False)
            
        # Clean up checkpoint on complete success
        if os.path.exists(checkpoint_path):
            try:
                os.remove(checkpoint_path)
            except:
                pass
            
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
        dangling_pattern = re.compile(r'[,;\s]+(?:and|but|or|so|to|then|which|that|because|when|while|with|and her|as well as|the door|waiting for)\.?$', re.IGNORECASE)
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

            # Check 2: Missing terminal punctuation, trailing comma, or dangling words (Kokoro TTS protection)
            if not re.search(r'[.!?]["\']?$', text) or text.endswith(',') or dangling_pattern.search(text) or text.endswith((" to.", " to")):
                flagged_ids.add(int(seg["id"]))
                continue

            # Check 2b: Starts with lowercase (continuation fragment)
            if text and text[0].islower():
                flagged_ids.add(int(seg["id"]))
                continue

            # Check 2c: Malformed punctuation patterns ('?.', '!.', '.?', '..', '.,', trailing comma/dash)
            if self.detect_punctuation_glitches(text):
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

        # Check 6: Generic Layer 3 entity consistency check across entire script
        if lang == "english" and self.movie_metadata:
            entity_defects = self.check_entity_consistency(segments, segments, target_language=lang)
            for eid in entity_defects:
                flagged_ids.add(eid)

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
3. FLAWLESS PUNCTUATION & AUDIO CADENCE:
   - Ensure zero malformed marks (no '?.', '!.', '.?', '..', or trailing dashes/commas).
   - End every finished sentence with a single clean period (.).
4. PURGE JUNK & REPETITION: Remove any stuttering, duplicate phrasing, channel branding, or untranslated characters.
5. STRICT TIMING INTEGRITY: Do NOT combine or remove segments. You MUST return a JSON object with a single key 'translations' containing EXACTLY the same segment IDs with polished text.
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
        2. Fixes dangling word cutoffs at segment boundaries for Kokoro TTS audio hygiene.
        3. Comprehensive Punctuation & Syntax Sanitization (purges '?.', '!.', '.?', '..', '.,', trailing dashes/commas).
        4. Standardizes canonical terms dynamically using self.movie_metadata.
        5. Layer 4: Universal Tail Purge — Scrubs YouTube subscription/bell/channel pleas from final 5%.
        6. Cleans boundary stuttering / duplicate sentences between adjacent segments.
        """
        import re
        lang = target_language.lower()
        if not segments:
            return segments

        # Layer 4: Universal Outro / YouTube Meta-Chatter Purge for final 5%
        tail_idx_threshold = max(0, int(len(segments) * 0.95))
        yt_tail_pattern = re.compile(
            r'\b(subscribe|subscribing|channel|bell icon|notification|leave a like|hit like|comment below|thanks for watching|see you in the next|share this video|share with your friends|stay tuned|keep watching|watch the rest|watch the series)\b'
            r'|[\u0900-\u097F]*(?:सब्सक्राइब|लाइक|घंटी|बेल|शेयर|कमेंट|चैनल|ॐ|ओम)[\u0900-\u097F]*'
            r'|^\s*(?:om|shanti|namaste|peace|bye|thanks)\b\.?$',
            re.IGNORECASE
        )

        outro_beats = [
            "The mystery finally draws to a close, leaving behind questions that may never be answered.",
            "Every clue in this case has pushed the boundaries of what the detectives thought was real.",
            "The deeper the investigation went, the darker the truth became.",
            "As the case concludes, dark questions linger in the cold silence.",
            "The secrets of this investigation remain buried deep within the shadows.",
            "The truth remains elusive, waiting to be uncovered in time.",
            "Until our next journey into the darkness, stay curious and vigilant.",
            "And with that, our story reaches its thrilling conclusion. Thank you for watching."
        ]

        # Scan and tag all outro chatter or micro-fragments (< 3 words) in the tail
        chatter_indices = []
        for i in range(tail_idx_threshold, len(segments)):
            t = segments[i].get(lang, "").strip()
            orig = segments[i].get("original_text", "")
            if yt_tail_pattern.search(t) or yt_tail_pattern.search(orig) or len(t.split()) < 3:
                chatter_indices.append(i)

        if chatter_indices:
            total_chatter = len(chatter_indices)
            for c_pos, idx in enumerate(chatter_indices):
                dist_from_end = total_chatter - 1 - c_pos
                beat_idx = max(0, len(outro_beats) - 1 - dist_from_end)
                segments[idx][lang] = outro_beats[beat_idx]

        for i, seg in enumerate(segments):
            text = seg.get(lang, "").strip()
            orig = seg.get("original_text", "")
            if not text:
                continue

            if lang == "english":
                # 1. Purge any Devanagari text leaking into English
                if re.search(r'[\u0900-\u097F]', text):
                    cleaned = re.sub(r'[\u0900-\u097F\s।॥]+', ' ', text).strip()
                    if len(cleaned.split()) >= 4:
                        text = cleaned
                    else:
                        text = cleaned if cleaned else text

                # 2. Fix dangling word cutoffs at the end of segments for Kokoro TTS
                text = re.sub(r'[,;\s]+(?:and|but|or|so|to|then|which|that|because|when|while|with|and her|when she went|it then|just then|as well as|the door|waiting for)\.?$', '.', text, flags=re.IGNORECASE)
                text = re.sub(r'\s+to$', '.', text)
                text = re.sub(r',\s*$', '.', text)

                # 3. Dynamic Term & Character Title Harmonization
                if self.movie_metadata:
                    for char in self.movie_metadata.get("characters", []):
                        cname = char.get("canonical_name", "")
                        gender = char.get("gender", "").lower()
                        # If a female character was accidentally called "Uncle <Name>", fix dynamically
                        if gender == "female" and cname:
                            first_name = cname.split()[0]
                            text = re.sub(rf'\bUncle\s+{first_name}\b', rf'Mama {first_name}', text, flags=re.IGNORECASE)
                    
                    for term in self.movie_metadata.get("key_terms", []):
                        canon_term = term.get("canonical_term", "")
                        for spelling in term.get("hindi_phonetic_spellings", []):
                            # Remove any accidental raw Devanagari term transliterations
                            if spelling in text:
                                text = text.replace(spelling, canon_term)

            # 4. Comprehensive Punctuation & Syntax Sanitization
            text = re.sub(r'[\?!]+\s*\.+', '.', text)          # '?.', '!.' -> '.'
            text = re.sub(r'\.+\s*[\?!]+', '.', text)          # '.?', '.!' -> '.'
            text = re.sub(r'[?!]{2,}', '.', text)              # '?!', '!?', '??', '!!' -> '.'
            text = re.sub(r'\.{2,}', '.', text)                # '..', '...', '....' -> '.'
            text = re.sub(r'[,;:–—-]\s*[.!?]', '.', text)      # ',.', ';.', ':.', '-.' -> '.'
            text = re.sub(r'[.!?]\s*[,;:–—-]', '.', text)      # '.,', '.:' -> '.'
            text = re.sub(r'[,;]{2,}', ',', text)              # ',,', ';;' -> ','
            text = re.sub(r'[,;:–—-]\s*$', '.', text)          # Trailing comma, semicolon, dash -> '.'
            text = re.sub(r'\s+([.,!?])', r'\1', text)         # Space before punctuation -> remove

            # Ensure proper capitalization and punctuation at the end of every segment for Kokoro TTS
            text = text.strip()
            if text and text[0].islower():
                text = text[0].upper() + text[1:]
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

            # 4a. Exact sentence boundary overlap
            if curr_sentences and next_sentences:
                last_curr = curr_sentences[-1].lower()
                first_next = next_sentences[0].lower()
                if last_curr and (last_curr == first_next or (len(last_curr) > 25 and (last_curr in first_next or first_next in last_curr))):
                    trimmed_next = ". ".join(next_sentences[1:])
                    if trimmed_next:
                        segments[i+1][lang] = trimmed_next + ('.' if not trimmed_next.endswith('.') else '')
                        continue

            # 4b. Fuzzy overlap ratio across adjacent segments to catch subtitle split duplication
            w1 = set(re.findall(r'\b[a-z]{3,}\b', curr_text.lower()))
            w2 = set(re.findall(r'\b[a-z]{3,}\b', next_text.lower()))
            overlap = len(w1 & w2) / max(1, min(len(w1), len(w2)))
            if overlap >= 0.70 and len(w1) >= 4 and len(w2) >= 4:
                if next_sentences and len(next_sentences) > 1:
                    segments[i+1][lang] = ". ".join(next_sentences[1:]) + "."
                elif curr_sentences and len(curr_sentences) > 1:
                    segments[i][lang] = ". ".join(curr_sentences[:-1]) + "."

        return segments

