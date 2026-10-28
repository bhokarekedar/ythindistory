import os
import json
from groq import Groq
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

class Transcriber:
    def __init__(self, output_dir: str = "temp", api_key: str = None):
        self.output_dir = output_dir
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
            print(f"YouTube Transcript Fetch Failed: {e}")
            return None

    def _llm_merge_segments(self, segments: list, batch_size: int = 50) -> list:
        """
        Uses an LLM to read the fragments and return the exact IDs that should be merged.
        This guarantees perfect grammatical groupings without messing up the timestamps.
        """
        if not segments:
            return []
            
        print("Grouping segments via LLM to preserve perfect video sync...")
        merged_segments = []
        
        # Process in batches to avoid API context limits
        for i in range(0, len(segments), batch_size):
            batch = segments[i:i+batch_size]
            
            prompt = """You are an expert multilingual subtitle editor (proficient in Japanese, Korean, Hindi, and English subtitles).
Your task is to analyze fragmented subtitle text and determine which fragments should be merged to form logical, complete sentences.
Rules:
1. Return strictly a JSON object with a single key 'groups' containing a list of lists of the IDs that should be merged.
2. Example Output: {"groups": [[1, 2], [3], [4, 5, 6]]}
3. NEVER split a single sentence in half! A group MUST represent a complete thought. If a fragment ends abruptly without terminating punctuation or a concluding verb (e.g., Hindi 'hai', 'tha', 'ho', 'gaya'; Japanese 'です', 'ます', 'た', 'だ'; Korean '다', '요', '었다'), or ends with a conjunction/particle/preposition (e.g., Hindi 'ki', 'ka', 'aur'; Japanese 'の', 'と', 'が', 'を', 'に', 'で'; Korean '의', '와', '과', '을', '를', '에'; English 'and', 'but', 'because', 'with', 'to'), you MUST merge it with the next fragment.
4. CRITICAL VISUAL RULE (ACT AS A VIDEO EDITOR): You must NEVER merge fragments across hard visual cuts. A fragment MUST start a brand new group if it contains:
   - A Location/Scene Change (e.g., "अगले सीन में", "पुलिस स्टेशन में", "Meanwhile in Tokyo", "다음 날", "その頃")
   - A Time Jump or Flashback (e.g., "15 साल बाद", "अगले दिन", "Years later", "10년 후", "翌日")
   - A New Character Introduction / Victim / Suspect Discovery
   - A Sudden Action/Shocking Event (e.g., "तभी अचानक", "Suddenly", "갑자기")
   These represent massive visual shifts on screen. Merging them into the middle of a previous sentence will ruin the video sync!
5. Make sure every single ID provided in the input is accounted for exactly once in the output groups.
"""
            # Build input JSON
            input_data = [{"id": s["id"], "text": s["text"]} for s in batch]
            user_content = f"Fragments:\n{json.dumps(input_data, ensure_ascii=False)}"
            
            import time
            for attempt in range(3):
                try:
                    completion = self.client.chat.completions.create(
                        model="qwen/qwen3.8-27b",
                        messages=[
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": user_content}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.0
                    )
                    
                    response_text = completion.choices[0].message.content
                    parsed = json.loads(response_text)
                    groups = parsed.get("groups", [])
                    
                    # Execute the merge based on the returned groups
                    for group in groups:
                        if not group:
                            continue
                        
                        group_segs = [s for s in batch if s["id"] in group]
                        if not group_segs:
                            continue
                            
                        merged_segments.append({
                            "id": group_segs[0]["id"], # Temporary ID, re-indexed later
                            "start": group_segs[0]["start"],
                            "end": group_segs[-1]["end"],
                            "text": " ".join([s["text"] for s in group_segs])
                        })
                    break # Success, break out of retry loop
                except Exception as e:
                    print(f"LLM Grouper attempt {attempt+1} failed: {e}")
                    time.sleep(2)
            else:
                print("Warning: LLM Grouper failed for this batch. Using raw fragments as fallback.")
                merged_segments.extend(batch)
                
        # Clean up any trailing dangling conjunctions/prepositions across segments
        dangling_words = {
            "की", "का", "के", "और", "तथा", "या", "लेकिन", "कि", "तो", "में", "से", "पर",
            "and", "but", "or", "because", "with", "to", "in", "of", "that", "so", "then"
        }
        for i in range(len(merged_segments) - 1):
            curr_text = merged_segments[i]["text"].strip()
            words = curr_text.split()
            if words and words[-1] in dangling_words:
                trailing = words[-1]
                merged_segments[i]["text"] = " ".join(words[:-1]).strip()
                merged_segments[i+1]["text"] = f"{trailing} {merged_segments[i+1]['text']}".strip()

        # Re-assign sequential IDs
        for i, m in enumerate(merged_segments):
            m["id"] = i + 1
            
        return merged_segments

    def transcribe(self, audio_path: str, language: str = None, youtube_url: str = None) -> str:
        """
        Transcribes the video by fetching official/auto subtitles directly from YouTube.
        Saves a timestamped JSON file.
        """
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        output_path = os.path.join(self.output_dir, f"{base_name}_transcript.json")

        segments = None
        if youtube_url:
            segments = self.fetch_youtube_transcript(youtube_url)
            
        if not segments:
            raise RuntimeError(
                f"Could not retrieve YouTube transcript for '{youtube_url}'. "
                "Please verify that the YouTube video has closed captions / subtitles available."
            )
        
        # Merge fragments into complete sentences via LLM for perfect TTS flow
        print(f"Original segments: {len(segments)}")
        segments = self._llm_merge_segments(segments)
        print(f"Merged into {len(segments)} highly accurate groups.")
            
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=4, ensure_ascii=False)
            
        print(f"Transcript saved to {output_path}")
        return output_path
