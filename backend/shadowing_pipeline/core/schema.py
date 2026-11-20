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
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, Field, ValidationError, model_validator


class Settings(BaseModel):
    buffer_seconds: float = Field(default=1.5, ge=0.5, le=5.0, description="Buffer silence seconds added to shadow pause")
    default_repeat: int = Field(default=2, ge=1, le=10, description="Default number of shadow repeats")
    voice_teacher: str = Field(default="af_heart", description="Default voice for teacher/narration (Kokoro)")
    voice_speaker_b: str = Field(default="am_adam", description="Default voice for dialogue second speaker (Kokoro)")
    speed: float = Field(default=0.85, ge=0.5, le=2.0, description="Default speech speed for Kokoro")


class YouTubeMetadata(BaseModel):
    title: str = Field(min_length=1, max_length=100, description="YouTube public video title")
    title_alternatives: List[str] = Field(min_length=3, max_length=3, description="Exactly 3 alternative titles")
    description: str = Field(max_length=5000, description="YouTube description containing {{CHAPTERS}}")
    tags: List[str] = Field(min_length=15, max_length=30, description="15 to 30 lowercase tags")
    hashtags: List[str] = Field(min_length=3, max_length=3, description="Exactly 3 hashtags starting with #")
    thumbnail_text: str = Field(min_length=1, description="2 to 5 words thumbnail overlay text")
    pinned_comment: str = Field(default="", max_length=10000, description="Comment text for pinned comment")
    playlist: str = Field(default="", description="Target YouTube playlist name")
    category: str = Field(default="Education", description="YouTube category name")
    language: str = Field(default="en", description="Default video language")
    made_for_kids: bool = Field(default=False, description="Whether marked for kids")


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
    title: str = Field(min_length=1, description="Internal working title used for files and logs")
    settings: Settings = Field(default_factory=Settings)
    youtube: Optional[YouTubeMetadata] = None
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


def validate_youtube_metadata(
    yt_data: Any, raw_segments: Optional[List[dict]] = None
) -> Tuple[Optional[YouTubeMetadata], List[str], List[str]]:
    """Validates the 'youtube' metadata dictionary.

    Returns:
        (parsed_youtube_metadata, errors, warnings)
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(yt_data, dict):
        return None, ["Key 'youtube' must be a dictionary object."], []

    # 1. title
    title = yt_data.get("title")
    if not isinstance(title, str) or len(title.strip()) == 0:
        errors.append("youtube.title is required and must not be empty.")
    elif len(title) > 100:
        errors.append(f"youtube.title must be at most 100 characters (found {len(title)} chars).")
    else:
        if len(title) > 70:
            warnings.append(f"youtube.title is {len(title)} characters (>70 chars). Consider shortening for mobile displays.")
        if title.isupper() and any(c.isalpha() for c in title):
            warnings.append("youtube.title must not be ALL CAPS.")

    # 2. title_alternatives
    alts = yt_data.get("title_alternatives")
    if not isinstance(alts, list) or len(alts) != 3:
        errors.append(f"youtube.title_alternatives must be a list of exactly 3 strings (found {len(alts) if isinstance(alts, list) else 0}).")
    else:
        for idx, alt in enumerate(alts):
            if not isinstance(alt, str) or len(alt.strip()) == 0:
                errors.append(f"youtube.title_alternatives[{idx}] must be a non-empty string.")
            elif len(alt) > 100:
                errors.append(f"youtube.title_alternatives[{idx}] exceeds 100 characters ({len(alt)} chars).")

    # 3. description & placeholder
    desc = yt_data.get("description")
    if not isinstance(desc, str):
        errors.append("youtube.description is required and must be a string.")
    else:
        if len(desc) > 5000:
            errors.append(f"youtube.description exceeds 5000 characters ({len(desc)} chars).")
        
        c_count = desc.count("{{CHAPTERS}}")
        if c_count == 0:
            errors.append("youtube.description must contain the literal placeholder '{{CHAPTERS}}'.")
        elif c_count > 1:
            errors.append(f"youtube.description must contain '{{CHAPTERS}}' exactly once (found {c_count} times).")
        else:
            # Must be on its own line
            own_line = any(line.strip() == "{{CHAPTERS}}" for line in desc.splitlines())
            if not own_line:
                errors.append("Placeholder '{{CHAPTERS}}' must be on its own line in description.")

    # 4. tags
    tags = yt_data.get("tags")
    if not isinstance(tags, list) or len(tags) < 15 or len(tags) > 30:
        errors.append(f"youtube.tags must be a list of 15 to 30 strings (found {len(tags) if isinstance(tags, list) else 0}).")
    else:
        seen_tags = set()
        for idx, t in enumerate(tags):
            if not isinstance(t, str):
                errors.append(f"youtube.tags[{idx}] is not a string.")
                continue
            if t != t.lower():
                errors.append(f"youtube.tags[{idx}] ('{t}') must be lowercase.")
            if "#" in t:
                errors.append(f"youtube.tags[{idx}] ('{t}') must not contain '#' character.")
            if t in seen_tags:
                errors.append(f"Duplicate tag '{t}' in youtube.tags.")
            seen_tags.add(t)

        total_tag_len = len(",".join(str(t) for t in tags))
        if total_tag_len > 500:
            errors.append(f"Total tags length including separating commas exceeds 500 characters ({total_tag_len} chars).")
        elif total_tag_len > 450:
            warnings.append(f"Total tags length is {total_tag_len} characters (>450 chars, max 500).")

    # 5. hashtags
    hashtags = yt_data.get("hashtags")
    if not isinstance(hashtags, list) or len(hashtags) != 3:
        errors.append(f"youtube.hashtags must be a list of exactly 3 strings (found {len(hashtags) if isinstance(hashtags, list) else 0}).")
    else:
        for idx, h in enumerate(hashtags):
            if not isinstance(h, str) or not h.startswith("#"):
                errors.append(f"youtube.hashtags[{idx}] ('{h}') must start with '#'.")
            elif " " in h:
                errors.append(f"youtube.hashtags[{idx}] ('{h}') must not contain spaces.")

    # 6. thumbnail_text
    thumb = yt_data.get("thumbnail_text")
    if not isinstance(thumb, str):
        errors.append("youtube.thumbnail_text is required and must be a string.")
    else:
        words = thumb.strip().split()
        if len(words) < 2 or len(words) > 5:
            errors.append(f"youtube.thumbnail_text must be 2 to 5 words (found {len(words)}: '{thumb}').")

    # 7. pinned_comment
    comment = yt_data.get("pinned_comment", "")
    if comment is not None and not isinstance(comment, str):
        errors.append("youtube.pinned_comment must be a string.")
    elif isinstance(comment, str) and len(comment) > 10000:
        errors.append(f"youtube.pinned_comment exceeds 10000 characters ({len(comment)} chars).")

    # 8. playlist
    playlist = yt_data.get("playlist")
    if playlist is not None and not isinstance(playlist, str):
        errors.append("youtube.playlist must be a string.")

    # 9. made_for_kids
    mfk = yt_data.get("made_for_kids", False)
    if not isinstance(mfk, bool):
        errors.append("youtube.made_for_kids must be a boolean.")

    # Cross-checks with script segments
    if isinstance(desc, str) and raw_segments:
        desc_lower = desc.lower()
        for s_idx, s in enumerate(raw_segments):
            if isinstance(s, dict) and s.get("type") == "section_title" and s.get("chapter", False):
                sec_text = s.get("text", "")
                # Extract main topic words (strip "Part 1:", "Section 1:", etc.)
                topic_core = re.sub(r"^(part|section)\s+\d+[:.]?\s*", "", sec_text, flags=re.I).strip()
                topic_words = [w.lower() for w in re.findall(r"[a-zA-Z]{4,}", topic_core)]
                if topic_words and not any(w in desc_lower for w in topic_words):
                    warnings.append(f"Description may not mention topic of chapter '{sec_text}'.")

    parsed_obj: Optional[YouTubeMetadata] = None
    if not errors:
        try:
            parsed_obj = YouTubeMetadata(
                title=title,
                title_alternatives=alts,
                description=desc,
                tags=tags,
                hashtags=hashtags,
                thumbnail_text=thumb,
                pinned_comment=comment or "",
                playlist=yt_data.get("playlist", ""),
                category=yt_data.get("category", "Education"),
                language=yt_data.get("language", "en"),
                made_for_kids=bool(mfk),
            )
        except ValidationError as val_err:
            for e in val_err.errors():
                errors.append(f"youtube.{'.'.join(str(p) for p in e['loc'])}: {e['msg']}")

    return parsed_obj, errors, warnings


def validate_script_full(
    raw_data: dict, config: Optional[dict] = None, require_youtube: bool = True
) -> Tuple[ShadowScript, List[str], List[str]]:
    """Comprehensive validation running all checks together.

    Validates top-level structure, youtube metadata, and all segments.
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

    # Top-level keys validation
    known_top_keys = {"title", "youtube", "segments", "settings"}
    if isinstance(raw_data, dict):
        for k in raw_data.keys():
            if k not in known_top_keys:
                warnings.append(f"Unknown top-level key '{k}' will be ignored.")

    raw_segments = raw_data.get("segments", []) if isinstance(raw_data, dict) else raw_data
    if not isinstance(raw_segments, list) or len(raw_segments) == 0:
        errors.append("Script must contain a non-empty 'segments' list.")

    # Validate YouTube Metadata
    parsed_youtube: Optional[YouTubeMetadata] = None
    if isinstance(raw_data, dict) and "youtube" in raw_data:
        parsed_youtube, yt_errors, yt_warnings = validate_youtube_metadata(
            raw_data["youtube"], raw_segments=raw_segments if isinstance(raw_segments, list) else None
        )
        errors.extend(yt_errors)
        warnings.extend(yt_warnings)
    elif require_youtube:
        errors.append("Missing required top-level key 'youtube'.")

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

    if isinstance(raw_segments, list):
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
        if parsed_youtube:
            script.youtube = parsed_youtube
    except ValidationError as err:
        pydantic_errors = [f"At [{' -> '.join(str(p) for p in e['loc'])}]: {e['msg']}" for e in err.errors()]
        raise ValueError("Script Schema Errors:\n- " + "\n- ".join(pydantic_errors)) from err

    warnings.append(f"Total script segments: {len(script.segments)}")
    warnings.append(f"Total video chapters detected: {chapters_count}")

    return script, errors, warnings


def parse_and_validate_script(raw_data: dict, config: Optional[dict] = None, require_youtube: bool = True) -> ShadowScript:
    """Parses and validates, raising ValueError with all errors if invalid."""
    script, _, _ = validate_script_full(raw_data, config, require_youtube=require_youtube)
    return script
