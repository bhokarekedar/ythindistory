import os
import json
from groq import Groq
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

class Transcriber:
    def __init__(self, output_dir: str = "temp", api_key: str = None, api_keys: list = None):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Collect all valid Groq API keys into pool
        keys = []
        if api_keys:
            keys.extend([k for k in api_keys if k])
        if api_key and api_key not in keys:
            keys.append(api_key)
        for ek in [os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_API_KEY_TWO"), os.environ.get("GROQ_API_KEY_THREE"), os.environ.get("GROQ_API_KEY_FOUR")]:
            if ek and ek not in keys:
                keys.append(ek)
                
        self.api_keys = keys
        self.current_idx = 0
        self.cooldowns = {i: 0.0 for i in range(len(self.api_keys))}
        if self.api_keys:
            self.client = Groq(api_key=self.api_keys[0])
            print(f"  [Transcriber Pool] 🔑 Loaded {len(self.api_keys)} Groq API key(s) for transcript processing.")
        else:
            self.client = None
            print("  [Transcriber Pool] ⚠️ Initialized Transcriber without Groq API keys.")

    def _parse_cooldown_seconds(self, err_str: str) -> float:
        import re
        m_min_sec = re.search(r'try again in\s+(\d+(?:\.\d+)?)m\s*(\d+(?:\.\d+)?)s', err_str, re.IGNORECASE)
        if m_min_sec:
            return float(m_min_sec.group(1)) * 60 + float(m_min_sec.group(2))
        m_min = re.search(r'try again in\s+(\d+(?:\.\d+)?)m\b', err_str, re.IGNORECASE)
        if m_min:
            return float(m_min.group(1)) * 60
        m_sec = re.search(r'try again in\s+(\d+(?:\.\d+)?)s', err_str, re.IGNORECASE)
        if m_sec:
            return float(m_sec.group(1))
        return 30.0

    def _rotate_client(self, err_str: str = ""):
        import time
        if not self.api_keys:
            return False
            
        cd_sec = self._parse_cooldown_seconds(err_str) if err_str else 30.0
        self.cooldowns[self.current_idx] = time.time() + cd_sec
        prev_idx = self.current_idx
        
        # Check if another key is ready
        now = time.time()
        available = [i for i in range(len(self.api_keys)) if i != prev_idx and self.cooldowns.get(i, 0) <= now]
        if available:
            self.current_idx = available[0]
            self.client = Groq(api_key=self.api_keys[self.current_idx])
            print(f"  [Transcriber Pool] ⚠️ Key #{prev_idx + 1} on cooldown ({int(cd_sec)}s). Rotating immediately to Key #{self.current_idx + 1} of {len(self.api_keys)}.")
            return True
            
        # All keys in cooldown: find soonest
        soonest_idx = min(self.cooldowns, key=self.cooldowns.get)
        wait_sec = max(1.0, self.cooldowns[soonest_idx] - now)
        if wait_sec <= 60: # For transcriber grouper, wait up to 60s
            print(f"  [Transcriber Pool] ⏳ All keys on cooldown. Waiting {int(wait_sec)}s for Key #{soonest_idx + 1}...")
            time.sleep(wait_sec + 1)
            self.current_idx = soonest_idx
            self.client = Groq(api_key=self.api_keys[self.current_idx])
            return True
            
        return False

    def _smart_rule_based_merge(self, segments: list, min_dur: float = 3.5, max_dur: float = 7.0) -> list:
        """
        High-speed deterministic linguistic merger. Groups micro-fragments into complete
        sentences based on punctuation, pause gaps, and duration with ZERO token cost.
        """
        if not segments:
            return []
            
        merged = []
        curr = []
        dangling_words = {
            "and", "but", "or", "because", "with", "to", "in", "of", "that", "so", "then",
            "की", "का", "के", "और", "तथा", "या", "लेकिन", "कि", "तो", "में", "से", "पर", "भी"
        }
        
        for s in segments:
            if not curr:
                curr.append(s)
                continue
                
            prev = curr[-1]
            gap = float(s.get("start", 0)) - float(prev.get("end", 0))
            curr_dur = float(s.get("end", 0)) - float(curr[0].get("start", 0))
            prev_text = prev.get("text", "").strip()
            last_word = prev_text.split()[-1].lower() if prev_text.split() else ""
            
            # Scene change / long pause (> 1.2s gap)
            if gap > 1.2 and curr_dur >= min_dur and last_word not in dangling_words:
                merged.append({
                    "id": curr[0]["id"],
                    "start": curr[0]["start"],
                    "end": prev["end"],
                    "text": " ".join(x.get("text", "").strip() for x in curr)
                })
                curr = [s]
                continue
                
            # Sentence-ending punctuation
            has_terminal = any(prev_text.endswith(p) for p in ('.', '!', '?', '।', '॥'))
            if has_terminal and curr_dur >= min_dur and last_word not in dangling_words:
                merged.append({
                    "id": curr[0]["id"],
                    "start": curr[0]["start"],
                    "end": prev["end"],
                    "text": " ".join(x.get("text", "").strip() for x in curr)
                })
                curr = [s]
                continue
                
            # Max duration threshold reached
            if curr_dur >= max_dur and last_word not in dangling_words:
                merged.append({
                    "id": curr[0]["id"],
                    "start": curr[0]["start"],
                    "end": prev["end"],
                    "text": " ".join(x.get("text", "").strip() for x in curr)
                })
                curr = [s]
                continue
                
            curr.append(s)
            
        if curr:
            merged.append({
                "id": curr[0]["id"],
                "start": curr[0]["start"],
                "end": curr[-1]["end"],
                "text": " ".join(x.get("text", "").strip() for x in curr)
            })
            
        for i, m in enumerate(merged):
            m["id"] = i + 1
            
        return merged

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
        Uses an LLM with multi-key pool rotation to group fragments into complete sentences.
        If all LLM keys reach daily rate limits, automatically falls back to smart linguistic merging.
        """
        if not segments:
            return []
            
        print("Grouping segments via LLM to preserve perfect video sync...")
        merged_segments = []
        
        # If we have no LLM client, use smart rule-based merger immediately
        if not self.client:
            print("  [Grouper] No Groq client available. Using high-speed linguistic merger...")
            return self._smart_rule_based_merge(segments)
        
        # Process in batches to avoid API context limits
        all_batches_failed = True
        for i in range(0, len(segments), batch_size):
            batch = segments[i:i+batch_size]
            
            prompt = """You are an expert multilingual subtitle editor (proficient in Japanese, Korean, Hindi, and English subtitles).
Your task is to analyze fragmented subtitle text and determine which fragments should be merged to form logical, complete sentences.
Rules:
1. Return strictly a JSON object with a single key 'groups' containing a list of lists of the IDs that should be merged.
2. Example Output: {"groups": [[1, 2], [3], [4, 5, 6]]}
3. NEVER split a single sentence in half! A group MUST represent a complete thought.
4. CRITICAL VISUAL RULE: NEVER merge fragments across hard visual cuts or scene changes.
5. Account for every single ID exactly once."""

            input_data = []
            for s in batch:
                dur = round(float(s.get("end", 0)) - float(s.get("start", 0)), 1)
                input_data.append({"id": s["id"], "duration_sec": dur, "text": s["text"]})
            user_content = f"Fragments:\n{json.dumps(input_data, ensure_ascii=False)}"
            
            import time
            batch_success = False
            for attempt in range(max(1, len(self.api_keys))):
                try:
                    # Use llama-3.1-8b-instant for fast, low-token grouping if available, or current model
                    completion = self.client.chat.completions.create(
                        model="llama-3.1-8b-instant",
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
                    
                    for group in groups:
                        if not group:
                            continue
                        group_segs = [s for s in batch if s["id"] in group]
                        if not group_segs:
                            continue
                        merged_segments.append({
                            "id": group_segs[0]["id"],
                            "start": group_segs[0]["start"],
                            "end": group_segs[-1]["end"],
                            "text": " ".join([s["text"] for s in group_segs])
                        })
                    batch_success = True
                    all_batches_failed = False
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    print(f"LLM Grouper attempt {attempt+1} failed: {e}")
                    is_rate_limit = "429" in err_str or "rate_limit" in err_str or "tpd" in err_str or "tokens per day" in err_str
                    if is_rate_limit and self._rotate_client(str(e)):
                        continue
                    time.sleep(1)
            
            if not batch_success:
                # Use smart rule-based merger for this batch instead of raw disconnected fragments!
                print("  [Grouper] LLM Grouper hit rate limits for this batch. Using smart linguistic merger...")
                merged_segments.extend(self._smart_rule_based_merge(batch))
                
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
