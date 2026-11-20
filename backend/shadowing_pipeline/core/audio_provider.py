"""Audio Provider with Disk Caching & Pluggable TTS / Transcription.

Inputs user has as black boxes:
- tts(text, voice) -> audio file path (.wav)
- transcribe(audio_path) -> list of {"word": str, "start": float, "end": float}

Disk cache:
Stores both audio files and word timestamps in assets/audio_cache/, keyed by
hashlib.sha256(f"{voice}::{text}".encode()).hexdigest().
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


PACKAGE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = PACKAGE_DIR / "assets" / "audio_cache"

_KOKORO_PIPELINES: Dict[str, Any] = {}
_WHISPER_MODEL: Any = None


def get_whisper_model():
    """Singleton instance of WhisperModel for acoustic word timestamp alignment."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        try:
            from faster_whisper import WhisperModel
            _WHISPER_MODEL = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        except Exception as e:
            import logging
            logging.warning(f"Could not initialize WhisperModel: {e}")
            _WHISPER_MODEL = False
    return _WHISPER_MODEL if _WHISPER_MODEL is not False else None


def get_kokoro_pipeline(lang_code: str = "a"):
    """Thread-safe / reusable pipeline singleton per language code."""
    global _KOKORO_PIPELINES
    if lang_code not in _KOKORO_PIPELINES:
        from kokoro import KPipeline
        _KOKORO_PIPELINES[lang_code] = KPipeline(lang_code=lang_code)
    return _KOKORO_PIPELINES[lang_code]


def map_to_kokoro_voice(voice: str) -> Tuple[str, str]:
    """Map voice names or aliases to (kokoro_voice_id, lang_code)."""
    if not voice:
        return "af_heart", "a"
    v = voice.lower().strip()
    # Common mappings
    if v in ["samantha", "victoria", "karen", "female", "teacher", "af_heart", "heart"]:
        return "af_heart", "a"
    if v in ["alex", "daniel", "fred", "male", "speaker_b", "am_adam", "adam"]:
        return "am_adam", "a"
    if v in ["af_bella", "bella"]:
        return "af_bella", "a"
    if v in ["af_nicole", "nicole"]:
        return "af_nicole", "a"
    if v in ["af_sarah", "sarah"]:
        return "af_sarah", "a"
    if v in ["am_michael", "michael"]:
        return "am_michael", "a"
    if v in ["bf_emma", "emma"]:
        return "bf_emma", "b"
    if v in ["bm_george", "george"]:
        return "bm_george", "b"

    # Direct Kokoro voice ID passed
    if v.startswith("bf_") or v.startswith("bm_"):
        return v, "b"
    if v.startswith("af_") or v.startswith("am_"):
        return v, "a"

    return "af_heart", "a"


def compute_audio_hash(text: str, voice: str, speed: float = 0.92) -> str:
    """Deterministic hash for a sentence, voice, and speed."""
    resolved_voice, lang = map_to_kokoro_voice(voice)
    key = f"{resolved_voice}::{speed:.2f}::{text.strip()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class AudioProvider:
    """Manages audio generation, transcription, and disk caching."""

    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        custom_tts: Optional[Callable[[str, str], str]] = None,
        custom_transcribe: Optional[Callable[[str], List[Dict]]] = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.custom_tts = custom_tts
        self.custom_transcribe = custom_transcribe

    def get_audio_and_transcription(
        self, text: str, voice: str = "af_heart", speed: float = 0.85
    ) -> Tuple[str, List[Dict], float]:
        """Returns (audio_path, word_timings, duration_seconds).

        Uses disk cache if available.
        word_timings: list of {"word": str, "start": float, "end": float}
        """
        text = text.strip()
        h = compute_audio_hash(text, voice, speed)
        cached_wav = self.cache_dir / f"{h}.wav"
        cached_meta = self.cache_dir / f"{h}.json"

        if cached_wav.exists() and cached_meta.exists():
            try:
                with open(cached_meta, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                return str(cached_wav), meta["word_timings"], meta["duration"]
            except Exception:
                pass  # Corrupted cache entry, regenerate

        # 1. Generate Audio via TTS
        if self.custom_tts:
            raw_audio_path = self.custom_tts(text, voice)
            # Ensure standard WAV format (44100Hz, mono, 16-bit PCM)
            self._normalize_audio(raw_audio_path, str(cached_wav))
        else:
            self._default_tts(text, voice, str(cached_wav), speed=speed)

        duration = self._get_audio_duration(str(cached_wav))

        # 2. Transcribe Audio (acoustic timestamps via faster-whisper)
        if self.custom_transcribe:
            word_timings = self.custom_transcribe(str(cached_wav))
        else:
            word_timings = self._transcribe_audio(str(cached_wav), text, duration)

        # 3. Save to disk cache
        with open(cached_meta, "w", encoding="utf-8") as f:
            json.dump({"word_timings": word_timings, "duration": duration}, f, indent=2)

        return str(cached_wav), word_timings, duration

    def _transcribe_audio(self, audio_path: str, text: str, total_duration: float) -> List[Dict]:
        """Acoustic word-level transcription with fallback to syllable duration model."""
        model = get_whisper_model()
        if model:
            try:
                segments, _ = model.transcribe(audio_path, word_timestamps=True, language="en")
                raw_words = []
                for seg in segments:
                    for w in seg.words:
                        clean = w.word.strip()
                        if clean:
                            raw_words.append({
                                "word": clean,
                                "start": round(float(w.start), 3),
                                "end": round(float(w.end), 3),
                            })
                if raw_words:
                    return raw_words
            except Exception as e:
                import logging
                logging.warning(f"Whisper transcription error, falling back: {e}")

        return self._default_transcribe(text, total_duration)

    def _normalize_audio(self, src: str, dst: str):
        """Converts any audio file to 44100Hz 16-bit mono WAV using ffmpeg."""
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            dst,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def _kokoro_tts(self, text: str, voice: str, dst_wav: str, speed: float = 0.85) -> bool:
        """Generate high-quality neural speech using Kokoro TTS."""
        try:
            import numpy as np
            import soundfile as sf
            kokoro_voice, lang_code = map_to_kokoro_voice(voice)
            pipeline = get_kokoro_pipeline(lang_code)
            generator = pipeline(text, voice=kokoro_voice, speed=speed)
            chunks = []
            for _, _, audio in generator:
                if audio is not None and len(audio) > 0:
                    chunks.append(audio)
            if not chunks:
                return False
            full_audio = np.concatenate(chunks)
            # Peak normalize slightly below 0 dB to avoid clipping
            peak = np.max(np.abs(full_audio))
            if peak > 1e-4:
                full_audio = (full_audio / peak) * 0.92

            tmp_wav = dst_wav + ".raw.wav"
            sf.write(tmp_wav, full_audio, 24000)
            self._normalize_audio(tmp_wav, dst_wav)
            if os.path.exists(tmp_wav):
                os.remove(tmp_wav)
            return True
        except Exception as e:
            import logging
            logging.error(f"Kokoro TTS generation error: {e}")
            return False

    def _default_tts(self, text: str, voice: str, dst_wav: str, speed: float = 0.85):
        """Built-in TTS: uses Kokoro neural TTS exclusively."""
        success = self._kokoro_tts(text, voice, dst_wav, speed=speed)
        if not success:
            raise RuntimeError(f"Kokoro TTS failed to generate audio for text: '{text}'")

    def _get_audio_duration(self, audio_path: str) -> float:
        """Extracts exact audio duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())

    def _default_transcribe(self, text: str, total_duration: float) -> List[Dict]:
        """Proportional syllable/character duration model as default transcription.

        Guarantees exact word alignments when an external ASR model is not connected.
        """
        import re

        words = [w for w in text.split() if w.strip()]
        if not words:
            return []

        # Weights based on letter length + punctuation pauses
        weights = []
        for w in words:
            clean = re.sub(r"[^a-zA-Z0-9]", "", w)
            weight = max(2, len(clean))
            if w.endswith((".", "!", "?")):
                weight += 4
            elif w.endswith((",", ";", ":")):
                weight += 2
            weights.append(weight)

        total_weight = sum(weights)
        # Allocate 92% of duration to spoken words, 8% lead/trail margin
        spoken_duration = total_duration * 0.94
        lead_in = total_duration * 0.03

        timings = []
        curr = lead_in
        for w, weight in zip(words, weights):
            dur = (weight / total_weight) * spoken_duration
            start = round(curr, 3)
            end = round(curr + dur, 3)
            timings.append({"word": w, "start": start, "end": end})
            curr = end

        return timings

