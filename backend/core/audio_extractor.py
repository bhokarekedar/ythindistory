import ffmpeg
import os

class AudioExtractor:
    def __init__(self, output_dir: str = "temp"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def extract_audio(self, video_path: str) -> str:
        """
        Extracts audio from a video file and saves it as a wav file.
        """
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(self.output_dir, f"{base_name}_audio.wav")
        
        # Overwrite if exists
        if os.path.exists(output_path):
            os.remove(output_path)

        stream = ffmpeg.input(video_path)
        stream = ffmpeg.output(stream, output_path, acodec='pcm_s16le', ac=1, ar='16k')
        ffmpeg.run(stream, quiet=True)
        return output_path
