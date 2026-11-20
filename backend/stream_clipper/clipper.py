import os
import sys
import glob
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
        self.is_mac = sys.platform == "darwin"
        os.makedirs(os.path.join(self.temp_dir, "stream_clips"), exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "stream_clips"), exist_ok=True)

    def download_segment(self, url: str, start_time: float, duration: float, clip_id: str) -> str:
        """
        Downloads only the specified start-to-end section of the stream.
        Optimized for both live HLS streams and standard VODs using direct stream extraction.
        Prioritizes high-speed 720p streams to minimize network latency.
        Saves into temp/stream_clips/{clip_id}_raw.mp4.
        """
        raw_output = os.path.join(self.temp_dir, "stream_clips", f"{clip_id}_raw.mp4")
        if os.path.exists(raw_output) and os.path.getsize(raw_output) > 10240:
            return raw_output

        # Method 1: Extract stream manifest/HLS URLs and download directly via FFmpeg
        try:
            ydl_opts = {
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                'quiet': True,
                'no_warnings': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                req_formats = info.get('requested_formats', [])
                if req_formats:
                    v_url = req_formats[0].get('url')
                    a_url = req_formats[1].get('url') if len(req_formats) > 1 else None
                else:
                    v_url = info.get('url')
                    a_url = None

            if v_url:
                cmd = [
                    'ffmpeg', '-y',
                    '-allowed_extensions', 'ALL',
                    '-extension_picky', '0',
                    '-ss', f"{start_time:.2f}",
                    '-i', v_url
                ]
                if a_url:
                    cmd.extend([
                        '-allowed_extensions', 'ALL',
                        '-extension_picky', '0',
                        '-ss', f"{start_time:.2f}",
                        '-i', a_url,
                        '-map', '0:v:0',
                        '-map', '1:a:0'
                    ])
                else:
                    cmd.extend(['-map', '0:v:0', '-map', '0:a:0?'])

                cmd.extend([
                    '-t', f"{duration:.2f}",
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    raw_output
                ])

                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode == 0 and os.path.exists(raw_output) and os.path.getsize(raw_output) > 10240:
                    return raw_output
        except Exception as e:
            print(f"[StreamClipper] Direct stream download fallback note: {e}")

        # Method 2: yt-dlp range download fallback
        tmpl_pattern = os.path.join(self.temp_dir, "stream_clips", f"{clip_id}_raw.%(ext)s")
        ydl_fallback_opts = {
            'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            'outtmpl': tmpl_pattern,
            'download_ranges': yt_dlp.utils.download_range_func(None, [(start_time, start_time + duration)]),
            'force_keyframes_at_cuts': True,
            'quiet': True,
            'no_warnings': True,
            'overwrites': True
        }

        with yt_dlp.YoutubeDL(ydl_fallback_opts) as ydl:
            ydl.download([url])

        candidates = glob.glob(os.path.join(self.temp_dir, "stream_clips", f"{clip_id}_raw.*"))
        valid = [c for c in candidates if os.path.exists(c) and os.path.getsize(c) > 1024]
        if not valid:
            raise FileNotFoundError(f"Failed to download stream clip section for {clip_id}")

        return valid[0]

    def render_vertical(
        self,
        raw_video_path: str,
        clip_id: str,
        layout: str = "blurred_stack"
    ) -> str:
        """
        Converts the downloaded horizontal segment into a high-res 1080x1920 9:16 vertical short.
        Uses Apple Silicon VideoToolbox hardware acceleration if available for 5x-10x faster encoding.
        """
        out_path = os.path.join(self.output_dir, "stream_clips", f"{clip_id}.mp4")

        # Hardware acceleration codec settings
        if self.is_mac:
            v_codec_args = ["-c:v", "h264_videotoolbox", "-b:v", "5000k"]
        else:
            v_codec_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]

        if layout == "center_crop":
            filter_graph = "crop=ih*(9/16):ih,scale=1080:1920:flags=lanczos,setsar=1"
            cmd = [
                "ffmpeg", "-y",
                "-i", raw_video_path,
                "-vf", filter_graph,
                "-map", "0:v:0",
                "-map", "0:a?"
            ] + v_codec_args + [
                "-pix_fmt", "yuv420p",
                "-r", "30",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                out_path
            ]
        else:
            # High-speed ambient blur: blurs downscaled 360p layer (9x fewer pixels) then scales up smoothly
            filter_graph = (
                "[0:v]scale=360:640:force_original_aspect_ratio=increase,"
                "crop=360:640,boxblur=8:2,scale=1080:1920:flags=fast_bilinear[bg];"
                "[0:v]scale=1080:-1:flags=lanczos[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", raw_video_path,
                "-filter_complex", filter_graph,
                "-map", "[v]",
                "-map", "0:a?"
            ] + v_codec_args + [
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
                    model="llama-3.1-8b-instant",
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
