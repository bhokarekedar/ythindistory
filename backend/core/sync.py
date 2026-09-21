import ffmpeg
import os
import wave
import contextlib

class AudioSynchronizer:
    def __init__(self, max_speed_change: float = 0.15, rewrite_threshold: float = 1.15):
        self.max_speed_change = max_speed_change
        self.rewrite_threshold = rewrite_threshold

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
        with contextlib.closing(wave.open(audio_path, 'r')) as f:
            frames = f.getnframes()
            rate = f.getframerate()
            return frames / float(rate)

    def process_segment(self, audio_path: str, target_duration: float, output_path: str) -> bool:
        """
        Adjusts the duration of the audio to match the target duration.
        Returns True if successful, False if the audio is too long and requires a rewrite.
        """
        duration = self.get_audio_duration(audio_path)
        
        if duration <= target_duration:
            # Pad with silence if it's shorter
            # apad pads the audio stream with silence
            stream = ffmpeg.input(audio_path)
            stream = ffmpeg.filter(stream, 'apad', whole_dur=f"{target_duration}")
            stream = ffmpeg.output(stream, output_path, acodec='pcm_s16le', ac=1, ar='16k', t=target_duration)
            ffmpeg.run(stream, quiet=True, overwrite_output=True)
            return True
            
        elif duration <= target_duration * self.rewrite_threshold:
            # Adjust speed if it's slightly longer
            speed_factor = duration / target_duration
            stream = ffmpeg.input(audio_path)
            stream = ffmpeg.filter(stream, 'atempo', speed_factor)
            stream = ffmpeg.output(stream, output_path, acodec='pcm_s16le', ac=1, ar='16k')
            ffmpeg.run(stream, quiet=True, overwrite_output=True)
            return True
            
        else:
            # Too long, requires LLM rewrite
            return False

    def build_timeline(self, segments: list, original_video_path: str, output_path: str):
        """
        Mixes all aligned audio segments onto the final video and prepends intro if exists.
        segments is a list of dicts: {"start": float, "audio_path": str}
        """
        inputs = [ffmpeg.input(original_video_path).video]
        audio_inputs = []
        
        for seg in segments:
            audio_in = ffmpeg.input(seg["audio_path"])
            delay_ms = int(seg["start"] * 1000)
            delayed_audio = ffmpeg.filter(audio_in, 'adelay', f"{delay_ms}|{delay_ms}")
            audio_inputs.append(delayed_audio)
            
        if audio_inputs:
            mixed_audio = ffmpeg.filter(audio_inputs, 'amix', inputs=len(audio_inputs), normalize=0)
        else:
            mixed_audio = ffmpeg.input(original_video_path).audio
            
        intro_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/intro.mp4"
        
        if os.path.exists(intro_path):
            print("Prepending intro video with crossfade...")
            intro = ffmpeg.input(intro_path)
            # Scale both to 1280x720 to prevent concat errors due to resolution mismatch
            intro_v = intro.video.filter('scale', 1280, 720).filter('setsar', 1)
            intro_a = intro.audio
            
            main_v = inputs[0].filter('scale', 1280, 720).filter('setsar', 1)
            main_a = mixed_audio
            
            # Crossfade logic
            fade_duration = 1.0 # 1 second crossfade
            intro_duration = self.get_video_duration(intro_path)
            offset = max(0, intro_duration - fade_duration)
            
            joined_v = ffmpeg.filter([intro_v, main_v], 'xfade', transition='fade', duration=fade_duration, offset=offset)
            joined_a = ffmpeg.filter([intro_a, main_a], 'acrossfade', d=fade_duration)
            
            out = ffmpeg.output(joined_v, joined_a, output_path, vcodec='libx264', acodec='aac')
        else:
            out = ffmpeg.output(inputs[0], mixed_audio, output_path, vcodec='copy', acodec='aac')
            
        ffmpeg.run(out, quiet=True, overwrite_output=True)
