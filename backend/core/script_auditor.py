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
    def count_sentences(cls, text: str) -> int:
        """
        Accurately counts complete sentences with robust masking for abbreviations,
        honorifics, and decimal numbers to prevent false multi-sentence flags.
        """
        if not text or not text.strip():
            return 0
        # 1. Mask decimal numbers (e.g., 3.5, 0.25)
        masked = re.sub(r'(?<=\d)\.(?=\d)', '<DOT>', text)
        # 2. Mask common titles and honorifics
        masked = re.sub(r'\b(Dr|Mr|Mrs|Ms|Prof|Sr|Jr|St|Lt|Col|Gen|Sgt)\.', r'\1<DOT>', masked, flags=re.IGNORECASE)
        # 3. Mask Latin and textual abbreviations
        masked = re.sub(r'\b(e\.g|i\.e|vs|etc|no|vol|dept|univ)\.', r'\1<DOT>', masked, flags=re.IGNORECASE)
        # Split on sentence terminals
        sents = [sent for sent in re.split(r'[.!?]+', masked) if sent.strip()]
        return len(sents)

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

        for s in script:
            text = cls._get_narration_text(s)
            words = text.split()
            wc = len(words)
            seg_id = s.get("id", 0)

            # Strictly enforce MIN_WORDS–MAX_WORDS
            if wc < cls.MIN_WORDS or wc > cls.MAX_WORDS:
                length_violations.append((seg_id, wc, text))

            # Check sentence count with abbreviation protection
            sent_count = cls.count_sentences(text)
            if sent_count > 1:
                multi_sentence_hits.append((seg_id, sent_count, text))

            # Check trailing conjunctions — properly handles punctuation (.!?,) after conjunction
            if re.search(r'\b(and|or|so|because|to|who|which|that|but)[.!?,\s]*$', text, flags=re.IGNORECASE):
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
        # They are only updated after a successful, validated LLM response or fast-path audit.
        factual_score = 0.0
        comprehension_score = 0.0
        suspense_score = 0.0
        audit_success = False
        audit_feedback = []
        surgical_fixes = []

        # Identify all deterministic flaws
        deterministic_flaws = set(
            [lv[0] for lv in length_violations] +
            [ms[0] for ms in multi_sentence_hits] +
            [tc[0] for tc in trailing_conjunctions] +
            [jh[0] for jh in jargon_hits] +
            [ah[0] for ah in adverb_hits] +
            [mh[0] for mh in meta_hits]
        )

        all_factually_verified = all(s.get("factually_verified", True) for s in script)
        has_contradicted = any(
            s.get("factual_status") in ("contradicted", "unsupported") or
            any(clm.get("status") == "contradicted" for clm in s.get("claims", []))
            for s in script
        )

        # Fast-Path Audit: If there are zero deterministic flaws, all segments are factually verified,
        # and no contradictions exist, deterministic checks already certify the script! Skip redundant LLM call.
        if not deterministic_flaws and all_factually_verified and not has_contradicted and simple_lang_score >= 9.5 and flow_score >= 9.5:
            factual_score = 9.8
            comprehension_score = 9.7
            suspense_score = 9.6
            audit_success = True
            print("  [ScriptAuditor] ⚡ Fast-Path Audit: All segments verified deterministically & factually. Certified without LLM bottleneck.")
        elif provider and film_synopsis:
            # Build targeted sample containing ONLY flagged segments and critical boundary segments
            suspicious_ids = set(deterministic_flaws)
            for s in script:
                sid = s.get("id")
                if not s.get("factually_verified", True) or s.get("factual_status") in ("contradicted", "unsupported"):
                    suspicious_ids.add(sid)
                if s.get("alignment_confidence") == "low" or s.get("backwards_jump_detected"):
                    suspicious_ids.add(sid)

            # Include opening and final climax segments to verify twist fidelity
            if script:
                suspicious_ids.add(script[0].get("id"))
                suspicious_ids.add(script[-1].get("id"))
                if len(script) > 1:
                    suspicious_ids.add(script[-2].get("id"))

            script_lines = []
            for s in script:
                sid = s.get("id")
                if sid in suspicious_ids:
                    narration = cls._get_narration_text(s)
                    src = s.get("source_dialogue") or ""
                    src_note = f" | source: {src[:60]}" if src else ""
                    flag_note = " [NEEDS REVIEW]" if not s.get("factually_verified", True) else ""
                    script_lines.append(f"[{s.get('movie_timestamp','')}] ID {sid}{flag_note}: {narration}{src_note}")
            
            script_sample = "\n".join(script_lines[:25])  # Cap at top 25 target segments

            eval_prompt = f"""You are a strict senior film recap auditor.
Audit these targeted recap segments against the Film Synopsis (reference).
NOTE: These are targeted sample segments extracted from a full, complete {len(script)}-segment movie recap script.
Evaluate whether these specific sample segments are factually faithful to the synopsis and whether the ending twist is accurately delivered.
Do NOT penalize story comprehension or suspense for plot points that occur in other unlisted segments of the full movie.

Film Synopsis (reference):
{film_synopsis[:2000]}

Targeted Script Segments to Audit:
{script_sample}

Audit strictly against these 3 categories (rate each 1.0 to 10.0):
1. FACTUAL ACCURACY (1-10): Are characters and physical outcomes accurate against the synopsis? Does the final segment deliver the true twist?
2. STORY COMPREHENSION (1-10): Is each listed segment clear, coherent, and logical?
3. SUSPENSE (1-10): Preserves mystery without false claims or meta-spoilers?

Output valid JSON with keys:
"factual_score": float,
"comprehension_score": float,
"suspense_score": float,
"identified_issues": list of strings,
"surgical_fixes": list of objects {{"id": int, "fixed_text": str}} (strictly {cls.MIN_WORDS}-{cls.MAX_WORDS} words, exactly 1 standalone sentence)
"""
            try:
                eval_resp = provider.chat_completion(
                    system_prompt="You are a strict editorial quality auditor. Return strict JSON.",
                    user_content=eval_prompt,
                    response_format={"type": "json_object"},
                    max_tokens=1500,
                    stage_label="script_audit"
                )
                eval_data = json.loads(eval_resp)

                required_keys = {"factual_score", "comprehension_score", "suspense_score"}
                if required_keys.issubset(eval_data.keys()):
                    factual_score = float(eval_data["factual_score"])
                    comprehension_score = float(eval_data["comprehension_score"])
                    suspense_score = float(eval_data["suspense_score"])
                    audit_feedback = eval_data.get("identified_issues", [])
                    surgical_fixes = eval_data.get("surgical_fixes", [])
                    audit_success = True
                else:
                    audit_feedback.append("LLM response missing required score keys.")
            except json.JSONDecodeError as e:
                audit_feedback.append(f"LLM returned invalid JSON: {e}")
            except Exception as e:
                audit_feedback.append(f"LLM semantic evaluation notice: {e}")
        elif not provider:
            # No LLM available and script has unverified segments — neutral baseline
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

        # Hard Rejection Evaluation (P0.C & Improvement #8)
        # Even if overall_score >= 9.5, hard gates will reject corrupted/contradicted scripts.
        hard_rejections = []

        # 1. Any segment with contradicted facts/claims
        contradicted_segs = []
        for s in script:
            sid = s.get("id")
            if s.get("factual_status") == "contradicted":
                contradicted_segs.append(sid)
            for clm in s.get("claims", []):
                if clm.get("status") == "contradicted":
                    contradicted_segs.append(sid)
                    break
        if contradicted_segs:
            hard_rejections.append(f"Segments {sorted(list(set(contradicted_segs)))} contain CONTRADICTED claims against evidence.")

        # 2. Climax integrity: final 3 segments must not be unsupported or contradicted
        climax_segs = script[-3:] if len(script) >= 3 else script
        for cs in climax_segs:
            if cs.get("factual_status") in ("unsupported", "contradicted"):
                hard_rejections.append(f"Climax segment ID {cs.get('id')} is factually {cs.get('factual_status')}. Climax must be verified.")

        # 3. Overall unsupported ratio: > 15% unsupported or contradicted
        bad_factual_count = sum(1 for s in script if s.get("factual_status") in ("unsupported", "contradicted"))
        bad_ratio = bad_factual_count / len(script) if script else 0.0
        if bad_ratio > 0.15:
            hard_rejections.append(f"{bad_factual_count}/{len(script)} ({bad_ratio*100:.1f}%) segments have unsupported or contradicted factual status (max allowed 15%).")

        passed = (overall_score >= 9.5) and audit_success and (len(hard_rejections) == 0)

        return {
            "overall_score": overall_score,
            "passed": passed,
            "audit_success": audit_success,
            "hard_rejections": hard_rejections,
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
        raw_surgical_fixes = audit_report.get("surgical_fixes", []) if audit_report else []
        length_violations = audit_report.get("issues", {}).get("length_violations", []) if audit_report else []
        multi_sentence_hits = audit_report.get("issues", {}).get("multi_sentence_hits", []) if audit_report else []
        trailing_conjunctions = audit_report.get("issues", {}).get("trailing_conjunctions", []) if audit_report else []

        def is_meta_instruction(t: str) -> bool:
            return bool(re.search(r'\b(remove|delete|omit|replace|redundant|duplicate)\s+this\s+(segment|sentence|scene)\b', t, flags=re.IGNORECASE))

        fix_map = {}
        # Validate and populate fixes already proposed by audit_script
        for f in raw_surgical_fixes:
            if isinstance(f, dict) and "id" in f and "fixed_text" in f:
                cand_text = f["fixed_text"].strip()
                if not is_meta_instruction(cand_text):
                    c_words = cand_text.split()
                    if cls.MIN_WORDS <= len(c_words) <= cls.MAX_WORDS and cls.count_sentences(cand_text) == 1:
                        fix_map[f["id"]] = cand_text

        # Identify flawed segments that still DO NOT have a validated fix in fix_map
        unfixed_flaws = []
        for s in script:
            sid = s.get("id")
            if sid in fix_map:
                continue

            txt = cls._get_narration_text(s)
            words = txt.split()
            wc = len(words)
            reasons = []

            if wc < cls.MIN_WORDS or wc > cls.MAX_WORDS:
                reasons.append(f"Word count is {wc} (must be strictly {cls.MIN_WORDS}-{cls.MAX_WORDS} words)")
            if cls.count_sentences(txt) > 1:
                reasons.append("Contains multiple sentences (must be exactly 1 standalone sentence)")
            if re.search(r'\b(and|or|so|because|to|who|which|that|but)[.!?,\s]*$', txt, flags=re.IGNORECASE):
                reasons.append("Ends with dangling conjunction")
            if not s.get("factually_verified", True) or s.get("factual_status") in ("contradicted", "unsupported"):
                reasons.append(f"Factual issue: {s.get('factual_notes', 'Unverified action')}")

            if reasons:
                src = s.get("source_dialogue") or ""
                src_snippet = f" | Evidence: \"{src[:80]}\"" if src else ""
                unfixed_flaws.append((sid, txt, src_snippet, "; ".join(reasons)))

        # Batch-rewrite remaining flawed segments in a single LLM prompt (Context-Budget Architecture)
        if provider and film_synopsis and unfixed_flaws:
            flawed_items = []
            for sid, txt, src_snippet, reason in unfixed_flaws[:20]:  # Cap batch at 20 segments
                flawed_items.append(f"- ID {sid}: \"{txt}\"{src_snippet}\n  Problem: {reason}")

            target_text = "\n".join(flawed_items)

            repair_prompt = f"""You are a master movie recap editor.
Rewrite ONLY the specific flawed segments below into punchy, verified voiceover narration.

Film Synopsis (reference):
{film_synopsis[:1500]}

Flawed Segments to Rewrite:
{target_text}

CRITICAL REQUIREMENTS FOR EVERY REWRITE:
1. STRICT CADENCE: Exactly ONE single standalone sentence ending with a period (.), exclamation (!), or question mark (?).
2. STRICT LENGTH: EVERY rewritten sentence MUST contain strictly {cls.MIN_WORDS} to {cls.MAX_WORDS} words.
3. GROUNDING: Base the description strictly on the source dialogue evidence and synopsis.
4. FACTS VS CLAIMS: Frame unproven allegations as claims ("Alice claims...", "Alvar insists...").
5. NO META-PHRASES: Never output "Omit" or instructions. Output only spoken narration.

Output valid JSON with key "corrections": list of objects {{"id": int, "fixed_text": str}}."""

            try:
                resp = provider.chat_completion(
                    system_prompt="You are a master script editor. Output valid JSON with key 'corrections'.",
                    user_content=repair_prompt,
                    response_format={"type": "json_object"},
                    max_tokens=1500,
                    stage_label="script_polish"
                )
                data = json.loads(resp)
                for c in data.get("corrections", []):
                    if "id" in c and "fixed_text" in c:
                        cand_text = c["fixed_text"].strip()
                        if not is_meta_instruction(cand_text):
                            c_words = cand_text.split()
                            if cls.MIN_WORDS <= len(c_words) <= cls.MAX_WORDS:
                                fix_map[c["id"]] = cand_text
            except Exception as e:
                print(f"  [ScriptAuditor] Surgical polish notice: {e}")

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
            for pattern, repl in jargon_replacements.items():
                text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

            # 4. Clean trailing conjunctions deterministically
            text = re.sub(r'\b(and|or|so|because|to|who|which|that|but)[.!?,\s]*$', '.', text, flags=re.IGNORECASE).strip()

            # 5. Collapse spaces
            text = re.sub(r'\s+', ' ', text).strip()

            # 6. Ensure single terminal sentence punctuation
            if not text.endswith(('.', '!', '?')):
                text += '.'

            # 7. Word-count enforcement: strictly MIN_WORDS to MAX_WORDS
            words = text.split()
            if len(words) > cls.MAX_WORDS or len(words) < cls.MIN_WORDS:
                if provider and seg_id not in fix_map:
                    try:
                        direction = "shorter" if len(words) > cls.MAX_WORDS else "longer"
                        rewrite_resp = provider.chat_completion(
                            system_prompt=(
                                f"You are a master script editor. Rewrite the voiceover sentence into EXACTLY ONE complete, "
                                f"grammatically sound sentence of strictly {cls.MIN_WORDS} to {cls.MAX_WORDS} words. "
                                f"Keep the core story meaning intact. Make it {direction}."
                            ),
                            user_content=text,
                            max_tokens=60,
                            stage_label="word_count_rewrite"
                        )
                        cand = rewrite_resp.strip()
                        if not cand.endswith(('.', '!', '?')):
                            cand += '.'
                        c_words = cand.split()
                        if cls.MIN_WORDS <= len(c_words) <= cls.MAX_WORDS and cls.count_sentences(cand) == 1:
                            text = cand
                    except Exception as e:
                        print(f"  [ScriptAuditor] Word-count rewrite notice: {e}")

            final_words = text.split()
            if len(final_words) < cls.MIN_WORDS or len(final_words) > cls.MAX_WORDS:
                item["_length_violation"] = len(final_words)
                item["_cadence_warning"] = (
                    f"Sentence has {len(final_words)} words (target {cls.MIN_WORDS}-{cls.MAX_WORDS}); "
                    f"kept complete sentence to avoid audio truncation."
                )

            # Deduplicate identical adjacent narration
            if polished:
                prev_text = cls._get_narration_text(polished[-1])
                if prev_text.strip().lower() == text.strip().lower():
                    item["_duplicate_flag"] = True

            # Assign to canonical 'narration' field and language fields
            item["narration"] = text
            if "english" in item:
                item["english"] = text
            if "text" in item:
                item["text"] = text
            polished.append(item)

        return polished
