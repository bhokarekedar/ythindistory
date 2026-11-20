"""Timeline Builder for English Shadowing Pipeline.

Flattens validated script segments into an exact timeline of speech and silence events.
Reuses generated TTS audio files across repetitions and caches them on disk.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
from shadowing_pipeline.core.audio_provider import AudioProvider
from shadowing_pipeline.core.schema import (
    DialogueSegment,
    FreeAnswerSegment,
    NarrationSegment,
    SectionTitleSegment,
    ShadowScript,
    ShadowSegment,
)
from shadowing_pipeline.core.word_aligner import align_script_words


@dataclass
class TimelineEvent:
    event_id: int
    start_time: float
    end_time: float
    duration: float
    type: str  # "speech" | "silence"
    sub_type: str  # "narration", "section_title", "shadow_speech", "shadow_silence", "dialogue", "free_answer_speech", "free_answer_silence"
    text: str
    speaker: Optional[str]
    badge_text: str
    audio_path: Optional[str]
    word_timings: List[Dict[str, Any]]
    repeat_index: Optional[int] = None
    repeat_total: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TimelineBuilder:
    def __init__(self, audio_provider: AudioProvider):
        self.audio_provider = audio_provider

    def build_timeline(
        self, script: ShadowScript, preview: bool = False
    ) -> List[TimelineEvent]:
        """Constructs a chronological list of timeline events.

        If preview=True, only processes the first 5 segments.
        """
        events: List[TimelineEvent] = []
        current_time = 0.0
        event_id = 0

        segments_to_process = (
            script.segments[:5] if preview else script.segments
        )

        default_buffer = script.settings.buffer_seconds
        default_repeat = script.settings.default_repeat
        teacher_voice = script.settings.voice_teacher
        speaker_b_voice = script.settings.voice_speaker_b
        speed = getattr(script.settings, "speed", 0.92)

        for seg_idx, segment in enumerate(segments_to_process):
            if isinstance(segment, NarrationSegment):
                voice = segment.voice or teacher_voice
                audio_path, raw_timings, dur = (
                    self.audio_provider.get_audio_and_transcription(
                        segment.text, voice, speed=speed
                    )
                )
                aligned_words = align_script_words(segment.text, raw_timings, dur)

                ev = TimelineEvent(
                    event_id=event_id,
                    start_time=round(current_time, 3),
                    end_time=round(current_time + dur, 3),
                    duration=round(dur, 3),
                    type="speech",
                    sub_type="narration",
                    text=segment.text,
                    speaker="Teacher",
                    badge_text="LISTEN & READ",
                    audio_path=audio_path,
                    word_timings=aligned_words,
                )
                events.append(ev)
                current_time += dur
                event_id += 1

            elif isinstance(segment, SectionTitleSegment):
                voice = segment.voice or teacher_voice
                audio_path, raw_timings, dur = (
                    self.audio_provider.get_audio_and_transcription(
                        segment.text, voice, speed=speed
                    )
                )
                aligned_words = align_script_words(segment.text, raw_timings, dur)

                # Add a brief 0.5s pause after section title for dramatic pacing
                total_title_dur = dur + 0.5

                ev = TimelineEvent(
                    event_id=event_id,
                    start_time=round(current_time, 3),
                    end_time=round(current_time + total_title_dur, 3),
                    duration=round(total_title_dur, 3),
                    type="speech",
                    sub_type="section_title",
                    text=segment.text,
                    speaker="Teacher",
                    badge_text="SECTION",
                    audio_path=audio_path,
                    word_timings=aligned_words,
                )
                events.append(ev)
                current_time += total_title_dur
                event_id += 1

            elif isinstance(segment, ShadowSegment):
                repeat_count = segment.repeat or default_repeat
                buffer_sec = (
                    segment.buffer_seconds
                    if segment.buffer_seconds is not None
                    else default_buffer
                )
                voice = teacher_voice

                # Generate TTS ONCE and reuse across all repeats
                audio_path, raw_timings, dur = (
                    self.audio_provider.get_audio_and_transcription(
                        segment.text, voice, speed=speed
                    )
                )
                aligned_words = align_script_words(segment.text, raw_timings, dur)
                pause_duration = round(dur + buffer_sec, 3)

                for r in range(1, repeat_count + 1):
                    # 1. Spoken sentence (repeat r)
                    speech_ev = TimelineEvent(
                        event_id=event_id,
                        start_time=round(current_time, 3),
                        end_time=round(current_time + dur, 3),
                        duration=round(dur, 3),
                        type="speech",
                        sub_type="shadow_speech",
                        text=segment.text,
                        speaker="Teacher",
                        badge_text=f"LISTEN & READ ({r}/{repeat_count})",
                        audio_path=audio_path,
                        word_timings=aligned_words,
                        repeat_index=r,
                        repeat_total=repeat_count,
                    )
                    events.append(speech_ev)
                    current_time += dur
                    event_id += 1

                    # 2. Learner repetition pause ("Your turn")
                    silence_ev = TimelineEvent(
                        event_id=event_id,
                        start_time=round(current_time, 3),
                        end_time=round(current_time + pause_duration, 3),
                        duration=round(pause_duration, 3),
                        type="silence",
                        sub_type="shadow_silence",
                        text=segment.text,
                        speaker="You",
                        badge_text=f"YOUR TURN ({r}/{repeat_count})",
                        audio_path=None,
                        word_timings=aligned_words,
                        repeat_index=r,
                        repeat_total=repeat_count,
                    )
                    events.append(silence_ev)
                    current_time += pause_duration
                    event_id += 1

            elif isinstance(segment, DialogueSegment):
                # Pick speaker voice
                is_speaker_b = any(
                    tok in segment.speaker.lower()
                    for tok in ["b", "alex", "john", "student", "daniel"]
                )
                voice = (
                    segment.voice
                    or (speaker_b_voice if is_speaker_b else teacher_voice)
                )

                audio_path, raw_timings, dur = (
                    self.audio_provider.get_audio_and_transcription(
                        segment.text, voice, speed=speed
                    )
                )
                aligned_words = align_script_words(segment.text, raw_timings, dur)

                ev = TimelineEvent(
                    event_id=event_id,
                    start_time=round(current_time, 3),
                    end_time=round(current_time + dur, 3),
                    duration=round(dur, 3),
                    type="speech",
                    sub_type="dialogue",
                    text=segment.text,
                    speaker=segment.speaker,
                    badge_text=segment.speaker.upper(),
                    audio_path=audio_path,
                    word_timings=aligned_words,
                )
                events.append(ev)
                current_time += dur
                event_id += 1

            elif isinstance(segment, FreeAnswerSegment):
                voice = segment.voice or teacher_voice
                audio_path, raw_timings, dur = (
                    self.audio_provider.get_audio_and_transcription(
                        segment.text, voice, speed=speed
                    )
                )
                aligned_words = align_script_words(segment.text, raw_timings, dur)

                # 1. Question speech
                speech_ev = TimelineEvent(
                    event_id=event_id,
                    start_time=round(current_time, 3),
                    end_time=round(current_time + dur, 3),
                    duration=round(dur, 3),
                    type="speech",
                    sub_type="free_answer_speech",
                    text=segment.text,
                    speaker="Teacher",
                    badge_text="❓ QUESTION",
                    audio_path=audio_path,
                    word_timings=aligned_words,
                )
                events.append(speech_ev)
                current_time += dur
                event_id += 1

                # 2. Free answer pause
                pause_dur = round(segment.pause_seconds, 3)
                silence_ev = TimelineEvent(
                    event_id=event_id,
                    start_time=round(current_time, 3),
                    end_time=round(current_time + pause_dur, 3),
                    duration=round(pause_dur, 3),
                    type="silence",
                    sub_type="free_answer_silence",
                    text=segment.text,
                    speaker="You",
                    badge_text="ANSWER ALOUD NOW",
                    audio_path=None,
                    word_timings=aligned_words,
                )
                events.append(silence_ev)
                current_time += pause_dur
                event_id += 1

        return events

