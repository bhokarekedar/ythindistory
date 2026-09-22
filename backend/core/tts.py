import os
import re
from google.cloud import texttospeech

class GoogleTTS:
    def __init__(self, output_dir: str = "temp/segments", voice_name: str = "hi-IN-Neural2-C"):
        self.output_dir = output_dir
        self.voice_name = voice_name
        
        # Authenticate using API Key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is missing from environment.")
            
        self.client = texttospeech.TextToSpeechClient(client_options={"api_key": api_key})
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_audio(self, segment_id: int, text: str) -> str:
        """
        Generates TTS audio for a specific segment using Google Cloud TTS.
        """
        output_path = os.path.join(self.output_dir, f"{segment_id:04d}.wav")
        text = re.sub(r"\s+", " ", text).strip()
        
        # Aggressively remove all punctuation to force Google TTS to speak without any pauses
        text = re.sub(r'[^\w\s\u0900-\u097F]', ' ', text)
        text = text.replace('\n', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        voice = texttospeech.VoiceSelectionParams(
            language_code="hi-IN",
            name=self.voice_name
        )
        
        # Output uncompressed PCM 16-bit to avoid re-encoding loss
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000
        )
        
        response = self.client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        with open(output_path, "wb") as out:
            out.write(response.audio_content)
            
        return output_path
