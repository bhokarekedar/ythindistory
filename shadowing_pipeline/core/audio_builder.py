"""Audio Track Assembly & Waveform Amplitude Pre-computation.

Concatenates speech clips and exact silence intervals into a single master audio track
using FFmpeg concat demuxer, and extracts frame-by-frame waveform amplitudes at 30fps.
"""

import os
import subprocess
import wave
from pathlib import Path
from typing import List, Tuple
import numpy as np
from shadowing_pipeline.core.timeline import TimelineEvent


class AudioBuilder:
    def __init__(self, temp_dir: Path):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def assemble_master_audio(
        self, events: List[TimelineEvent], output_path: str
    ) -> str:
        """Assembles all speech and silence segments into a single master WAV file."""
        output_wav = str(Path(output_path).resolve())
        concat_list_file = self.temp_dir / "audio_concat.txt"

        lines = []
        silence_idx = 0

        for ev in events:
            if ev.type == "speech" and ev.audio_path and os.path.exists(ev.audio_path):
                # Check if speech event has padding (e.g. section_title)
                actual_dur = self._get_wav_duration(ev.audio_path)
                diff = ev.duration - actual_dur
                lines.append(f"file '{Path(ev.audio_path).resolve()}'")
                if diff > 0.05:
                    silence_wav = self._generate_silence(diff, f"pad_{silence_idx}")
                    lines.append(f"file '{silence_wav}'")
                    silence_idx += 1
            else:
                # Silence event
                silence_wav = self._generate_silence(ev.duration, f"silence_{silence_idx}")
                lines.append(f"file '{silence_wav}'")
                silence_idx += 1

        with open(concat_list_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        # Concat using ffmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_file),
            "-c:a",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            output_wav,
        ]
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
        return output_wav

    def _generate_silence(self, duration: float, name_tag: str) -> str:
        """Generates a pure silence WAV file of the exact duration."""
        silence_file = self.temp_dir / f"{name_tag}_{duration:.3f}.wav"
        if not silence_file.exists():
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=44100:cl=mono",
                "-t",
                f"{duration:.3f}",
                "-c:a",
                "pcm_s16le",
                str(silence_file),
            ]
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
            )
        return str(silence_file.resolve())

    def _get_wav_duration(self, wav_path: str) -> float:
        with wave.open(wav_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)

    def extract_frame_amplitudes(
        self, master_wav: str, fps: int = 30, num_bars: int = 52
    ) -> np.ndarray:
        """Extracts normalized multi-bar frequency/envelope heights for each video frame.

        Returns:
            np.ndarray of shape (num_frames, num_bars) with values in [0.0, 1.0].
        """
        with wave.open(master_wav, "rb") as wf:
            n_channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)

        # Parse 16-bit PCM
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
        if n_channels > 1:
            samples = samples.reshape(-1, n_channels).mean(axis=1)

        samples /= 32768.0  # Normalize to [-1.0, 1.0]

        samples_per_frame = int(round(sample_rate / fps))
        total_video_frames = int(np.ceil(len(samples) / samples_per_frame))

        # Pad samples if needed
        total_needed = total_video_frames * samples_per_frame
        if len(samples) < total_needed:
            samples = np.pad(samples, (0, total_needed - len(samples)))

        bar_heights = np.zeros((total_video_frames, num_bars), dtype=np.float32)

        # Pre-generate pseudo-frequency pattern weights for nice organic shape
        x_indices = np.linspace(-1.5, 1.5, num_bars)
        bell_curve = np.exp(-0.5 * (x_indices**2))
        bell_curve /= bell_curve.max()

        for f_idx in range(total_video_frames):
            start = f_idx * samples_per_frame
            end = start + samples_per_frame
            frame_slice = samples[start:end]

            # RMS Energy
            rms = np.sqrt(np.mean(frame_slice**2))
            if rms < 0.005:
                # Silence: flat
                bar_heights[f_idx, :] = 0.0
            else:
                # Active audio: non-linear scaling for responsive visual movement
                norm_amp = min(1.0, float(rms * 4.5))
                # Add slight organic per-bar wave modulation
                phase = f_idx * 0.25
                modulation = 0.75 + 0.25 * np.sin(x_indices * 4.0 + phase)
                bar_heights[f_idx, :] = np.clip(
                    norm_amp * bell_curve * modulation, 0.05, 1.0
                )

        return bar_heights

