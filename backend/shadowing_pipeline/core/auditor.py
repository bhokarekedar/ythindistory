import os
import json
import re
import copy
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

try:
    from core.providers import GroqProvider
except ImportError:
    # If called without PYTHONPATH=backend
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    from core.providers import GroqProvider


AUDIT_SYSTEM_PROMPT = """You are a strict QA editor for English shadowing video scripts (ESL, A2 to B2 learners).
Below is a script JSON for the channel "Shadow English Daily". Audit it against the rules
and return fixes as patches. Do NOT rewrite the whole script.

## How the engine works (needed to judge correctly)
- Script JSON has "title", optional "youtube" metadata, and "segments". No settings, pause_seconds, speed or theme.
- shadow: the engine plays the sentence twice with a learner pause after each play, so each
  shadow sentence must appear only once in the JSON.
- shadow_pair: lines played in order with pauses, then the block repeats twice.
- narration: spoken once, no pause. dialogue: listen only. free_answer: question, then a
  long learner pause. section_title: title card, needs chapter:true and "spoken".
- Allowed types: narration, section_title, shadow, shadow_pair, dialogue, free_answer.
- Allowed fields: id, type, text, spoken, voice, repeat, chapter, lines.
- Voice roles: teacher, speaker_a, speaker_b.

## Checks

A. STRUCTURE
 1. Valid JSON, unique ids.
 2. Order: hook (2 narration), welcome (3), how-to-practice (2) + shadow "Let's begin.",
    warm-up section, 6 to 8 main parts, outro (4 narration).
 3. Every section_title has chapter:true and a "spoken" version without colons.
 4. Forbidden fields anywhere: pause_seconds, speed, settings, theme.
 5. Target 120 to 150 shadow sentences (shadow_pair lines count too).

B. SHADOW SENTENCE QUALITY
 1. Length 5 to 16 words, never over 20. Flag longer ones and give a shorter version.
 2. Standalone and natural: no "as I said", no context-dependent names, nothing a native
    speaker would not say.
 3. No duplicates or near-duplicates anywhere in the script. Flag the later one.
 4. No more than 3 consecutive sentences with the same opening pattern
    (e.g. "Could you...", "I'd like to..."). Flag the 4th and rewrite it.
 5. Each part should mix statements, questions and responses, and go from easy to hard.
 6. Flag sentences with unusual or very formal wording, grammar mistakes, or odd collocations.
 7. Contractions should be used naturally (I'm, don't, we'd).

C. TTS SAFETY
 1. Any sentence containing digits, times, dates, currency, %, symbols, abbreviations or
    hyphenated tokens (7:00, $25, 3 March, Dr., Wi-Fi, 24/7) must have a "spoken" field.
 2. Check that every "spoken" value reads naturally and matches "text" in meaning.
 3. No emojis, brackets, markdown, ">>", "(pause)", stage directions or timestamps
    anywhere in text or spoken.
 4. Flag words TTS often mispronounces (heteronyms like "read", "lead", "wind", rare names,
    acronyms) and suggest a "spoken" fix.

D. NARRATION QUALITY
 1. Teacher tone: calm, friendly, short sentences. Remove hype or filler.
 2. Narration must say that each sentence is said two times (consistent with the engine).
 3. Each main part after the first opens with a short praise or transition.
 4. Each part has 1 to 2 narration segments explaining when and why to use this English.
 5. Narration segments over 60 words should be split into two segments.
 6. The outro has a recap of skills, a comment challenge and "keep speaking English."

E. LEARNING VALUE
 1. Is there enough variety across parts? Flag a part that is repetitive or thin.
 2. Are there 2 to 3 free_answer questions and 1 to 2 dialogues, as required?
 3. Does the script cover the topic broadly and with realistic situations?

## Output format (ONLY valid JSON, nothing else)
{
  "summary": {
    "shadow_count": 0,
    "parts_count": 0,
    "estimated_minutes": 0,
    "verdict": "pass | needs_fixes | major_rewrite",
    "top_issues": ["max 5 short strings"]
  },
  "patches": [
    {
      "action": "replace",
      "id": "p3_07",
      "segment": { "id": "p3_07", "type": "shadow", "text": "...", "spoken": "..." },
      "reason": "short reason"
    },
    {
      "action": "delete",
      "id": "p4_12",
      "reason": "duplicate of p2_05"
    },
    {
      "action": "insert_after",
      "id": "p5_10",
      "segment": { "id": "p5_10b", "type": "shadow", "text": "..." },
      "reason": "part 5 is short on questions"
    }
  ]
}

Rules for patches:
- Every replaced or inserted segment must follow all the rules above and be complete.
- New ids must be unique (e.g. p5_10b). Never reuse a deleted id.
- Keep patches minimal: fix only what is wrong (e.g. add spoken phonetic field, fix long sentence, remove duplicate).
- Do NOT rewrite or rephrase sentences that are already good.
- If more than 30 percent of the script needs fixes, set verdict to "major_rewrite" and list the parts to regenerate.
"""


class ShadowingScriptAuditor:
    """
    Automated QA Script Auditor for English Shadowing Videos.
    Powered by the shared Groq LLM rotation pool (core.providers.GroqProvider).
    """

    def __init__(self, model: str = "qwen/qwen3.8-27b", api_key: str = None, api_keys: list = None):
        groq_keys = []
        if api_key:
            groq_keys.append(api_key)
        if api_keys:
            groq_keys.extend([k for k in api_keys if k and k not in groq_keys])
        for ek in [
            os.getenv("GROQ_API_KEY"),
            os.getenv("GROQ_API_KEY_TWO"),
            os.getenv("GROQ_API_KEY_THREE"),
            os.getenv("GROQ_API_KEY_FOUR"),
        ]:
            if ek and ek not in groq_keys:
                groq_keys.append(ek)

        self.model = model
        self.provider = GroqProvider(model=self.model, api_keys=groq_keys)

    @staticmethod
    def apply_patches(script_data: Dict[str, Any], patches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Safely applies replace, delete, and insert_after patches to a script dictionary.
        Returns a new modified copy of the script dictionary.
        """
        new_script = copy.deepcopy(script_data)
        segments = new_script.get("segments", [])

        for patch in patches:
            action = patch.get("action")
            target_id = patch.get("id")

            if not action or not target_id:
                continue

            if action == "replace":
                replacement = patch.get("segment")
                if not replacement:
                    continue
                for i, seg in enumerate(segments):
                    if seg.get("id") == target_id:
                        segments[i] = replacement
                        break

            elif action == "delete":
                segments = [s for s in segments if s.get("id") != target_id]

            elif action == "insert_after":
                insertion = patch.get("segment")
                if not insertion:
                    continue
                insert_idx = -1
                for i, seg in enumerate(segments):
                    if seg.get("id") == target_id:
                        insert_idx = i
                        break
                if insert_idx != -1:
                    segments.insert(insert_idx + 1, insertion)
                else:
                    # Fallback append
                    segments.append(insertion)

        new_script["segments"] = segments
        return new_script

    def audit_script(self, script_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs the LLM QA audit on the script segments.
        Calculates affected segment percentage and whether approval is required (> 10%).
        """
        if not isinstance(script_data, dict):
            raise ValueError("Script data must be a JSON dictionary.")

        raw_segments = script_data.get("segments", [])
        if not raw_segments:
            raise ValueError("Script has no 'segments' to audit.")

        total_segments = len(raw_segments)

        # Build clean minimal payload for LLM to keep tokens tight
        # We only pass id, type, text, spoken, voice, lines, chapter
        clean_segments = []
        for s in raw_segments:
            item = {"id": s.get("id"), "type": s.get("type"), "text": s.get("text", "")}
            if "spoken" in s:
                item["spoken"] = s["spoken"]
            if "voice" in s:
                item["voice"] = s["voice"]
            if "chapter" in s:
                item["chapter"] = s["chapter"]
            if "lines" in s:
                item["lines"] = s["lines"]
            clean_segments.append(item)

        user_content = json.dumps(
            {
                "title": script_data.get("title", "English Shadowing Script"),
                "total_segments": total_segments,
                "segments": clean_segments,
            },
            ensure_ascii=False,
            indent=None,
        )

        # Call Groq LLM
        print(f"[Auditor] Auditing {total_segments} script segments using Groq ({self.model})...")
        raw_res = self.provider.chat_completion(
            system_prompt=AUDIT_SYSTEM_PROMPT,
            user_content=user_content,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=4000,
            stage_label="shadowing_qa_audit",
        )

        try:
            audit_result = json.loads(raw_res)
        except Exception as e:
            print(f"[Auditor] Failed to parse JSON from LLM: {e}. Raw response:\n{raw_res}")
            raise ValueError(f"Audit LLM did not return valid JSON: {e}")

        summary = audit_result.get("summary", {})
        patches = audit_result.get("patches", [])

        # Validate patches structure
        valid_patches = []
        for p in patches:
            if isinstance(p, dict) and p.get("action") in ["replace", "delete", "insert_after"] and p.get("id"):
                valid_patches.append(p)

        patch_count = len(valid_patches)
        patch_percentage = round((patch_count / total_segments * 100), 1) if total_segments > 0 else 0.0

        # 10% threshold rule:
        # <= 10%: auto-applied
        # > 10%: requires user approval
        requires_approval = patch_percentage > 10.0

        modified_script = self.apply_patches(script_data, valid_patches)

        # In summary, ensure counts are populated
        if not summary.get("shadow_count"):
            summary["shadow_count"] = sum(
                1 if s.get("type") == "shadow" else (len(s.get("lines", [])) if s.get("type") == "shadow_pair" else 0)
                for s in modified_script.get("segments", [])
            )
        if not summary.get("parts_count"):
            summary["parts_count"] = sum(
                1 for s in modified_script.get("segments", [])
                if s.get("type") == "section_title"
            )

        return {
            "success": True,
            "summary": summary,
            "patches": valid_patches,
            "total_segments": total_segments,
            "patch_count": patch_count,
            "patch_percentage": patch_percentage,
            "requires_approval": requires_approval,
            "modified_script": modified_script,
            "original_script": script_data,
        }
