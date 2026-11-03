import os
import json
import re
from groq import Groq

class ScriptQualityEvaluator:
    """
    Pre-Flight Script Quality Gate.
    Analyzes raw YouTube auto-generated captions before any translation or voiceover
    synthesis occurs. Evaluates ASR phonetic health, acoustic noise interference,
    hallucinated entities, and narrative coherence.
    Enforces a strict >= 90% quality score threshold to prevent wasting compute on
    garbled/unusable audio sources.
    """
    def __init__(self, api_key: str = None, min_score: int = 90):
        self.min_score = min_score
        
        # Load API keys pool for rotation
        keys = []
        if api_key:
            keys.append(api_key)
        for k in [os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_API_KEY_TWO"), os.environ.get("GROQ_API_KEY_THREE"), os.environ.get("GROQ_API_KEY_FOUR")]:
            if k and k not in keys:
                keys.append(k)
        self.api_keys = keys

    def evaluate(self, transcript_path: str, channel_type: str = "movie_recap") -> dict:
        """
        Evaluates the transcript. Returns a dictionary with:
        {
            "score": int,
            "verdict": "ACCEPT" | "REJECT",
            "reason": str,
            "detected_flaws": list[str],
            "recommendation": str
        }
        """
        if not os.path.exists(transcript_path):
            return {
                "score": 0,
                "verdict": "REJECT",
                "reason": f"Transcript file not found: {transcript_path}",
                "detected_flaws": ["Missing transcript file"],
                "recommendation": "Check video source or download step."
            }

        with open(transcript_path, "r", encoding="utf-8") as f:
            segments = json.load(f)

        if not segments or len(segments) < 10:
            return {
                "score": 0,
                "verdict": "REJECT",
                "reason": f"Transcript is empty or has too few segments ({len(segments)} segments).",
                "detected_flaws": ["Insufficient subtitle data"],
                "recommendation": "Select a video with full closed captions."
            }

        # Inspect opening 50 segments (where setup, character names, and hook reside)
        sample_segs = segments[:50]
        sample_text = "\n".join([f"ID {s.get('id', idx+1)}: {s.get('text', '')}" for idx, s in enumerate(sample_segs)])

        # Auto-detect language family from character sets
        devanagari_count = len(re.findall(r'[\u0900-\u097F]', sample_text))
        total_letters = len(re.findall(r'\w', sample_text)) or 1
        devanagari_ratio = devanagari_count / total_letters

        if devanagari_ratio > 0.15:
            lang_label = "Hindi / Hinglish"
        elif re.search(r'[\uAC00-\uD7AF]', sample_text):
            lang_label = "Korean"
        elif re.search(r'[\u3040-\u30FF\u4E00-\u9FAF]', sample_text):
            lang_label = "Japanese"
        elif re.search(r'[\u0400-\u04FF]', sample_text):
            lang_label = "Russian"
        else:
            lang_label = "English (or Latin-based language)"

        prompt = f"""You are an elite, multi-lingual YouTube Voiceover Transcript Quality Inspector.
Your mission is to evaluate the raw auto-generated closed captions of a YouTube narration video (Source Language: {lang_label}) and determine whether the transcript is CLEAN, COHERENT, and PRODUCTION-READY for voiceover translation/rescripting, or if it is SEVERELY MUTILATED by background music, audio distortion, clipping, or ASR speech-to-text hallucinations.

EVALUATION CRITERIA (Apply generically to {lang_label}):
1. Acoustic Distortion & Phonetic Gibberish:
   - Are words corrupted into nonsensical phonetic mashups due to loud background music, sound effects, or fast speech?
   - In {lang_label}, does the text contain unnatural, meaningless word combinations that no human speaker would say?

2. Entity & Setting Consistency:
   - Are character names, locations, and key story elements coherent with the story's setting?
   - Did the ASR algorithm mishear foreign names as common everyday phonetic words or culturally mismatched entities?

3. Syntactic Completeness & Missing Actions:
   - Did background noise swallow verbs, subjects, or negations (e.g. turning 'told them not to do it' into an incomplete fragment)?
   - Are sentences sliced into disjointed fragments that fail to communicate clear actions?

4. Narrative Continuity:
   - Can an audience or translation model follow the cause-and-effect progression of the plot?
   - Are key story beats intact, or has acoustic distortion rendered the storyline incomprehensible?

SCORING RULES (0 to 100):
- 90 - 100: Clean, coherent, and production-ready. Natural flow, complete thoughts, accurate story progression. Minor phonetic typos that are easily resolvable from context are acceptable. -> VERDICT: "ACCEPT"
- Below 90: Incoherent fragments, heavy ASR corruption, dropped essential verbs/negations, nonsensical phrasing, or loss of narrative logic. -> VERDICT: "REJECT"

You MUST respond with a STRICT JSON object only:
{{
  "score": <integer 0-100>,
  "verdict": "ACCEPT" or "REJECT",
  "detected_language": "{lang_label}",
  "reason": "<concise explanation of why it passed or failed based on actual text quality>",
  "detected_flaws": ["<flaw 1>", "<flaw 2>"],
  "recommendation": "<actionable advice>"
}}"""

        for k_idx, key in enumerate(self.api_keys):
            try:
                client = Groq(api_key=key)
                response = client.chat.completions.create(
                    model="qwen/qwen3.8-27b",
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": f"Sample Transcript (Opening 50 Segments):\n{sample_text}"}
                    ],
                    response_format={"type": "json_object"}
                )

                content = response.choices[0].message.content
                result = json.loads(content)
                score = int(result.get("score", 0))
                
                # Enforce minimum threshold strictly
                if score < self.min_score:
                    result["verdict"] = "REJECT"
                else:
                    result["verdict"] = "ACCEPT"

                print(f"  [Quality Evaluator] 🔍 Transcript Score: {score}/100 | Verdict: {result['verdict']}")
                return result

            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate_limit" in err_str:
                    print(f"  [Quality Evaluator] Key #{k_idx+1} hit rate limit. Trying next key...")
                    continue
                print(f"  [Quality Evaluator] Error during evaluation on key #{k_idx+1}: {e}")

        # Fallback if all Groq keys failed
        return {
            "score": 85,
            "verdict": "REJECT",
            "reason": "Transcript quality evaluator could not complete due to API availability.",
            "detected_flaws": ["API evaluation unavailable"],
            "recommendation": "Retry or check API credentials."
        }
