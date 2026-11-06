"""
Movie Understanding: Event Map + Character Map Extraction.

Builds a structured intermediate representation of the movie from the dialogue timeline.
This replaces reliance on a single prose synopsis as the ground truth.

The event map provides:
1. A character map with roles, relationships, and evidence references.
2. A chronological event timeline with importance scores.
3. Unresolved questions and final revelations for twist preservation.
4. Timeline anchors — key moments with exact subtitle timestamps.

The model builds this map FROM the dialogue timeline, then the recap generator
uses it instead of (or alongside) the prose synopsis.
"""

import json
import re
from typing import List, Dict, Optional


class MovieUnderstanding:
    """
    Extracts a structured event map from the dialogue timeline.
    Provides a verifiable, persistent representation of what actually
    happened in the movie, grounded in subtitle evidence.
    """

    @classmethod
    def extract_event_map(cls, dialogues: List[dict], provider,
                          film_synopsis: str = "",
                          movie_title: str = "",
                          max_dialogue_tokens: int = 2000) -> dict:
        """
        Build a structured event map from the dialogue timeline.

        Uses the LLM to extract characters, events, and relationships from
        chronological dialogue windows, then assembles them into a coherent map.

        Args:
            dialogues: Parsed subtitle dicts with 'start', 'end', 'text', 'id'.
            provider: GroqProvider for LLM calls.
            film_synopsis: Optional Wikipedia synopsis as supplementary reference.
            movie_title: Cleaned movie title string.
            max_dialogue_tokens: Token budget for dialogue in extraction prompt.

        Returns:
            Structured event map dict.
        """
        if not dialogues:
            return cls._empty_event_map(movie_title)

        total_runtime_sec = max(
            3600.0,
            max(float(d.get("end", d.get("start", 0))) for d in dialogues)
        )

        # ── Phase 1: Extract characters + events from dialogue windows ──
        # Split dialogues into 3 windows (beginning, middle, end) for broader coverage
        # while keeping each LLM call within token budget.
        window_count = 3
        window_dur = total_runtime_sec / window_count
        window_extractions = []

        for w_idx in range(window_count):
            w_start = w_idx * window_dur
            w_end = (w_idx + 1) * window_dur if w_idx < window_count - 1 else total_runtime_sec + 10.0
            w_dialogues = [d for d in dialogues if w_start <= d["start"] < w_end]

            if not w_dialogues:
                continue

            # Importance-aware sampling: keep lines with names, numbers, short revelations
            sampled = cls._importance_sample_dialogues(w_dialogues, max_dialogue_tokens)

            window_label = ["Beginning", "Middle", "End"][w_idx]
            time_range = f"{cls._fmt_sec(w_start)} - {cls._fmt_sec(min(total_runtime_sec, w_end))}"

            extraction = cls._extract_window(
                provider=provider,
                sampled_dialogue=sampled,
                window_label=window_label,
                time_range=time_range,
                movie_title=movie_title,
                film_synopsis=film_synopsis if w_idx == 0 else "",  # Only first window gets synopsis
                is_final=w_idx == window_count - 1,
            )
            if extraction:
                window_extractions.append(extraction)

        # ── Phase 2: Merge window extractions into unified event map ──
        event_map = cls._merge_extractions(window_extractions, movie_title)

        return event_map

    @classmethod
    def _importance_sample_dialogues(cls, dialogues: List[dict],
                                     max_tokens: int = 2000) -> str:
        """
        Sample dialogues with importance scoring:
        1. Preserve lines with names, numbers, dates, locations, revelations.
        2. Preserve surrounding context (1 line before/after important lines).
        3. Sample remaining chronologically with guaranteed end coverage.
        """
        if not dialogues:
            return ""

        def estimate_tokens(text: str) -> int:
            return max(1, int(len(text) / 3.3))

        # Score each line for importance
        NAME_PATTERN = re.compile(
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b'  # Capitalized names
        )
        NUMBER_PATTERN = re.compile(
            r'\b\d{2,}\b'  # Numbers with 2+ digits (years, amounts, dates)
        )
        REVEAL_WORDS = re.compile(
            r'(?i)\b(kill|murder|dead|die|truth|reveal|secret|lie|betray|confess|'
            r'discover|hidden|stolen|missing|innocent|guilty|arrest|escape|'
            r'love|marry|divorce|pregnant|father|mother|son|daughter|brother|sister)\b'
        )
        LOCATION_WORDS = re.compile(
            r'(?i)\b(hospital|house|office|prison|church|school|hotel|station|'
            r'apartment|room|basement|attic|garden|park|street|city|town)\b'
        )

        importance = []
        for i, d in enumerate(dialogues):
            text = d.get("text", "").strip()
            score = 0
            word_count = len(text.split())

            # Short lines are often critical revelations
            if 2 <= word_count <= 8:
                score += 3
            elif word_count <= 12:
                score += 1

            # Lines with proper nouns (character names)
            if NAME_PATTERN.search(text):
                score += 2

            # Lines with numbers (dates, years, amounts)
            if NUMBER_PATTERN.search(text):
                score += 2

            # Lines with revelation/relationship words
            if REVEAL_WORDS.search(text):
                score += 3

            # Lines with location markers
            if LOCATION_WORDS.search(text):
                score += 1

            importance.append((i, score))

        # Mark important lines and their neighbors
        important_indices = set()
        for i, score in importance:
            if score >= 3:
                important_indices.add(i)
                # Add context: 1 line before and after
                if i > 0:
                    important_indices.add(i - 1)
                if i < len(dialogues) - 1:
                    important_indices.add(i + 1)

        # Guarantee end-of-window coverage (last 10% of lines)
        end_start = max(0, int(len(dialogues) * 0.9))
        for i in range(end_start, len(dialogues)):
            important_indices.add(i)

        # Build selected lines: important first, then fill chronologically
        selected = sorted(important_indices)
        remaining = [i for i in range(len(dialogues)) if i not in important_indices]

        # Add remaining lines evenly distributed until token budget
        if remaining:
            step = max(1, len(remaining) // 20)
            sampled_remaining = remaining[::step]
            selected = sorted(set(selected) | set(sampled_remaining))

        # Build output respecting token budget
        result_lines = []
        accumulated_tokens = 0
        for idx in selected:
            d = dialogues[idx]
            ts = int(d.get("start", 0))
            text = d.get("text", "").strip()
            line = f"[{ts // 3600:02d}:{(ts % 3600) // 60:02d}:{ts % 60:02d}] (ID:{d.get('id', idx + 1)}) {text}"
            lt = estimate_tokens(line)
            if accumulated_tokens + lt > max_tokens:
                break
            result_lines.append(line)
            accumulated_tokens += lt

        return "\n".join(result_lines)

    @classmethod
    def _extract_window(cls, *, provider, sampled_dialogue: str,
                        window_label: str, time_range: str,
                        movie_title: str, film_synopsis: str,
                        is_final: bool) -> Optional[dict]:
        """Extract characters and events from a single dialogue window via LLM."""
        if not sampled_dialogue.strip():
            return None

        synopsis_section = ""
        if film_synopsis:
            synopsis_section = f"\nFilm Synopsis (supplementary reference — dialogue is primary):\n{film_synopsis[:1200]}\n"

        final_instruction = ""
        if is_final:
            final_instruction = (
                "\nCRITICAL: This is the FINAL section. Identify the true climax, "
                "final revelation/twist, and resolution. Note any identity reveals, "
                "truth vs. lie resolutions, and the actual ending outcome."
            )

        system_prompt = (
            "You are a movie analysis expert. Extract characters and events from dialogue evidence. "
            "Output strict JSON."
        )

        user_prompt = f"""Analyze this dialogue window from '{movie_title}' ({window_label}: {time_range}).
{synopsis_section}
Dialogue Evidence:
{sampled_dialogue}
{final_instruction}

Extract JSON with these keys:
"characters": list of {{"name": str, "role": str (Protagonist/Antagonist/Supporting/Minor), "relationships": [str], "evidence_ids": [int]}}
"events": list of {{"event_id": str (E001...), "time_start_sec": int, "time_end_sec": int, "description": str (what happened), "characters": [str], "evidence_ids": [int], "importance": int (1-10), "is_flashback": bool}}
"unresolved_questions": [str] — mysteries or unanswered questions raised
"revelations": [str] — truths, secrets, or twists revealed in this window"""

        try:
            resp = provider.chat_completion(
                system_prompt=system_prompt,
                user_content=user_prompt,
                response_format={"type": "json_object"},
                max_tokens=1200,
                stage_label=f"event_map_{window_label.lower()}"
            )
            return json.loads(resp)
        except Exception as e:
            print(f"  [MovieUnderstanding] ⚠️ Event extraction ({window_label}): {e}")
            return None

    @classmethod
    def _merge_extractions(cls, extractions: List[dict], movie_title: str) -> dict:
        """Merge character and event extractions from multiple windows."""
        merged_characters = {}
        merged_events = []
        all_questions = []
        all_revelations = []
        event_counter = 1

        for ext in extractions:
            # Merge characters (deduplicate by name)
            for char in ext.get("characters", []):
                name = char.get("name", "").strip()
                if not name:
                    continue
                if name in merged_characters:
                    existing = merged_characters[name]
                    # Upgrade role if we have better info
                    if char.get("role") and char["role"] != "Minor":
                        existing["role"] = char["role"]
                    existing["relationships"] = list(set(
                        existing.get("relationships", []) + char.get("relationships", [])
                    ))
                    existing["evidence_ids"] = list(set(
                        existing.get("evidence_ids", []) + char.get("evidence_ids", [])
                    ))
                else:
                    merged_characters[name] = {
                        "name": name,
                        "role": char.get("role", ""),
                        "relationships": char.get("relationships", []),
                        "evidence_ids": char.get("evidence_ids", []),
                    }

            # Merge events (re-number sequentially)
            for event in ext.get("events", []):
                event["event_id"] = f"E{event_counter:03d}"
                event_counter += 1
                merged_events.append(event)

            all_questions.extend(ext.get("unresolved_questions", []))
            all_revelations.extend(ext.get("revelations", []))

        # Sort events by time_start_sec
        merged_events.sort(key=lambda e: e.get("time_start_sec", 0))

        # Deduplicate questions and revelations
        all_questions = list(dict.fromkeys(all_questions))
        all_revelations = list(dict.fromkeys(all_revelations))

        # Identify timeline anchors (events with importance >= 7)
        timeline_anchors = [
            {
                "event_id": e["event_id"],
                "timestamp_sec": e.get("time_start_sec", 0),
                "description": e.get("description", ""),
            }
            for e in merged_events
            if e.get("importance", 0) >= 7
        ]

        return {
            "movie_title": movie_title,
            "characters": list(merged_characters.values()),
            "events": merged_events,
            "unresolved_questions": all_questions,
            "final_revelations": all_revelations,
            "timeline_anchors": timeline_anchors,
        }

    @classmethod
    def format_event_map_for_prompt(cls, event_map: dict, block_start_sec: float = 0.0,
                                    block_end_sec: float = float("inf"),
                                    max_tokens: int = 400) -> str:
        """
        Format relevant portion of event map for prompt injection.
        Filters events to the specified block window.
        Budget: ~400 tokens.
        """
        lines = ["MOVIE EVENT MAP:"]

        # Characters (compact)
        chars = event_map.get("characters", [])
        if chars:
            char_strs = []
            for c in chars[:8]:
                parts = [f"{c['name']}: {c.get('role', '')}"]
                if c.get("relationships"):
                    parts.append(f"({', '.join(c['relationships'][:2])})")
                char_strs.append(" ".join(parts))
            lines.append("Characters: " + "; ".join(char_strs))

        # Events relevant to this block
        events = event_map.get("events", [])
        block_events = [
            e for e in events
            if (e.get("time_start_sec", 0) >= block_start_sec - 60
                and e.get("time_start_sec", 0) <= block_end_sec + 60)
        ]
        # Also include high-importance events from earlier blocks for context
        prior_important = [
            e for e in events
            if (e.get("time_start_sec", 0) < block_start_sec - 60
                and e.get("importance", 0) >= 8)
        ][-3:]

        if prior_important:
            lines.append("Key Prior Events: " + " | ".join(
                e["description"][:60] for e in prior_important
            ))

        if block_events:
            for e in block_events[:8]:
                fb_tag = " [FLASHBACK]" if e.get("is_flashback") else ""
                lines.append(
                    f"  E{e.get('event_id', '?')}: {e['description'][:80]}{fb_tag} "
                    f"(importance: {e.get('importance', '?')})"
                )

        # Unresolved questions
        questions = event_map.get("unresolved_questions", [])
        if questions:
            lines.append("Open Questions: " + " | ".join(questions[:3]))

        # Final revelations (only show near end of movie)
        if block_end_sec >= float("inf") or block_end_sec > 0.75 * max(
            e.get("time_end_sec", 0) for e in events
        ) if events else False:
            revs = event_map.get("final_revelations", [])
            if revs:
                lines.append("Revelations: " + " | ".join(revs[:3]))

        return "\n".join(lines)

    @classmethod
    def populate_evidence_store(cls, event_map: dict, evidence_store) -> None:
        """
        Populate an EvidenceStore from the extracted event map.
        This transfers dialogue-grounded facts into the source story state.
        """
        # Add characters
        for char in event_map.get("characters", []):
            evidence_store.add_character(
                name=char["name"],
                role=char.get("role", ""),
                relationships=char.get("relationships", []),
                first_seen_sec=0.0,
                evidence_ids=char.get("evidence_ids", []),
            )

        # Add events as confirmed facts
        for event in event_map.get("events", []):
            evidence_store.add_source_fact(
                fact=event.get("description", ""),
                evidence_ids=event.get("evidence_ids", []),
                timestamp_sec=event.get("time_start_sec", 0),
            )

        # Add mysteries
        for question in event_map.get("unresolved_questions", []):
            evidence_store.add_mystery(question=question)

    @staticmethod
    def _fmt_sec(secs: float) -> str:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = int(secs % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _empty_event_map(movie_title: str) -> dict:
        return {
            "movie_title": movie_title,
            "characters": [],
            "events": [],
            "unresolved_questions": [],
            "final_revelations": [],
            "timeline_anchors": [],
        }

