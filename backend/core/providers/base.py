from abc import ABC, abstractmethod
from typing import List, Dict, Any

class LLMProvider(ABC):
    @abstractmethod
    def translate_segments(self, segments: List[Dict[str, Any]], system_prompt: str, context: str = "") -> List[Dict[str, Any]]:
        """
        Translates a batch of segments.
        Expected input segments format: [{"id": 1, "text": "Hello"}]
        Expected output format: [{"id": 1, "hindi": "नमस्ते"}]
        """
        pass
