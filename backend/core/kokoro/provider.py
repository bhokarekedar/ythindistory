import os
import wave
import numpy as np
import soundfile as sf
from kokoro import KPipeline

KOKORO_TTS_RATE = 24000
KOKORO_TTS_CHANNELS = 1
KOKORO_TTS_SAMPWIDTH = 2   # 16-bit = 2 bytes/sample

class KokoroTTS:
    """
    Text-to-Speech using the local Kokoro 82M model.
    Produces 24 kHz mono 16-bit PCM, saved as WAV.
    """
    def __init__(self,
                 output_dir: str = "temp/segments",
                 voice_name: str = "hf_alpha",
                 lang_code: str = "h"):
        self.output_dir = output_dir
        self.voice_name = voice_name
        self.lang_code = lang_code
        
        # Initialize pipeline for the specified language
        self.pipeline = KPipeline(lang_code=self.lang_code)
        os.makedirs(self.output_dir, exist_ok=True)

    def _save_audio_as_wav(self, audio_data: np.ndarray, path: str):
        """Saves numpy audio array to a WAV file"""
        sf.write(path, audio_data, KOKORO_TTS_RATE)

    def generate_audio(self, segment_id: int, text: str) -> str:
        """
        Generates TTS audio for one segment using Kokoro.
        Returns the path to the saved WAV file.
        """
        output_path = os.path.join(self.output_dir, f"{segment_id:04d}.wav")
        
        # The generator yields (graphemes, phonemes, audio)
        generator = self.pipeline(text, voice=self.voice_name, speed=1) if text.strip() else []
        
        audio_chunks = []
        for i, (gs, ps, audio) in enumerate(generator):
            audio_chunks.append(audio)
            
        if not audio_chunks:
            # If text is empty or Kokoro yields nothing, create 0.1s of silence
            print(f"  [Kokoro] Warning: No audio generated for segment {segment_id} ('{text}'). Padding with silence.")
            final_audio = np.zeros(int(KOKORO_TTS_RATE * 0.1), dtype=np.float32)
        else:
            # Concatenate all chunks
            final_audio = np.concatenate(audio_chunks)
            
        self._save_audio_as_wav(final_audio, output_path)
        
        return output_path


