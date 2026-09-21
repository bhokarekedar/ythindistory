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

    # Audio stretching is no longer used. We dynamically retime the video instead.

    def build_timeline(self, segments: list, original_video_path: str, output_path: str, job_dir: str = "temp"):
        """
        Dynamically retimes the video by slicing it into chunks, altering speed to match audio, and concatenating.
        """
        chunks_dir = os.path.join(job_dir, "video_chunks")
        os.makedirs(chunks_dir, exist_ok=True)
        
        concat_list_path = os.path.join(chunks_dir, "concat.txt")
        concat_lines = []
        
        current_time = 0.0
        total_duration = self.get_video_duration(original_video_path)
        
        chunk_idx = 0
        
        # 1. Generate Video Chunks
        for seg in segments:
            # Handle Gap
            if seg["start"] > current_time:
                gap_dur = seg["start"] - current_time
                if gap_dur > 0.1:
                    chunk_path = os.path.join(chunks_dir, f"chunk_{chunk_idx:04d}_gap.mp4")
                    if not os.path.exists(chunk_path):
                        v = ffmpeg.input(original_video_path, ss=current_time, t=gap_dur).video
                        a = ffmpeg.input(original_video_path, ss=current_time, t=gap_dur).audio
                        
                        v = v.filter('scale', 1280, 720).filter('setsar', 1).filter('fps', fps=30, round='near').filter('format', 'yuv420p')
                        a = a.filter('aresample', 48000)
                        
                        out = ffmpeg.output(v, a, chunk_path, vcodec='libx264', acodec='aac', ac=2, ar=48000)
                        try:
                            ffmpeg.run(out, quiet=True, overwrite_output=True)
                        except ffmpeg.Error as e:
                            print("FFmpeg Error (gap):", e.stderr.decode('utf8') if e.stderr else str(e))
                            raise e
                            
                    concat_lines.append(f"file '{os.path.abspath(chunk_path)}'")
                    chunk_idx += 1
                    
            # Handle Segment
            orig_dur = seg["end"] - seg["start"]
            if orig_dur <= 0.1:
                orig_dur = 0.1
                
            hindi_dur = self.get_audio_duration(seg["audio_path"])
            
            chunk_path = os.path.join(chunks_dir, f"chunk_{chunk_idx:04d}_seg.mp4")
            if not os.path.exists(chunk_path):
                speed_factor = orig_dur / hindi_dur
                
                v = ffmpeg.input(original_video_path, ss=seg["start"], t=orig_dur).video
                a = ffmpeg.input(seg["audio_path"]).audio
                
                pts_factor = 1.0 / speed_factor
                v = v.filter('setpts', f"{pts_factor}*PTS")
                v = v.filter('scale', 1280, 720).filter('setsar', 1).filter('fps', fps=30, round='near').filter('format', 'yuv420p')
                a = a.filter('aresample', 48000)
                
                out = ffmpeg.output(v, a, chunk_path, vcodec='libx264', acodec='aac', ac=2, ar=48000)
                try:
                    ffmpeg.run(out, quiet=True, overwrite_output=True)
                except ffmpeg.Error as e:
                    print("FFmpeg Error (seg):", e.stderr.decode('utf8') if e.stderr else str(e))
                    raise e
                    
            concat_lines.append(f"file '{os.path.abspath(chunk_path)}'")
            chunk_idx += 1
            current_time = seg["end"]
            
        # Handle Final Gap
        if current_time < total_duration:
            gap_dur = total_duration - current_time
            if gap_dur > 0.1:
                chunk_path = os.path.join(chunks_dir, f"chunk_{chunk_idx:04d}_gap.mp4")
                if not os.path.exists(chunk_path):
                    v = ffmpeg.input(original_video_path, ss=current_time, t=gap_dur).video
                    a = ffmpeg.input(original_video_path, ss=current_time, t=gap_dur).audio
                    
                    v = v.filter('scale', 1280, 720).filter('setsar', 1).filter('fps', fps=30, round='near').filter('format', 'yuv420p')
                    a = a.filter('aresample', 48000)
                    
                    out = ffmpeg.output(v, a, chunk_path, vcodec='libx264', acodec='aac', ac=2, ar=48000)
                    try:
                        ffmpeg.run(out, quiet=True, overwrite_output=True)
                    except ffmpeg.Error as e:
                        print("FFmpeg Error (final gap):", e.stderr.decode('utf8') if e.stderr else str(e))
                        raise e
                        
                concat_lines.append(f"file '{os.path.abspath(chunk_path)}'")
                
        # 2. Concat Chunks
        with open(concat_list_path, "w") as f:
            f.write("\n".join(concat_lines))
            
        mixed_video_path = os.path.join(job_dir, "mixed_temp.mp4")
        if not os.path.exists(mixed_video_path):
            try:
                out = ffmpeg.input(concat_list_path, format='concat', safe=0)
                out = ffmpeg.output(out, mixed_video_path, c='copy')
                ffmpeg.run(out, quiet=True, overwrite_output=True)
            except ffmpeg.Error as e:
                err_msg = e.stderr.decode('utf8') if e.stderr else str(e)
                print(f"FFmpeg Error in concat:\n{err_msg}")
                raise e
                
        # 3. Intro Crossfade Logic
        intro_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/intro.mp4"
        if os.path.exists(intro_path):
            print("Prepending intro video with crossfade...")
            intro = ffmpeg.input(intro_path)
            intro_v = intro.video.filter('scale', 1280, 720).filter('setsar', 1).filter('fps', fps=30, round='near').filter('format', 'yuv420p').filter('settb', '1/30')
            intro_a = intro.audio.filter('aresample', 48000)
            
            main = ffmpeg.input(mixed_video_path)
            main_v = main.video.filter('settb', '1/30')
            main_a = main.audio
            
            fade_duration = 1.0
            intro_duration = self.get_video_duration(intro_path)
            offset = max(0, intro_duration - fade_duration)
            
            joined_v = ffmpeg.filter([intro_v, main_v], 'xfade', transition='fade', duration=fade_duration, offset=offset)
            joined_a = ffmpeg.filter([intro_a, main_a], 'acrossfade', d=fade_duration)
            
            out = ffmpeg.output(joined_v, joined_a, output_path, vcodec='libx264', acodec='aac')
            try:
                ffmpeg.run(out, quiet=True, overwrite_output=True)
            except ffmpeg.Error as e:
                print("FFmpeg Error in crossfade:", e.stderr.decode('utf8') if e.stderr else str(e))
                raise e
        else:
            # No intro, just copy
            out = ffmpeg.output(ffmpeg.input(mixed_video_path), output_path, c='copy')
            ffmpeg.run(out, quiet=True, overwrite_output=True)
