"""Schema & Validation for English Shadowing Script.

Defines Pydantic models for script validation with descriptive error reporting.
"""

from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field, ValidationError, model_validator


class Settings(BaseModel):
    buffer_seconds: float = Field(default=1.5, ge=0.5, le=5.0, description="Buffer silence seconds added to shadow pause")
    default_repeat: int = Field(default=2, ge=1, le=10, description="Default number of shadow repeats")
    voice_teacher: str = Field(default="Samantha", description="Default voice for teacher/narration")
    voice_speaker_b: str = Field(default="Alex", description="Default voice for dialogue second speaker")


class NarrationSegment(BaseModel):
    type: Literal["narration"]
    text: str = Field(min_length=1, description="Teacher narration text")
    voice: Optional[str] = None


class SectionTitleSegment(BaseModel):
    type: Literal["section_title"]
    text: str = Field(min_length=1, description="Section title text")
    voice: Optional[str] = None


class ShadowSegment(BaseModel):
    type: Literal["shadow"]
    text: str = Field(min_length=1, description="Sentence for learner to shadow")
    repeat: Optional[int] = Field(default=None, ge=1, le=10, description="Repetition count override")
    buffer_seconds: Optional[float] = Field(default=None, ge=0.5, le=5.0)


class DialogueSegment(BaseModel):
    type: Literal["dialogue"]
    speaker: str = Field(min_length=1, description="Speaker name/tag (e.g., 'Speaker A', 'Teacher')")
    text: str = Field(min_length=1, description="Spoken dialogue text")
    voice: Optional[str] = None


class FreeAnswerSegment(BaseModel):
    type: Literal["free_answer"]
    text: str = Field(min_length=1, description="Prompt/question asked by teacher")
    pause_seconds: float = Field(default=6.0, gt=0.0, le=60.0, description="Silent pause for student answer")
    voice: Optional[str] = None


SegmentUnion = Union[
    NarrationSegment,
    SectionTitleSegment,
    ShadowSegment,
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
        # Allow passing bare list of segments: [ {...}, {...} ]
        if isinstance(data, list):
            data = {"title": "English Shadowing Practice", "segments": data}
        elif isinstance(data, dict):
            # Allow passing a single segment object: { "type": "shadow", ... }
            if "type" in data and "segments" not in data:
                data = {"title": "English Shadowing Practice", "segments": [data]}
            elif "segments" in data and "title" not in data:
                data["title"] = "English Shadowing Practice"
        else:
            raise ValueError("Root script must be a JSON object or array of segments.")

        if "segments" not in data or not isinstance(data["segments"], list) or not data["segments"]:
            raise ValueError("Script must contain a non-empty 'segments' list.")
        return data


def parse_and_validate_script(raw_data: dict) -> ShadowScript:
    """Parses a dictionary and validates it against the ShadowScript schema.

    Returns the validated ShadowScript object or raises a ValueError with clear explanations.
    """
    try:
        return ShadowScript.model_validate(raw_data)
    except ValidationError as err:
        messages = []
        for error in err.errors():
            loc = " -> ".join(str(p) for p in error["loc"])
            messages.append(f"At [{loc}]: {error['msg']} (got {error.get('input', 'N/A')})")
        raise ValueError("Invalid script JSON:\n- " + "\n- ".join(messages)) from err

