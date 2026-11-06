"""
Evidence Store: Dual Memory System for Movie Recap Pipeline.

Maintains two strictly separate memory layers:
1. SOURCE STORY STATE — What the movie actually establishes (from dialogue evidence ONLY).
   Generated narration can NEVER establish a confirmed movie fact.
2. NARRATION STATE — What the recap has already explained to the viewer.

This separation prevents LLM hallucinations from propagating between blocks:
if Block 2's narration incorrectly states "Alice killed David", the source story state
will NOT absorb that claim as fact — it stays in narration_state only, and subsequent
blocks receive the correct source facts.
"""

import json
from typing import List, Dict, Optional, Set


class EvidenceStore:
    """
    Dual-memory evidence store for evidence-driven movie recap generation.

    Source facts come ONLY from dialogue evidence.
    Narration coverage tracks what the recap has explained.
    Generated narration NEVER establishes a confirmed movie fact.
    """

    def __init__(self, movie_title: str):
        self.movie_title = movie_title

        # ─── SOURCE STORY STATE (populated from dialogue evidence only) ───
        # name -> {"role": str, "relationships": [str], "first_seen_sec": float, "evidence_ids": [int]}
        self.characters: Dict[str, dict] = {}
        # Each: {"fact": str, "evidence_ids": [int], "timestamp_sec": float, "block_index": int}
        self.confirmed_events: List[dict] = []
        # Each: {"claimant": str, "claim": str, "dialogue_id": int, "timestamp_sec": float, "confirmed": bool}
        self.character_claims: List[dict] = []
        # Each: {"description": str, "evidence_ids": [int], "timestamp_sec": float}
        self.evidence_items: List[dict] = []
        # Each: {"question": str, "raised_at_sec": float, "resolved": bool, "resolution": str}
        self.unresolved_mysteries: List[dict] = []

        # ─── NARRATION STATE (populated from generated recap narration) ───
        # Brief text summaries of events already explained in the recap
        self.narrated_events: List[str] = []
        # Character names already introduced to the viewer
        self.narrated_characters: Set[str] = set()
        # block_index -> summary of what was narrated
        self.narrative_coverage: Dict[int, str] = {}
        # Track which confirmed_events have been covered by narration
        self.covered_event_indices: Set[int] = set()

    # ─────────────────────────────────────────────────────────────────────
    # SOURCE STORY STATE MUTATIONS (dialogue evidence only)
    # ─────────────────────────────────────────────────────────────────────

    def add_character(self, name: str, role: str = "",
                      relationships: List[str] = None,
                      first_seen_sec: float = 0.0,
                      evidence_ids: List[int] = None):
        """Register a character from dialogue evidence. Updates if already exists."""
        if name in self.characters:
            existing = self.characters[name]
            if role and not existing.get("role"):
                existing["role"] = role
            if relationships:
                existing_rels = set(existing.get("relationships", []))
                existing_rels.update(relationships)
                existing["relationships"] = sorted(existing_rels)
            if evidence_ids:
                existing_eids = set(existing.get("evidence_ids", []))
                existing_eids.update(evidence_ids)
                existing["evidence_ids"] = sorted(existing_eids)
        else:
            self.characters[name] = {
                "role": role,
                "relationships": relationships or [],
                "first_seen_sec": first_seen_sec,
                "evidence_ids": evidence_ids or [],
            }

    def add_source_fact(self, fact: str, evidence_ids: List[int],
                        timestamp_sec: float, block_index: int = -1):
        """
        Only dialogue evidence can establish a confirmed fact.
        Generated narration must NEVER call this method.
        """
        self.confirmed_events.append({
            "fact": fact,
            "evidence_ids": evidence_ids,
            "timestamp_sec": timestamp_sec,
            "block_index": block_index,
        })

    def add_character_claim(self, claimant: str, claim: str,
                            dialogue_id: int, timestamp_sec: float = 0.0):
        """
        Characters can claim things — these are NOT confirmed facts.
        They stay as claims until explicitly confirmed by new evidence.
        """
        self.character_claims.append({
            "claimant": claimant,
            "claim": claim,
            "dialogue_id": dialogue_id,
            "timestamp_sec": timestamp_sec,
            "confirmed": False,
        })

    def add_evidence(self, description: str, evidence_ids: List[int],
                     timestamp_sec: float = 0.0):
        """Record physical or verbal evidence discovered in dialogue."""
        self.evidence_items.append({
            "description": description,
            "evidence_ids": evidence_ids,
            "timestamp_sec": timestamp_sec,
        })

    def add_mystery(self, question: str, raised_at_sec: float = 0.0):
        """Record an unresolved question raised by the dialogue."""
        self.unresolved_mysteries.append({
            "question": question,
            "raised_at_sec": raised_at_sec,
            "resolved": False,
            "resolution": "",
        })

    def resolve_mystery(self, question_substring: str, resolution: str):
        """Mark a mystery as resolved when new evidence answers it."""
        for m in self.unresolved_mysteries:
            if not m["resolved"] and question_substring.lower() in m["question"].lower():
                m["resolved"] = True
                m["resolution"] = resolution
                break

    def confirm_claim(self, claim_index: int, confirming_evidence_ids: List[int]):
        """
        Promote a character claim to confirmed fact when new dialogue evidence supports it.
        The claim remains in character_claims (with confirmed=True) AND is added to confirmed_events.
        """
        if 0 <= claim_index < len(self.character_claims):
            claim_entry = self.character_claims[claim_index]
            claim_entry["confirmed"] = True
            self.add_source_fact(
                fact=f"{claim_entry['claimant']} claimed: {claim_entry['claim']} — CONFIRMED",
                evidence_ids=confirming_evidence_ids,
                timestamp_sec=claim_entry["timestamp_sec"],
            )

    # ─────────────────────────────────────────────────────────────────────
    # NARRATION STATE MUTATIONS (from generated recap)
    # ─────────────────────────────────────────────────────────────────────

    def record_narration(self, block_index: int, narrated_text: str,
                         characters_mentioned: List[str] = None,
                         event_indices_covered: List[int] = None):
        """
        Track what the recap has explained. This is separate from source facts.
        Narration state tells us what the viewer already knows.
        """
        self.narrated_events.append(narrated_text)
        self.narrative_coverage[block_index] = narrated_text
        if characters_mentioned:
            self.narrated_characters.update(characters_mentioned)
        if event_indices_covered:
            self.covered_event_indices.update(event_indices_covered)

    # ─────────────────────────────────────────────────────────────────────
    # QUERY METHODS
    # ─────────────────────────────────────────────────────────────────────

    def get_unconfirmed_claims(self) -> List[dict]:
        """Return all character claims not yet confirmed by evidence."""
        return [c for c in self.character_claims if not c["confirmed"]]

    def get_open_mysteries(self) -> List[dict]:
        """Return all unresolved mysteries."""
        return [m for m in self.unresolved_mysteries if not m["resolved"]]

    def get_uncovered_events(self) -> List[dict]:
        """Return confirmed events not yet narrated in the recap."""
        return [
            e for i, e in enumerate(self.confirmed_events)
            if i not in self.covered_event_indices
        ]

    def is_fact_confirmed(self, fact_substring: str) -> bool:
        """Check if a fact is confirmed by source evidence."""
        lower_sub = fact_substring.lower()
        return any(lower_sub in e["fact"].lower() for e in self.confirmed_events)

    # ─────────────────────────────────────────────────────────────────────
    # PROMPT FORMATTING (compact, token-budgeted)
    # ─────────────────────────────────────────────────────────────────────

    def format_source_state_for_prompt(self, max_tokens: int = 250) -> str:
        """
        Compact representation of SOURCE story state for prompt injection.
        This is what the movie actually establishes — not what the recap has said.
        Budget: ~250 tokens.
        """
        lines = ["SOURCE STORY STATE (from dialogue evidence):"]

        # Characters (top 8)
        if self.characters:
            char_strs = []
            for name, info in list(self.characters.items())[:8]:
                role = info.get("role", "")
                rels = info.get("relationships", [])
                parts = [f"{name}: {role}"] if role else [name]
                if rels:
                    parts.append(f"({', '.join(rels[:2])})")
                char_strs.append(" ".join(parts))
            lines.append("Characters: " + "; ".join(char_strs))

        # Confirmed facts (last 5)
        if self.confirmed_events:
            facts = [e["fact"] for e in self.confirmed_events[-5:]]
            lines.append("Confirmed Facts: " + " | ".join(facts))

        # Unconfirmed claims (last 4)
        unconfirmed = self.get_unconfirmed_claims()
        if unconfirmed:
            claims = [f"{c['claimant']} claims: {c['claim']}" for c in unconfirmed[-4:]]
            lines.append("Unproven Claims: " + " | ".join(claims))

        # Open mysteries (last 3)
        open_m = self.get_open_mysteries()
        if open_m:
            lines.append("Open Mysteries: " + " | ".join(m["question"] for m in open_m[-3:]))

        # Evidence (last 3)
        if self.evidence_items:
            lines.append("Evidence: " + " | ".join(e["description"] for e in self.evidence_items[-3:]))

        return "\n".join(lines)

    def format_narration_state_for_prompt(self) -> str:
        """
        Compact representation of what the recap has already covered.
        Used to avoid repeating information and ensure continuity.
        Budget: ~100 tokens.
        """
        lines = ["NARRATION STATE (what the viewer already knows):"]

        if self.narrated_characters:
            lines.append("Introduced: " + ", ".join(sorted(self.narrated_characters)[:10]))

        # Last 2 block summaries
        if self.narrative_coverage:
            recent = sorted(self.narrative_coverage.items())[-2:]
            for block_idx, summary in recent:
                lines.append(f"Block {block_idx}: {summary[:120]}")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the full evidence store for checkpointing to disk."""
        return {
            "movie_title": self.movie_title,
            "source_state": {
                "characters": self.characters,
                "confirmed_events": self.confirmed_events,
                "character_claims": self.character_claims,
                "evidence_items": self.evidence_items,
                "unresolved_mysteries": self.unresolved_mysteries,
            },
            "narration_state": {
                "narrated_events": self.narrated_events,
                "narrated_characters": sorted(self.narrated_characters),
                "narrative_coverage": self.narrative_coverage,
                "covered_event_indices": sorted(self.covered_event_indices),
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceStore":
        """Restore an evidence store from a checkpoint dict."""
        store = cls(data.get("movie_title", ""))
        src = data.get("source_state", {})
        store.characters = src.get("characters", {})
        store.confirmed_events = src.get("confirmed_events", [])
        store.character_claims = src.get("character_claims", [])
        store.evidence_items = src.get("evidence_items", [])
        store.unresolved_mysteries = src.get("unresolved_mysteries", [])

        nar = data.get("narration_state", {})
        store.narrated_events = nar.get("narrated_events", [])
        store.narrated_characters = set(nar.get("narrated_characters", []))
        store.narrative_coverage = {
            int(k): v for k, v in nar.get("narrative_coverage", {}).items()
        }
        store.covered_event_indices = set(nar.get("covered_event_indices", []))
        return store

