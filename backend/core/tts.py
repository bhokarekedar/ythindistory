import subprocess
import os
import re

class PiperTTS:
    def __init__(self, model_path: str = "models/hi_IN-priyamvada-medium.onnx", output_dir: str = "temp/segments"):
        self.model_path = model_path
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
    def _smart_split(self, text: str, max_chars: int = 200) -> list[str]:
        """
        Splits text based on Hindi natural boundaries (danda, spaces)
        """
        chunks = []
        text = text.strip()

        while len(text) > max_chars:
            window = text[:max_chars]
            
            # Prefer Hindi danda
            cut = window.rfind("।")
            if cut != -1:
                cut += 1
                chunks.append(text[:cut].strip())
                text = text[cut:].strip()
                continue

            # Word-safe fallback
            space_cut = window.rfind(" ")
            if space_cut != -1:
                chunks.append(text[:space_cut].strip())
                text = text[space_cut:].strip()
                continue

            # Extreme fallback
            chunks.append(window)
            text = text[max_chars:].strip()

        if text:
            chunks.append(text)

        return chunks

    def generate_audio(self, segment_id: int, text: str) -> str:
        """
        Generates TTS audio for a specific segment.
        Piper reads from standard input and outputs to a wav file.
        """
        output_path = os.path.join(self.output_dir, f"{segment_id:04d}.wav")
        
        # Clean text
        text = re.sub(r"\s+", " ", text).strip()
        
        # For very long segments, we split them. (MVP simply passes the whole text to piper)
        # Piper handles longer texts, but splitting can help with memory.
        # Here we just use subprocess to call piper.
        
        # Assuming piper binary is in PATH
        cmd = [
            "piper",
            "--model", self.model_path,
            "--output_file", output_path
        ]
        
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        process.communicate(input=text.encode('utf-8'))
        
        if process.returncode != 0:
            raise RuntimeError(f"Piper TTS failed for segment {segment_id}")
            
        return output_path
