import os
import json
from groq import Groq

def is_valid_movie_title(t: str) -> bool:
    if not t or not isinstance(t, str):
        return False
    t_clean = t.strip().lower()
    invalid_keywords = [
        "", "none", "null", "unknown", "untitled", "n/a", "na",
        "extract the movie title from the story", "movie recap", "film recap",
        "movie name", "unnamed", "not mentioned", "not specified"
    ]
    if t_clean in invalid_keywords:
        return False
    if t_clean.startswith("unknown") or t_clean.startswith("[") or t_clean.endswith("]"):
        return False
    return True

class MetadataGenerator:
    def __init__(self, api_key: str = None):
        # Using Qwen 27B since it's available on Groq and great for JSON generation
        self.model_name = "qwen/qwen3.8-27b"
        self.client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"))

    def generate(self, script_path: str, output_path: str, target_lang: str, movie_title: str = None):
        print("Generating SEO-optimized YouTube & Facebook metadata with Movie Attribution...")
        
        with open(script_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
            
        # Detect movie title and genre from cached metadata if not passed
        genre = "Thriller / Mystery"
        dir_name = os.path.dirname(script_path)
        if not movie_title and os.path.exists(dir_name):
            for f in os.listdir(dir_name):
                if f.endswith("_audio_metadata.json"):
                    try:
                        with open(os.path.join(dir_name, f), "r", encoding="utf-8") as mf:
                            m_data = json.load(mf)
                            cached_title = m_data.get("movie_title")
                            if is_valid_movie_title(cached_title):
                                movie_title = cached_title
                            genre = m_data.get("genre", genre)
                    except:
                        pass

        # Combine text to get story context
        full_text = " ".join([s.get(target_lang, s.get("text", "")) for s in segments])
        full_text = full_text[:4000]
        
        has_movie = is_valid_movie_title(movie_title)
        
        if has_movie:
            movie_section_prompt = f"""CONFIRMED FILM INFO (TOP PRIORITY):
- Movie Title: {movie_title}
- Genre: {genre}

MANDATORY ATTRIBUTION (HIGHEST PRIORITY):
- Since the movie name is known, prominently feature it:
  1. Description Header:
     🎬 Movie: {movie_title}
     🎭 Genre: {genre}
  2. In Tags: Include "{movie_title}", "{movie_title} recap", "{movie_title} ending explained", "{movie_title} review".
  3. In Title: Add badge "| {movie_title} Recap"."""
        else:
            movie_section_prompt = f"""SCRIPT MOVIE DETECTION & ATTRIBUTION (SMART SCAN):
- Genre Context: {genre}

INSTRUCTIONS:
Carefully inspect the beginning and narration of the script to see if the narrator explicitly introduces or mentions the movie name (e.g. 'aaj hum movie X explain karenge', 'today we explore the film X...', 'X is a psychological thriller...').

CASE 1 - IF NARRATOR MENTIONS THE MOVIE NAME:
  - Give it TOP PRIORITY!
  - Extract the clean, canonical movie title in 'movie_title'.
  - Include in description right after the hook:
    🎬 Movie: [Extracted Movie Title]
    🎭 Genre: {genre}
  - In Title: Add badge '| [Extracted Movie Title] Recap'.
  - In Tags: Include '[Extracted Movie Title]', '[Extracted Movie Title] recap', '[Extracted Movie Title] ending explained'.

CASE 2 - IF NARRATOR NEVER MENTIONS THE MOVIE NAME:
  - If the narrator simply narrates the story without ever naming the movie, DO NOT GUESS OR INVENT A TITLE!
  - Set 'movie_title': "".
  - STRICTLY SKIP the '🎬 Movie:' line completely from the description! Go directly from the hook into the story synopsis.
  - NEVER output placeholders like '[Movie Name]', 'Unknown', 'Untitled', or 'N/A'.
  - In Title: End with '| Movie Recap' or '| Thriller Story' (e.g. 'He Discovered A Hidden Room In His House | Movie Recap').
  - In Tags: Focus on story, suspense, and recap tags without fake movie names."""

        if has_movie:
            title_rule = f"- Include badge '| {movie_title} Recap'"
            desc_rule = f"- MOVIE HEADER: Include '🎬 Movie: {movie_title}' and '🎭 Genre: {genre}'"
            tags_rule = f"- Include: '{movie_title}', '{movie_title} recap', '{movie_title} ending explained', 'movie recap', 'mystery recap', 'film breakdown', 'movie explained'."
            movie_json_default = movie_title
        else:
            title_rule = "- If movie is mentioned in script, use '| [Movie Title] Recap', otherwise end with '| Movie Recap' or '| Thriller Story'"
            desc_rule = f"- If movie is mentioned in script, include '🎬 Movie: [Movie Title]' and '🎭 Genre: {genre}'. If NOT mentioned, SKIP '🎬 Movie:' cleanly (do not use placeholders!)"
            tags_rule = "- Include the movie name if mentioned; otherwise use high-ranking genre & recap tags: 'movie recap', 'mystery recap', 'film breakdown', 'movie explained', 'crime thriller', 'plot summary'."
            movie_json_default = ""

        prompt = f"""You are an elite YouTube & Facebook video growth hacker and SEO strategist.
Based on the following movie recap story, generate viral metadata designed to maximize Click-Through Rate (CTR) and search discoverability.

{movie_section_prompt}

1. TITLE RULES:
   - Make it ultra click-worthy, dramatic, and emotionally charged with an irresistible information gap.
   - Keep under 75 characters so mobile devices don't truncate it.
   - DO NOT use emojis in the title.
   {title_rule}

2. DESCRIPTION RULES:
   - LINE 1 & 2: A captivating narrative hook that grips viewers immediately.
   {desc_rule}
   - SYNOPSIS: A rich, keyword-dense 3-4 sentence story summary highlighting the central mystery, characters, and high stakes without spoiling the final twist.
   - SEARCH SEO: Naturally weave high-volume search phrases into the synopsis.

3. TAGS / KEYWORDS:
   - Provide 15-20 high-ranking search tags.
   {tags_rule}

Return STRICTLY a JSON object with this format:
{{
    "title": "Your Irresistible Title Here",
    "description": "Your hooked SEO description here",
    "keywords": ["tag1", "tag2", "tag3"],
    "movie_title": "{movie_json_default}"
}}"""
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": full_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            
            response_text = completion.choices[0].message.content
            metadata = json.loads(response_text)
            
            # Post-processing & Sanitization
            raw_title = metadata.get("movie_title") or movie_title or ""
            if is_valid_movie_title(raw_title):
                clean_title = raw_title.strip()
                metadata["movie_title"] = clean_title
                # Ensure description has attribution if missing
                if "🎬 Movie:" not in metadata.get("description", "") and clean_title.lower() not in metadata.get("description", "").lower():
                    lines = metadata.get("description", "").split("\n")
                    # Insert right after the first paragraph (hook)
                    insert_idx = 1
                    for idx, line in enumerate(lines):
                        if line.strip() == "":
                            insert_idx = idx + 1
                            break
                    attr_block = f"\n🎬 Movie: {clean_title}\n🎭 Genre: {genre}\n"
                    lines.insert(insert_idx, attr_block)
                    metadata["description"] = "\n".join(lines).strip()
            else:
                # Movie is not mentioned / unknown -> Cleanly skip!
                metadata["movie_title"] = ""
                # Strip out any hallucinated placeholder line like '🎬 Movie: Unknown'
                desc_lines = metadata.get("description", "").split("\n")
                filtered_lines = []
                for line in desc_lines:
                    l_lower = line.lower()
                    if "🎬 movie:" in l_lower and any(bad in l_lower for bad in ["unknown", "[", "]", "n/a", "none"]):
                        continue
                    filtered_lines.append(line)
                metadata["description"] = "\n".join(filtered_lines).strip()
                # Clean title if it contains placeholders
                cur_title = metadata.get("title", "")
                for bad_badge in ["| Unknown Recap", "| [Movie Name] Recap", "| None Recap"]:
                    if bad_badge in cur_title:
                        cur_title = cur_title.replace(bad_badge, "| Movie Recap")
                metadata["title"] = cur_title
                # Clean tags
                metadata["keywords"] = [k for k in metadata.get("keywords", []) if not any(bad in k.lower() for bad in ["unknown", "[movie", "n/a"])]

            if os.path.dirname(output_path):
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)
                
            print(f"Metadata saved to: {output_path} (Movie: {metadata.get('movie_title') or 'Skipped - Not Mentioned'})")
            return output_path
        except Exception as e:
            print(f"Metadata generation failed: {e}")
            return None
