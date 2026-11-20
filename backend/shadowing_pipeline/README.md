# English Shadowing YouTube Video Generator Pipeline

A high-performance Python script-to-video pipeline for English shadowing YouTube channels (inspired by [English Fluency Teacher](https://www.youtube.com/watch?v=r863keDLrbU)).

## Features
- **1080p 30fps Full HD**: Warm orange-yellow gradient with wavy curve patterns and large bold Poppins typography.
- **Word-Level Pill Highlighting**: Highlights words with a white rounded rectangle pill in sync with speech timestamps.
- **Shadowing Timeline Logic**:
  - Repeats sentence $N$ times (default 2).
  - Speech playback with active animated audio waveforms.
  - "Your turn" repetition pause of $(audio\_duration + buffer\_seconds)$ with a smooth filling progress bar and dimmed waveform.
- **Zero-RAM Streaming**: Directly streams uncompressed frames to FFmpeg's stdin pipe. 60-minute videos render in constant memory (< 150MB RAM).
- **Disk Caching**: TTS audio and transcriptions are cached on disk keyed by `hash(voice + text)`, avoiding duplicate TTS calls.
- **Punctuation & Contraction Alignment**: Preserves punctuation ("Let's", "don't", "begin.") while aligning transcript words.
- **Dual Interface**: Full CLI (`python make_video.py script.json`) and Web UI with live progress and embedded video player.
- **Debug Artifacts**: Automatically outputs `.mp4` video, standard `.srt` subtitle file, and `timeline.json`.

---

## Folder Structure
```
├── shadowing_pipeline/
│   ├── assets/
│   │   ├── fonts/           # Poppins-Bold.ttf & Poppins-ExtraBold.ttf
│   │   ├── images/          # illustration.png & logo.png
│   │   └── audio_cache/     # Cached .wav and .json transcription files
│   ├── config/
│   │   └── theme.json       # Visual style, colors, fonts, margins, waveform
│   ├── core/
│   │   ├── schema.py        # Pydantic models & validation
│   │   ├── audio_provider.py# TTS & ASR black-box provider with disk cache
│   │   ├── word_aligner.py  # Monotone sequence word alignment
│   │   ├── timeline.py      # Timeline event flattening
│   │   ├── audio_builder.py # FFmpeg audio concat & waveform analysis
│   │   ├── visual_engine.py # Pillow frame renderer
│   │   ├── video_renderer.py# FFmpeg streaming video encoder
│   │   ├── exporters.py     # SRT and timeline.json generation
│   │   └── pipeline.py      # Unified orchestrator
│   ├── static/
│   │   └── index.html       # Web UI
│   ├── server.py            # FastAPI Web Server
│   └── requirements.txt
├── make_video.py            # CLI entry point
├── sample_script.json       # Runnable sample script
└── output/                  # Rendered MP4, SRT, and timeline files
```

---

## How to Plug In Your Real Black-Box Functions

In `shadowing_pipeline/core/audio_provider.py` or when initializing the pipeline in Python:

```python
from shadowing_pipeline.core.pipeline import ShadowingVideoPipeline

def my_custom_tts(text: str, voice: str) -> str:
    # Your TTS implementation: returns path to generated audio file (.wav / .mp3)
    return "/path/to/generated_audio.wav"

def my_custom_transcribe(audio_path: str) -> list[dict]:
    # Your ASR implementation: returns list of {"word": str, "start": float, "end": float}
    return [
        {"word": "Hello", "start": 0.1, "end": 0.4},
        {"word": "world", "start": 0.45, "end": 0.9}
    ]

pipeline = ShadowingVideoPipeline(
    custom_tts=my_custom_tts,
    custom_transcribe=my_custom_transcribe
)
pipeline.run("script.json", output_dir="output")
```

---

## CLI Usage

```bash
# Render full video
python make_video.py sample_script.json

# Fast preview (first 5 segments)
python make_video.py sample_script.json --preview

# Custom output directory
python make_video.py sample_script.json --output-dir output --name my_lesson
```

---

## Web UI Usage

```bash
python -m shadowing_pipeline.server
```
Visit `http://localhost:8000` to paste script JSON, preview first 5 segments, watch live render progress, and download MP4/SRT files.

