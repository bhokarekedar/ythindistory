import os
import subprocess
import json
from typing import Dict, Any, Optional
import yt_dlp

try:
    from groq import Groq
except ImportError:
    Groq = None


class StreamClipRenderer:
    def __init__(self, temp_dir: str = "temp", output_dir: str = "output"):
        self.temp_dir = temp_dir
        self.output_dir = output_dir
        os.makedirs(os.path.join(self.temp_dir, "stream_clips"), exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "stream_clips"), exist_ok=True)

    def download_segment(self, url: str, start_time: float, duration: float, clip_id: str) -> str:
        """
        Downloads only the specified start-to-end section of the stream via yt-dlp.
        Saves into temp/stream_clips/{clip_id}_raw.mp4.
        """
        raw_output = os.path.join(self.temp_dir, "stream_clips", f"{clip_id}_raw.mp4")
        if os.path.exists(raw_output) and os.path.getsize(raw_output) > 10240:
            return raw_output

        end_time = start_time + duration
        time_range = f"*{start_time:.1f}-{end_time:.1f}"

        ydl_opts = {
            'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': raw_output,
            'download_ranges': yt_dlp.utils.download_range_func(None, [(start_time, end_time)]),
            'force_keyframes_at_cuts': True,
            'quiet': True,
            'no_warnings': True,
            'overwrites': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if not os.path.exists(raw_output):
            raise FileNotFoundError(f"Failed to download stream clip section for {clip_id}")

        return raw_output

    def render_vertical(
        self,
        raw_video_path: str,
        clip_id: str,
        layout: str = "blurred_stack"
    ) -> str:
        """
        Converts the downloaded horizontal segment into a high-res 1080x1920 9:16 vertical short.
        Layout options:
        - 'blurred_stack': Sharp centered video with blurred ambient background (standard for stream clips)
        - 'center_crop': Direct 9:16 center crop
        """
        out_path = os.path.join(self.output_dir, "stream_clips", f"{clip_id}.mp4")

        # Choose FFmpeg filter graph
        if layout == "center_crop":
            filter_graph = "crop=ih*(9/16):ih,scale=1080:1920:flags=lanczos,setsar=1"
        else:
            # Blurred Stack: Top/Bottom blurred ambient fill with crystal-clear center focus
            filter_graph = (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,boxblur=25:5[bg];"
                "[0:v]scale=1080:-1:flags=lanczos[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", raw_video_path,
            "-vf", filter_graph,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            out_path
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg render error: {res.stderr.decode('utf-8', errors='ignore')[-500:]}")

        return out_path

    def generate_ai_metadata(
        self,
        stream_title: str,
        streamer: str,
        top_keywords: list,
        sample_chat: list
    ) -> Dict[str, Any]:
        """
        Generates YouTube Shorts metadata (Hook title, Description, Tags) using Groq if available.
        Falls back to proven viral template.
        """
        kw_str = ", ".join(top_keywords[:4])
        chat_str = '", "'.join(sample_chat[:3])

        groq_key = os.environ.get("GROQ_API_KEY")
        if Groq and groq_key:
            try:
                client = Groq(api_key=groq_key)
                prompt = (
                    f"Create viral YouTube Shorts metadata for a highlight clip from stream '{stream_title}' by {streamer}.\n"
                    f"Chat exploded with keywords: {kw_str}\n"
                    f"Chat messages: \"{chat_str}\"\n\n"
                    "Provide a JSON response with:\n"
                    "{\n"
                    '  "title": "Dramatic short title under 70 chars with 1 emoji and #Shorts",\n'
                    '  "description": "Engaging 2-sentence description with hashtags",\n'
                    '  "tags": ["Shorts", "StreamerName", "keyword1", "viral"]\n'
                    "}"
                )
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.7
                )
                data = json.loads(response.choices[0].message.content)
                return data
            except Exception as e:
                print(f"[StreamClipper] AI metadata fallback used: {e}")

        # Fallback template
        title_tag = top_keywords[0] if top_keywords else "HYPE"
        return {
            "title": f"When Chat Went CRAZY! ({title_tag}) 😱 #Shorts",
            "description": f"The exact moment the live stream chat exploded during {streamer}'s stream!\n\n#Shorts #LiveStream #Highlights #{title_tag}",
            "tags": ["Shorts", streamer, "StreamHighlights", title_tag, "TwitchClips", "Viral"]
        }

