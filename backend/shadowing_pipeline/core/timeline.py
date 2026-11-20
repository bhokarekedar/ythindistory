"""Timeline Builder for English Shadowing Pipeline.

Flattens validated script segments into an exact timeline of SPEECH and SILENCE events
implementing the complete Segment Behavior Specification:
- shadow (N repeats, calculated pause, speed factor schedules)
- shadow_pair (multi-line exchange repeated as a block)
- narration (single speech event, caption chunking for >25 words, narration gap)
- section_title (spoken override, chapter recording for chapters.txt, section gap)
- dialogue (single speech event, conversational gap)
- free_answer (single speech event, long calculated pause)

All settings, timing formulas, voice mappings, and pronunciation rules come from config.json.
"""

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shadowing_pipeline.core.audio_provider import AudioProvider
from shadowing_pipeline.core.schema import (
    DialogueSegment,
    FreeAnswerSegment,
    NarrationSegment,
    SectionTitleSegment,
    ShadowPairSegment,
    ShadowScript,
    ShadowSegment,
)
from shadowing_pipeline.core.word_aligner import align_script_words

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.json"


def load_pipeline_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Loads configuration dictionary with fallback defaults."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read config from {path}: {e}")

    # Fallback default configuration
    return {
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
            "teacher": {"voice_id": "af_heart", "speed": 0.92, "lang_code": "a"},
            "speaker_a": {"voice_id": "af_heart", "speed": 0.92, "lang_code": "a"},
            "speaker_b": {"voice_id": "am_adam", "speed": 0.92, "lang_code": "a"},
        },
        "pronunciation": {
            "Wi-Fi": "why fye",
            "SIM": "sim",
        },
    }


def apply_pronunciation(text: str, pronunciation_dict: Dict[str, str]) -> str:
    """Replaces words in text sent to TTS using whole-word regex matching."""
    if not pronunciation_dict or not text:
        return text
    result = text
    for word, replacement in pronunciation_dict.items():
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        result = pattern.sub(replacement, result)
    return result


@dataclass
class TimelineEvent:
    event_id: int
    segment_id: str
    event_type: str  # "SPEECH" | "SILENCE"
    type: str  # "speech" | "silence" (backward compatible)
    sub_type: str  # "narration", "section_title", "shadow", "shadow_silence", "dialogue", "free_answer", "free_answer_silence"
    start_time: float
    end_time: float
    duration: float
    text: str  # Displayed text
    spoken_text: str  # Text sent to TTS
    voice: str  # Role or voice id
    speed: float
    speaker: Optional[str]
    badge_text: str
    audio_path: Optional[str]
    word_timings: List[Dict[str, Any]]
    repeat_index: Optional[int] = None
    repeat_total: Optional[int] = None
    chapter: bool = False

    @property
    def start(self) -> float:
        return self.start_time

    @property
    def end(self) -> float:
        return self.end_time

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["start"] = self.start_time
        d["end"] = self.end_time
        return d


class TimelineBuilder:
    """Transforms validated scripts into chronological audio/video timeline events."""

    def __init__(
        self,
        audio_provider: AudioProvider,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.audio_provider = audio_provider
        self.config = config or load_pipeline_config()

        # Extract timing parameters
        timing = self.config.get("timing", {})
        self.default_repeat = int(timing.get("default_repeat", 2))
        self.repeat_speed_factors = timing.get("repeat_speed_factors", [1.0, 0.92])
        self.narration_gap = float(timing.get("narration_gap_seconds", 0.4))
        self.section_gap = float(timing.get("section_gap_seconds", 0.8))

        self.shadow_timing = timing.get(
            "shadow",
            {"pause_factor": 1.2, "min_pause_seconds": 2.0, "max_pause_seconds": 12.0},
        )
        self.free_answer_timing = timing.get(
            "free_answer",
            {"pause_factor": 1.6, "min_pause_seconds": 4.0, "max_pause_seconds": 15.0},
        )

        self.voices_config = self.config.get("voices", {})
        self.pronunciation_dict = self.config.get("pronunciation", {})

        # Track recorded chapters
        self.chapters: List[Dict[str, Any]] = []

    def resolve_voice_info(self, role: Optional[str], default_role: str = "teacher") -> Tuple[str, float]:
        """Resolves role or voice name into (voice_id, speed)."""
        target_role = role or default_role
        if target_role in self.voices_config:
            cfg = self.voices_config[target_role]
            return cfg.get("voice_id", "af_heart"), float(cfg.get("speed", 0.92))

        # Fallback to teacher or direct voice name
        if "teacher" in self.voices_config:
            cfg = self.voices_config["teacher"]
            return cfg.get("voice_id", target_role), float(cfg.get("speed", 0.92))

        return target_role, 0.92

    def calc_shadow_pause(self, audio_dur: float, text: str = "") -> float:
        """Calculates learner response pause based on audio length + sentence-length buffer.

        Rules:
        - Audio duration is calculated first.
        - Buffer added based on sentence length:
          * Shorter sentence (<= 6 words): 2.0 to 2.5s buffer (within 2 to 3s).
          * Medium sentence (7 to 14 words): 2.5 to 3.2s buffer.
          * Longer sentence (>= 15 words): 3.2 to 4.0s buffer (within 3 to 4s).
        - Guaranteed minimum of at least 2.0s to speak.
        """
        words = text.strip().split() if text else []
        word_count = len(words)

        if word_count <= 6:
            buffer = 2.0 + (word_count / 6.0) * 0.5
        elif word_count <= 14:
            buffer = 2.5 + ((word_count - 6) / 8.0) * 0.7
        else:
            buffer = min(4.0, 3.2 + ((word_count - 14) / 10.0) * 0.8)

        total_pause = max(2.0, round(audio_dur + buffer, 3))
        return total_pause

    def calc_free_answer_pause(self, audio_dur: float) -> float:
        """Calculates learner response pause for free answer segments."""
        pf = float(self.free_answer_timing.get("pause_factor", 1.6))
        p_min = float(self.free_answer_timing.get("min_pause_seconds", 4.0))
        p_max = float(self.free_answer_timing.get("max_pause_seconds", 15.0))
        return round(min(max(audio_dur * pf, p_min), p_max), 3)

    def _split_narration_chunks(self, text: str) -> List[str]:
        """Splits long narration text (>25 words) into 1-2 sentence caption chunks."""
        words = text.strip().split()
        if len(words) <= 25:
            return [text.strip()]

        raw_sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s.strip()]
        if len(raw_sentences) <= 1:
            return [text.strip()]

        chunks = []
        curr: List[str] = []
        for s in raw_sentences:
            curr.append(s)
            curr_words = " ".join(curr).split()
            if len(curr_words) >= 14 or len(curr) >= 2:
                chunks.append(" ".join(curr))
                curr = []
        if curr:
            chunks.append(" ".join(curr))
        return chunks if chunks else [text.strip()]

    def build_timeline(
        self, script: ShadowScript, preview: bool = False
    ) -> List[TimelineEvent]:
        """Builds chronological timeline events for all segments."""
        events: List[TimelineEvent] = []
        self.chapters = []
        current_time = 0.0
        event_id = 0

        segments_to_process = script.segments[:5] if preview else script.segments

        for seg_idx, segment in enumerate(segments_to_process):
            seg_id = getattr(segment, "id", None) or f"seg_{seg_idx:02d}"

            # -----------------------------------------------------------------
            # 1. NARRATION
            # -----------------------------------------------------------------
            if isinstance(segment, NarrationSegment):
                voice_id, base_speed = self.resolve_voice_info(segment.voice, "teacher")
                chunks = self._split_narration_chunks(segment.text)

                for chunk_idx, chunk_text in enumerate(chunks):
                    # Spoken override only applies to single-chunk or first chunk
                    spoken_raw = (segment.spoken if len(chunks) == 1 else chunk_text) or chunk_text
                    spoken_text = apply_pronunciation(spoken_raw, self.pronunciation_dict)

                    audio_path, raw_timings, dur = self.audio_provider.get_audio_and_transcription(
                        spoken_text, voice=voice_id, speed=base_speed
                    )
                    aligned_words = align_script_words(chunk_text, raw_timings, dur)

                    sub_id = f"{seg_id}_{chunk_idx+1}" if len(chunks) > 1 else seg_id
                    ev = TimelineEvent(
                        event_id=event_id,
                        segment_id=sub_id,
                        event_type="SPEECH",
                        type="speech",
                        sub_type="narration",
                        start_time=round(current_time, 3),
                        end_time=round(current_time + dur, 3),
                        duration=round(dur, 3),
                        text=chunk_text,
                        spoken_text=spoken_text,
                        voice=voice_id,
                        speed=base_speed,
                        speaker="Teacher",
                        badge_text="LISTEN & READ",
                        audio_path=audio_path,
                        word_timings=aligned_words,
                    )
                    events.append(ev)
                    current_time += dur
                    event_id += 1

                # Inter-narration gap
                current_time += self.narration_gap

            # -----------------------------------------------------------------
            # 2. SECTION TITLE
            # -----------------------------------------------------------------
            elif isinstance(segment, SectionTitleSegment):
                voice_id, base_speed = self.resolve_voice_info(segment.voice, "teacher")
                display_text = segment.text.strip()
                spoken_raw = segment.spoken.strip() if segment.spoken else display_text
                spoken_text = apply_pronunciation(spoken_raw, self.pronunciation_dict)

                audio_path, raw_timings, dur = self.audio_provider.get_audio_and_transcription(
                    spoken_text, voice=voice_id, speed=base_speed
                )
                aligned_words = align_script_words(display_text, raw_timings, dur)

                # Record chapter timestamp if chapter is True
                is_chapter = getattr(segment, "chapter", False) or False
                if is_chapter:
                    self.chapters.append({
                        "start_time": round(current_time, 3),
                        "title": display_text,
                        "segment_id": seg_id,
                    })

                total_card_dur = dur + self.section_gap
                ev = TimelineEvent(
                    event_id=event_id,
                    segment_id=seg_id,
                    event_type="SPEECH",
                    type="speech",
                    sub_type="section_title",
                    start_time=round(current_time, 3),
                    end_time=round(current_time + total_card_dur, 3),
                    duration=round(total_card_dur, 3),
                    text=display_text,
                    spoken_text=spoken_text,
                    voice=voice_id,
                    speed=base_speed,
                    speaker="Teacher",
                    badge_text="SECTION BREAK",
                    audio_path=audio_path,
                    word_timings=aligned_words,
                    chapter=is_chapter,
                )
                events.append(ev)
                current_time += total_card_dur
                event_id += 1

            # -----------------------------------------------------------------
            # 3. SHADOW (Sentence repeats N times, silence after EACH time)
            # -----------------------------------------------------------------
            elif isinstance(segment, ShadowSegment):
                repeat_count = int(segment.repeat or self.default_repeat)
                voice_id, base_speed = self.resolve_voice_info(segment.voice, "teacher")
                display_text = segment.text.strip()
                spoken_raw = segment.spoken.strip() if segment.spoken else display_text
                spoken_text = apply_pronunciation(spoken_raw, self.pronunciation_dict)

                # Pre-generate or cache speech for each repetition speed factor
                cached_takes: Dict[float, Tuple[str, List[Dict], float]] = {}

                for r in range(1, repeat_count + 1):
                    # Determine speed factor for this repeat round
                    speed_factor = 1.0
                    if self.repeat_speed_factors:
                        speed_idx = (r - 1) % len(self.repeat_speed_factors)
                        speed_factor = float(self.repeat_speed_factors[speed_idx])
                    actual_speed = round(base_speed * speed_factor, 2)

                    if actual_speed not in cached_takes:
                        audio_path, raw_timings, dur = self.audio_provider.get_audio_and_transcription(
                            spoken_text, voice=voice_id, speed=actual_speed
                        )
                        aligned_words = align_script_words(display_text, raw_timings, dur)
                        cached_takes[actual_speed] = (audio_path, aligned_words, dur)

                    a_path, w_timings, dur = cached_takes[actual_speed]
                    pause_dur = self.calc_shadow_pause(dur, display_text)

                    # 1. SPEECH Event (teacher speaks)
                    speech_ev = TimelineEvent(
                        event_id=event_id,
                        segment_id=seg_id,
                        event_type="SPEECH",
                        type="speech",
                        sub_type="shadow",
                        start_time=round(current_time, 3),
                        end_time=round(current_time + dur, 3),
                        duration=round(dur, 3),
                        text=display_text,
                        spoken_text=spoken_text,
                        voice=voice_id,
                        speed=actual_speed,
                        speaker="Teacher",
                        badge_text=f"LISTEN & READ ({r}/{repeat_count})",
                        audio_path=a_path,
                        word_timings=w_timings,
                        repeat_index=r,
                        repeat_total=repeat_count,
                    )
                    events.append(speech_ev)
                    current_time += dur
                    event_id += 1

                    # 2. SILENCE Event (learner response)
                    silence_ev = TimelineEvent(
                        event_id=event_id,
                        segment_id=seg_id,
                        event_type="SILENCE",
                        type="silence",
                        sub_type="shadow_silence",
                        start_time=round(current_time, 3),
                        end_time=round(current_time + pause_dur, 3),
                        duration=round(pause_dur, 3),
                        text=display_text,
                        spoken_text="",
                        voice=voice_id,
                        speed=actual_speed,
                        speaker="You",
                        badge_text=f"YOUR TURN ({r}/{repeat_count})",
                        audio_path=None,
                        word_timings=w_timings,
                        repeat_index=r,
                        repeat_total=repeat_count,
                    )
                    events.append(silence_ev)
                    current_time += pause_dur
                    event_id += 1

            # -----------------------------------------------------------------
            # 4. SHADOW PAIR (Conversation exchange repeated as a whole block)
            # -----------------------------------------------------------------
            elif isinstance(segment, ShadowPairSegment):
                repeat_count = int(segment.repeat or self.default_repeat)
                lines = segment.lines

                # Pre-generate audio for each line
                cached_line_takes: List[Dict[float, Tuple[str, List[Dict], float]]] = [{} for _ in lines]

                for r in range(1, repeat_count + 1):
                    speed_factor = 1.0
                    if self.repeat_speed_factors:
                        speed_idx = (r - 1) % len(self.repeat_speed_factors)
                        speed_factor = float(self.repeat_speed_factors[speed_idx])

                    for l_idx, line in enumerate(lines):
                        display_text = line.text.strip()
                        default_role = "speaker_a" if l_idx % 2 == 0 else "speaker_b"
                        voice_id, base_speed = self.resolve_voice_info(line.voice, default_role)
                        actual_speed = round(base_speed * speed_factor, 2)

                        spoken_raw = line.spoken.strip() if line.spoken else display_text
                        spoken_text = apply_pronunciation(spoken_raw, self.pronunciation_dict)

                        if actual_speed not in cached_line_takes[l_idx]:
                            audio_path, raw_timings, dur = self.audio_provider.get_audio_and_transcription(
                                spoken_text, voice=voice_id, speed=actual_speed
                            )
                            aligned_words = align_script_words(display_text, raw_timings, dur)
                            cached_line_takes[l_idx][actual_speed] = (audio_path, aligned_words, dur)

                        a_path, w_timings, dur = cached_line_takes[l_idx][actual_speed]
                        pause_dur = self.calc_shadow_pause(dur, display_text)

                        line_id = f"{seg_id}_L{l_idx+1}"
                        speaker_name = "Speaker A" if l_idx % 2 == 0 else "Speaker B"

                        # Line SPEECH
                        speech_ev = TimelineEvent(
                            event_id=event_id,
                            segment_id=line_id,
                            event_type="SPEECH",
                            type="speech",
                            sub_type="shadow",
                            start_time=round(current_time, 3),
                            end_time=round(current_time + dur, 3),
                            duration=round(dur, 3),
                            text=display_text,
                            spoken_text=spoken_text,
                            voice=voice_id,
                            speed=actual_speed,
                            speaker=speaker_name,
                            badge_text=f"LISTEN & READ ({r}/{repeat_count})",
                            audio_path=a_path,
                            word_timings=w_timings,
                            repeat_index=r,
                            repeat_total=repeat_count,
                        )
                        events.append(speech_ev)
                        current_time += dur
                        event_id += 1

                        # Line SILENCE
                        silence_ev = TimelineEvent(
                            event_id=event_id,
                            segment_id=line_id,
                            event_type="SILENCE",
                            type="silence",
                            sub_type="shadow_silence",
                            start_time=round(current_time, 3),
                            end_time=round(current_time + pause_dur, 3),
                            duration=round(pause_dur, 3),
                            text=display_text,
                            spoken_text="",
                            voice=voice_id,
                            speed=actual_speed,
                            speaker="You",
                            badge_text=f"YOUR TURN ({r}/{repeat_count})",
                            audio_path=None,
                            word_timings=w_timings,
                            repeat_index=r,
                            repeat_total=repeat_count,
                        )
                        events.append(silence_ev)
                        current_time += pause_dur
                        event_id += 1

            # -----------------------------------------------------------------
            # 5. DIALOGUE (Listen only, no repeat, no learner silence)
            # -----------------------------------------------------------------
            elif isinstance(segment, DialogueSegment):
                default_role = "speaker_b" if "b" in segment.speaker.lower() else "speaker_a"
                voice_id, base_speed = self.resolve_voice_info(segment.voice, default_role)
                display_text = segment.text.strip()
                spoken_raw = segment.spoken.strip() if segment.spoken else display_text
                spoken_text = apply_pronunciation(spoken_raw, self.pronunciation_dict)

                audio_path, raw_timings, dur = self.audio_provider.get_audio_and_transcription(
                    spoken_text, voice=voice_id, speed=base_speed
                )
                aligned_words = align_script_words(display_text, raw_timings, dur)

                ev = TimelineEvent(
                    event_id=event_id,
                    segment_id=seg_id,
                    event_type="SPEECH",
                    type="speech",
                    sub_type="dialogue",
                    start_time=round(current_time, 3),
                    end_time=round(current_time + dur, 3),
                    duration=round(dur, 3),
                    text=display_text,
                    spoken_text=spoken_text,
                    voice=voice_id,
                    speed=base_speed,
                    speaker=segment.speaker,
                    badge_text=segment.speaker.upper(),
                    audio_path=audio_path,
                    word_timings=aligned_words,
                )
                events.append(ev)
                current_time += dur
                event_id += 1

                # Conversational gap
                current_time += self.narration_gap

            # -----------------------------------------------------------------
            # 6. FREE ANSWER (Question speech + single long thinking pause)
            # -----------------------------------------------------------------
            elif isinstance(segment, FreeAnswerSegment):
                voice_id, base_speed = self.resolve_voice_info(segment.voice, "teacher")
                display_text = segment.text.strip()
                spoken_raw = segment.spoken.strip() if segment.spoken else display_text
                spoken_text = apply_pronunciation(spoken_raw, self.pronunciation_dict)

                audio_path, raw_timings, dur = self.audio_provider.get_audio_and_transcription(
                    spoken_text, voice=voice_id, speed=base_speed
                )
                aligned_words = align_script_words(display_text, raw_timings, dur)
                pause_dur = self.calc_free_answer_pause(dur)

                # Question SPEECH
                speech_ev = TimelineEvent(
                    event_id=event_id,
                    segment_id=seg_id,
                    event_type="SPEECH",
                    type="speech",
                    sub_type="free_answer",
                    start_time=round(current_time, 3),
                    end_time=round(current_time + dur, 3),
                    duration=round(dur, 3),
                    text=display_text,
                    spoken_text=spoken_text,
                    voice=voice_id,
                    speed=base_speed,
                    speaker="Teacher",
                    badge_text="QUESTION",
                    audio_path=audio_path,
                    word_timings=aligned_words,
                )
                events.append(speech_ev)
                current_time += dur
                event_id += 1

                # Answer SILENCE
                silence_ev = TimelineEvent(
                    event_id=event_id,
                    segment_id=seg_id,
                    event_type="SILENCE",
                    type="silence",
                    sub_type="free_answer_silence",
                    start_time=round(current_time, 3),
                    end_time=round(current_time + pause_dur, 3),
                    duration=round(pause_dur, 3),
                    text=display_text,
                    spoken_text="",
                    voice=voice_id,
                    speed=base_speed,
                    speaker="You",
                    badge_text="YOUR ANSWER",
                    audio_path=None,
                    word_timings=aligned_words,
                )
                events.append(silence_ev)
                current_time += pause_dur
                event_id += 1

        return events
