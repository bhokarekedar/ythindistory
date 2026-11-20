"""Unit tests for combined script + YouTube metadata schema.

Verifies:
1. Valid sample file passes validation.
2. Missing 'youtube' key fails with validation error.
3. Description without '{{CHAPTERS}}' fails.
4. Tags over 500 characters fails.
5. Title over 100 characters fails.
6. Chapters always start with '00:00 Intro' and use displayed title text.
7. Rendering output / timeline generation does not change when the 'youtube' object is edited.
"""

import copy
import json
import unittest
from pathlib import Path
from shadowing_pipeline.core.audio_provider import AudioProvider
from shadowing_pipeline.core.exporters import (
    build_chapters_list,
    export_chapters_txt,
    export_youtube_metadata,
)
from shadowing_pipeline.core.schema import (
    parse_and_validate_script,
    validate_script_full,
    validate_youtube_metadata,
)
from shadowing_pipeline.core.timeline import TimelineBuilder


SAMPLE_VALID_SCRIPT = {
    "title": "Job Interview English - Shadowing 01",
    "youtube": {
        "title": "Job Interview English Shadowing Practice | Speak Along",
        "title_alternatives": [
            "Answer Interview Questions in English | Shadowing Practice",
            "Speak Confidently in Job Interviews | English Shadowing",
            "Can You Answer These Interview Questions in English?",
        ],
        "description": "English shadowing practice for job interviews. Listen, repeat aloud, and build confidence.\n\n{{CHAPTERS}}\n\nSubscribe for a new lesson every week.\n\n#EnglishShadowing #JobInterviewEnglish #SpeakEnglish",
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
            "common interview answers english",
        ],
        "hashtags": ["#EnglishShadowing", "#JobInterviewEnglish", "#SpeakEnglish"],
        "thumbnail_text": "SPEAK IN INTERVIEWS",
        "pinned_comment": "If you finished the lesson, comment: \"I'm ready for my interview.\"",
        "playlist": "English Shadowing Practice: Work and Career",
        "category": "Education",
        "language": "en",
        "made_for_kids": False,
    },
    "segments": [
        {"id": "hook_01", "type": "narration", "text": "Have you ever known the perfect answer, but forgotten it?"},
        {"id": "p1_title", "type": "section_title", "chapter": True, "text": "Part 1: Greetings and Small Talk", "spoken": "Part one. Greetings and small talk."},
        {"id": "p1_01", "type": "shadow", "text": "Hello, it's nice to meet you."},
        {"id": "p2_title", "type": "section_title", "chapter": True, "text": "Part 2: Talking About Your Experience", "spoken": "Part two. Talking about your experience."},
        {"id": "p2_01", "type": "shadow", "text": "I've worked in customer service for three years."},
        {"id": "outro_01", "type": "narration", "text": "Excellent work. Keep practicing English."},
    ],
}


class MockAudioProvider(AudioProvider):
    def __init__(self):
        pass

    def get_audio_and_transcription(self, text, voice="af_heart", speed=0.85):
        words = text.split()
        dur = max(1.5, len(words) * 0.35)
        timings = [{"word": w, "start": 0.0, "end": 0.5} for w in words]
        return f"/mock/{voice}.wav", timings, dur


class TestYouTubeMetadataSchema(unittest.TestCase):
    def setUp(self):
        self.mock_audio = MockAudioProvider()
        self.builder = TimelineBuilder(self.mock_audio)

    def test_valid_file_passes(self):
        """Valid combined script + YouTube metadata passes cleanly."""
        script, errors, warnings = validate_script_full(SAMPLE_VALID_SCRIPT)
        self.assertEqual(len(errors), 0)
        self.assertIsNotNone(script.youtube)
        self.assertEqual(script.youtube.title, "Job Interview English Shadowing Practice | Speak Along")
        self.assertEqual(len(script.youtube.title_alternatives), 3)

    def test_missing_youtube_fails(self):
        """Missing top-level 'youtube' key must fail validation."""
        bad_data = copy.deepcopy(SAMPLE_VALID_SCRIPT)
        del bad_data["youtube"]
        with self.assertRaises(ValueError) as ctx:
            validate_script_full(bad_data)
        self.assertIn("Missing required top-level key 'youtube'", str(ctx.exception))

    def test_description_without_chapters_placeholder_fails(self):
        """Description missing {{CHAPTERS}} must fail validation."""
        bad_data = copy.deepcopy(SAMPLE_VALID_SCRIPT)
        bad_data["youtube"]["description"] = "No chapters placeholder here at all."
        with self.assertRaises(ValueError) as ctx:
            validate_script_full(bad_data)
        self.assertIn("must contain the literal placeholder '{{CHAPTERS}}'", str(ctx.exception))

    def test_description_with_chapters_not_on_own_line_fails(self):
        """Placeholder {{CHAPTERS}} embedded inside other text fails (must be on its own line)."""
        bad_data = copy.deepcopy(SAMPLE_VALID_SCRIPT)
        bad_data["youtube"]["description"] = "Here are chapters {{CHAPTERS}} in one sentence."
        with self.assertRaises(ValueError) as ctx:
            validate_script_full(bad_data)
        self.assertIn("must be on its own line", str(ctx.exception))

    def test_tags_over_500_chars_fails(self):
        """Tags list exceeding 500 characters total must fail validation."""
        bad_data = copy.deepcopy(SAMPLE_VALID_SCRIPT)
        # Create 16 long tags that exceed 500 chars total
        bad_data["youtube"]["tags"] = [f"very long english shadowing tag number {i:02d} for learners practicing fluency" for i in range(16)]
        total_len = len(",".join(bad_data["youtube"]["tags"]))
        self.assertGreater(total_len, 500)
        with self.assertRaises(ValueError) as ctx:
            validate_script_full(bad_data)
        self.assertIn("exceeds 500 characters", str(ctx.exception))

    def test_title_over_100_chars_fails(self):
        """YouTube title over 100 characters must fail validation."""
        bad_data = copy.deepcopy(SAMPLE_VALID_SCRIPT)
        bad_data["youtube"]["title"] = "A" * 101
        with self.assertRaises(ValueError) as ctx:
            validate_script_full(bad_data)
        self.assertIn("youtube.title must be at most 100 characters", str(ctx.exception))

    def test_chapters_always_start_with_0000_intro_and_use_displayed_titles(self):
        """Chapters must always prepend '00:00 Intro' and use the displayed title text, not spoken."""
        script = parse_and_validate_script(SAMPLE_VALID_SCRIPT)
        events = self.builder.build_timeline(script)
        total_duration = events[-1].end_time

        formatted_chapters, warnings = build_chapters_list(self.builder.chapters, total_duration=total_duration)

        # 1. First chapter must ALWAYS be 00:00 Intro
        self.assertEqual(formatted_chapters[0]["time"], "00:00")
        self.assertEqual(formatted_chapters[0]["title"], "Intro")

        # 2. Section chapters must use displayed text, NOT spoken text
        titles = [ch["title"] for ch in formatted_chapters]
        self.assertIn("Part 1: Greetings and Small Talk", titles)
        self.assertIn("Part 2: Talking About Your Experience", titles)
        self.assertNotIn("Part one. Greetings and small talk.", titles)

        # 3. Formatted chapters.txt starts with '00:00 Intro'
        chapters_txt = export_chapters_txt(formatted_chapters, "/tmp/test_chapters.txt")
        self.assertTrue(chapters_txt.startswith("00:00 Intro"))

    def test_rendering_timeline_output_does_not_change_when_youtube_is_edited(self):
        """The timeline builder and video renderer must ignore the 'youtube' object completely."""
        script1 = parse_and_validate_script(SAMPLE_VALID_SCRIPT)
        events1 = self.builder.build_timeline(script1)

        modified_script = copy.deepcopy(SAMPLE_VALID_SCRIPT)
        modified_script["youtube"]["title"] = "Completely Different Title Here"
        modified_script["youtube"]["description"] = "Different description.\n\n{{CHAPTERS}}\n\nMore text."
        modified_script["youtube"]["tags"] = [f"different tag {i:02d}" for i in range(16)]
        modified_script["youtube"]["playlist"] = "Different Playlist"

        script2 = parse_and_validate_script(modified_script)
        events2 = self.builder.build_timeline(script2)

        # Timelines must be identical
        self.assertEqual(len(events1), len(events2))
        for e1, e2 in zip(events1, events2):
            self.assertEqual(e1.start_time, e2.start_time)
            self.assertEqual(e1.end_time, e2.end_time)
            self.assertEqual(e1.text, e2.text)
            self.assertEqual(e1.audio_path, e2.audio_path)


if __name__ == "__main__":
    unittest.main()
