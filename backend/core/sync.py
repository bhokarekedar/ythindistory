import ffmpeg
import os
import wave
import contextlib

# ─────────────────────────────────────────────────────────────────────────────
# TARGET AUDIO SPEC
# Google TTS outputs 16kHz mono 16-bit PCM.
# We upsample to 48kHz stereo for broadcast compatibility.
# ─────────────────────────────────────────────────────────────────────────────
TARGET_RATE = 48000
TARGET_CHANNELS = 2
TARGET_SAMPWIDTH = 2  # 16-bit

# Minimum silence gap enforced between any two consecutive TTS segments.
# Prevents sentences from running together while keeping narration tight.
MIN_PAUSE_S = 0.40

# Silence added after the last segment before audio ends.
TRAILING_SILENCE_S = 1.5


class AudioSynchronizer:
    def __init__(self, max_speed_change: float = 0.15, rewrite_threshold: float = 1.15):
        self.max_speed_change = max_speed_change
        self.rewrite_threshold = rewrite_threshold

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    def get_video_duration(self, video_path: str) -> float:
        import subprocess
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())

    def get_audio_duration(self, audio_path: str) -> float:
        with contextlib.closing(wave.open(audio_path, "r")) as f:
            return f.getnframes() / float(f.getframerate())

    def _resample_wav_ffmpeg(self, input_path: str, output_path: str):
        """Resample a WAV to TARGET_RATE / stereo / 16-bit. Called once per segment."""
        (
            ffmpeg
            .input(input_path)
            .audio
            .filter("aresample", TARGET_RATE)
            .filter("aformat", sample_fmts="s16", channel_layouts="stereo")
            .output(output_path, ar=TARGET_RATE, ac=TARGET_CHANNELS)
            .run(quiet=True, overwrite_output=True)
        )

    def _silence_bytes(self, n_frames: int) -> bytes:
        return b"\x00" * (n_frames * TARGET_CHANNELS * TARGET_SAMPWIDTH)

    def _apply_watermarks(self, v_stream, settings, watermark_path="/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/watermark.png"):
        """Helper to apply the watermark to an ffmpeg video stream at multiple corners."""
        if not settings:
            return v_stream
            
        corners = {
            "topLeft": getattr(settings, "topLeft", None),
            "topRight": getattr(settings, "topRight", None),
            "bottomLeft": getattr(settings, "bottomLeft", None),
            "bottomRight": getattr(settings, "bottomRight", None)
        }
        
        enabled_corners = [(pos, corner) for pos, corner in corners.items() if corner and corner.enabled]
        if not enabled_corners:
            return v_stream
            
        wm_input = ffmpeg.input(watermark_path)
        splits = wm_input.split() if len(enabled_corners) > 1 else [wm_input]
        
        for i, (position, corner) in enumerate(enabled_corners):
            wm = splits[i].filter('scale', w=corner.size, h='-1')
            main_w, main_h = "main_w", "main_h"
            
            # Determine coordinates
            if position == "topLeft":
                x, y = corner.offsetX, corner.offsetY
            elif position == "topRight":
                x, y = f"{main_w}-overlay_w-{corner.offsetX}", corner.offsetY
            elif position == "bottomLeft":
                x, y = corner.offsetX, f"{main_h}-overlay_h-{corner.offsetY}"
            elif position == "bottomRight":
                x, y = f"{main_w}-overlay_w-{corner.offsetX}", f"{main_h}-overlay_h-{corner.offsetY}"
                
            v_stream = ffmpeg.overlay(v_stream, wm, x=x, y=y)
            
        return v_stream

    # ─────────────────────────────────────────────────────────────────────────
    # Step 0: Compute audio timeline
    # This is the KEY fix — compute WHERE each sentence starts in the output
    # audio, enforcing minimum pauses so sentences never run together.
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_audio_timeline(self, segments: list, job_dir: str) -> list:
        """
        Returns an augmented segment list with two new fields per segment:
          - audio_start:  exact second in the output WAV where TTS begins
          - audio_end:    exact second where TTS ends (audio_start + tts_dur)
          - tts_dur:      actual duration of the TTS WAV file

        Placement rules:
          1. First segment: starts at its original start time (no shift).
          2. Each subsequent segment: starts at
               max(seg.original_start, prev_audio_end + MIN_PAUSE_S)
             This means:
               - If TTS was SHORT (narrator spoke fast): original timing preserved.
               - If TTS was LONG (ran over): next sentence is pushed to after
                 prev TTS ends + minimum pause. Never overlapping. Never rushing.

        This timeline drives BOTH the audio WAV and the video timeline — they
        are always in sync because they share the same start/end times.
        """
        resampled_dir = os.path.join(job_dir, "resampled_wavs")
        os.makedirs(resampled_dir, exist_ok=True)

        timeline = []
        prev_audio_end = 0.0

        for i, seg in enumerate(segments):
            seg_id = seg.get("id", i)
            src = seg["audio_path"]
            dst = os.path.join(resampled_dir, f"{seg_id:04d}_48k.wav")

            # Resample once (cached)
            if not os.path.exists(dst):
                self._resample_wav_ffmpeg(src, dst)

            with contextlib.closing(wave.open(dst, "r")) as f:
                tts_dur = f.getnframes() / float(f.getframerate())

            # Compute placement
            if i == 0:
                audio_start = seg["start"]
            else:
                # Respect original timing unless TTS overran — then push forward
                audio_start = max(seg["start"], prev_audio_end + MIN_PAUSE_S)

            audio_end = audio_start + tts_dur
            prev_audio_end = audio_end

            entry = dict(seg)
            entry["audio_start"] = audio_start
            entry["audio_end"] = audio_end
            entry["tts_dur"] = tts_dur
            entry["resampled_path"] = dst
            timeline.append(entry)

            print(
                f"  [Timeline] Seg {seg_id}: orig=[{seg['start']:.2f}-{seg['end']:.2f}] "
                f"audio=[{audio_start:.2f}-{audio_end:.2f}] tts={tts_dur:.3f}s"
            )

        total_audio_dur = prev_audio_end + TRAILING_SILENCE_S
        print(f"  [Timeline] Total audio duration: {total_audio_dur:.2f}s")
        return timeline, total_audio_dur

    # ─────────────────────────────────────────────────────────────────────────
    # Step A: Build ONE continuous lossless WAV
    # ─────────────────────────────────────────────────────────────────────────

    def _build_audio_track(self, timeline: list, total_audio_dur: float, job_dir: str) -> str:
        """
        Builds a single WAV that spans the full output duration.

        Each TTS segment is placed at its computed audio_start sample position.
        Gaps between segments are clean silence (PCM zeros).

        Built entirely in pure Python bytearray math:
          - Zero FFmpeg encoding passes on the audio
          - Zero AAC chunk boundaries
          - Zero click/pop artifacts
          - Perfect silence in gaps = natural pause between sentences
        """
        total_frames = int(total_audio_dur * TARGET_RATE) + TARGET_RATE  # +1s overflow guard
        print(f"  [Audio] Building unified PCM track: {total_audio_dur:.1f}s @ {TARGET_RATE}Hz stereo...")

        # Allocate silence buffer
        pcm_buffer = bytearray(self._silence_bytes(total_frames))

        for entry in timeline:
            seg_id = entry.get("id", 0)
            dst = entry["resampled_path"]

            with contextlib.closing(wave.open(dst, "r")) as f:
                pcm = f.readframes(f.getnframes())

            start_frame = int(entry["audio_start"] * TARGET_RATE)
            byte_offset = start_frame * TARGET_CHANNELS * TARGET_SAMPWIDTH
            max_bytes = len(pcm_buffer) - byte_offset

            if max_bytes <= 0:
                print(f"  [Audio] WARNING: seg {seg_id} beyond buffer, skipping")
                continue

            write_pcm = pcm[:max_bytes] if len(pcm) > max_bytes else pcm
            pcm_buffer[byte_offset: byte_offset + len(write_pcm)] = write_pcm
            print(f"  [Audio] Seg {seg_id}: wrote {len(write_pcm)//4} frames at {entry['audio_start']:.3f}s")

        # Write final WAV
        audio_track_path = os.path.join(job_dir, "narrator_audio_track.wav")
        with wave.open(audio_track_path, "w") as out_wav:
            out_wav.setnchannels(TARGET_CHANNELS)
            out_wav.setsampwidth(TARGET_SAMPWIDTH)
            out_wav.setframerate(TARGET_RATE)
            out_wav.writeframes(bytes(pcm_buffer))

        print(f"  [Audio] DONE: {audio_track_path}")
        return audio_track_path

    # ─────────────────────────────────────────────────────────────────────────
    # Step B: Build the video-only timeline driven by audio timestamps
    # ─────────────────────────────────────────────────────────────────────────

    def _build_video_timeline(self, timeline: list, original_video_path: str,
                              total_audio_dur: float, job_dir: str, watermark_settings=None, text_watermark_settings=None) -> str:
        """
        Produces a video-only MP4 retimed to exactly match the audio timeline.

        For each segment:
          - The original video clip [seg.start, seg.end] is extracted and
            time-scaled so its duration matches tts_dur (the audio duration).
          - This ensures audio and video are always in sync.

        For gaps between segments (silence in audio):
          - We play the original video at its natural speed to fill the gap.

        Audio is NOT embedded here; it comes from the unified WAV.
        The total video duration = total_audio_dur (perfectly matches audio).
        """
        chunks_dir = os.path.join(job_dir, "video_chunks")
        os.makedirs(chunks_dir, exist_ok=True)
        concat_list_path = os.path.join(chunks_dir, "concat_video.txt")
        concat_lines = []
        chunk_idx = 0
        video_cursor = 0.0   # Tracks position in the ORIGINAL video
        audio_cursor = 0.0   # Tracks position in the OUTPUT timeline

        for entry in timeline:
            seg_id = entry.get("id", 0)
            orig_start = entry["start"]
            orig_end = entry["end"]
            orig_dur = max(orig_end - orig_start, 0.05)
            audio_start = entry["audio_start"]
            audio_end = entry["audio_end"]
            tts_dur = entry["tts_dur"]

            # ── Gap chunk: original video played at natural speed ──────────
            # Gap in audio = silence between prev TTS end and this TTS start
            gap_dur = audio_start - audio_cursor
            if gap_dur > 0.05:
                # How much original video to use for this gap?
                # Use the original video gap (original silence between segments)
                orig_gap = orig_start - video_cursor
                if orig_gap < 0.05:
                    orig_gap = gap_dur  # fallback if no original gap
                # Clamp: don't use more original video than available
                orig_gap = min(orig_gap, self.get_video_duration(original_video_path) - video_cursor)
                orig_gap = max(orig_gap, 0.05)

                chunk_path = os.path.join(chunks_dir, f"chunk_{chunk_idx:04d}_gap.mp4")
                if not os.path.exists(chunk_path):
                    # Scale video speed to fill exactly gap_dur output time
                    pts_scale = orig_gap / gap_dur  # <1 = speed up, >1 = slow
                    v = (
                        ffmpeg.input(original_video_path).video
                        .filter("trim", start=video_cursor, duration=orig_gap)
                        .filter("setpts", "PTS-STARTPTS")
                        .filter("setpts", f"{gap_dur / orig_gap}*PTS")
                        .filter("scale", 1280, 720).filter("setsar", 1)
                        .filter("fps", fps=30, round="near").filter("format", "yuv420p")
                    )
                    v = self._apply_watermarks(v, watermark_settings, "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/watermark.png")
                    v = self._apply_watermarks(v, text_watermark_settings, "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/textWatermark.png")
                    a = ffmpeg.input(
                        "anullsrc=channel_layout=stereo:sample_rate=48000",
                        format="lavfi", t=gap_dur
                    ).audio
                    out = ffmpeg.output(v, a, chunk_path,
                                        vcodec="libx264", acodec="aac",
                                        ac=2, ar=48000,
                                        **{"crf": "18", "preset": "fast"})
                    try:
                        ffmpeg.run(out, quiet=True, overwrite_output=True)
                    except ffmpeg.Error as e:
                        print(f"FFmpeg Error (gap chunk {chunk_idx}):",
                              e.stderr.decode("utf8") if e.stderr else str(e))
                        raise
                concat_lines.append(f"file '{os.path.abspath(chunk_path)}'")
                chunk_idx += 1
                video_cursor += orig_gap
                audio_cursor = audio_start

            # ── Segment chunk: original video retimed to match TTS ─────────
            chunk_path = os.path.join(chunks_dir, f"chunk_{chunk_idx:04d}_seg.mp4")
            if not os.path.exists(chunk_path):
                # PTS scale: orig_dur seconds of video → tts_dur seconds of output
                pts_factor = tts_dur / orig_dur   # >1 = slow down, <1 = speed up
                v = (
                    ffmpeg.input(original_video_path).video
                    .filter("trim", start=orig_start, duration=orig_dur)
                    .filter("setpts", "PTS-STARTPTS")
                    .filter("setpts", f"{pts_factor}*PTS")
                    .filter("scale", 1280, 720).filter("setsar", 1)
                    .filter("fps", fps=30, round="near").filter("format", "yuv420p")
                )
                v = self._apply_watermarks(v, watermark_settings, "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/watermark.png")
                v = self._apply_watermarks(v, text_watermark_settings, "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/textWatermark.png")
                a = ffmpeg.input(
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                    format="lavfi", t=tts_dur
                ).audio
                out = ffmpeg.output(v, a, chunk_path,
                                    vcodec="libx264", acodec="aac",
                                    ac=2, ar=48000,
                                    **{"crf": "18", "preset": "fast"})
                try:
                    ffmpeg.run(out, quiet=True, overwrite_output=True)
                except ffmpeg.Error as e:
                    print(f"FFmpeg Error (seg chunk {chunk_idx} id={seg_id}):",
                          e.stderr.decode("utf8") if e.stderr else str(e))
                    raise

            concat_lines.append(f"file '{os.path.abspath(chunk_path)}'")
            chunk_idx += 1
            video_cursor = orig_end
            audio_cursor = audio_end

        # ── Final trailing silence gap ─────────────────────────────────────
        trailing_dur = total_audio_dur - audio_cursor
        if trailing_dur > 0.1:
            # Use remaining original video (or freeze if exhausted)
            orig_remaining = self.get_video_duration(original_video_path) - video_cursor
            if orig_remaining > 0.1:
                use_dur = min(orig_remaining, trailing_dur)
                chunk_path = os.path.join(chunks_dir, f"chunk_{chunk_idx:04d}_trail.mp4")
                if not os.path.exists(chunk_path):
                    pts_factor = trailing_dur / use_dur
                    v = (
                        ffmpeg.input(original_video_path).video
                        .filter("trim", start=video_cursor, duration=use_dur)
                        .filter("setpts", "PTS-STARTPTS")
                        .filter("setpts", f"{pts_factor}*PTS")
                        .filter("scale", 1280, 720).filter("setsar", 1)
                        .filter("fps", fps=30, round="near").filter("format", "yuv420p")
                    )
                    v = self._apply_watermarks(v, watermark_settings, "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/watermark.png")
                    v = self._apply_watermarks(v, text_watermark_settings, "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/textWatermark.png")
                    a = ffmpeg.input(
                        "anullsrc=channel_layout=stereo:sample_rate=48000",
                        format="lavfi", t=trailing_dur
                    ).audio
                    out = ffmpeg.output(v, a, chunk_path,
                                        vcodec="libx264", acodec="aac",
                                        ac=2, ar=48000,
                                        **{"crf": "18", "preset": "fast"})
                    ffmpeg.run(out, quiet=True, overwrite_output=True)
                concat_lines.append(f"file '{os.path.abspath(chunk_path)}'")

        # ── Concatenate all video chunks ───────────────────────────────────
        with open(concat_list_path, "w") as f:
            f.write("\n".join(concat_lines))

        video_only_path = os.path.join(job_dir, "video_only.mp4")
        if not os.path.exists(video_only_path):
            try:
                out = ffmpeg.input(concat_list_path, format="concat", safe=0)
                ffmpeg.output(out, video_only_path, c="copy").run(quiet=True, overwrite_output=True)
            except ffmpeg.Error as e:
                print("FFmpeg Error (video concat):",
                      e.stderr.decode("utf8") if e.stderr else str(e))
                raise

        print(f"  [Video] DONE: {video_only_path}")
        return video_only_path

    # ─────────────────────────────────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────────────────────────────────

    def build_timeline(self, segments: list, original_video_path: str,
                       output_path: str, job_dir: str = "temp", watermark_settings=None, text_watermark_settings=None):
        """
        Produces the final video:
          0. Compute audio timeline  → where each sentence starts/ends in output
          A. Build unified lossless WAV  → pure Python PCM, zero glitches
          B. Build retimed video-only timeline  → driven by audio timestamps
          C. Mux A+B once with loudnorm  → single encode pass
          D. Prepend intro with crossfade  → (if intro.mp4 exists)

        Both audio (A) and video (B) are driven by the SAME timeline computed
        in step 0. This guarantees A/V sync at every sentence boundary.
        """
        # ── Step 0: Shared timeline ───────────────────────────────────────
        print("\n[Sync] Step 0: Computing audio timeline (sentence pacing)...")
        timeline, total_audio_dur = self._compute_audio_timeline(segments, job_dir)

        # ── Step A: Lossless audio WAV ────────────────────────────────────
        print(f"\n[Sync] Step A: Building unified narrator WAV ({total_audio_dur:.1f}s)...")
        audio_track_path = self._build_audio_track(timeline, total_audio_dur, job_dir)

        # ── Step B: Video timeline ────────────────────────────────────────
        print("\n[Sync] Step B: Building retimed video timeline...")
        video_only_path = self._build_video_timeline(timeline, original_video_path, total_audio_dur, job_dir, watermark_settings, text_watermark_settings)

        # ── Step C: Mux video + clean audio ──────────────────────────────
        print("\n[Sync] Step C: Muxing video + clean audio (single encode pass)...")
        mixed_video_path = os.path.join(job_dir, "mixed_temp.mp4")
        if not os.path.exists(mixed_video_path):
            try:
                video_in = ffmpeg.input(video_only_path).video
                audio_in = (
                    ffmpeg.input(audio_track_path).audio
                    # Loudnorm: normalize volume across the entire track in one pass
                    .filter("loudnorm", I="-16", TP="-1.5", LRA="11")
                )
                out = ffmpeg.output(
                    video_in, audio_in,
                    mixed_video_path,
                    vcodec="copy",          # Video already encoded — no re-encode
                    acodec="aac",
                    ac=TARGET_CHANNELS,
                    ar=TARGET_RATE,
                    audio_bitrate="192k",
                )
                ffmpeg.run(out, quiet=True, overwrite_output=True)
            except ffmpeg.Error as e:
                print("FFmpeg Error (mux):", e.stderr.decode("utf8") if e.stderr else str(e))
                raise

        # ── Step D: Prepend Intro ─────────────────────────────────────────
        intro_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/intro.mp4"
        if os.path.exists(intro_path):
            print("\n[Sync] Step D: Prepending intro with crossfade...")
            intro = ffmpeg.input(intro_path)
            intro_v = (
                intro.video
                .filter("scale", 1280, 720).filter("setsar", 1)
                .filter("fps", fps=30, round="near").filter("format", "yuv420p")
                .filter("settb", "1/30")
            )
            intro_a = intro.audio.filter("aresample", TARGET_RATE)

            main = ffmpeg.input(mixed_video_path)
            main_v = (
                main.video
                .filter("fps", fps=30, round="near")
                .filter("settb", "1/30")
            )
            main_a = main.audio

            fade_duration = 1.0
            intro_duration = self.get_video_duration(intro_path)
            offset = max(0, intro_duration - fade_duration)

            joined_v = ffmpeg.filter([intro_v, main_v], "xfade",
                                     transition="fade", duration=fade_duration, offset=offset)
            joined_a = ffmpeg.filter([intro_a, main_a], "acrossfade", d=fade_duration)

            out = ffmpeg.output(joined_v, joined_a, output_path,
                                vcodec="libx264", acodec="aac",
                                ac=TARGET_CHANNELS, ar=TARGET_RATE)
            try:
                ffmpeg.run(out, quiet=True, overwrite_output=True)
            except ffmpeg.Error as e:
                print("FFmpeg Error (crossfade):", e.stderr.decode("utf8") if e.stderr else str(e))
                raise
        else:
            ffmpeg.output(ffmpeg.input(mixed_video_path), output_path, c="copy").run(
                quiet=True, overwrite_output=True
            )

        print(f"\n[Sync] ✅ Final output: {output_path}")
