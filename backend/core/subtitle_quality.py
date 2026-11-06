"""
Subtitle Quality Report.

Generates a comprehensive quality analysis of extracted subtitles BEFORE allowing
the movie into the generation stage. Uses multiple signals rather than a single
cue-count threshold to determine subtitle fitness.

A 120-minute movie with 100 subtitle cues gets flagged for review even if it passes
the current 30-cue minimum. But sparse subtitles are NOT automatically rejected —
some movies genuinely have long visual sequences.
"""

import re
from typing import List, Dict


class SubtitleQualityReport:
    """
    Analyzes extracted subtitle dialogues and produces a structured quality report.
    This report is consumed by the engine to decide whether to proceed, flag for review,
    or reject the subtitle track entirely.
    """

    # Patterns that indicate non-dialogue content
    NON_DIALOGUE_PATTERNS = [
        r'^\[.*\]$',                          # [music], [applause], [narrator]
        r'^\(.*\)$',                          # (sighs), (door slams)
        r'^♪',                                # ♪ song lyrics
        r'^#',                                # # song lyrics (some formats)
        r'^\*.*\*$',                          # *sound effects*
        r'(?i)^\s*♪\s*$',                     # lone music note
        r'(?i)^[\s♪♫#]+$',                    # only music symbols
        r'(?i)^\[?(music|applause|laughter|cheering|sobbing|gasps?|sighs?|grunts?|screams?|laughing|crying|singing)\]?$',
        r'(?i)^\(?(background\s+noise|static|silence|inaudible|indistinct)\)?$',
    ]

    @classmethod
    def analyze(cls, dialogues: List[dict], total_runtime_sec: float) -> dict:
        """
        Analyze subtitle quality across multiple dimensions.

        Args:
            dialogues: List of parsed subtitle dicts with 'start', 'end', 'text', 'id'.
            total_runtime_sec: Total movie runtime in seconds.

        Returns:
            Comprehensive quality report dict.
        """
        total_cues = len(dialogues)
        runtime_minutes = max(1.0, total_runtime_sec / 60.0)

        if total_cues == 0:
            return cls._empty_report(total_runtime_sec)

        # ── 1. Basic Counts ──
        all_texts = [d.get("text", "").strip() for d in dialogues]
        total_words = sum(len(t.split()) for t in all_texts)
        cues_per_minute = round(total_cues / runtime_minutes, 2)

        # ── 2. Empty or Unusually Short Cues ──
        empty_or_short = sum(1 for t in all_texts if len(t.split()) < 2)
        empty_or_short_pct = round(100.0 * empty_or_short / total_cues, 2) if total_cues else 0.0

        # ── 3. Duplicate Cue Detection ──
        duplicate_count = 0
        for i in range(1, len(all_texts)):
            if all_texts[i].lower() == all_texts[i - 1].lower() and all_texts[i]:
                duplicate_count += 1
        duplicate_pct = round(100.0 * duplicate_count / total_cues, 2) if total_cues else 0.0

        # ── 4. Invalid or Overlapping Timestamps ──
        invalid_timestamps = 0
        for i, d in enumerate(dialogues):
            st = float(d.get("start", 0))
            et = float(d.get("end", st))
            if et < st:
                invalid_timestamps += 1
            elif et - st > 30.0:
                # Suspiciously long single cue (>30s) — likely encoding error
                invalid_timestamps += 1
            if i > 0:
                prev_end = float(dialogues[i - 1].get("end", 0))
                if st < prev_end - 0.1:
                    # Overlapping timestamps (allowing 100ms tolerance)
                    invalid_timestamps += 1

        # ── 5. Long Silence Gaps (>5 minutes without dialogue) ──
        long_silence_gaps = []
        GAP_THRESHOLD_SEC = 300.0  # 5 minutes
        if total_cues >= 2:
            for i in range(1, total_cues):
                prev_end = float(dialogues[i - 1].get("end", 0))
                curr_start = float(dialogues[i].get("start", 0))
                gap = curr_start - prev_end
                if gap >= GAP_THRESHOLD_SEC:
                    long_silence_gaps.append({
                        "gap_start_sec": round(prev_end, 1),
                        "gap_end_sec": round(curr_start, 1),
                        "gap_duration_sec": round(gap, 1),
                        "after_cue_id": dialogues[i - 1].get("id", i),
                    })
            # Also check gap at the very end of the movie
            last_end = float(dialogues[-1].get("end", 0))
            if total_runtime_sec - last_end >= GAP_THRESHOLD_SEC:
                long_silence_gaps.append({
                    "gap_start_sec": round(last_end, 1),
                    "gap_end_sec": round(total_runtime_sec, 1),
                    "gap_duration_sec": round(total_runtime_sec - last_end, 1),
                    "after_cue_id": dialogues[-1].get("id", total_cues),
                })

        # ── 6. Non-Dialogue Content ──
        non_dialogue_count = 0
        for t in all_texts:
            if any(re.match(p, t.strip()) for p in cls.NON_DIALOGUE_PATTERNS):
                non_dialogue_count += 1
        non_dialogue_pct = round(100.0 * non_dialogue_count / total_cues, 2) if total_cues else 0.0

        # ── 7. Coverage Distribution (quartile analysis) ──
        quartile_dur = total_runtime_sec / 4.0
        coverage = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
        for d in dialogues:
            st = float(d.get("start", 0))
            if st < quartile_dur:
                coverage["Q1"] += 1
            elif st < 2 * quartile_dur:
                coverage["Q2"] += 1
            elif st < 3 * quartile_dur:
                coverage["Q3"] += 1
            else:
                coverage["Q4"] += 1

        coverage_pcts = {}
        for q, count in coverage.items():
            coverage_pcts[q] = round(100.0 * count / total_cues, 1) if total_cues else 0.0

        # ── 8. Quality Grading ──
        warnings = []
        quality_grade, recommendation = cls._compute_grade(
            total_cues=total_cues,
            cues_per_minute=cues_per_minute,
            runtime_minutes=runtime_minutes,
            empty_or_short_pct=empty_or_short_pct,
            duplicate_pct=duplicate_pct,
            non_dialogue_pct=non_dialogue_pct,
            invalid_timestamps=invalid_timestamps,
            long_silence_gaps=long_silence_gaps,
            coverage_pcts=coverage_pcts,
            total_words=total_words,
            warnings=warnings,
        )

        return {
            "total_cues": total_cues,
            "total_words": total_words,
            "cues_per_minute": cues_per_minute,
            "empty_or_short_pct": empty_or_short_pct,
            "duplicate_pct": duplicate_pct,
            "invalid_timestamp_count": invalid_timestamps,
            "long_silence_gaps": long_silence_gaps,
            "non_dialogue_pct": non_dialogue_pct,
            "coverage_distribution": coverage,
            "coverage_distribution_pct": coverage_pcts,
            "quality_grade": quality_grade,
            "warnings": warnings,
            "recommendation": recommendation,
            "runtime_minutes": round(runtime_minutes, 1),
        }

    @classmethod
    def _compute_grade(cls, *, total_cues, cues_per_minute, runtime_minutes,
                       empty_or_short_pct, duplicate_pct, non_dialogue_pct,
                       invalid_timestamps, long_silence_gaps, coverage_pcts,
                       total_words, warnings) -> tuple:
        """
        Multi-signal quality grading. Returns (quality_grade, recommendation).

        Does NOT automatically reject sparse subtitles — uses combined signals.
        """
        # Scoring system: start at 100, deduct for issues
        score = 100.0

        # Cue density checks
        if cues_per_minute < 1.0:
            warnings.append(
                f"Very sparse subtitles: {cues_per_minute:.1f} cues/min "
                f"(expected ≥3 for dialogue-heavy films)."
            )
            score -= 20
        elif cues_per_minute < 3.0:
            warnings.append(
                f"Below-average subtitle density: {cues_per_minute:.1f} cues/min."
            )
            score -= 10

        # Total cue check relative to runtime
        expected_min_cues = max(80, runtime_minutes * 2.5)
        if total_cues < expected_min_cues:
            warnings.append(
                f"Only {total_cues} cues for a {runtime_minutes:.0f}-minute movie "
                f"(expected ≥{int(expected_min_cues)})."
            )
            score -= 15

        # Word density
        words_per_cue = total_words / max(1, total_cues)
        if words_per_cue < 3.0:
            warnings.append(
                f"Very short cues: avg {words_per_cue:.1f} words/cue."
            )
            score -= 10

        # Empty/short ratio
        if empty_or_short_pct > 30.0:
            warnings.append(f"{empty_or_short_pct:.1f}% of cues have fewer than 2 words.")
            score -= 15
        elif empty_or_short_pct > 15.0:
            warnings.append(f"{empty_or_short_pct:.1f}% of cues are very short.")
            score -= 5

        # Duplicate ratio
        if duplicate_pct > 10.0:
            warnings.append(f"{duplicate_pct:.1f}% of cues are duplicates of adjacent cues.")
            score -= 10
        elif duplicate_pct > 5.0:
            score -= 5

        # Non-dialogue content
        if non_dialogue_pct > 40.0:
            warnings.append(
                f"{non_dialogue_pct:.1f}% of cues are non-dialogue "
                f"(music descriptions, sound effects)."
            )
            score -= 20
        elif non_dialogue_pct > 20.0:
            warnings.append(f"{non_dialogue_pct:.1f}% of cues appear to be non-dialogue content.")
            score -= 10

        # Invalid timestamps
        if invalid_timestamps > total_cues * 0.1:
            warnings.append(f"{invalid_timestamps} cues have invalid or overlapping timestamps.")
            score -= 15
        elif invalid_timestamps > 5:
            score -= 5

        # Long silence gaps
        if len(long_silence_gaps) >= 3:
            total_gap = sum(g["gap_duration_sec"] for g in long_silence_gaps)
            warnings.append(
                f"{len(long_silence_gaps)} gaps longer than 5 minutes "
                f"(total silent time: {total_gap/60:.1f} min)."
            )
            score -= 10

        # Coverage distribution — flag extreme imbalance
        pct_vals = list(coverage_pcts.values())
        if pct_vals:
            min_q = min(pct_vals)
            max_q = max(pct_vals)
            if min_q < 10.0 and max_q > 40.0:
                warnings.append(
                    f"Uneven subtitle distribution: "
                    f"min quartile {min_q:.1f}%, max quartile {max_q:.1f}%."
                )
                score -= 10

        # Grade assignment
        if score >= 80:
            quality_grade = "good"
            recommendation = "proceed"
        elif score >= 60:
            quality_grade = "acceptable"
            recommendation = "proceed"
        elif score >= 40:
            quality_grade = "sparse"
            recommendation = "review"
        else:
            quality_grade = "poor"
            recommendation = "review"

        return quality_grade, recommendation

    @classmethod
    def _empty_report(cls, total_runtime_sec: float) -> dict:
        """Return a report for an empty subtitle track."""
        return {
            "total_cues": 0,
            "total_words": 0,
            "cues_per_minute": 0.0,
            "empty_or_short_pct": 0.0,
            "duplicate_pct": 0.0,
            "invalid_timestamp_count": 0,
            "long_silence_gaps": [],
            "non_dialogue_pct": 0.0,
            "coverage_distribution": {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0},
            "coverage_distribution_pct": {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0},
            "quality_grade": "poor",
            "warnings": ["No subtitle cues found."],
            "recommendation": "reject",
            "runtime_minutes": round(total_runtime_sec / 60.0, 1),
        }

    @classmethod
    def format_report(cls, report: dict) -> str:
        """Format a quality report as a human-readable summary for console output."""
        lines = [
            f"  [SubtitleQuality] 📊 Subtitle Quality Report:",
            f"    Cues: {report['total_cues']} ({report['cues_per_minute']} cues/min) | "
            f"Words: {report['total_words']} | Runtime: {report['runtime_minutes']}m",
            f"    Empty/Short: {report['empty_or_short_pct']}% | "
            f"Duplicates: {report['duplicate_pct']}% | "
            f"Non-Dialogue: {report['non_dialogue_pct']}%",
            f"    Invalid Timestamps: {report['invalid_timestamp_count']} | "
            f"Silence Gaps (>5m): {len(report['long_silence_gaps'])}",
            f"    Coverage: {report['coverage_distribution_pct']}",
            f"    Grade: {report['quality_grade'].upper()} | "
            f"Recommendation: {report['recommendation'].upper()}",
        ]
        if report["warnings"]:
            for w in report["warnings"]:
                lines.append(f"    ⚠️ {w}")
        return "\n".join(lines)

