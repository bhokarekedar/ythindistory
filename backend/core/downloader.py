import yt_dlp
import os

class YouTubeDownloader:
    def __init__(self, output_dir: str = "temp"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def download(self, url: str) -> str:
        """
        Downloads a YouTube video and returns the path to the downloaded file.
        """
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(self.output_dir, '%(id)s.%(ext)s'),
            'merge_output_format': 'mp4',
            # Add these specific extractor args to bypass recent YouTube bot/JS checks
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
