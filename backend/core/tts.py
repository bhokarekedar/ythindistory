import os
import re
import wave
from google import genai
from google.genai import types

# ─────────────────────────────────────────────────────────────────────────────
# Gemini TTS output spec (confirmed from API probe)
# mime_type : audio/l16; rate=24000; channels=1
# format    : raw signed 16-bit PCM, little-endian, mono, 24 kHz
# ─────────────────────────────────────────────────────────────────────────────
GEMINI_TTS_RATE = 24000
GEMINI_TTS_CHANNELS = 1
GEMINI_TTS_SAMPWIDTH = 2   # 16-bit = 2 bytes/sample


class GeminiTTS:
    """
    Text-to-Speech using gemini-3.1-flash-tts-preview.

    Free tier available via Google AI Studio API key (GEMINI_STUDIO_KEY).
    Produces natural-sounding Hindi narration with the Zephyr voice.
    Output: 24 kHz mono 16-bit PCM, saved as WAV.
    """

    def __init__(self,
                 output_dir: str = "temp/segments",
                 voice_name: str = "Zephyr",
                 model: str = "gemini-3.1-flash-tts-preview"):
        self.output_dir = output_dir
        self.voice_name = voice_name
        self.model = model

        api_key = os.environ.get("GEMINI_STUDIO_KEY")
        if not api_key:
            raise ValueError("GEMINI_STUDIO_KEY is missing from environment.")

        self.client = genai.Client(api_key=api_key)
        os.makedirs(self.output_dir, exist_ok=True)

    def _clean_text(self, text: str) -> str:
        """
        Light cleanup — Gemini TTS handles text naturally so we don't need
        to aggressively strip punctuation. We only:
          - Collapse whitespace
          - Remove truly invalid chars (keep Devanagari, Latin, spaces, periods)
        """
        text = re.sub(r'\s+', ' ', text).strip()
        # Keep Devanagari (\u0900-\u097F), Latin alphanum (\w), spaces, periods, and square brackets []
        text = re.sub(r'[^\w\s\u0900-\u097F.\[\]]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _save_pcm_as_wav(self, pcm_data: bytes, path: str):
        """Wraps raw PCM bytes in a WAV header and saves to disk."""
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(GEMINI_TTS_CHANNELS)
            wf.setsampwidth(GEMINI_TTS_SAMPWIDTH)
            wf.setframerate(GEMINI_TTS_RATE)
            wf.writeframes(pcm_data)

    def generate_audio(self, segment_id: int, text: str) -> str:
        """
        Generates TTS audio for one segment using Gemini 3.1 Flash TTS.

        The prompt includes a narration style direction so Gemini speaks
        in a professional movie-narrator tone, not a casual conversational tone.
        Returns the path to the saved WAV file.
        """
        output_path = os.path.join(self.output_dir, f"{segment_id:04d}.wav")
        text = self._clean_text(text)

        # Style direction: tells Gemini to narrate like a Hindi movie narrator
        prompt = f"[Speak as a professional Hindi movie narrator, clear and engaging pace] {text}"

        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=self.voice_name
                                )
                            )
                        )
                    )
                )
                break # Success
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait_time = 45 + (attempt * 10) # The error usually asks to wait ~45s
                    print(f"  [TTS Rate Limit] Hit 10 requests/min quota. Waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
                    import time
                    time.sleep(wait_time)
                else:
                    if attempt == max_retries - 1:
                        raise e
                    print(f"  [TTS Error] {e}. Retrying {attempt+1}/{max_retries}...")
                    import time
                    time.sleep(5)

        part = response.candidates[0].content.parts[0]
        pcm_data = part.inline_data.data

        # API returns raw PCM (audio/l16; rate=24000; channels=1)
        # Wrap in WAV header so the rest of the pipeline can use wave.open()
        self._save_pcm_as_wav(pcm_data, output_path)
        return output_path
