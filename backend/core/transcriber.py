import os
import json
from groq import Groq

class Transcriber:
    def __init__(self, model_name: str = "whisper-large-v3-turbo", output_dir: str = "temp", chunk_minutes: int = 10):
        self.model_name = model_name
        self.output_dir = output_dir
        self.chunk_minutes = chunk_minutes
        os.makedirs(self.output_dir, exist_ok=True)
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribes the audio using Groq Whisper API and saves a timestamped JSON file.
        In MVP, we process the whole file (assuming it's small). 
        # TODO: Implement pydub/ffmpeg audio chunking here if audio is > 25MB (Groq limit).
        """
        print(f"Transcribing {audio_path} via Groq...")
        
        # For Groq, we need to send the audio file directly. 
        # Max file size for Groq Whisper is 25MB.
        # We request verbose_json to get timestamps.
        with open(audio_path, "rb") as file:
            transcription = self.client.audio.transcriptions.create(
              file=(os.path.basename(audio_path), file.read()),
              model=self.model_name,
              response_format="verbose_json",
            )
        
        segments = []
        for i, segment in enumerate(transcription.segments):
            segments.append({
                "id": i + 1,
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip()
            })
            
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        output_path = os.path.join(self.output_dir, f"{base_name}_transcript.json")
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=4, ensure_ascii=False)
            
        print(f"Transcript saved to {output_path}")
        return output_path
