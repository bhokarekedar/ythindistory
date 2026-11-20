"""Unit tests for English Shadowing Pipeline Segment Behavior Specification.

Tests:
- shadow with repeat 1, 2, and 3
- shadow_pair with 2 rounds
- narration producing no silence
- free_answer using its own pause rule
- ignored pause_seconds
- validation error aggregation and warnings
"""

import unittest
from pathlib import Path
from typing import Dict, List, Tuple

from shadowing_pipeline.core.audio_provider import AudioProvider
from shadowing_pipeline.core.schema import (
    ShadowScript,
    parse_and_validate_script,
    validate_script_full,
)
from shadowing_pipeline.core.timeline import TimelineBuilder, TimelineEvent


class MockAudioProvider(AudioProvider):
    """Fast mock audio provider that produces deterministic durations."""

    def __init__(self, char_rate: float = 0.05):
        # Do not initialize parent disk directories
        self.char_rate = char_rate

    def get_audio_and_transcription(
        self, text: str, voice: str = "af_heart", speed: float = 0.92
    ) -> Tuple[str, List[Dict], float]:
        # Deterministic duration based on word count
        words = text.split()
        dur = max(1.5, len(words) * 0.35)
        timings = []
        curr = 0.0
        w_dur = dur / max(1, len(words))
        for w in words:
            timings.append({"word": w, "start": round(curr, 3), "end": round(curr + w_dur, 3)})
            curr += w_dur
        return f"/mock/audio/{voice}_{speed:.2f}.wav", timings, round(dur, 3)


class TestTimelineSpec(unittest.TestCase):
    def setUp(self):
        self.mock_audio = MockAudioProvider()
        self.config = {
            "timing": {
                "default_repeat": 2,
                "repeat_speed_factors": [1.0, 0.92],
                "narration_gap_seconds": 0.4,
                "section_gap_seconds": 0.8,
                "shadow": {
                    "pause_factor": 1.2,
                    "min_pause_seconds": 2.0,
                    "max_pause_seconds": 12.0,
                },
                "free_answer": {
                    "pause_factor": 1.6,
                    "min_pause_seconds": 4.0,
                    "max_pause_seconds": 15.0,
                },
            },
            "voices": {
                "teacher": {"voice_id": "af_heart", "speed": 0.92},
                "speaker_a": {"voice_id": "af_heart", "speed": 0.92},
                "speaker_b": {"voice_id": "am_adam", "speed": 0.92},
            },
            "pronunciation": {
                "Wi-Fi": "why fye",
                "SIM": "sim",
            },
        }
        self.sample_youtube = {
            "title": "Job Interview English Shadowing Practice | Speak Along",
            "title_alternatives": [
                "Answer Interview Questions in English | Shadowing Practice",
                "Speak Confidently in Job Interviews | English Shadowing",
                "Can You Answer These Interview Questions in English?",
            ],
            "description": "English shadowing practice for job interviews.\n\n{{CHAPTERS}}\n\nSubscribe for more.",
            "tags": [
                "english shadowing practice",
                "job interview english",
                "english interview questions",
                "english sentences for job interview",
                "shadowing english",
                "speak english confidently",
                "english speaking practice",
                "learn english",
                "english conversation practice",
                "interview english phrases",
                "business english",
                "english for work",
                "english listening and speaking",
                "repeat after me english",
                "english fluency practice",
            ],
            "hashtags": ["#EnglishShadowing", "#JobInterviewEnglish", "#SpeakEnglish"],
            "thumbnail_text": "SPEAK IN INTERVIEWS",
            "pinned_comment": "Comment below!",
            "playlist": "Work English",
            "category": "Education",
            "language": "en",
            "made_for_kids": False,
        }
        self.builder = TimelineBuilder(self.mock_audio, config=self.config)

    def _with_youtube(self, d: dict) -> dict:
        merged = dict(d)
        if "youtube" not in merged:
            merged["youtube"] = self.sample_youtube
        return merged

    def test_shadow_repeat_1_2_3(self):
        """Verify shadow segment with repeat 1, 2, and 3."""
        # Repeat = 1
        script_r1 = parse_and_validate_script(self._with_youtube({
            "title": "Test R1",
            "segments": [{"type": "shadow", "text": "This is a test sentence.", "repeat": 1}],
        }), self.config)
        events_r1 = self.builder.build_timeline(script_r1)
        self.assertEqual(len(events_r1), 2)
        self.assertEqual(events_r1[0].event_type, "SPEECH")
        self.assertEqual(events_r1[1].event_type, "SILENCE")
        self.assertEqual(events_r1[0].repeat_index, 1)
        self.assertEqual(events_r1[1].repeat_index, 1)

        # Expected pause = audio_dur + buffer (calculated from sentence length)
        expected_pause_r1 = self.builder.calc_shadow_pause(events_r1[0].duration, "This is a test sentence.")
        self.assertAlmostEqual(events_r1[1].duration, expected_pause_r1, places=2)
        # Verify buffer is in the 2-3s range for shorter sentence
        buffer_val = events_r1[1].duration - events_r1[0].duration
        self.assertTrue(2.0 <= buffer_val <= 3.0)

        # Repeat = 2 (default)
        script_r2 = parse_and_validate_script(self._with_youtube({
            "title": "Test R2",
            "segments": [{"type": "shadow", "text": "This is a test sentence.", "repeat": 2}],
        }), self.config)
        events_r2 = self.builder.build_timeline(script_r2)
        self.assertEqual(len(events_r2), 4)
        self.assertEqual([e.event_type for e in events_r2], ["SPEECH", "SILENCE", "SPEECH", "SILENCE"])
        self.assertEqual(events_r2[0].repeat_index, 1)
        self.assertEqual(events_r2[1].repeat_index, 1)
        self.assertEqual(events_r2[2].repeat_index, 2)
        self.assertEqual(events_r2[3].repeat_index, 2)
        # Check UI badge text
        self.assertIn("1/2", events_r2[0].badge_text)
        self.assertIn("1/2", events_r2[1].badge_text)
        self.assertIn("2/2", events_r2[2].badge_text)
        self.assertIn("2/2", events_r2[3].badge_text)

        # Repeat = 3
        script_r3 = parse_and_validate_script(self._with_youtube({
            "title": "Test R3",
            "segments": [{"type": "shadow", "text": "This is a test sentence.", "repeat": 3}],
        }), self.config)
        events_r3 = self.builder.build_timeline(script_r3)
        self.assertEqual(len(events_r3), 6)
        self.assertEqual(
            [e.event_type for e in events_r3],
            ["SPEECH", "SILENCE", "SPEECH", "SILENCE", "SPEECH", "SILENCE"],
        )
        self.assertEqual(events_r3[4].repeat_index, 3)
        self.assertEqual(events_r3[5].repeat_index, 3)

    def test_shadow_pair_two_rounds(self):
        """Verify shadow_pair practices each line N times (speech + silence) before moving to next line."""
        script_pair = parse_and_validate_script(self._with_youtube({
            "title": "Test Shadow Pair",
            "segments": [
                {
                    "type": "shadow_pair",
                    "id": "pair_01",
                    "repeat": 2,
                    "lines": [
                        {"text": "Where is the departure gate?", "voice": "speaker_a"},
                        {"text": "It is down the hall to your right.", "voice": "speaker_b"},
                    ],
                }
            ],
        }), self.config)
        events = self.builder.build_timeline(script_pair)

        # 2 lines * 2 (speech + silence) * 2 rounds = 8 events total
        self.assertEqual(len(events), 8)

        # Line 1 practiced twice: Take 1 (Listen & Read -> Your Turn) -> Take 2 (Listen & Read -> Your Turn)
        self.assertEqual(events[0].event_type, "SPEECH")
        self.assertEqual(events[0].text, "Where is the departure gate?")
        self.assertEqual(events[0].repeat_index, 1)
        self.assertEqual(events[1].event_type, "SILENCE")
        self.assertEqual(events[1].repeat_index, 1)

        self.assertEqual(events[2].event_type, "SPEECH")
        self.assertEqual(events[2].text, "Where is the departure gate?")
        self.assertEqual(events[2].repeat_index, 2)
        self.assertEqual(events[3].event_type, "SILENCE")
        self.assertEqual(events[3].repeat_index, 2)

        # Line 2 practiced twice: Take 1 (Listen & Read -> Your Turn) -> Take 2 (Listen & Read -> Your Turn)
        self.assertEqual(events[4].event_type, "SPEECH")
        self.assertEqual(events[4].text, "It is down the hall to your right.")
        self.assertEqual(events[4].repeat_index, 1)
        self.assertEqual(events[5].event_type, "SILENCE")
        self.assertEqual(events[5].repeat_index, 1)

        self.assertEqual(events[6].event_type, "SPEECH")
        self.assertEqual(events[6].text, "It is down the hall to your right.")
        self.assertEqual(events[6].repeat_index, 2)
        self.assertEqual(events[7].event_type, "SILENCE")
        self.assertEqual(events[7].repeat_index, 2)

    def test_narration_produces_no_silence(self):
        """Verify narration creates only SPEECH events and zero learner silence pauses."""
        script_narr = parse_and_validate_script(self._with_youtube({
            "title": "Test Narration",
            "segments": [
                {"type": "narration", "text": "Welcome to our practice session today."},
                {"type": "narration", "text": "Remember to speak aloud after each sentence."},
            ],
        }), self.config)
        events = self.builder.build_timeline(script_narr)

        # Must have exactly 2 speech events and 0 silence events
        self.assertEqual(len(events), 2)
        for e in events:
            self.assertEqual(e.event_type, "SPEECH")
            self.assertEqual(e.sub_type, "narration")
            self.assertIsNotNone(e.audio_path)

        # Narration gap is respected between events
        # Event 1 end_time + narration_gap <= Event 2 start_time
        gap = round(events[1].start_time - events[0].end_time, 2)
        self.assertAlmostEqual(gap, 0.4, places=2)

    def test_free_answer_own_pause_rule(self):
        """Verify free_answer uses free_answer pause rule (1.6x factor, min 4s, max 15s) and does not repeat."""
        script_fa = parse_and_validate_script(self._with_youtube({
            "title": "Test Free Answer",
            "segments": [
                {"type": "free_answer", "text": "What do you usually like to eat for breakfast?"}
            ],
        }), self.config)
        events = self.builder.build_timeline(script_fa)

        # Exactly 1 SPEECH (question) and 1 SILENCE (answer)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_type, "SPEECH")
        self.assertEqual(events[1].event_type, "SILENCE")
        self.assertEqual(events[1].sub_type, "free_answer_silence")

        q_dur = events[0].duration
        expected_pause = round(min(max(q_dur * 1.6, 4.0), 15.0), 3)
        self.assertAlmostEqual(events[1].duration, expected_pause, places=2)

    def test_ignored_pause_seconds(self):
        """Verify pause_seconds in script is ignored in favor of dynamically calculated pauses, and warns."""
        raw_data = self._with_youtube({
            "title": "Test Ignored Pauses",
            "segments": [
                {
                    "type": "shadow",
                    "text": "Excuse me, where is the check-in desk?",
                    "pause_seconds": 99.0,  # Should be ignored!
                }
            ],
        })
        script, errors, warnings = validate_script_full(raw_data, self.config)
        self.assertEqual(len(errors), 0)
        # Verify warning was recorded
        self.assertTrue(any("pause_seconds" in w for w in warnings))

        events = self.builder.build_timeline(script)
        # Verify pause is NOT 99.0s
        silence_ev = events[1]
        self.assertNotEqual(silence_ev.duration, 99.0)
        expected_calc = self.builder.calc_shadow_pause(events[0].duration, "Excuse me, where is the check-in desk?")
        self.assertAlmostEqual(silence_ev.duration, expected_calc, places=2)

    def test_validation_errors_aggregated(self):
        """Verify that all schema errors are collected and reported together."""
        invalid_data = {
            "title": "Invalid Script",
            "segments": [
                {"type": "unknown_type", "id": "dup_01", "text": "Valid text."},
                {"type": "shadow", "id": "dup_01", "text": ""},  # Duplicate ID & Empty text
                {"type": "shadow_pair", "lines": [{"text": "Only one line"}]},  # < 2 lines
                {"type": "narration", "text": "Valid", "voice": "alien_voice"},  # Unknown voice
            ],
        }
        with self.assertRaises(ValueError) as ctx:
            validate_script_full(invalid_data, self.config)

        err_msg = str(ctx.exception)
        # All errors must be present in the exception message
        self.assertIn("unknown or missing type", err_msg)
        self.assertIn("Duplicate segment id", err_msg)
        self.assertIn("empty text", err_msg)
        self.assertIn("at least 2 lines", err_msg)
        self.assertIn("unknown voice role", err_msg)


if __name__ == "__main__":
    unittest.main()

