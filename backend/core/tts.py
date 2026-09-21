import os
import re
import base64
from typing import Optional
from sarvamai import SarvamAI

class SarvamTTS:
    def __init__(self, output_dir: str = "temp/segments", speaker: str = "shubh"):
        self.output_dir = output_dir
        self.speaker = speaker
        self.client = SarvamAI(api_subscription_key=os.environ.get("SARVAM_TTS_API_KEY"))
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_audio(self, segment_id: int, text: str) -> str:
        """
        Generates TTS audio for a specific segment using Sarvam AI.
        """
        output_path = os.path.join(self.output_dir, f"{segment_id:04d}.wav")
        text = re.sub(r"\s+", " ", text).strip()
        
        # Convert text to speech exactly matching Sarvam 0.1.31a4 SDK spec
        response = self.client.text_to_speech.convert(
            model="bulbul:v3",
            text=text,
            language_code="hi-IN",
            speaker=self.speaker,
        )
        
        # In this SDK version, the response object directly holds the audios array.
        if not response.audios or len(response.audios) == 0:
            raise RuntimeError(f"Sarvam TTS failed to return audio for segment {segment_id}")
            
        audio_b64 = response.audios[0]
        audio_bytes = base64.b64decode(audio_b64)
        
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
            
        return output_path
