"""Word Alignment Engine.

Aligns raw transcription word timestamps against script display tokens.
Handles punctuation, contractions (Let's, don't, I'm, we've), compound words,
and missing tokens by monotone sequence matching and interpolation.
"""

import re
from typing import Dict, List, Optional


def clean_token(token: str) -> str:
    """Removes all non-alphanumeric characters and lowercases."""
    return re.sub(r"[^a-z0-9]", "", token.lower())


def align_script_words(
    script_text: str,
    transcript_words: List[Dict],
    total_duration: float,
) -> List[Dict]:
    """Aligns script display words to transcript timestamps.

    Returns a list of dicts:
    [{"word": str, "start": float, "end": float}]
    where 'word' is the verbatim script word (preserving punctuation and casing).
    """
    script_tokens = [w for w in script_text.strip().split() if w.strip()]
    if not script_tokens:
        return []

    if not transcript_words:
        # Uniform proportional allocation as a safe fallback
        seg_dur = total_duration / len(script_tokens)
        return [
            {
                "word": tok,
                "start": round(i * seg_dur, 3),
                "end": round((i + 1) * seg_dur, 3),
            }
            for i, tok in enumerate(script_tokens)
        ]

    aligned: List[Dict] = []
    t_idx = 0
    t_len = len(transcript_words)

    for i, s_tok in enumerate(script_tokens):
        s_clean = clean_token(s_tok)
        matched_start: Optional[float] = None
        matched_end: Optional[float] = None

        # Look ahead up to 5 transcript tokens
        for probe_idx in range(t_idx, min(t_idx + 5, t_len)):
            cand_word = clean_token(transcript_words[probe_idx]["word"])

            # 1. Direct match
            if cand_word == s_clean:
                matched_start = transcript_words[probe_idx]["start"]
                matched_end = transcript_words[probe_idx]["end"]
                t_idx = probe_idx + 1
                break

            # 2. Two-token contraction/compound (e.g. "let" + "s" for "lets")
            if probe_idx + 1 < t_len:
                combo2 = clean_token(
                    transcript_words[probe_idx]["word"]
                    + transcript_words[probe_idx + 1]["word"]
                )
                if combo2 == s_clean:
                    matched_start = transcript_words[probe_idx]["start"]
                    matched_end = transcript_words[probe_idx + 1]["end"]
                    t_idx = probe_idx + 2
                    break

            # 3. Three-token compound (e.g. "could" + "n" + "t" for "couldnt")
            if probe_idx + 2 < t_len:
                combo3 = clean_token(
                    transcript_words[probe_idx]["word"]
                    + transcript_words[probe_idx + 1]["word"]
                    + transcript_words[probe_idx + 2]["word"]
                )
                if combo3 == s_clean:
                    matched_start = transcript_words[probe_idx]["start"]
                    matched_end = transcript_words[probe_idx + 2]["end"]
                    t_idx = probe_idx + 3
                    break

        aligned.append(
            {
                "word": s_tok,
                "start": matched_start,
                "end": matched_end,
            }
        )

    # Post-process: interpolate missing/unmatched tokens and ensure monotonic timestamps
    last_end = 0.0
    for i, item in enumerate(aligned):
        if item["start"] is None or item["end"] is None:
            # Look ahead for next matched token
            next_start = total_duration
            unmatched_count = 0
            for j in range(i, len(aligned)):
                if aligned[j]["start"] is not None:
                    next_start = aligned[j]["start"]
                    break
                unmatched_count += 1

            avail_span = max(0.1, next_start - last_end)
            step = avail_span / max(1, unmatched_count)
            item["start"] = round(last_end, 3)
            item["end"] = round(min(next_start, last_end + step), 3)

        # Monotonicity checks
        if item["start"] < last_end:
            item["start"] = round(last_end, 3)
        if item["end"] <= item["start"]:
            item["end"] = round(item["start"] + 0.15, 3)

        last_end = item["end"]

    return aligned

