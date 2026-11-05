import re
import json
from typing import Dict, List

class ScriptAuditor:
    """
    Independent, generic movie recap script quality auditor.
    Evaluates scripts across 5 weighted categories according to professional YouTube recap standards:
    1. Factual accuracy (30%)
    2. Story comprehension & clarity (25%)
    3. Simple language (20%)
    4. Suspense & engagement (15%)
    5. Narration flow (10%)
    """

    BANNED_JARGON_PATTERNS = [
        r'\borthodox\s+freudian\b',
        r'\bparanoid\s+delusion',
        r'\bforensic\s+inconsistenc',
        r'\bpredatory\s+suitor',
        r'\bcontemptuously\s+scoff',
        r'\bclinical\s+discharge\b',
        r'\blegal\s+incapacitat',
        r'\bdisciplinary\s+punishment\b',
        r'\belaborate\s+psychological\b',
        r'\bepistemological\b',
        r'\bexistential\b',
    ]

    BANNED_ADVERBS = [
        r'\bfearlessly\b',
        r'\bfiercely\b',
        r'\bbrilliantly\b',
        r'\bmaliciously\b',
        r'\barrogantly\b',
        r'\bcontemptuously\b',
        r'\bmercilessly\b',
        r'\bviciously\b'
    ]

    FORBIDDEN_META = [
        r'\bin\s+this\s+scene\b',
        r'\bcut\s+to\b',
        r'\bthe\s+scene\s+shifts\b',
        r'\bwe\s+see\b',
        r'\bwe\s+are\s+shown\b',
        r'\bthe\s+camera\s+pans\b',
        r'\bthe\s+camera\s+shows\b'
    ]

    # Canonical word-count rule — must match the generation prompt (10–16 words)
    MIN_WORDS = 10
    MAX_WORDS = 16

    @classmethod
    def _get_narration_text(cls, segment: dict) -> str:
        """
        Returns the canonical narration text from a segment, regardless of target language.
        Checks 'narration' first (new canonical field), then 'english', 'hindi', 'text'.
        This ensures the auditor works correctly for Hindi, English, and any future language.
        """
        return (
            segment.get("narration")
            or segment.get("english")
            or segment.get("hindi")
            or segment.get("text")
            or ""
        )

    @classmethod
    def audit_script(cls, script: List[dict], film_synopsis: str = "", provider=None) -> Dict:
        """
        Runs comprehensive, generic quality audit on script segments.
        Returns a detailed report with scores, failure diagnoses, and overall rating.

        IMPORTANT: This auditor checks language rules deterministically and uses an LLM to
        compare narration against the film synopsis. It cannot verify whether individual
        events are accurately placed in the timeline — that requires per-segment source
        dialogue evidence passed to apply_generic_polish().
        """
        if not script:
            return {"overall_score": 0.0, "passed": False, "reason": "Script is empty"}

        jargon_hits = []
        adverb_hits = []
        meta_hits = []
        length_violations = []  # < MIN_WORDS or > MAX_WORDS
        multi_sentence_hits = []
        trailing_conjunctions = []

        def count_sentences(text: str) -> int:
            # Mask common abbreviations so 'Dr.', 'Mr.', etc. do not falsely trigger sentence splits
            masked = re.sub(r'\b(Dr|Mr|Mrs|Ms|Prof|Sr|Jr)\.', r'\1<DOT>', text, flags=re.IGNORECASE)
            sents = [sent for sent in re.split(r'[.!?]+', masked) if sent.strip()]
            return len(sents)

        for s in script:
            text = cls._get_narration_text(s)
            words = text.split()
            wc = len(words)
            seg_id = s.get("id", 0)

            # Strictly enforce MIN_WORDS–MAX_WORDS
            if wc < cls.MIN_WORDS or wc > cls.MAX_WORDS:
                length_violations.append((seg_id, wc, text))

            # Check sentence count with abbreviation protection
            sent_count = count_sentences(text)
            if sent_count > 1:
                multi_sentence_hits.append((seg_id, sent_count, text))

            # Check trailing conjunctions — correct regex (no literal asterisk)
            if re.search(r'\b(and|or|so|because|to|who|which)\s*$', text, flags=re.IGNORECASE):
                trailing_conjunctions.append((seg_id, text))

            # Check jargon
            for jp in cls.BANNED_JARGON_PATTERNS:
                if re.search(jp, text, flags=re.IGNORECASE):
                    jargon_hits.append((seg_id, text))
                    break

            # Check dramatic adverbs
            for ap in cls.BANNED_ADVERBS:
                if re.search(ap, text, flags=re.IGNORECASE):
                    adverb_hits.append((seg_id, text))
                    break

            # Check meta words
            for mp in cls.FORBIDDEN_META:
                if re.search(mp, text, flags=re.IGNORECASE):
                    meta_hits.append((seg_id, text))
                    break

        # Calculate Simple Language Score (out of 10)
        lang_deductions = (
            (len(jargon_hits) * 0.4) +
            (len(adverb_hits) * 0.2) +
            (len(length_violations) * 0.1)
        )
        simple_lang_score = max(3.0, round(10.0 - lang_deductions, 2))

        # Calculate Narration Flow Score (out of 10)
        flow_deductions = (
            (len(multi_sentence_hits) * 0.5) +
            (len(trailing_conjunctions) * 0.5) +
            (len(meta_hits) * 0.5)
        )
        flow_score = max(3.0, round(10.0 - flow_deductions, 2))

        # LLM-based semantic scores default to FAILURE, not inflated defaults.
        # They are only updated after a successful, validated LLM response.
        # This prevents the auditor from certifying a script when the LLM call fails.
        factual_score = 0.0
        comprehension_score = 0.0
        suspense_score = 0.0
        audit_success = False
        audit_feedback = []
        surgical_fixes = []

        if provider and film_synopsis:
            # Build script sample with source dialogue context if available
            script_lines = []
            for s in script:
                narration = cls._get_narration_text(s)
                src = s.get("source_dialogue") or ""
                src_note = f" | source: {src[:80]}" if src else ""
                script_lines.append(
                    f"[{s.get('movie_timestamp','')}] ID {s.get('id')}: {narration}{src_note}"
                )
            script_sample = "\n".join(script_lines)

            eval_prompt = f"""You are a strict, independent senior film editor and YouTube recap auditor.
Evaluate this movie recap script against the verified Authoritative Film Synopsis and professional YouTube recap standards.
Where 'source' dialogue is provided beside a segment, use it as primary evidence for factual accuracy.

Authoritative Film Synopsis (COMPLETE):
{film_synopsis[:6000]}

Recap Script Segments (format: [timestamp] ID n: narration | source: dialogue evidence):
{script_sample}

Audit strictly against these 3 categories (rate each from 1.0 to 10.0):
1. FACTUAL ACCURACY & SOURCE VALIDATION (Score 1-10):
   - Are character names, roles, and relationships accurate (e.g. distinguishing twins, identifying doctors/investigators)?
   - SEPARATE FACTS, CLAIMS, AND INFERENCES: Does the script avoid presenting unverified subjective character claims as objective facts early on?
   - Are physical evidence, injuries, survival/death, and legal/council outcomes accurately reported as verified in the synopsis?
   - Does it faithfully deliver the true climax and twist resolution without inverting revelations?
   - For segments with source dialogue provided: does the narration accurately reflect what the dialogue establishes?

2. STORY COMPREHENSION & CHRONOLOGY (Score 1-10):
   - Are transitions logical and cause-and-effect clear?
   - Are non-linear timelines, flashbacks, or flash-forwards clearly signposted with conversational time markers?
   - Does it avoid confusing scene jumps, invented actions, or redundant adjacent repetitions?

3. SUSPENSE & ENGAGEMENT (Score 1-10):
   - Does it preserve the central mystery without prematurely spoiling key reveals?
   - Does it build tension through authentic story events and deliver a gripping, accurate resolution?

Output strictly valid JSON with keys:
"factual_score": float,
"comprehension_score": float,
"suspense_score": float,
"identified_issues": list of strings (concise summary of top factual/story flaws),
"surgical_fixes": list of objects {{"id": int, "fixed_text": str}} (rewriting flawed segments in strictly 10-16 words, 1 standalone sentence)
"""
            try:
                eval_resp = provider.chat_completion(
                    system_prompt="You are a strict editorial quality auditor. Return strict JSON.",
                    user_content=eval_prompt,
                    response_format={"type": "json_object"},
                    max_tokens=2500
                )
                eval_data = json.loads(eval_resp)

                # Validate that required keys are present before trusting scores
                required_keys = {"factual_score", "comprehension_score", "suspense_score"}
                if required_keys.issubset(eval_data.keys()):
                    factual_score = float(eval_data["factual_score"])
                    comprehension_score = float(eval_data["comprehension_score"])
                    suspense_score = float(eval_data["suspense_score"])
                    audit_feedback = eval_data.get("identified_issues", [])
                    surgical_fixes = eval_data.get("surgical_fixes", [])
                    audit_success = True
                else:
                    audit_feedback.append("LLM response missing required score keys — audit not certified.")
            except json.JSONDecodeError as e:
                audit_feedback.append(f"LLM returned invalid JSON — audit not certified: {e}")
            except Exception as e:
                audit_feedback.append(f"LLM semantic evaluation failed — audit not certified: {e}")
        elif not provider:
            # No LLM available — only deterministic scores apply; treat semantic scores as neutral
            factual_score = 7.0
            comprehension_score = 7.0
            suspense_score = 7.0
            audit_success = True  # deterministic checks only

        # Weighted Overall Score Formula:
        # Factual: 30%, Comprehension: 25%, Simple Language: 20%, Suspense: 15%, Flow: 10%
        overall_score = round(
            (factual_score * 0.30) +
            (comprehension_score * 0.25) +
            (simple_lang_score * 0.20) +
            (suspense_score * 0.15) +
            (flow_score * 0.10),
            2
        )

        passed = (overall_score >= 9.5) and audit_success

        return {
            "overall_score": overall_score,
            "passed": passed,
            "audit_success": audit_success,
            "category_scores": {
                "factual_accuracy": factual_score,
                "story_comprehension": comprehension_score,
                "simple_language": simple_lang_score,
                "suspense_engagement": suspense_score,
                "narration_flow": flow_score
            },
            "issues": {
                "jargon_hits": jargon_hits,
                "adverb_hits": adverb_hits,
                "meta_hits": meta_hits,
                "length_violations": length_violations,
                "multi_sentence_hits": multi_sentence_hits,
                "trailing_conjunctions": trailing_conjunctions,
                "semantic_issues": audit_feedback
            },
            "surgical_fixes": surgical_fixes
        }

    @classmethod
    def apply_generic_polish(cls, script: List[dict], provider=None, film_synopsis: str = "", audit_report: dict = None, dialogues: List[dict] = None) -> List[dict]:
        """
        Generic, multi-movie automated polish pass.
        1. Corrects any identified factual, semantic, or twist errors using the film synopsis and dialogue timeline.
        2. Ensures all segments strictly adhere to simple conversational English (10-16 words).
        3. Separates subjective claims from objective facts.
        4. Eliminates jargon, adverbs, meta-phrases, and multi-sentence formatting.
        5. When a segment exceeds MAX_WORDS, requests an LLM rewrite rather than blindly truncating.
        """
        surgical_fixes = audit_report.get("surgical_fixes", []) if audit_report else []
        issues = audit_report.get("issues", {}).get("semantic_issues", []) if audit_report else []
        length_violations = audit_report.get("issues", {}).get("length_violations", []) if audit_report else []
        bad_length_ids = [lv[0] for lv in length_violations]

        def is_meta_instruction(t: str) -> bool:
            return bool(re.search(r'\b(remove|delete|omit|replace|redundant|duplicate)\s+this\s+(segment|sentence|scene)\b', t, flags=re.IGNORECASE))

        def parse_to_sec(ts_str: str) -> float:
            try:
                parts = str(ts_str).replace(",", ".").split(":")
                if len(parts) == 3:
                    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                elif len(parts) == 2:
                    return float(parts[0]) * 60 + float(parts[1])
                return float(ts_str)
            except Exception:
                return 0.0

        fix_map = {}
        if surgical_fixes:
            for f in surgical_fixes:
                if "id" in f and "fixed_text" in f and not is_meta_instruction(f["fixed_text"]):
                    fix_map[f["id"]] = f["fixed_text"]

        # Run LLM repair prompt for any identified semantic issues or length violations
        if provider and film_synopsis and (issues or bad_length_ids):
            flawed_context = "\n".join(f"- {iss}" for iss in issues[:8]) if issues else "Ensure all segments are factually faithful and flow smoothly."
            length_context = f"\nSegments with word-count violations (must be strictly {cls.MIN_WORDS} to {cls.MAX_WORDS} words): {bad_length_ids}" if bad_length_ids else ""

            # Provide dialogue context near flawed/violated segments for factual grounding
            dialogue_context_lines = []
            target_ids = set([lv[0] for lv in length_violations] + list(fix_map.keys()))
            if dialogues and target_ids:
                for s in script:
                    sid = s.get("id")
                    if sid in target_ids:
                        ts = parse_to_sec(s.get("movie_timestamp", "00:00:00"))
                        nearby = [d.get("text", "").strip() for d in dialogues if abs(float(d.get("start", 0)) - ts) <= 45.0]
                        if nearby:
                            dialogue_context_lines.append(f"Segment ID {sid} [{s.get('movie_timestamp')}]: Dialogue context: {' | '.join(nearby[:5])}")

            diag_snippet = ""
            if dialogue_context_lines:
                diag_snippet = "\n\nActual Dialogue Context at Target Timestamps:\n" + "\n".join(dialogue_context_lines[:15])

            script_sample = "\n".join([f"ID {s.get('id')} [{s.get('movie_timestamp','')}]: {cls._get_narration_text(s)}" for s in script])
            repair_prompt = f"""You are a master movie recap editor.
The following recap script has several identified factual, story, or pacing errors:
{flawed_context}{length_context}{diag_snippet}

Authoritative Film Synopsis (COMPLETE):
{film_synopsis[:6000]}

Full Script:
{script_sample}

Carefully review all segments against the Authoritative Film Synopsis and dialogue context.
CRITICAL REQUIREMENTS FOR EVERY FIX:
1. SOURCE ACCURACY: Base the description strictly on the actual event supported by the dialogue and synopsis at that timestamp.
2. SEPARATE FACTS, CLAIMS, AND INFERENCES: If a character makes an accusation or claim not yet confirmed, state it as a claim ("Alice claims...", "Alvar insists...", "She suspects..."). Do NOT present unproven theories as facts early on.
3. STRICT LENGTH: EVERY fix MUST contain strictly {cls.MIN_WORDS} to {cls.MAX_WORDS} words.
4. STRICT CADENCE: Exactly ONE single standalone sentence ending with a period (.), exclamation (!), or question mark (?).
5. NO META-PHRASES: Every sentence MUST be genuine spoken story narration. Never output "Remove this" or "Omit".
6. NO DUPLICATE ADJACENT SEGMENTS: Each segment must uniquely advance the story.

Output valid JSON with key "corrections": a list of objects {{"id": int, "fixed_text": str}}.
"""
            try:
                resp = provider.chat_completion(
                    system_prompt="You are a master script editor. Output valid JSON with key 'corrections'.",
                    user_content=repair_prompt,
                    response_format={"type": "json_object"},
                    max_tokens=2500
                )
                data = json.loads(resp)
                for c in data.get("corrections", []):
                    if "id" in c and "fixed_text" in c:
                        txt = c["fixed_text"].strip()
                        if not is_meta_instruction(txt):
                            fix_map[c["id"]] = txt
            except Exception as e:
                print(f"  [ScriptAuditor] Repair prompt notice: {e}")

        polished = []
        for s in script:
            item = dict(s)
            seg_id = item.get("id")

            # Apply LLM factual/semantic fix if available
            if seg_id in fix_map:
                text = fix_map[seg_id]
            else:
                text = cls._get_narration_text(item)

            # 1. Clean meta phrases
            for mp in cls.FORBIDDEN_META:
                text = re.sub(mp, "", text, flags=re.IGNORECASE).strip()

            # 2. Clean dramatic adverbs
            for ap in cls.BANNED_ADVERBS:
                text = re.sub(ap, "", text, flags=re.IGNORECASE).strip()

            # 3. Clean common jargon
            jargon_replacements = {
                r'\borthodox\s+freudian\s+concepts\b': 'traditional psychology ideas',
                r'\bdeep-seated\s+paranoid\s+delusions\b': 'false beliefs caused by paranoia',
                r'\bforensic\s+inconsistencies\b': 'differences in the medical reports',
                r'\bpredatory\s+suitors\b': 'men who wanted to exploit her wealth',
                r'\bcontemptuously\s+scoffs\b': 'laughs',
                r'\bclinical\s+discharge\b': 'official release',
                r'\blegal\s+incapacitation\b': 'legal detention',
                r'\bdisciplinary\s+punishment\b': 'punishment from staff',
                r'\belaborate\s+psychological\s+manifestations\b': 'false ideas created by her mind',
            }
            for pattern, repl in jargon_replacements.items():
                text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

            # Collapse double spaces
            text = re.sub(r'\s+', ' ', text).strip()

            # Ensure single sentence punctuation
            if not text.endswith(('.', '!', '?')):
                text += '.'

            # Word-count enforcement: strictly MIN_WORDS to MAX_WORDS
            # Both over-length and under-length segments are sent to LLM for grammatical rewrite.
            # CRITICAL (Issue 5): NEVER blindly slice words mid-sentence (e.g. words[:16]),
            # which destroys grammar, cuts thoughts in half, and causes audio glitches in TTS.
            # Instead, validate every rewrite and preserve complete grammatical sentences.
            words = text.split()
            if len(words) > cls.MAX_WORDS or len(words) < cls.MIN_WORDS:
                if provider:
                    rewritten_candidate = None
                    # Pass 1: Targeted length adjustment
                    try:
                        direction = "shorter" if len(words) > cls.MAX_WORDS else "longer"
                        rewrite_resp = provider.chat_completion(
                            system_prompt=(
                                f"You are a master script editor. Rewrite the voiceover sentence into EXACTLY ONE complete, "
                                f"grammatically sound sentence of strictly {cls.MIN_WORDS} to {cls.MAX_WORDS} words. "
                                f"Keep the core story meaning intact. Make it {direction}."
                            ),
                            user_content=text,
                            max_tokens=60
                        )
                        cand = rewrite_resp.strip()
                        if not cand.endswith(('.', '!', '?')):
                            cand += '.'
                        c_words = cand.split()
                        if cls.MIN_WORDS <= len(c_words) <= cls.MAX_WORDS:
                            rewritten_candidate = cand
                    except Exception as e:
                        print(f"  [ScriptAuditor] Word-count rewrite pass 1 notice: {e}")

                    # Pass 2: Fallback attempt if pass 1 was still out of range
                    if not rewritten_candidate:
                        try:
                            rewrite_resp_2 = provider.chat_completion(
                                system_prompt=(
                                    f"Condense or expand this into a SINGLE complete standalone sentence of strictly 12 to 14 words. "
                                    f"End with a period. Never leave a dangling clause."
                                ),
                                user_content=text,
                                max_tokens=50
                            )
                            cand2 = rewrite_resp_2.strip()
                            if not cand2.endswith(('.', '!', '?')):
                                cand2 += '.'
                            c2_words = cand2.split()
                            if cls.MIN_WORDS <= len(c2_words) <= cls.MAX_WORDS:
                                rewritten_candidate = cand2
                        except Exception:
                            pass

                    if rewritten_candidate:
                        text = rewritten_candidate
                    else:
                        # LLM rewrite attempts did not reach the exact range.
                        # Preserve grammatical sentence integrity rather than cutting off mid-phrase!
                        item["_length_violation"] = len(words)
                        item["_cadence_warning"] = (
                            f"Sentence has {len(words)} words (target {cls.MIN_WORDS}-{cls.MAX_WORDS}); "
                            f"kept grammatically complete sentence to avoid audio truncation."
                        )
                else:
                    item["_length_violation"] = len(words)
                    item["_cadence_warning"] = f"Sentence has {len(words)} words; provider unavailable for rewrite."

            # Post-polish validation: flag any segment that still violates rules after all fixes
            final_words = text.split()
            if len(final_words) < cls.MIN_WORDS or len(final_words) > cls.MAX_WORDS:
                item["_length_violation"] = len(final_words)

            # Deduplicate identical adjacent narration
            if polished:
                prev_text = cls._get_narration_text(polished[-1])
                if prev_text.strip().lower() == text.strip().lower():
                    # Mark as duplicate rather than silently replacing with broken text
                    item["_duplicate_flag"] = True

            # Assign to canonical 'narration' field and legacy language-specific fields
            item["narration"] = text
            if "english" in item:
                item["english"] = text
            if "hindi" in item:
                item["hindi"] = text
            if "text" in item:
                item["text"] = text
            polished.append(item)

        return polished
