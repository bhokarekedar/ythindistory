import os
import yt_dlp


class YouTubeDownloader:
    def __init__(self, output_dir: str = "temp"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def download(self, url: str) -> str:
        """
        Download a YouTube video and return the downloaded file path.
        """

        ydl_opts = {
            # Let yt-dlp select the best available format
            "format": "best",

            "outtmpl": os.path.join(
                self.output_dir,
                "%(id)s.%(ext)s"
            ),

            # Use the Chrome profile that contains your
            # authenticated YouTube session
            "cookiesfrombrowser": (
                "chrome",
                "Default",
            ),

            # JavaScript runtime
            "js_runtimes": {
                "deno": None,
            },

            # Download EJS challenge-solving components
            "remote_components": {
                "ejs": ["github"],
            },

            "quiet": False,
            "no_warnings": False,
            "ignoreerrors": False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    url,
                    download=True
                )

                if not info:
                    raise Exception(
                        "Unable to extract video information"
                    )

                filepath = ydl.prepare_filename(info)

                # Normal output
                if os.path.exists(filepath):
                    return filepath

                # Check if the final extension changed
                base_path = os.path.splitext(filepath)[0]

                for ext in ["mp4", "webm", "mkv", "m4a"]:
                    possible_path = f"{base_path}.{ext}"

                    if os.path.exists(possible_path):
                        return possible_path

                raise Exception(
                    f"Downloaded file could not be found: {filepath}"
                )

        except yt_dlp.utils.DownloadError as e:
            raise Exception(
                f"yt-dlp download failed: {str(e)}"
            ) from e