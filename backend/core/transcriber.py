import os
import json
from groq import Groq
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

class Transcriber:
    def __init__(self, model_name: str = "whisper-large-v3-turbo", output_dir: str = "temp", chunk_minutes: int = 10, api_key: str = None):
        self.model_name = model_name
        self.output_dir = output_dir
        self.chunk_minutes = chunk_minutes
        os.makedirs(self.output_dir, exist_ok=True)
        self.client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"))

    def fetch_youtube_transcript(self, url: str) -> list:
        """
        Attempts to instantly download the transcript directly from YouTube servers.
        Returns a list of segments if successful, otherwise None.
        """
        try:
            from urllib.parse import urlparse, parse_qs
            # Extract video ID
            parsed_url = urlparse(url)
            video_id = ""
            if parsed_url.hostname in ['www.youtube.com', 'youtube.com']:
                video_id = parse_qs(parsed_url.query).get('v', [None])[0]
            elif parsed_url.hostname in ['youtu.be']:
                video_id = parsed_url.path[1:]
                
            if not video_id:
                return None

            print(f"Fetching official YouTube transcript for video {video_id}...")
            
            # Fetch transcripts, prioritizing english and hindi
            transcript_list = YouTubeTranscriptApi().list(video_id)
            
            try:
                transcript = transcript_list.find_transcript(['en', 'hi', 'en-US', 'hi-IN'])
            except NoTranscriptFound:
                # If neither english nor hindi exists, just get whatever is available and we'll translate it later
                transcript = transcript_list.find_transcript([t.language_code for t in transcript_list])
                
            fetched_data = transcript.fetch()
            
            # Convert YouTube's format to our segment format
            segments = []
            for i, seg in enumerate(fetched_data):
                # Handle both dicts (older versions) and objects (newer versions)
                text = seg['text'] if isinstance(seg, dict) else seg.text
                start = seg['start'] if isinstance(seg, dict) else seg.start
                duration = seg['duration'] if isinstance(seg, dict) else seg.duration
                
                segments.append({
                    "id": i + 1,
                    "start": start,
                    "end": start + duration,
                    "text": text.strip()
                })
            
            return segments
        except Exception as e:
            print(f"YouTube Transcript Fetch Failed: {e}. Falling back to Whisper...")
            return None

    def _merge_segments(self, segments: list, max_duration: float = 25.0) -> list:
        """
        Merges short or incomplete fragments into longer sentences.
        This prevents the TTS engine from receiving fragments and taking unnatural pauses mid-sentence.
        """
        if not segments:
            return []
            
        merged = []
        current_seg = None
        
        for seg in segments:
            if not current_seg:
                current_seg = seg.copy()
                continue
                
            text = current_seg["text"].strip()
            ends_with_punc = text.endswith(('.', '!', '?', '।', ',', ';'))
            duration = current_seg["end"] - current_seg["start"]
            
            # Merge if the sentence hasn't naturally ended (no punctuation).
            # We use a massive 60-second absolute cap to prevent infinite merging 
            # if the transcriber fails to output any punctuation.
            # Also merge extremely short fragments (under 1.5s) regardless.
            if (not ends_with_punc and duration < 60.0) or (duration < 1.5):
                current_seg["text"] += " " + seg["text"].strip()
                current_seg["end"] = seg["end"]
            else:
                merged.append(current_seg)
                current_seg = seg.copy()
                
        if current_seg:
            merged.append(current_seg)
            
        # Re-assign sequential IDs
        for i, m in enumerate(merged):
            m["id"] = i + 1
            
        return merged

    def transcribe(self, audio_path: str, language: str = None, youtube_url: str = None) -> str:
        """
        Transcribes the audio. First tries to fetch official YouTube transcript if url is provided.
        Falls back to Groq Whisper API if no transcript exists.
        Saves a timestamped JSON file.
        """
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        output_path = os.path.join(self.output_dir, f"{base_name}_transcript.json")

        segments = None
        
        # 1. Fast Path: Try Official YouTube Transcript first
        if youtube_url:
            segments = self.fetch_youtube_transcript(youtube_url)
            
        # 2. Fallback Path: Groq Whisper
        if not segments:
            print(f"Transcribing {audio_path} via Groq Whisper...")
            with open(audio_path, "rb") as file:
                kwargs = {
                    "file": (os.path.basename(audio_path), file.read()),
                    "model": self.model_name,
                    "response_format": "verbose_json",
                    "temperature": 0.0,
                    "prompt": "यह एक कहानी है। स्वागत है दोस्तों।", # Conditions the model to output proper Hindi and reduces gibberish
                }
                if language:
                    kwargs["language"] = language
                else:
                    # Force Hindi language detection to prevent Whisper from outputting Urdu/Arabic script
                    # This fixes the issue where the raw transcript had Urdu characters instead of Devanagari/English!
                    kwargs["language"] = "hi"
                
                transcription = self.client.audio.transcriptions.create(**kwargs)
            
            segments = []
            for i, segment in enumerate(transcription.segments):
                segments.append({
                    "id": i + 1,
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"].strip()
                })
        
        # Merge fragments into complete sentences for better TTS flow
        if segments:
            print(f"Original segments: {len(segments)}")
            segments = self._merge_segments(segments)
            print(f"Merged into {len(segments)} sentences for smoother audio flow.")
            
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        output_path = os.path.join(self.output_dir, f"{base_name}_transcript.json")
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=4, ensure_ascii=False)
            
        print(f"Transcript saved to {output_path}")
        return output_path
