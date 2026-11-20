"""Schema & Validation for English Shadowing Script.

Defines Pydantic models and comprehensive validation for:
- narration
- section_title
- shadow
- shadow_pair
- dialogue
- free_answer

Follows the complete Segment Behavior Specification with multi-error aggregation
and warning diagnostics.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, Field, ValidationError, model_validator


class Settings(BaseModel):
    buffer_seconds: float = Field(default=1.5, ge=0.5, le=5.0, description="Buffer silence seconds added to shadow pause")
    default_repeat: int = Field(default=2, ge=1, le=10, description="Default number of shadow repeats")
    voice_teacher: str = Field(default="af_heart", description="Default voice for teacher/narration (Kokoro)")
    voice_speaker_b: str = Field(default="am_adam", description="Default voice for dialogue second speaker (Kokoro)")
    speed: float = Field(default=0.92, ge=0.5, le=2.0, description="Default speech speed for Kokoro")


class NarrationSegment(BaseModel):
    id: Optional[str] = None
    type: Literal["narration"]
    text: str = Field(min_length=1, description="Teacher narration text")
    spoken: Optional[str] = None
    voice: Optional[str] = None


class SectionTitleSegment(BaseModel):
    id: Optional[str] = None
    type: Literal["section_title"]
    text: str = Field(min_length=1, description="Section title text")
    spoken: Optional[str] = None
    chapter: Optional[bool] = False
    voice: Optional[str] = None


class ShadowSegment(BaseModel):
    id: Optional[str] = None
    type: Literal["shadow"]
    text: str = Field(min_length=1, description="Sentence for learner to shadow")
    spoken: Optional[str] = None
    repeat: Optional[int] = Field(default=None, ge=1, le=10, description="Repetition count override")
    voice: Optional[str] = None
    pause_seconds: Optional[float] = None
    buffer_seconds: Optional[float] = None


class ShadowPairLine(BaseModel):
    text: str = Field(min_length=1, description="Spoken line text")
    spoken: Optional[str] = None
    voice: Optional[str] = None


class ShadowPairSegment(BaseModel):
    id: Optional[str] = None
    type: Literal["shadow_pair"]
    lines: List[ShadowPairLine] = Field(min_length=2, description="At least two lines for the exchange")
    repeat: Optional[int] = Field(default=None, ge=1, le=10)


class DialogueSegment(BaseModel):
    id: Optional[str] = None
    type: Literal["dialogue"]
    speaker: str = Field(default="Speaker", description="Speaker name/tag")
    text: str = Field(min_length=1, description="Spoken dialogue text")
    spoken: Optional[str] = None
    voice: Optional[str] = None


class FreeAnswerSegment(BaseModel):
    id: Optional[str] = None
    type: Literal["free_answer"]
    text: str = Field(min_length=1, description="Prompt/question asked by teacher")
    spoken: Optional[str] = None
    voice: Optional[str] = None
    pause_seconds: Optional[float] = None


SegmentUnion = Union[
    NarrationSegment,
    SectionTitleSegment,
    ShadowSegment,
    ShadowPairSegment,
    DialogueSegment,
    FreeAnswerSegment,
]


class ShadowScript(BaseModel):
    title: str = Field(min_length=1, description="Title of the video/lesson")
    settings: Settings = Field(default_factory=Settings)
    segments: List[SegmentUnion] = Field(min_length=1, description="List of script segments")

    @model_validator(mode="before")
    @classmethod
    def validate_segments_structure(cls, data):
        if isinstance(data, list):
            data = {"title": "English Shadowing Practice", "segments": data}
        elif isinstance(data, dict):
            if "type" in data and "segments" not in data:
                data = {"title": "English Shadowing Practice", "segments": [data]}
            elif "segments" in data and "title" not in data:
                data["title"] = "English Shadowing Practice"
        else:
            raise ValueError("Root script must be a JSON object or array of segments.")

        if "segments" not in data or not isinstance(data["segments"], list) or not data["segments"]:
            raise ValueError("Script must contain a non-empty 'segments' list.")
        return data


def validate_script_full(
    raw_data: dict, config: Optional[dict] = None
) -> Tuple[ShadowScript, List[str], List[str]]:
    """Comprehensive validation running all checks together.

    Returns:
        (parsed_script, errors, warnings)
    Raises:
        ValueError if errors is non-empty.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(raw_data, (dict, list)):
        errors.append("Script root must be a JSON object or an array of segments.")
        raise ValueError("Script Validation Errors:\n- " + "\n- ".join(errors))

    raw_segments = raw_data.get("segments", []) if isinstance(raw_data, dict) else raw_data
    if not isinstance(raw_segments, list) or len(raw_segments) == 0:
        errors.append("Script must contain a non-empty 'segments' list.")
        raise ValueError("Script Validation Errors:\n- " + "\n- ".join(errors))

    valid_types = {
        "narration",
        "section_title",
        "shadow",
        "shadow_pair",
        "dialogue",
        "free_answer",
    }

    # Available voice roles
    known_roles = {"teacher", "speaker_a", "speaker_b"}
    if config and "voices" in config:
        known_roles.update(config["voices"].keys())

    seen_ids = set()
    prev_shadow_text = None
    prev_shadow_id = None
    chapters_count = 0

    for idx, seg in enumerate(raw_segments):
        if not isinstance(seg, dict):
            errors.append(f"Segment index {idx} is not a valid dictionary object.")
            continue

        seg_type = seg.get("type")
        seg_id = seg.get("id", f"seg_{idx}")

        # 1. Duplicate ID
        if "id" in seg and seg["id"]:
            sid = str(seg["id"])
            if sid in seen_ids:
                errors.append(f"Duplicate segment id '{sid}' detected at index #{idx}.")
            seen_ids.add(sid)

        # 2. Unknown type
        if not seg_type or seg_type not in valid_types:
            errors.append(f"Segment #{idx} (id='{seg_id}'): unknown or missing type '{seg_type}'.")
            continue

        # 3. Empty text check
        if seg_type == "shadow_pair":
            lines = seg.get("lines", [])
            if not isinstance(lines, list) or len(lines) < 2:
                errors.append(
                    f"Segment '{seg_id}' (shadow_pair) must contain at least 2 lines, found {len(lines) if isinstance(lines, list) else 0}."
                )
            else:
                for l_idx, line in enumerate(lines):
                    if not isinstance(line, dict) or not line.get("text", "").strip():
                        errors.append(f"Segment '{seg_id}' (shadow_pair) line #{l_idx} has empty text.")
                    l_voice = line.get("voice") if isinstance(line, dict) else None
                    if l_voice and l_voice not in known_roles:
                        errors.append(
                            f"Segment '{seg_id}' (shadow_pair) line #{l_idx} has unknown voice role '{l_voice}'."
                        )
        else:
            text = seg.get("text", "")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"Segment #{idx} (id='{seg_id}', type='{seg_type}') has empty text.")

        # 4. Unknown voice role
        voice_role = seg.get("voice")
        if voice_role and voice_role not in known_roles:
            errors.append(
                f"Segment '{seg_id}' specifies unknown voice role '{voice_role}'. Known roles: {sorted(list(known_roles))}."
            )

        # 5. Warnings
        # Pause_seconds warning (script should never specify pause values)
        if "pause_seconds" in seg and seg["pause_seconds"] is not None:
            warnings.append(
                f"Segment '{seg_id}' specifies 'pause_seconds'={seg['pause_seconds']}, which is ignored. Pauses are automatically calculated."
            )

        # Shadow specific checks
        if seg_type == "shadow":
            s_text = seg.get("text", "").strip()
            word_count = len(s_text.split())
            if word_count > 25:
                warnings.append(
                    f"Shadow segment '{seg_id}' contains {word_count} words (>25 words). Consider splitting for better learner recall."
                )
            if prev_shadow_text is not None and prev_shadow_text.lower() == s_text.lower():
                warnings.append(
                    f"Two identical consecutive shadow segments detected ('{prev_shadow_id}' and '{seg_id}')."
                )
            prev_shadow_text = s_text
            prev_shadow_id = seg_id
        else:
            prev_shadow_text = None
            prev_shadow_id = None

        if seg_type == "section_title" and seg.get("chapter", False):
            chapters_count += 1

    if errors:
        raise ValueError("Script Validation Errors:\n- " + "\n- ".join(errors))

    # Parse with Pydantic
    try:
        script = ShadowScript.model_validate(raw_data)
    except ValidationError as err:
        pydantic_errors = [f"At [{' -> '.join(str(p) for p in e['loc'])}]: {e['msg']}" for e in err.errors()]
        raise ValueError("Script Schema Errors:\n- " + "\n- ".join(pydantic_errors)) from err

    warnings.append(f"Total script segments: {len(script.segments)}")
    warnings.append(f"Total video chapters detected: {chapters_count}")

    return script, errors, warnings


def parse_and_validate_script(raw_data: dict, config: Optional[dict] = None) -> ShadowScript:
    """Parses and validates, raising ValueError with all errors if invalid."""
    script, _, _ = validate_script_full(raw_data, config)
    return script
