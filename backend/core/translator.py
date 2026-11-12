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
5. DURATION PACING & WORD-COUNT BUDGET (PREVENT VIDEO DRIFT):
   - Each input segment provides 'duration_sec' and 'max_words' (~2.2 - 2.5 words per second).
   - You MUST budget your English sentence length to stay within or close to 'max_words'.
   - NEVER write bloated, verbose sentences (e.g. 20+ words for a 3-second clip).
   - Keep sentences punchy, complete, and concise so the voiceover finishes synchronously with the video scene cut!
6. STRICT TIMING & ID PRESERVATION:
   - Return exactly one polished translation object for every input ID. Do not merge, skip, or delete IDs."""
            else:
                base_prompt = """You are a master YouTube movie-recap and storytelling narrator.
Your task is NOT to translate word-for-word, but to RE-SCRIPT and ELEVATE the narrative into an engaging, polished, and personal storytelling experience!

CRITICAL RULES FOR NARRATIVE EXCELLENCE:
1. BE A MASTER STORYTELLER (NEVER TRANSLATE WORD-FOR-WORD):
   - Do NOT translate literally. Re-script the text with personal storytelling flair, enthusiasm, and tension.
   - Use natural storytelling beats and audience engagement ('Now, this is where things take a bizarre turn...', 'Imagine being in his shoes...', 'Suddenly, an unexpected revelation changes everything.').
   - Keep the pace lively, engaging, and atmospheric.
2. TOTAL BRANDING & CHATTER PURGE ([SKIP_PROMO]):
   - NEVER mention any third-party channel names (e.g., 'Filmi Cheeti', 'Mystery Recapped', 'Binge Lab', 'Cinema Mirage') or original creator names/handles.
   - WHENEVER the speaker talks about other movies, previous uploads ('I recently explained...'), links in description/comments, sponsors, or channel subscriptions:
     DO NOT translate it! Set the translated text for that ID to exactly "[SKIP_PROMO]".
   - The automation pipeline will automatically drop the audio and cleanly trim out the promotional video footage from the final cut.
   - If the first segment contains a general greeting about the film, replace it with a captivating story hook about this movie. Focus 100% on the movie plot and characters.
3. ABSOLUTE STANDALONE SENTENCES & KOKORO TTS AUDIO RULES:
   - CRITICAL: NEVER SLICE OR CHOP A SINGLE SENTENCE ACROSS MULTIPLE IDS!
   - Kokoro Text-to-Speech (TTS) makes bizarre glitched breathing noises when sentences end abruptly on clauses or conjunctions.
   - Every single segment MUST be a complete, grammatically sound, finished standalone sentence or dialogue ending strictly with a period (.), exclamation point (!), or question mark (?).
   - NEVER start a segment with a lowercase continuation word (e.g., 'inside to look', 'and her', 'began to clean'). Always capitalize the first word.
   - NEVER end a segment on a comma (,), an unfinished preposition, a relative pronoun, or a trailing conjunction (e.g., 'who', 'which', 'that', 'the one who', 'the very one who', 'when she went', 'and her', 'it then', 'just then', 'and', 'but', 'because', 'so', 'to', 'with', 'from').
   - If the input Hindi subtitle chunk is short (3-5 words) or cut off mid-thought, DO NOT translate it literally as a half-sentence fragment. Use the story context to complete the full, independent thought cleanly within that segment!
4. SEAMLESS BOUNDARY HARMONIZATION & NO DUPLICATE REPETITIONS:
   - When an input segment begins with a fragment or trailing clause from a sentence that was already completed in the previous segment, DO NOT re-translate or paraphrase that thought again.
   - Omit the trailing remnant and dedicate the segment entirely to advancing the new action or thought.
   - Maintain uniform entity naming and noun forms across adjacent lines (never arbitrarily flip between singular and plural, or swap synonyms for the same subject back-to-back).
   - Seamlessly advance the narrative without stuttering, semantic looping, or duplicating lines across adjacent segments.
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
9. DURATION PACING & WORD-COUNT BUDGET (CRITICAL VISUAL SYNC):
   - Each segment provides 'duration_sec' and 'max_words' (~2.2 - 2.5 words per second of original video).
   - You MUST budget your translated sentence length to fit within or close to 'max_words'.
   - NEVER write bloated, over-long compound sentences (e.g. 20+ words for a 3-second scene) that spill over into later scenes.
   - Write punchy, cinematic sentences that capture the full action and finish synchronously with the camera transition.
10. NATURAL SPOKEN RHYTHM & PACING:
   - Write sentences that sound natural, rhythmic, and captivating for a voiceover narrator. End complete sentences with a period (.).
11. FIX TRANSCRIPTION TYPOS: Correct phonetic transcription errors using context.
12. PRESERVE STORY INTEGRITY & SEGMENT IDS:
   - For all movie story plot events, maintain strict 1-to-1 narrative progression without compressing or skipping plot points.
   - Return exactly one translation object for every input ID. If an ID contains promotional chatter, set its text to "[SKIP_PROMO]". Do not merge or omit ID numbers from the output JSON.
13. UNIVERSAL 3RD-PERSON POV & UNAMBIGUOUS CHARACTER ATTRIBUTION:
   - The narration must remain 100% in the third-person voice ("Alice said", "Dr. Alvar revealed", "She realized").
   - NEVER slip into first-person pronouns ("I", "my", "we", "mine") during character dialogue or testimony unless explicitly enclosed in direct quotation marks: e.g., Alice said, "I will go in alone."
   - When the source narrator recounts a character speaking about their family ("मेरा बेटा"), attribute kinship explicitly to that specific character (e.g., "García del Olmo swore his son would never commit suicide," NEVER "my son").
14. PHONETIC ASR REPAIR & HINDI IDIOM RESOLUTION:
   - Recognize common ASR phonetic mishearings in crime/mystery settings:
     * "कॉर्नर" / "लुसिया कॉर्नर" in forensic contexts -> MUST be translated as "Coroner" / "the forensic coroner" (NEVER "Lucia Corner").
     * "मेल वर्ल्ड" in an asylum/hospital context -> MUST be translated as "Male Ward" (NEVER "male world").
     * "tlegram" / "टेलीग्राम" -> "telegram".
     * Completely IGNORE and STRIP all acoustic tags such as [गला साफ़ करने की आवाज़], [संगीत], [हंसी], or [तालियां]. Never let them influence grammar or sentence flow.
   - Cultural idioms: "मुंह बोली बहन" / "मुंह बोला भाई" MUST be translated as "adoptive sister/brother", "foster sister/brother", or "the girl he considered his sister". Strictly BAN "verbal sister", "talking sister", or "mouth sister".
15. CLIMAX MASTER TWIST PRESERVATION (FINAL 15% OF SCRIPT):
   - In psychological thrillers and mystery recaps, the resolution holds 80% of audience satisfaction.
   - You are FORBIDDEN from omitting, skipping, or diluting character identity reveals, motives, or plot deductions.
   - When the true identity of a culprit or key figure is revealed (e.g. Dr. Donadío being the fake client), you MUST explicitly state the deduction and its narrative impact clearly.
16. OUTRO CHATTER & META-COMMENTARY PURGE ([SKIP_PROMO]):
   - Any segment where the creator addresses video length ("video bohot lambi ho gayi hai"), asks for likes/subscribes, talks about reels, or says goodbye MUST be translated strictly as "[SKIP_PROMO]"."""

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
  "movie_title": "Exact title of the movie if mentioned or introduced in the transcript, otherwise null",
  "genre": "Genre (e.g. Horror, Mystery Thriller, True Crime, Sci-Fi)",
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

MOVIE TITLE EXTRACTION RULES:
- If the narrator clearly mentions, introduces, or names the movie title in the script (e.g. 'aaj hum movie X explain karenge', 'today we will explain the movie X', 'in this film X...'), extract the clean, accurate movie title into "movie_title".
- If the narrator NEVER mentions or names the movie title in the script, set "movie_title": null.
- STRICT RULE: DO NOT guess, fabricate, or hallucinate a movie title if it is not mentioned in the transcript!

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

            # Duration & word-count pacing check (prevent voiceover from spilling into next scene)
            dur = 0.0
            if "start" in src and "end" in src:
                dur = float(src["end"]) - float(src["start"])
            elif "duration" in src:
                dur = float(src["duration"])
            if dur > 0.5:
                word_count = len(trans_text.split())
                max_allowed_words = max(8, int(round(dur * 3.0)))
                if word_count > max_allowed_words:
                    if sid not in defects:
                        defects[sid] = []
                    defects[sid].append(f"Pacing defect: {word_count} words exceeds scene duration ({dur:.1f}s, target ~{int(dur*2.4)} words). Condense into a punchy, complete sentence.")

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

    @classmethod
    def sanitize_segment_text(cls, text: str, target_language: str = "english") -> str:
        """
        Sanitizes and normalizes segment text for Kokoro TTS audio hygiene:
        - Resolves mixed punctuation marks ('?.', '!.', '.?') into single clean marks ('?', '!').
        - Eliminates repeated marks ('??', '!!', '..').
        - Fixes dangling conjunctions or trailing commas.
        - Capitalizes the first character.
        - Ensures every segment ends with valid terminal punctuation (., !, ?, etc.)
          WITHOUT appending an unwanted period to question marks or exclamation marks.
        """
        if not text:
            return ""
        import re
        lang = target_language.lower()
        
        # 1. Strip bracketed acoustic tags (e.g. [गला साफ़ करने की आवाज़], [संगीत], [हंसी])
        text = re.sub(r'\[(?:गला साफ़ करने की आवाज़|संगीत|हंसी|तालियां|throat clearing|cough|applause)[^\]]*\]', '', text, flags=re.IGNORECASE)

        # 2. Purge any Devanagari text leaking into English
        if lang == "english" and re.search(r'[\u0900-\u097F]', text):
            cleaned = re.sub(r'[\u0900-\u097F\s।॥]+', ' ', text).strip()
            if len(cleaned.split()) >= 4:
                text = cleaned
            elif cleaned:
                text = cleaned

        # 3. Fix dangling word cutoffs at the end of segments for Kokoro TTS
        text = re.sub(r'[,;\s]+(?:and|but|or|so|to|then|which|that|who|whom|whose|because|when|while|with|and her|when she went|it then|just then|as well as|the door|waiting for|is the one who|the one who|very one who)\.?$', '.', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+(?:who|to|with|from|at)\.?$', '.', text, flags=re.IGNORECASE)
        text = re.sub(r',\s*$', '.', text)

        # 4. Map known ASR phonetic and transliteration distortions in English
        if lang == "english":
            text = re.sub(r'\bverbal sister\b', 'adoptive sister', text, flags=re.IGNORECASE)
            text = re.sub(r'\btalking sister\b', 'adoptive sister', text, flags=re.IGNORECASE)
            text = re.sub(r'\bmouth sister\b', 'adoptive sister', text, flags=re.IGNORECASE)
            text = re.sub(r'\bLucia Corner\b', 'the forensic coroner', text, flags=re.IGNORECASE)
            text = re.sub(r'\bdoctor Corner\b', 'the coroner', text, flags=re.IGNORECASE)
            text = re.sub(r'\bMale world\b', 'Male ward', text)
            text = re.sub(r'\bmale world\b', 'male ward', text)
            text = re.sub(r'\btlegram\b', 'telegram', text, flags=re.IGNORECASE)

        # 5. Punctuation collision / glitch removal
        text = re.sub(r'\?+\s*\.+', '?', text)              # '?.', '?..' -> '?'
        text = re.sub(r'!+\s*\.+', '!', text)               # '!.', '!..' -> '!'
        text = re.sub(r'\.+\s*\?+', '?', text)              # '.?' -> '?'
        text = re.sub(r'\.+\s*!+', '!', text)               # '.!' -> '!'
        text = re.sub(r'\?{2,}', '?', text)                 # '??' -> '?'
        text = re.sub(r'!{2,}', '!', text)                  # '!!' -> '!'
        text = re.sub(r'\.{2,}', '.', text)                 # '..', '...', '....' -> '.'
        text = re.sub(r'[,;:–—-]\s*([.!?])', r'\1', text)   # ',.', ';.', '-.' -> '.', '?', '!'
        text = re.sub(r'([.!?])\s*[,;:–—-]', r'\1', text)   # '.,', '?:' -> '.', '?'
        text = re.sub(r'[,;]{2,}', ',', text)               # ',,', ';;' -> ','
        text = re.sub(r'[,;:–—-]\s*$', '.', text)           # Trailing comma, semicolon, dash -> '.'
        # 6. Smart Duplicate Word Deduplication (Whitelist-Aware)
        # Prevents glossary collisions ("Apartment Apartment 604" -> "Apartment 604") 
        # while strictly preserving legitimate English grammar ("that that", "had had", "very very", "do do", "Jong-in in").
        legitimate_duplicates = {'that', 'had', 'very', 'do'}
        def _collapse_dup(m):
            w = m.group(1)
            if w.lower() in legitimate_duplicates:
                return m.group(0)
            return w

        # Match consecutive identical words, ignoring hyphens so hyphenated names ("Jong-in in") are preserved
        text = re.sub(r'(?<!-)\b([A-Za-z]{2,})\s+\1\b(?!-)', _collapse_dup, text, flags=re.IGNORECASE)

        # 7. Ensure proper capitalization
        text = text.strip()
        if text and text[0].islower():
            text = text[0].upper() + text[1:]

        # 8. Ensure terminal punctuation without corrupting '?' or '!'
        valid_terminals = ('.', '!', '?', '"', "'", '।', '॥')
        if text and not text.endswith(valid_terminals):
            text += '.'

        # 9. Post-pass safety cleanup for any mixed marks (guarantees zero '?.')
        text = re.sub(r'\?\s*\.+', '?', text)               # Guaranteed cleanup of '?.', '?..' -> '?'
        text = re.sub(r'!\s*\.+', '!', text)                # Guaranteed cleanup of '!.', '!..' -> '!'
        text = re.sub(r'[,;]\s*\.', '.', text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s+\.', '.', text)

        return text.strip()

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
6. NO DUPLICATE REPETITIONS OR ENTITY DRIFT:
   - If two adjacent segments repeat the same statement, idiom, or semantic thought, eliminate the redundant repetition and ensure the actual new narrative action is translated.
   - Maintain uniform entity naming and noun forms across adjacent segments (do not alternate between singular and plural or switch synonyms without narrative reason).
7. DURATION PACING & WORD-COUNT BUDGET:
   - Check if any segment is overly verbose and far exceeds its duration budget.
   - If a sentence is bloated with filler or excessive description, tighten it into a punchy, complete sentence so voiceover finishes synchronously with the video scene cut.
8. UNIVERSAL 3RD-PERSON POV: Maintain strict third-person narration. Disallow unquoted first-person pronoun slips ("I", "my") during character exposition.
9. CLIMAX PRESERVATION MANDATE: Ensure major plot twists, true character identities, and forensic deductions are never omitted or watered down.
10. ASR & IDIOM DISAMBIGUATION: Ensure forensic/institutional terms are correct (e.g. 'coroner' instead of 'corner', 'ward' instead of 'world', 'adoptive sister' instead of 'verbal sister').
11. CRITICAL: You MUST return a JSON object with a single key 'translations' containing EXACTLY the same 'id's as provided.
12. Do not merge segments. Do not delete IDs. Return ALL provided IDs.
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

    def decode_script_to_stick_figure_cartoon(self, script_text: str, target_language: str = "hindi", output_path: str = None) -> list:
        """
        Decodes a raw story script into rapid, high-retention narrative scene segments
        with child-like MS Paint stick-figure image prompts for Cloudflare FLUX.1.
        """
        lang = target_language.lower()
        print(f"\n  [Cartoon Director] 🎨 Decoding story script into stick-figure MS Paint scenes ({lang.capitalize()})...")

        system_prompt = f"""You are an elite YouTube webcomic director and animator specializing in viral, high-retention stick-figure storytelling (inspired by Basically Primitive, Sam O'Nella Academy, and Casually Explained).

Your mission is to convert the user's story script into sequential, rapid-paced animation scene segments.

CRITICAL VISUAL STYLE, PALETTE & RETENTION RULES:

1. FREQUENT VISUAL CUTS (CHANGE PER SENTENCE OR ACTION BEAT):
   - Audience retention drops if an image stays on screen for too long.
   - CUT FREQUENTLY: Visuals MUST change on every sentence or distinct character action beat (approx 2.0 to 4.0 seconds per visual).
   - NEVER combine multiple sentences into a single image.
   - If a sentence contains two consecutive actions or an emotional shift (e.g., 'The professor explained his theory, and the student looked utterly confused'), split it into two distinct visual cuts:
     * Cut A: The professor passionately explaining.
     * Cut B: The student staring with spiral dizzy eyes.

2. COLOR PALETTE (STRICTLY MUTED & SOFT - NO BRIGHT/NEON COLOURS):
   - NEVER use bright, saturated, or neon colors. The palette MUST be muted, matte, and understated (like Basically Primitive):
     * Sky: Pale desaturated powder blue.
     * Grass / Foliage: Soft sage green, pale olive, or muted mint green.
     * Buildings / Dirt: Muted warm beige, sandy limestone, or soft earth tan.
     * Sun: Pale pastel yellow.
     * Backgrounds use solid, flat block colors with zero gradients and zero shading.

3. SCRIPT-DRIVEN CHARACTER IDENTITY & ULTRA-MINIMALIST STICK ANATOMY:
   - ALL characters are literal 2D black stick figures with oversized round flat white paper heads (NO flesh tones) and thin black stick limbs:
     * Protagonist / Narrator (Iconic Basically Primitive style): Oversized perfectly circular white head with bold black outline, bright orange spiky hair on top, two tiny black dot eyes, simple open/line mouth, and a pure minimalist black stick figure body (single thin black line torso, straight black stick arms, straight black stick legs). Absolutely ZERO clothing, ZERO hoodie, ZERO shirt, ZERO pants, completely flat 2D stick linework!
     * Professor / Scholar: Circular white head with sparse gray side hair and tiny round wireframe glasses, thin black stick body holding a simple flat book or manila folder.
     * Doctor / Scientist: Circular white head with glasses, simple flat white lab coat shape over thin black stick limbs.
     * Office Worker: Circular white head, thin black stick body with a simple small black necktie.
   - CRITICAL RULE: NEVER mention "hoodie", "jacket", "jeans", "shoes", or detailed clothing for the narrator/characters, as that causes image models to draw realistic 3D figures instead of pure stick figures! Keep them as pure stick figures with single-line limbs.

4. DISTINCT IDENTITIES DURING CONVERSATIONS & INTERACTIONS:
   - When two or more characters appear in the same scene or dialogue, NEVER make them identical generic clones!
   - Give each character a distinct identity matching the script:
     * Distinct hair or headwear (e.g., one has glasses and gray hair, the other has messy black hair or a cap).
     * Distinct clothing item or prop (e.g., one in a jacket holding a folder, the other in a t-shirt with a backpack).
     * Contrasting expressions and poses (e.g., one speaking actively with stick arm gesturing, the other listening with arms crossed or an eyebrow raised).

5. ANIMAL & CREATURE VISUAL CONSISTENCY (STRICTLY PURE WHITE STICK-COMIC STYLE - NO REALISTIC OR SHADED ANIMALS):
   - All animals, pets, and creatures (elephants, dogs, monkeys, cats, birds, etc.) MUST be drawn in the EXACT same simplistic stick-comic aesthetic as the human stick figures:
     * Body Fill: Pure flat solid WHITE fill (like paper). NEVER gray, brown, textured, or realistically colored.
     * Outlines: Bold black marker ink contour outlines.
     * Limbs & Tails: Thin black stick legs, thin black stick arms, and thin curved stick tails.
     * Faces: Minimalist cartoon dot eyes, simple black marker mouth/snout, zero 3D shading, zero fur/skin textures, and zero muscle contours.
     * Example Elephant: "a minimalist stick-figure elephant with a pure solid flat white body, thin black stick legs, a simple curved white trunk with black outlines, and simple dot eyes (zero gray shading, zero 3D textures, flat white fill)".
     * Example Dog: "a minimalist stick-figure dog with a pure solid flat white body, thin black stick legs, floppy ears, and black dot eyes (pure white fill, zero shading)".
     * Example Monkey: "a minimalist stick-figure monkey with a pure solid flat white body, thin black stick limbs and long stick tail, and cute dot eyes (pure white fill, zero shading)".
     * NEVER draw standard clip-art, Disney-style, or 3D shaded animals. They must look like a hand-drawn MS Paint webcomic stick creature!

6. VERBATIM SCRIPT PRESERVATION (THE SCRIPT IS THE ABSOLUTE SOURCE OF TRUTH):
   - CRITICAL: DO NOT alter, rewrite, paraphrase, summarize, embellish, or invent a single word of the user's spoken script!
   - Every sentence from the input text MUST be preserved VERBATIM in the 'text' field.
   - DO NOT add channel intros (e.g. "Welcome back to the channel", "Hey guys"), commentary, or fake dialogue.
   - Simply take the exact, verbatim sentences from the input text, segment them sentence-by-sentence (or clause-by-clause), and write the matching 'image_prompt' for each one.
   - If '{lang}' == 'english': the 'text' field MUST MATCH THE INPUT SCRIPT SENTENCES 100% WORD-FOR-WORD.
   - If '{lang}' == 'hindi': provide a faithful direct spoken Hindi translation of that exact sentence without altering its meaning.

7. MANDATORY PROMPT TEMPLATE FOR EVERY SEGMENT:
   Every single segment MUST include an 'image_prompt' following this EXACT template:
   "A low-fidelity MS Paint digital drawing in a deadpan webcomic style. Extreme wide long shot, centered 16:9 composition with generous empty headroom above and wide ground below. There are [EXACT NUMBER OF SUBJECTS, e.g. 'only one subject: an old wise stick figure with an oversized circular white head, sparse gray hair on the sides, small round wireframe glasses, tiny dot eyes, and thin black stick limbs']. The background depicts [SCRIPT-MATCHING SCENERY, e.g. 'solid powder blue sky and flat sage green grass with scribbled bushes', 'flat earth-tan mountains under a muted blue sky', 'a muted beige room wall'] drawn with flat, muted MS Paint bucket-fill colors. Deliberately messy, mouse-drawn linework. Absolutely zero shading, zero gradients, zero 3D depth, and zero realistic textures. Zero extra people or realistic human faces."

   CRITICAL RULES FOR THE BRACKETS:
   - SCRIPT-MATCHING BACKGROUNDS & ENVIRONMENTAL DETAIL:
     * NEVER depict a plain empty wall or blank void. The background must establish the story's actual physical location!
     * Include 2 to 3 iconic environmental details drawn in flat MS Paint bucket-fill colors:
       - Library / Study: Tall scribbled wooden bookshelves with muted book spines, a wooden desk with open books/papers, and a flat sage green or slate gray floor.
       - Desert / Outdoors: Rolling sand dunes under a powder blue sky, ancient stone pyramids or ruins in the background, flat sandy horizon.
       - Science Lab: Blackboard with scribbled formulas, lab workbench with flat-colored beakers/flasks.
       - House / Bedroom: Simple wooden bed, window showing outdoors, wooden floorboards.
     * All scenery drawn with flat, muted MS Paint bucket-fill colors (powder blue, sage green, sandy beige, soft slate gray, muted rust). NO gradients, NO 3D shading.

   - NATURAL POSES & FURNITURE INTERACTIONS (NO STANDING ON TABLES):
     * If a character is sitting: Describe them as "sitting on a simple chair behind a wooden desk with stick arms resting on the tabletop". NEVER use words like "perched on a rectangle" or "standing on a table".
     * If a character is standing: They stand on the flat floor or ground with feet touching the ground line.
     * If reading or holding something: Stick arms extend holding the specific prop (e.g. "holding an open book", "pointing toward the horizon").

   - VISUAL PROGRESSION & SHOT DIVERSITY (NO REPEATING STATIC SHOTS):
     * NEVER generate two identical static poses for consecutive sentences that describe the same character!
     * If consecutive beats focus on the same subject:
       - Beat 1: Wide establishing shot showing the character in their environment (e.g. wide shot of professor sitting at the library desk surrounded by tall bookshelves).
       - Beat 2: Medium shot or active gesture (e.g. medium shot of the professor leaning forward with wide curious dot eyes, holding up a glowing book, or pointing an arm).

   - ZERO PENCIL/SKETCH: NEVER use the word "pencil", "doodle", or "sketch" in any image_prompt, as the AI model will add unwanted graphite shading. Always use "MS Paint", "bucket-fill", and "mouse-drawn" instead.

   - SCRIPT-DRIVEN FOCAL PRIORITY (ANIMALS & PROPS FIRST):
     * When the narration explicitly talks about specific animals, creatures, or objects (e.g. "pigeons and squirrels", "sleeping sea lion", "pet dog", "glowing red book", "pyramid"):
       Make those specific mentioned creatures/objects the PRIMARY focal subjects in the foreground of the prompt!
       Example: "The main subjects are a cartoon stick pigeon and a cartoon stick squirrel on a flat gray sidewalk eating breadcrumbs tossed by a stick figure."
       NEVER bury key story animals behind giant buildings or generic full-body standing poses, or the AI will omit them!

   - SCRIPT-DRIVEN CHARACTER AGE & IDENTITY:
     * Old Person / Elder / Professor: Circular white head, sparse gray hair tufts on the sides, small round wireframe glasses, tiny dot eyes, simple line mouth, thin black stick limbs.
     * Young Narrator: Circular white head, spiky orange or black hair, tiny dot eyes, simple line mouth, thin black stick limbs.
     * Scientist / Doctor: Circular white head with glasses, simple flat white lab coat shape over thin stick limbs.
     * Historical King / Emperor: Circular white head, simple flat cartoon crown on stick head.
     * ALL characters MUST strictly remain 2D stick figures with circular flat white heads (NO flesh tones, NO realistic faces).

   - STRICT COUNT: Always state the EXACT number of subjects (e.g. 'only one stick figure', 'only two subjects: one stick figure and one dog'). NEVER use plural words like 'all characters' or 'all animals'.
   - ZERO EXTRA SUBJECTS: Always end the prompt with: 'Zero extra people, zero extra animals, zero realistic human faces.'
   - NEVER place words, letters, text overlays, or speech bubbles inside the image itself.

Output strictly a JSON object with a single key 'segments':
{{
  "segments": [
    {{
      "id": 1,
      "text": "spoken narration line in target language",
      "image_prompt": "A low-fidelity MS Paint digital drawing in a deadpan webcomic style. Extreme wide long shot, centered 16:9 composition with generous empty headroom above and wide ground below. There are [exact subjects with stick-figure details]. The background depicts [contextual scenery in flat muted MS Paint bucket-fill colors]. Deliberately messy, mouse-drawn linework. Absolutely zero shading, zero gradients, zero 3D depth, and zero realistic textures. Zero extra people or realistic human faces."
    }}
  ]
}}"""

        groq_keys = []
        if self.api_key: groq_keys.append(self.api_key)
        for k in [os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_API_KEY_TWO"), os.environ.get("GROQ_API_KEY_THREE"), os.environ.get("GROQ_API_KEY_FOUR")]:
            if k and k not in groq_keys:
                groq_keys.append(k)

        # 1. Clean and parse sections (filtering headers, divider lines, and estimated length metadata)
        def is_metadata_line(raw: str) -> bool:
            c = raw.strip()
            if not c:
                return True
            if c.startswith("#"):
                return True
            if re.match(r"^[_\-*=]{3,}$", c):
                return True
            c_low = c.lower()
            if any(k in c_low for k in ["estimated length", "estimated duration", "word count", "target length"]):
                return True
            return False

        lines = script_text.split("\n")
        sections = []
        cur_title = None
        cur_lines = []

        for l in lines:
            s = l.strip()
            if is_metadata_line(s):
                continue
            m = re.match(r"^\*?\*?\[(.*?)\]\*?\*?", s)
            if m:
                if cur_lines and cur_title:
                    sections.append((cur_title, " ".join(cur_lines)))
                    cur_lines = []
                cur_title = m.group(1).strip()
                continue
            if cur_title is None:
                cur_title = "Scene"
            cur_lines.append(s)

        if cur_lines and cur_title:
            sections.append((cur_title, " ".join(cur_lines)))

        if not sections:
            sections = [("Scene", script_text)]

        decoded_segments = []
        total_raw_segs = []

        # Intelligent multi-model & multi-key rotation to eliminate 429 rate limit errors
        models_to_try = [
            ("openai/gpt-oss-120b", 1500),
            ("openai/gpt-oss-20b", 1200),
            ("qwen/qwen3.8-27b", 600)  # Capped at 600 tokens to stay well below 1000 OTPM ceiling
        ]

        # Focused system instructions for rapid, reliable JSON output across all scene batches
        batch_system_prompt = """You are a storyboard director for a 2D stick-figure YouTube animation channel (Basically Primitive / Casually Explained style).
Your task is to generate a visual scene description for each provided narration beat.
Style rules:
- Characters: 2D minimalist stick figures with circular flat white heads, dot eyes, and thin black stick limbs (narrator has spiky orange hair; old people have sparse gray hair and glasses).
- Animals & Props: clearly feature any mentioned animal or object (e.g. stick pigeon, stick squirrel, stick sea lion, stick dog, stick deer, campfire, island, trees) interacting directly with the characters.
- Environment: flat muted MS Paint bucket-fill colors (powder blue sky, sage green grass, earth-tan sand, beige rooms).
- Composition: wide 16:9 shot, eye-level framing, showing all characters and animals clearly in frame.
- Output: valid JSON with key "scenes": [{"id": 1, "visual": "short 15-25 word action description focusing directly on characters and animals"}]"""

        IDEA_SHIFT_PREFIXES = (
            "now imagine", "now think", "but ", "so why ", "then there are", 
            "suddenly", "meanwhile", "here's the", "and here's where", "still, ", 
            "take ", "for example", "instead", "in contrast", "so some ", "so nature ", "which means "
        )

        def is_idea_shift(sentence: str) -> bool:
            s_low = sentence.lower().strip()
            return any(s_low.startswith(p) for p in IDEA_SHIFT_PREFIXES)

        def est_dur(text: str) -> float:
            words = len(text.split())
            commas = text.count(",") + text.count("—") + text.count(";")
            sentence_ends = text.count(".") + text.count("?") + text.count("!")
            # Natural speech model accounting for punctuation pauses: 155-160 WPM + punctuation breathing pauses
            return max(1.5, round((words / 2.6) + (0.35 * commas) + (0.60 * sentence_ends), 2))

        def split_long_sentence(sent: str, is_hook: bool = False) -> list:
            max_words = 7 if is_hook else 17
            if len(sent.split()) <= max_words:
                return [sent]
            parts = re.split(r'(?<=,)\s+(?=where |and |but |so |which |because )|(?<=—)\s*|(?<=;)\s*', sent)
            clean = [p.strip() for p in parts if p.strip()]
            if len(clean) > 1:
                return clean
            return [sent]

        def get_section_pacing(title: str):
            t = title.lower()
            if any(k in t for k in ["hook", "intro", "teaser", "opening"]):
                # Hook (0-30s): 2-3s per visual (rapid cuts signals 'this is worth staying for')
                return {"min_dur": 1.8, "max_dur": 3.2, "target": 2.5, "type": "Hook"}
            elif any(k in t for k in ["emotional", "twist", "dramatic", "climax"]):
                # Emotional or twist moments: 6-8s (slow zoom lets the point land)
                return {"min_dur": 5.0, "max_dur": 8.0, "target": 6.8, "type": "Twist"}
            elif any(k in t for k in ["closing", "outro", "conclusion"]):
                # Closing: 5-7s (calm, satisfying ending)
                return {"min_dur": 4.5, "max_dur": 7.5, "target": 5.8, "type": "Closing"}
            else:
                # Setup and body: 4-6s (enough time to register while explaining idea)
                return {"min_dur": 3.8, "max_dur": 6.8, "target": 5.0, "type": "Body"}

        def decode_single_section(s_title: str, s_text: str) -> list:
            from groq import Groq

            is_hook = any(k in s_title.lower() for k in ["hook", "intro", "teaser", "opening"])
            pacing = get_section_pacing(s_title)

            # 1. Deterministic sentence extraction & long sentence splitting
            raw_sentences = [st.strip() for st in re.split(r'(?<=[.!?])\s+', s_text) if st.strip()]
            if not raw_sentences:
                return []

            expanded_sentences = []
            for rs in raw_sentences:
                expanded_sentences.extend(split_long_sentence(rs, is_hook=is_hook))

            # 2. Hybrid Idea Chunking (Floor 2s, Ceiling 8s, Target based on section type)
            sec_chunks = []
            cur_chunk = []
            cur_dur = 0.0

            for sent in expanded_sentences:
                sd = est_dur(sent)
                if not cur_chunk:
                    cur_chunk.append(sent)
                    cur_dur = sd
                    continue

                dur_with_next = cur_dur + sd
                has_shift = is_idea_shift(sent)

                if is_hook:
                    # Hook: 2-3s rapid cuts
                    if cur_dur >= pacing["min_dur"] or has_shift or dur_with_next > pacing["max_dur"]:
                        sec_chunks.append((cur_chunk, cur_dur))
                        cur_chunk = [sent]
                        cur_dur = sd
                    else:
                        cur_chunk.append(sent)
                        cur_dur = dur_with_next
                else:
                    # Body (4-6s), Twist (6-8s), Closing (5-7s)
                    if (cur_dur >= pacing["min_dur"] and (has_shift or dur_with_next > pacing["max_dur"])) or (cur_dur >= pacing["target"]):
                        sec_chunks.append((cur_chunk, cur_dur))
                        cur_chunk = [sent]
                        cur_dur = sd
                    else:
                        cur_chunk.append(sent)
                        cur_dur = dur_with_next

            if cur_chunk:
                sec_chunks.append((cur_chunk, cur_dur))

            # 3. Process scenes in mini-batches of up to 4 scenes for rapid reliable visual generation
            BATCH_SIZE = 4
            section_segs = []

            for b_idx in range(0, len(sec_chunks), BATCH_SIZE):
                batch_chunks = sec_chunks[b_idx:b_idx + BATCH_SIZE]
                batch_texts = [" ".join(c[0]) for c in batch_chunks]
                batch_input = "\n".join([f"{i+1}. {txt}" for i, txt in enumerate(batch_texts)])
                user_msg = (
                    f"Section Context: [{s_title}].\n"
                    f"Generate a visual description for each of these {len(batch_texts)} narration beats:\n\n"
                    f"{batch_input}\n\n"
                    f"Respond strictly with a JSON object: {{\"scenes\": [{{\"id\": 1, \"visual\": \"...\"}}]}}"
                )

                batch_prompts = []
                for model_name, max_toks in models_to_try:
                    for k_idx, key in enumerate(groq_keys if groq_keys else [None]):
                        try:
                            client = Groq(api_key=key)
                            completion = client.chat.completions.create(
                                model=model_name,
                                messages=[
                                    {"role": "system", "content": batch_system_prompt},
                                    {"role": "user", "content": user_msg}
                                ],
                                response_format={"type": "json_object"},
                                temperature=0.2,
                                max_tokens=min(max_toks, 800)
                            )
                            data = json.loads(completion.choices[0].message.content)
                            scs = data.get("scenes", []) or data.get("segments", [])
                            if scs:
                                batch_prompts = [sc.get("visual", "") or sc.get("image_prompt", "") for sc in scs]
                                while len(batch_prompts) < len(batch_texts):
                                    batch_prompts.append("")
                                break
                        except Exception as e:
                            err_str = str(e)
                            if "429" in err_str or "rate_limit" in err_str.lower():
                                continue
                            break
                    if batch_prompts:
                        break

                for i, (c_sents, c_d) in enumerate(batch_chunks):
                    chunk_text = " ".join(c_sents)
                    vis = batch_prompts[i] if (i < len(batch_prompts) and batch_prompts[i] and len(batch_prompts[i].strip()) > 10) else f"Stick-figure scene illustrating: {chunk_text}"
                    full_prompt = (
                        f"A low-fidelity MS Paint digital drawing in a deadpan webcomic style. Wide 16:9 framing. "
                        f"{vis}. Flat muted MS Paint bucket-fill colors, deliberately messy mouse-drawn linework. "
                        f"Zero shading, zero 3D depth, zero gradients. Zero extra people, zero extra animals."
                    )
                    # Enforce hard floor (2.0s) and ceiling (8.0s)
                    final_dur = max(2.0, min(8.0, round(c_d, 2)))
                    section_segs.append({
                        "text": chunk_text,
                        "image_prompt": full_prompt,
                        "dur": final_dur
                    })

            return section_segs

        all_section_segs = []
        for s_title, s_text in sections:
            if not s_text.strip():
                continue
            segs = decode_single_section(s_title, s_text)
            all_section_segs.extend(segs)

        total_raw_segs = all_section_segs

        # Format and assign timings
        cur_time = 0.0
        for idx, s in enumerate(total_raw_segs, 1):
            seg_text = s.get("text", "").strip()
            # Clean any stray markdown tags from narration text
            seg_text = re.sub(r"^\*?\*?\[.*?\]\*?\*?", "", seg_text).strip()
            seg_text = re.sub(r"^[#*_-]+", "", seg_text).strip()
            if not seg_text:
                continue

            # Use hybrid-pacing duration assigned during section chunking (clamped between 2.0s and 8.0s)
            dur = s.get("dur", max(2.0, min(8.0, round(len(seg_text.split()) / 2.3, 2))))
            start_t = round(cur_time, 2)
            end_t = round(cur_time + dur, 2)
            cur_time = end_t
            
            prompt = s.get("image_prompt", "")
            if not prompt or len(prompt.strip()) < 20:
                prompt = f"A 2D digital illustration in a child-like, low-fidelity MS Paint style, 16:9 widescreen YouTube longform framing. All characters and animals are basic minimalist stick-comic figures with pure solid flat white bodies, thin black stick limbs, bold black marker outlines, and simple expressive facial features. The scene shows a minimalist stick-figure character with clean simple gestures. The background uses solid, flat, muted desaturated block colors with absolutely no shading and zero text overlays. Crucially, the environmental details are drawn with deliberately messy, scribbled linework, resembling a poorly drawn webcomic or a kid's drawing."

            seg_dict = {
                "id": len(decoded_segments) + 1,
                "start": start_t,
                "end": end_t,
                "text": seg_text,
                lang: seg_text,
                "image_prompt": prompt,
                "use_ai_image": True
            }
            if lang != "english":
                seg_dict["original_text"] = seg_text
            decoded_segments.append(seg_dict)

        print(f"  [Cartoon Director] ✅ Decoded {len(decoded_segments)} stick-figure scene beats across {len(sections)} sections!")

        # Fallback if LLM failed
        if not decoded_segments:
            print("  [Cartoon Director] ⚠️ Fallback: splitting script by sentences...")
            lines = [l.strip() for l in re.split(r'[.!?।\n]+', script_text) if l.strip()]
            cur_time = 0.0
            for idx, line in enumerate(lines, 1):
                dur = max(3.0, round(len(line.split()) / 2.2, 2))
                start_t = round(cur_time, 2)
                end_t = round(cur_time + dur, 2)
                cur_time = end_t
                decoded_segments.append({
                    "id": idx,
                    "start": start_t,
                    "end": end_t,
                    "text": line,
                    lang: line,
                    "image_prompt": f"A 2D digital illustration in a child-like, low-fidelity MS Paint style, 16:9 widescreen. All characters are basic minimalist stick-comic figures with pure solid flat white bodies, thin black stick limbs, bold black marker outlines, and simple expressive facial features. The scene shows a minimalist stick-figure character with clean simple gestures. The background uses solid, flat block colors with absolutely no shading and zero text overlays. Crucially, the environmental details like the green tree leaves and bushes are drawn with deliberately messy, scribbled linework, resembling a poorly drawn webcomic or a kid's drawing.",
                    "use_ai_image": True
                })

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(decoded_segments, f, indent=4, ensure_ascii=False)
            print(f"  [Cartoon Director] Saved {len(decoded_segments)} scene segments to: {output_path}")

        return decoded_segments

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
                        if val and val.lower() not in ["translation/rewrite failed", "error"] and "story continues" not in val.lower():
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
            
            # Build context (including actual translated text of the immediately preceding segment)
            prev_context = segments[i-1]["text"] if i > 0 else ""
            next_idx = i + self.batch_size
            next_context = segments[next_idx]["text"] if next_idx < len(segments) else ""
            
            prev_translated_info = ""
            if i > 0:
                prev_id = int(segments[i-1]["id"])
                prev_entry = translated_map.get(prev_id)
                if prev_entry:
                    prev_trans_text = prev_entry.get(lang_key, "").strip()
                    if prev_trans_text:
                        prev_translated_info = (
                            f"Immediately preceding segment [ID {prev_id}] was already translated as:\n"
                            f"\"{prev_trans_text}\"\n"
                            f"(CRITICAL: Do NOT repeat, rephrase, or duplicate what was already narrated in segment {prev_id}. "
                            f"Advance the narrative with new action.)\n\n"
                        )
            
            context = f"{prev_translated_info}Source Text Surrounding Context:\n{prev_context} [...] {next_context}"
            
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

                # 3. Detect Adjacent Stutter / Duplicate Thoughts (within batch and across batch boundary)
                prev_eval_text = ""
                if i > 0:
                    prev_id = int(segments[i-1]["id"])
                    prev_entry = translated_map.get(prev_id)
                    if prev_entry:
                        prev_eval_text = prev_entry.get(lang_key, "").strip()

                for r_idx, r in enumerate(valid_results):
                    sid = int(r.get("id", 0))
                    val_text = r.get("translated_text", r.get(lang_key, r.get("text", ""))).strip()
                    compare_text = prev_eval_text if r_idx == 0 else valid_results[r_idx-1].get("translated_text", valid_results[r_idx-1].get(lang_key, "")).strip()
                    if val_text and compare_text:
                        w1 = set(re.findall(r'\b[a-z]{3,}\b', compare_text.lower()))
                        w2 = set(re.findall(r'\b[a-z]{3,}\b', val_text.lower()))
                        if len(w1) >= 4 and len(w2) >= 4:
                            overlap = len(w1 & w2) / max(1, min(len(w1), len(w2)))
                            if overlap >= 0.58:
                                qa_defects.setdefault(sid, []).append(
                                    f"DUPLICATE STUTTER: Segment repeats the preceding sentence's idea/words ({int(overlap*100)}% overlap with '{compare_text[:40]}...'). Rewrite to eliminate repetition and translate only the new plot action."
                                )

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
                if not final_text or (lang_key == "english" and re.search(r'[\u0900-\u097F]', final_text)):
                    print(f"  [Safety Recovery] Segment {seg_id} requires clean {lang_key} translation. Running dedicated recovery...")
                    for retry_att in range(self.max_retries + 1):
                        try:
                            recov = self._execute_translation([seg], system_prompt, context="", target_language=lang_key)
                            cand = recov[0].get(lang_key, recov[0].get("translated_text", "")) if recov else ""
                            if cand and cand.strip():
                                # Disallow any Devanagari in English output
                                if lang_key == "english" and re.search(r'[\u0900-\u097F]', cand):
                                    continue
                                final_text = cand.strip()
                                break
                        except Exception as re_err:
                            print(f"  [Safety Recovery] Attempt {retry_att+1} failed for segment {seg_id}: {re_err}")
                        time.sleep(2 * (retry_att + 1))
                    
                    if not final_text or (lang_key == "english" and re.search(r'[\u0900-\u097F]', final_text)):
                        # Production Rule: Never inject gibberish, placeholders, or raw untranslated text into final script.
                        raise RuntimeError(
                            f"[PROD PIPELINE HALT] Segment {seg_id} failed translation after all retries. "
                            f"Halting pipeline to guarantee zero gibberish or corruptions in the final video. "
                            f"Progress up to segment {seg_id-1} is safely saved in the checkpoint."
                        )

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
            r'\b(subscribe|subscribing|channel|bell icon|notification|leave a like|hit like|comment below|thanks for watching|see you in the next|share this video|share with your friends|stay tuned|keep watching|watch the rest|watch the series|video is quite long|video is too long|that is all for today|thank you for watching this far|until our next journey|reels? ke zamane)\b'
            r'|[\u0900-\u097F]*(?:सब्सक्राइब|लाइक|घंटी|बेल|शेयर|कमेंट|चैनल|ॐ|ओम|लंबी हो गई|इतना ही|टाटा बाय|अगली वीडियो|अगले वीडियो)[\u0900-\u097F]*'
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
                text = re.sub(r'[,;\s]+(?:and|but|or|so|to|then|which|that|who|whom|whose|because|when|while|with|and her|when she went|it then|just then|as well as|the door|waiting for|is the one who|the one who|very one who)\.?$', '.', text, flags=re.IGNORECASE)
                text = re.sub(r'\s+(?:who|to|with|from|at)\.?$', '.', text, flags=re.IGNORECASE)
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
            text = self.sanitize_segment_text(text, target_language=lang)
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
                        segments[i+1][lang] = self.sanitize_segment_text(trimmed_next, target_language=lang)
                        continue

            # 4b. Fuzzy overlap ratio across adjacent segments to catch subtitle split duplication
            w1 = set(re.findall(r'\b[a-z]{3,}\b', curr_text.lower()))
            w2 = set(re.findall(r'\b[a-z]{3,}\b', next_text.lower()))
            overlap = len(w1 & w2) / max(1, min(len(w1), len(w2)))
            if overlap >= 0.58 and len(w1) >= 4 and len(w2) >= 4:
                if next_sentences and len(next_sentences) > 1:
                    segments[i+1][lang] = ". ".join(next_sentences[1:]) + "."
                elif curr_sentences and len(curr_sentences) > 1:
                    segments[i][lang] = ". ".join(curr_sentences[:-1]) + "."
                else:
                    print(f"  [Anti-Stutter] ⚠️ Detected duplicate thought between Segments {segments[i].get('id')} and {segments[i+1].get('id')} ({int(overlap*100)}% overlap). Re-synthesizing segment {segments[i+1].get('id')}...")
                    try:
                        fix_prompt = (
                            f"The following two consecutive segments duplicate the same thought/action:\n"
                            f"Segment {segments[i].get('id')}: \"{curr_text}\"\n"
                            f"Segment {segments[i+1].get('id')} (DUPLICATE): \"{next_text}\"\n"
                            f"Source text for Segment {segments[i+1].get('id')}: \"{segments[i+1].get('original_text', segments[i+1].get('text', ''))}\"\n\n"
                            f"Task: Rewrite Segment {segments[i+1].get('id')} into a single, punchy, complete sentence that translates the NEW action from its source text without repeating what Segment {segments[i].get('id')} already said."
                        )
                        recov = self._execute_translation([segments[i+1]], fix_prompt, context="", target_language=lang)
                        if recov:
                            new_val = recov[0].get("translated_text", recov[0].get(lang, ""))
                            if new_val and new_val.strip() != next_text:
                                segments[i+1][lang] = self.sanitize_segment_text(new_val, target_language=lang)
                    except Exception as e:
                        print(f"  [Anti-Stutter] Warning: Recovery failed: {e}")

        return segments

