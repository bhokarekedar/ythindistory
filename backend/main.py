from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import time
import shutil
import threading
import ffmpeg
import yaml
import re
import glob
from dotenv import load_dotenv

load_dotenv()

from core.downloader import YouTubeDownloader
from core.audio_extractor import AudioExtractor
from core.transcriber import Transcriber
from core.translator import StoryTranslator
from core.tts import GeminiTTS
from core.kokoro.provider import KokoroTTS
from core.sync import AudioSynchronizer
from core.metadata import MetadataGenerator
from core.api_keys import ApiKeyManager
from core.image_generator import CloudflareImageGenerator
from core.quality_evaluator import ScriptQualityEvaluator
import json
import urllib.request
app = FastAPI(title="Movie Recap Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local dev (e.g. localhost:5173)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
import os

os.makedirs("output", exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")

from typing import Optional, List

class WatermarkCorner(BaseModel):
    enabled: bool = False
    offsetX: int = 10
    offsetY: int = 10
    size: int = 180

class WatermarkSettings(BaseModel):
    topLeft: Optional[WatermarkCorner] = None
    topRight: Optional[WatermarkCorner] = None
    bottomLeft: Optional[WatermarkCorner] = None
    bottomRight: Optional[WatermarkCorner] = None

class TimeRange(BaseModel):
    start: float
    end: float

class VideoRequest(BaseModel):
    url: str
    target_language: str = "hindi"
    channel_type: str = "movie_recap"  # "movie_recap" or "thriller_story"
    watermark: Optional[WatermarkSettings] = None
    textWatermark: Optional[WatermarkSettings] = None
    skip_intervals: Optional[List[TimeRange]] = None
    webhook_url: Optional[str] = None
    burn_subtitles: bool = True
    pause_for_review: bool = True
    force_regenerate_script: bool = False

class SnapshotRequest(BaseModel):
    url: str
    channel_type: str = "movie_recap"
    watermark: WatermarkSettings
    textWatermark: Optional[WatermarkSettings] = None

# In-memory status store for MVP
job_status = {}
job_evaluations = {}
pending_jobs = {}

def send_webhook_with_n8n_autostart(webhook_url: str, payload: dict, max_retries: int = 3):
    """
    Checks if n8n is running on port 5678. If not running, launches n8n automatically
    in a detached background session and waits for it to become ready before sending.
    """
    import socket
    import subprocess
    import time
    import urllib.request
    import urllib.error

    def is_n8n_listening():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                return s.connect_ex(("127.0.0.1", 5678)) == 0
        except Exception:
            return False

    # Only attempt auto-start if the destination is a local n8n instance
    if ("5678" in webhook_url or "localhost" in webhook_url or "127.0.0.1" in webhook_url) and not is_n8n_listening():
        print("\n  [Webhook] 🚀 n8n is not running on port 5678. Automatically launching n8n in background...")
        cmd = "source ~/.nvm/nvm.sh 2>/dev/null && nvm use 20 && export N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=false && n8n start"
        try:
            subprocess.Popen(
                ["bash", "-c", cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            for attempt in range(15):
                time.sleep(2)
                if is_n8n_listening():
                    print(f"  [Webhook] ✅ n8n is ready and listening on port 5678! (waited {attempt*2 + 2}s)")
                    time.sleep(3)  # Brief buffer for n8n webhook routes to register
                    break
        except Exception as launch_err:
            print(f"  [Webhook] ⚠️ Could not auto-launch n8n: {launch_err}")

    print(f"  [Webhook] Sending completion POST to {webhook_url}...")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"}, method="POST")

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                print("  [Webhook] ✅ Success! Dispatched to n8n.")
                return True
        except urllib.error.HTTPError as he:
            print(f"  [Webhook] HTTP Error {he.code}: {he.reason}")
            if he.code == 404:
                print("  [Webhook Hint] 404 Not Found: Ensure your workflow in n8n is toggled to ACTIVE and uses the Production URL (/webhook/..., not /webhook-test/...).")
            time.sleep(2)
        except Exception as e:
            print(f"  [Webhook] Attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    return False

TRAINING_DATASET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "training_dataset")
os.makedirs(TRAINING_DATASET_DIR, exist_ok=True)

def archive_training_script(video_id: str, channel_type: str, target_lang: str, script_path: str, transcript_path: str = None):
    """
    Permanently archives the source transcript and LLM-generated script in 'training_dataset/'
    for future LLM fine-tuning and training. This directory is NEVER deleted by temp/output cleanup.
    """
    import datetime
    try:
        archive_dir = os.path.join(TRAINING_DATASET_DIR, video_id)
        os.makedirs(archive_dir, exist_ok=True)
        
        # 1. Copy the raw translated script JSON
        if os.path.exists(script_path):
            dst_script = os.path.join(archive_dir, f"{video_id}_{channel_type}_{target_lang}_script.json")
            shutil.copy2(script_path, dst_script)
            
            with open(script_path, "r", encoding="utf-8") as f:
                segments = json.load(f)
                
            # 2. Build paired fine-tuning dataset (JSON and JSONL format for HuggingFace / Unsloth)
            paired_data = {
                "video_id": video_id,
                "channel_type": channel_type,
                "target_language": target_lang,
                "created_at": datetime.datetime.now().isoformat(),
                "total_segments": len(segments),
                "pairs": []
            }
            
            jsonl_entries = []
            for s in segments:
                orig = s.get("original_text", "").strip()
                trans = s.get(target_lang, "").strip()
                if orig and trans:
                    paired_data["pairs"].append({
                        "id": s.get("id"),
                        "start": s.get("start"),
                        "end": s.get("end"),
                        "source_script": orig,
                        "llm_script": trans
                    })
                    # Standard instruction format for fine-tuning LLMs
                    jsonl_entries.append({
                        "instruction": f"Translate and elevate this {channel_type.replace('_', ' ')} segment into high-energy spoken {target_lang.capitalize()} narration.",
                        "input": orig,
                        "output": trans
                    })
                    
            paired_path = os.path.join(archive_dir, f"{video_id}_{channel_type}_{target_lang}_pairs.json")
            with open(paired_path, "w", encoding="utf-8") as f:
                json.dump(paired_data, f, indent=2, ensure_ascii=False)
                
            jsonl_path = os.path.join(archive_dir, f"{video_id}_{channel_type}_{target_lang}_finetune.jsonl")
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for entry in jsonl_entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    
            # 3. Build a clean human-readable script text file (.txt)
            txt_path = os.path.join(archive_dir, f"{video_id}_{channel_type}_{target_lang}_full_script.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"=== {channel_type.upper()} ({target_lang.upper()}) SCRIPT - {video_id} ===\n\n")
                f.write("FULL CONTINUOUS NARRATION:\n")
                f.write(" ".join([s.get(target_lang, "").strip() for s in segments if s.get(target_lang)]))
                f.write("\n\n" + "="*50 + "\n\n")
                f.write("SEGMENT-BY-SEGMENT PAIRS (SOURCE vs LLM GENERATED):\n\n")
                for s in segments:
                    f.write(f"[{s.get('id')}] ({s.get('start', 0):.2f}s - {s.get('end', 0):.2f}s)\n")
                    f.write(f"SOURCE : {s.get('original_text', '').strip()}\n")
                    f.write(f"LLM    : {s.get(target_lang, '').strip()}\n\n")

            print(f"  [Dataset Archive] 📚 Permanently archived training script and finetune pairs to: {archive_dir}")

        # 4. Copy original transcript if available
        if transcript_path and os.path.exists(transcript_path):
            dst_orig = os.path.join(archive_dir, f"{video_id}_source_transcript.json")
            shutil.copy2(transcript_path, dst_orig)

    except Exception as e:
        print(f"  [Dataset Archive] ⚠️ Failed to archive training script: {e}")

def cleanup_job_temp(video_id: str):
    """Removes heavy scratch render files (video chunks, resampled audio, mixed temp files) while preserving audio & video cache."""
    try:
        if video_id:
            job_temp = os.path.join("temp", video_id)
            if os.path.exists(job_temp):
                for stale in ["video_only.mp4", "mixed_temp.mp4", "narrator_audio_track.wav"]:
                    p = os.path.join(job_temp, stale)
                    if os.path.exists(p):
                        try: os.remove(p)
                        except: pass
                for stale_dir in ["video_chunks", "resampled_wavs"]:
                    p = os.path.join(job_temp, stale_dir)
                    if os.path.exists(p):
                        shutil.rmtree(p, ignore_errors=True)
                print(f"  [Cleanup] 🧹 Cleared scratch render artifacts for: {job_temp}")
    except Exception as e:
        print(f"  [Cleanup] Warning while clearing temp files: {e}")

def schedule_delayed_output_cleanup(video_id: str, delay_seconds: int = 180):
    """Preserves output video permanently so n8n / YouTube uploads are never interrupted."""
    pass

def process_pipeline(job_id: str, request: VideoRequest):
    url = request.url
    target_lang = getattr(request, 'target_language', 'hindi').lower()
    channel_type = getattr(request, 'channel_type', 'movie_recap').lower()
    
    key_manager = ApiKeyManager()
    groq_api_key = key_manager.get_next_key()
    
    is_local_file = os.path.exists(url) and os.path.isfile(url)
    
    # Try to extract video ID for caching
    if is_local_file:
        video_id = os.path.splitext(os.path.basename(url))[0]
    else:
        video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        video_id = video_id_match.group(1) if video_id_match else job_id
        
    job_dir = f"temp/{video_id}"
    os.makedirs(job_dir, exist_ok=True)
    
    output_folder = f"output/{video_id}"
    os.makedirs(output_folder, exist_ok=True)
    output_suffix = f"_{channel_type}" if channel_type == "thriller_story" else ""
    final_output = os.path.join(output_folder, f"{video_id}{output_suffix}_final.mp4")
    metadata_output = os.path.join(output_folder, f"{video_id}{output_suffix}_metadata.json")
    
    if os.path.exists(final_output):
        print(f"\n[JOB {job_id}] ⚡ FINAL VIDEO ALREADY EXISTS! Skipping generation and firing webhook directly.")
        job_status[job_id] = f"Completed: {final_output}"
        
        # If metadata is missing, generate it or create fallback so webhook can proceed
        if not os.path.exists(metadata_output):
            script_path = f"temp/{video_id}/{video_id}_audio_{target_lang}{output_suffix}_transcript.json"
            if not os.path.exists(script_path):
                script_path = f"temp/{video_id}/{video_id}_audio_transcript.json"
            if os.path.exists(script_path):
                try:
                    groq_api_key = os.getenv("GROQ_API_KEY")
                    metadata_generator = MetadataGenerator(api_key=groq_api_key)
                    metadata_generator.generate(script_path, metadata_output, target_lang=target_lang)
                    print(f"  [Metadata] Generated missing metadata: {metadata_output}")
                except Exception as meta_err:
                    print(f"  [Metadata] Could not generate metadata: {meta_err}")
            
            if not os.path.exists(metadata_output):
                with open(metadata_output, "w", encoding="utf-8") as f:
                    json.dump({
                        "title": f"Story - {video_id}",
                        "description": f"Video explanation for {video_id}.",
                        "keywords": ["story", "recap", "explanation"]
                    }, f, indent=2)
                print(f"  [Metadata] Created fallback metadata: {metadata_output}")

        # Check publishing configuration
        publishing_cfg = config.get("publishing", {})
        allow_youtube = publishing_cfg.get("enable_youtube_webhook", False)
        allow_facebook = publishing_cfg.get("enable_facebook_upload", False)

        if channel_type == "full_movie" or not allow_youtube:
            print(f"  [Publishing] 🛑 Auto-upload to YouTube & Facebook is PAUSED (full movie raw video testing mode).")
            print(f"  [Publishing] 📁 Preserving output video permanently at: {final_output}")
            return

        if request.webhook_url and allow_youtube:
            abs_video_path = os.path.abspath(final_output)
            abs_metadata_path = os.path.abspath(metadata_output)
            
            with open(abs_metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            payload = {
                "job_id": job_id,
                "channel_type": channel_type,
                "video_id": video_id,
                "status": "success",
                "final_video_path": abs_video_path,
                "metadata_path": abs_metadata_path,
                "download_url": f"http://127.0.0.1:8000/output/{video_id}/{os.path.basename(final_output)}",
                "url": url,
                "title": meta.get("title", f"Video {video_id}"),
                "description": meta.get("description", ""),
                "tags": meta.get("keywords", [])
            }
            send_webhook_with_n8n_autostart(request.webhook_url, payload)

        # Auto-publish directly to Facebook Page (Woivy Recaps)
        if allow_facebook and os.getenv("FB_PAGE_ACCESS_TOKEN") and os.getenv("FB_PAGE_ID"):
            try:
                from core.facebook_uploader import FacebookUploader
                fb_uploader = FacebookUploader()
                fb_uploader.upload_video(
                    final_output,
                    title=meta.get("title", f"Video {video_id}"),
                    description=meta.get("description", ""),
                    tags=meta.get("keywords", []),
                    movie_title=meta.get("movie_title")
                )
            except Exception as fb_err:
                print(f"  [Facebook Auto-Publisher] ⚠️ Warning: {fb_err}")
        return
    
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print("Warning: failed to load config.yaml, using defaults")
        config = {}
        
    try:
        if channel_type == "full_movie":
            # ─────────────────────────────────────────────────────────────
            # CHANNEL 3: FULL MOVIE TO YOUTUBE RECAP (LOCAL MOVIE FILE)
            # ─────────────────────────────────────────────────────────────
            from core.movie_recap_engine import MovieRecapEngine
            recap_engine = MovieRecapEngine(
                api_key=groq_api_key,
                model=config.get("groq", {}).get("translation_model", "qwen/qwen3.8-27b")
            )

            # Step 1: Video File
            if is_local_file:
                video_path = url
                job_status[job_id] = "Using local movie video file"
                print(f"\n[JOB {job_id}] Step 1: Using local movie video file: {video_path}")
            else:
                video_path = f"temp/videos/{video_id}.mp4"
                if not os.path.exists(video_path):
                    downloader = YouTubeDownloader(output_dir="temp/videos")
                    video_path = downloader.download(url)

            # Step 2: Extract Embedded Studio Subtitles
            transcript_path = os.path.join(job_dir, f"{video_id}_audio_transcript.json")
            if os.path.exists(transcript_path):
                print(f"\n[JOB {job_id}] Step 2: Found cached movie dialogue JSON. Skipping extraction.")
            else:
                job_status[job_id] = "Extracting studio dialogue tracks from movie..."
                print(f"\n[JOB {job_id}] Step 2: Extracting studio dialogue tracks from movie container...")
                transcript_path = recap_engine.extract_subtitles_to_json(video_path, job_dir, preferred_lang=target_lang)

            # Step 3: Distill Dialogue into Master YouTube Recap Script
            target_lang = request.target_language.lower()
            script_path = os.path.join(job_dir, f"{video_id}_audio_{target_lang}_transcript.json")
            if os.path.exists(script_path) and not request.force_regenerate_script:
                job_status[job_id] = f"Script generation skipped (using cache)"
                print(f"\n[JOB {job_id}] Step 3: {target_lang.capitalize()} recap script found in cache. Skipping.")
            else:
                job_status[job_id] = f"Generating {target_lang} master movie recap script..."
                print(f"\n[JOB {job_id}] Step 3: Generating {target_lang} master movie recap script...")
                script_path = recap_engine.generate_recap_script(
                    video_path, transcript_path, script_path, target_lang=target_lang, overwrite=True
                )
                print(f"[JOB {job_id}] Full movie recap script ready: {script_path}")
        else:
            # ─────────────────────────────────────────────────────────────
            # CHANNELS 1 & 2: YOUTUBE MOVIE RECAP & THRILLER STORY
            # ─────────────────────────────────────────────────────────────
            # Step 1: Video Download
            if is_local_file:
                video_path = url
                job_status[job_id] = "Using local video file"
                print(f"\n[JOB {job_id}] Step 1: Using local video file: {video_path}")
            else:
                video_path = f"temp/videos/{video_id}.mp4"
                if os.path.exists(video_path) and os.path.getsize(video_path) >= 1024 * 1024:
                    job_status[job_id] = "Video download skipped (using cache)"
                    print(f"\n[JOB {job_id}] Step 1: Video found in cache. Skipping download.")
                else:
                    if os.path.exists(video_path):
                        try: os.remove(video_path)
                        except: pass
                    job_status[job_id] = "Downloading video..."
                    print(f"\n[JOB {job_id}] Step 1: Downloading Video from {url}")
                    downloader = YouTubeDownloader(output_dir="temp/videos")
                    video_path = downloader.download(url)
                print(f"[JOB {job_id}] Video stored at: {video_path}")
                
            # Step 2: Audio Extraction
            raw_audio_path = os.path.join(job_dir, f"{video_id}_audio.mp3")
            if os.path.exists(raw_audio_path):
                job_status[job_id] = "Audio extraction skipped (using cache)"
                print(f"\n[JOB {job_id}] Step 2: Extracted audio found in cache. Skipping.")
            else:
                job_status[job_id] = "Extracting audio..."
                print(f"\n[JOB {job_id}] Step 2: Extracting Audio...")
                extractor = AudioExtractor(output_dir=job_dir)
                raw_audio_path = extractor.extract_audio(video_path)
                print(f"[JOB {job_id}] Audio extracted to: {raw_audio_path}")
                
            # Step 3: Transcription
            transcript_path = os.path.join(job_dir, f"{video_id}_audio_transcript.json")
            if os.path.exists(transcript_path):
                job_status[job_id] = "Transcription skipped (using cache)"
                print(f"\n[JOB {job_id}] Step 3: Transcript found in cache. Skipping.")
            else:
                job_status[job_id] = "Fetching YouTube transcript..."
                print(f"\n[JOB {job_id}] Step 3: Fetching Official YouTube Transcript...")
                transcriber = Transcriber(
                    output_dir=job_dir, 
                    api_key=groq_api_key
                )
                transcript_path = transcriber.transcribe(raw_audio_path, youtube_url=url)
                print(f"[JOB {job_id}] YouTube Transcript ready. JSON stored at: {transcript_path}")
                
            # Step 3.5: Pre-Flight Script Quality Gate (Threshold >= 90%)
            job_status[job_id] = "Evaluating transcript quality & ASR integrity..."
            print(f"\n[JOB {job_id}] Step 3.5: Evaluating Transcript Quality Gate (Threshold >= 90%)...")
            evaluator = ScriptQualityEvaluator(api_key=groq_api_key, min_score=90)
            eval_result = evaluator.evaluate(transcript_path, channel_type=channel_type)
            job_evaluations[job_id] = eval_result
            score = eval_result.get("score", 0)
            verdict = eval_result.get("verdict", "REJECT")
            
            if score < 90 or verdict == "REJECT":
                reason = eval_result.get("reason", "Acoustic distortion and ASR corruption detected.")
                flaws = "; ".join(eval_result.get("detected_flaws", [])[:2])
                rejection_msg = f"Rejected (Score: {score}% - Below 90% Threshold): {reason}"
                job_status[job_id] = rejection_msg
                print(f"\n[JOB {job_id}] ❌ PIPELINE ABORTED: {rejection_msg}")
                if flaws:
                    print(f"[JOB {job_id}] Flagged Flaws: {flaws}")
                # Clean up scratch files immediately to conserve space
                cleanup_job_temp(video_id)
                return

            print(f"[JOB {job_id}] ✅ Transcript Quality Approved (Score: {score}%). Proceeding to translation.")
            job_status[job_id] = f"Transcript approved (Score: {score}%). Proceeding to translation..."

            # Step 4: Translation / Script Rewrite
            target_lang = request.target_language.lower()
            script_path = os.path.join(job_dir, f"{video_id}_audio_{target_lang}{output_suffix}_transcript.json")
            if os.path.exists(script_path):
                job_status[job_id] = f"Script generation skipped (using cache)"
                print(f"\n[JOB {job_id}] Step 4: {target_lang.capitalize()} script found in cache. Skipping.")
            else:
                job_status[job_id] = f"Generating {target_lang} script ({channel_type})..."
                print(f"\n[JOB {job_id}] Step 4: Generating {target_lang} script for {channel_type}...")
                translator = StoryTranslator(
                    primary_provider=config.get("llm", {}).get("primary_provider", "groq"),
                    fallback_provider=config.get("llm", {}).get("fallback_provider", "none"),
                    translation_model=config.get("groq", {}).get("translation_model", "llama-3.1-70b-versatile"),
                    batch_size=config.get("translation", {}).get("batch_size", 20),
                    api_key=groq_api_key
                )
                script_path = translator.translate_transcript(transcript_path, target_language=target_lang, output_dir=job_dir, channel_type=channel_type)
                print(f"[JOB {job_id}] Script generation complete. JSON stored at: {script_path}")
            print(f"[JOB {job_id}] Script generation complete. JSON stored at: {script_path}")
            
        # Archive script permanently for LLM training dataset before any cleanup can occur
        archive_training_script(video_id, channel_type, target_lang, script_path, transcript_path)
            
        # Prepare pipeline state to support pause/resume
        req_dict = request.model_dump() if hasattr(request, "model_dump") else request.dict()
        state = {
            "job_id": job_id,
            "video_id": video_id,
            "channel_type": channel_type,
            "target_lang": target_lang,
            "script_path": os.path.abspath(script_path),
            "job_dir": os.path.abspath(job_dir),
            "video_path": os.path.abspath(video_path),
            "final_output": os.path.abspath(final_output),
            "metadata_output": os.path.abspath(metadata_output),
            "output_folder": os.path.abspath(output_folder),
            "url": url,
            "groq_api_key": groq_api_key,
            "request": req_dict
        }
        pending_jobs[job_id] = state

        # Save to disk for crash recovery
        state_file = os.path.join(job_dir, "job_state.json")
        try:
            with open(state_file, "w", encoding="utf-8") as sf:
                json.dump(state, sf, indent=2)
        except Exception as e:
            print(f"  [Resume] Warning writing job_state.json: {e}")

        # Pause for manual script review and verification (default True for both movie_recap and thriller_story)
        if getattr(request, "pause_for_review", True):
            job_status[job_id] = "waiting_review"
            print(f"\n[JOB {job_id}] ⏸️ SCRIPT GENERATED! Pipeline paused for manual review & fixes.")
            print(f"  [Review] Script path: {script_path}")
            print(f"  [Review] Inspect/edit the script on the UI or in your editor, then click 'Resume' to generate audio and video.\n")
            return

        # Otherwise continue immediately
        execute_resume_pipeline(job_id, state)

    except ffmpeg.Error as e:
        err_msg = e.stderr.decode('utf8') if e.stderr else str(e)
        job_status[job_id] = f"FFmpeg Error: {err_msg}"
        print(f"\n[JOB {job_id}] FFmpeg Error:\n{err_msg}")
    except Exception as e:
        job_status[job_id] = f"Error: {str(e)}"
        print(f"\n[JOB {job_id}] Exception: {str(e)}")


def execute_resume_pipeline(job_id: str, state: dict):
    """
    Resumes pipeline from Step 5 (TTS Voice Generation) using the latest,
    potentially manually corrected script from disk, then renders final video,
    burns in styled subtitles, generates SEO metadata, and publishes.
    """
    try:
        video_id = state["video_id"]
        channel_type = state["channel_type"]
        target_lang = state["target_lang"]
        script_path = state["script_path"]
        job_dir = state["job_dir"]
        video_path = state["video_path"]
        final_output = state["final_output"]
        metadata_output = state["metadata_output"]
        output_folder = state["output_folder"]
        url = state["url"]
        groq_api_key = state.get("groq_api_key") or os.getenv("GROQ_API_KEY", "")

        req_data = state.get("request", {})
        request = VideoRequest(**req_data) if isinstance(req_data, dict) else req_data

        try:
            with open("config.yaml", "r") as f:
                config = yaml.safe_load(f)
        except Exception:
            config = {}

        # Step 5: TTS Generation from latest script on disk
        tts_provider = config.get("tts", {}).get("provider", "gemini")
        job_status[job_id] = f"Generating {target_lang.capitalize()} voice via {tts_provider.capitalize()}..."
        print(f"\n[JOB {job_id}] Step 5: Generating {target_lang.capitalize()} Voice via {tts_provider.capitalize()}...")

        if tts_provider == "kokoro":
            default_voice = "hf_alpha" if target_lang == "hindi" else "af_heart"
            speaker = default_voice 
            lang_code_char = 'h' if target_lang == "hindi" else 'a'
            tts = KokoroTTS(output_dir=f"{job_dir}/segments", voice_name=speaker, lang_code=lang_code_char)
        else:
            speaker = config.get("gemini_tts", {}).get("voice", "Zephyr")
            model = config.get("gemini_tts", {}).get("model", "gemini-3.1-flash-tts-preview")
            tts = GeminiTTS(output_dir=f"{job_dir}/segments", voice_name=speaker, model=model)

        sync = AudioSynchronizer(
            max_speed_change=config.get("sync", {}).get("max_speed_change", 0.15),
            rewrite_threshold=config.get("sync", {}).get("rewrite_threshold", 1.15)
        )

        # Always read fresh script from disk so any manual fixes are honored!
        with open(script_path, "r", encoding="utf-8") as f:
            segments = json.load(f)

        # Step 5B: Generate AI Visual Images via Cloudflare FLUX.1 if thriller story
        if channel_type == "thriller_story":
            print(f"\n[JOB {job_id}] Step 5B: Generating Cloudflare FLUX.1 AI Images for Tagged Segments...")
            img_gen = CloudflareImageGenerator()
            ai_dir = os.path.join(job_dir, "ai_images")
            os.makedirs(ai_dir, exist_ok=True)
            for seg in segments:
                img_path = os.path.join(ai_dir, f"seg_{seg['id']:04d}.jpg")
                if os.path.exists(img_path):
                    seg["use_ai_image"] = True
                    seg["ai_image_path"] = img_path
                elif seg.get("use_ai_image") and seg.get("image_prompt"):
                    if not os.path.exists(img_path):
                        print(f"  [Cloudflare FLUX.1] Generating visual for segment {seg['id']}...")
                        img_gen.generate_image(seg["image_prompt"], img_path)
                    seg["ai_image_path"] = img_path

            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(segments, f, indent=4, ensure_ascii=False)

        aligned_audio_segments = []
        for i, seg in enumerate(segments):
            text = seg.get(target_lang, "").strip()
            if not text or text.lower() in ["translation/rewrite failed", "error", "failed", "[skip_promo]", "skip_promo"]:
                print(f"  [TTS] Skipping segment {seg['id']} (Empty text or promo placeholder: '{text}')")
                continue

            text = StoryTranslator.sanitize_segment_text(text, target_language=target_lang)
            audio_path = os.path.join(f"{job_dir}/segments", f"{seg['id']:04d}.wav")
            
            if not os.path.exists(audio_path):
                print(f"  [TTS] Generating Audio for Segment {seg['id']} ({i+1}/{len(segments)})...")
                tts.generate_audio(seg["id"], text)

            aligned_audio_segments.append({
                "id": seg["id"],
                "start": seg["start"],
                "end": seg["end"],
                "text": text,
                "audio_path": audio_path,
                "movie_timestamp": seg.get("movie_timestamp"),
                "is_scene_change": seg.get("is_scene_change", False),
                "scene_location": seg.get("scene_location", ""),
                "use_ai_image": seg.get("use_ai_image", False),
                "ai_image_path": seg.get("ai_image_path", None)
            })

        output_folder = os.path.join("output", video_id)
        os.makedirs(output_folder, exist_ok=True)

        job_status[job_id] = f"Rendering final video ({channel_type})..."
        print(f"\n[JOB {job_id}] Step 6: Rendering Final Video for {channel_type} (Captions: {getattr(request, 'burn_subtitles', True)})...")

        # Clear stale render artifacts
        for stale in ["video_only.mp4", "mixed_temp.mp4"]:
            p = os.path.join(job_dir, stale)
            if os.path.exists(p):
                os.remove(p)
                print(f"  [Cache] Removed stale: {stale}")

        sync.build_timeline(
            aligned_audio_segments, video_path, final_output,
            job_dir=job_dir,
            watermark_settings=request.watermark,
            text_watermark_settings=request.textWatermark,
            skip_intervals=request.skip_intervals,
            channel_type=channel_type,
            burn_subtitles=getattr(request, 'burn_subtitles', True)
        )

        for sub_ext in ["srt", "ass"]:
            sub_f = os.path.join(job_dir, f"subtitles.{sub_ext}")
            if os.path.exists(sub_f):
                shutil.copy2(sub_f, os.path.join(output_folder, f"{video_id}.{sub_ext}"))

        job_status[job_id] = "Generating SEO Metadata..."
        print(f"\n[JOB {job_id}] Step 7: Generating SEO Metadata...")
        metadata_generator = MetadataGenerator(api_key=groq_api_key)
        metadata_generator.generate(script_path, metadata_output, target_lang=target_lang)

        job_status[job_id] = f"Completed: {final_output}"
        print(f"\n[JOB {job_id}] ✅ DONE! Final video and metadata saved to {output_folder}")

        # Check publishing configuration
        publishing_cfg = config.get("publishing", {})
        allow_youtube = publishing_cfg.get("enable_youtube_webhook", False)
        allow_facebook = publishing_cfg.get("enable_facebook_upload", False)

        if channel_type == "full_movie" or not allow_youtube:
            print(f"  [Publishing] 🛑 Auto-upload to YouTube & Facebook is PAUSED (full movie raw video testing mode).")
            print(f"  [Publishing] 📁 Preserving output video permanently at: {final_output}")
        elif request.webhook_url and allow_youtube:
            abs_video_path = os.path.abspath(final_output)
            abs_metadata_path = os.path.abspath(metadata_output)
            with open(abs_metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            payload = {
                "job_id": job_id,
                "channel_type": channel_type,
                "video_id": video_id,
                "status": "success",
                "final_video_path": abs_video_path,
                "metadata_path": abs_metadata_path,
                "download_url": f"http://127.0.0.1:8000/output/{video_id}/{os.path.basename(final_output)}",
                "url": url,
                "title": meta.get("title", f"Video {video_id}"),
                "description": meta.get("description", ""),
                "tags": meta.get("keywords", [])
            }
            send_webhook_with_n8n_autostart(request.webhook_url, payload)
            schedule_delayed_output_cleanup(video_id, delay_seconds=180)

        if allow_facebook and os.getenv("FB_PAGE_ACCESS_TOKEN") and os.getenv("FB_PAGE_ID") and channel_type != "full_movie":
            try:
                from core.facebook_uploader import FacebookUploader
                fb_uploader = FacebookUploader()
                fb_uploader.upload_video(
                    final_output,
                    title=meta.get("title", f"Video {video_id}"),
                    description=meta.get("description", ""),
                    tags=meta.get("keywords", []),
                    movie_title=meta.get("movie_title")
                )
            except Exception as fb_err:
                print(f"  [Facebook Auto-Publisher] ⚠️ Warning: {fb_err}")

        cleanup_job_temp(video_id)
        
    except ffmpeg.Error as e:
        err_msg = e.stderr.decode('utf8') if e.stderr else str(e)
        job_status[job_id] = f"FFmpeg Error: {err_msg}"
        print(f"\n[JOB {job_id}] FFmpeg Error:\n{err_msg}")
    except Exception as e:
        job_status[job_id] = f"Error: {str(e)}"
        print(f"\n[JOB {job_id}] Exception: {str(e)}")

@app.get("/api/storage-stats")
def get_storage_stats():
    def get_dir_size(path):
        if not os.path.exists(path):
            return "0 MB"
        total = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except:
                    pass
        if total > 1024 * 1024 * 1024:
            return f"{total / (1024 * 1024 * 1024):.2f} GB"
        return f"{total / (1024 * 1024):.1f} MB"
        
    return {
        "temp_size": get_dir_size("temp"),
        "output_size": get_dir_size("output")
    }

@app.post("/api/cleanup")
def cleanup_all():
    """Immediately clears all files in temp/ and output/ to reclaim 100% of space."""
    import shutil
    cleared = []
    if os.path.exists("temp"):
        for item in os.listdir("temp"):
            if item == "api_key_state.txt":
                continue
            p = os.path.join("temp", item)
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                cleared.append(f"temp/{item}")
            except Exception as e:
                print(f"Error deleting {p}: {e}")
                
    if os.path.exists("output"):
        for item in os.listdir("output"):
            p = os.path.join("output", item)
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                cleared.append(f"output/{item}")
            except Exception as e:
                print(f"Error deleting {p}: {e}")
                
    return {"status": "success", "cleared": cleared}

@app.post("/api/cleanup/{video_id}")
def cleanup_single(video_id: str):
    import shutil
    cleanup_job_temp(video_id)
    out_dir = os.path.join("output", video_id)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)
    return {"status": "success", "message": f"Cleared {video_id} temp and output."}

def find_pending_job(job_id: str) -> Optional[dict]:
    p_job = pending_jobs.get(job_id)
    if not p_job:
        for candidate in glob.glob("temp/*/job_state.json"):
            try:
                with open(candidate, "r", encoding="utf-8") as cf:
                    cdata = json.load(cf)
                    if cdata.get("job_id") == job_id:
                        p_job = cdata
                        pending_jobs[job_id] = p_job
                        break
            except Exception:
                pass
    return p_job

@app.post("/api/process")
def process_video(request: VideoRequest, background_tasks: BackgroundTasks):
    import uuid
    job_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(process_pipeline, job_id, request)
    return {"status": "started", "job_id": job_id}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    st = job_status.get(job_id, "Not found")
    p_job = find_pending_job(job_id)
    if st == "Not found" and p_job:
        final_out = p_job.get("final_output", "")
        if final_out and os.path.exists(final_out):
            st = f"Completed: {final_out}"
        elif p_job.get("script_path") and os.path.exists(p_job.get("script_path")):
            st = "waiting_review"

    return {
        "job_id": job_id, 
        "status": st,
        "evaluation": job_evaluations.get(job_id, None),
        "waiting_review": st == "waiting_review",
        "script_path": p_job.get("script_path") if p_job else None,
        "video_id": p_job.get("video_id") if p_job else None,
        "channel_type": p_job.get("channel_type") if p_job else None
    }

@app.post("/api/resume/{job_id}")
def resume_pipeline_endpoint(job_id: str, background_tasks: BackgroundTasks):
    p_job = find_pending_job(job_id)
    if not p_job:
        raise HTTPException(status_code=404, detail=f"No pending job found with id {job_id}")

    job_status[job_id] = "Resuming pipeline (generating audio)..."
    background_tasks.add_task(execute_resume_pipeline, job_id, p_job)
    return {"status": "resumed", "job_id": job_id}

@app.get("/api/script/{job_id}")
def get_script_endpoint(job_id: str):
    p_job = find_pending_job(job_id)
    if not p_job or not os.path.exists(p_job.get("script_path", "")):
        raise HTTPException(status_code=404, detail="Script file not found for this job")

    with open(p_job["script_path"], "r", encoding="utf-8") as f:
        segments = json.load(f)
    return {
        "job_id": job_id,
        "video_id": p_job.get("video_id"),
        "script_path": p_job.get("script_path"),
        "target_lang": p_job.get("target_lang", "english"),
        "total_segments": len(segments),
        "segments": segments
    }

class ScriptUpdateRequest(BaseModel):
    segments: List[dict]

@app.post("/api/script/{job_id}")
def update_script_endpoint(job_id: str, payload: ScriptUpdateRequest):
    p_job = find_pending_job(job_id)
    if not p_job or not os.path.exists(p_job.get("script_path", "")):
        raise HTTPException(status_code=404, detail="Script file not found for this job")

    with open(p_job["script_path"], "w", encoding="utf-8") as f:
        json.dump(payload.segments, f, indent=4, ensure_ascii=False)
    
    return {"status": "success", "message": f"Saved {len(payload.segments)} segments to script."}

@app.get("/api/training-datasets")
def list_training_datasets():
    """Lists all archived LLM training datasets and paired scripts."""
    datasets = []
    if os.path.exists(TRAINING_DATASET_DIR):
        for video_id in sorted(os.listdir(TRAINING_DATASET_DIR)):
            vpath = os.path.join(TRAINING_DATASET_DIR, video_id)
            if os.path.isdir(vpath):
                files = os.listdir(vpath)
                pairs_file = next((f for f in files if f.endswith("_pairs.json")), None)
                total_pairs = 0
                if pairs_file:
                    try:
                        with open(os.path.join(vpath, pairs_file), "r", encoding="utf-8") as pf:
                            total_pairs = json.load(pf).get("total_segments", 0)
                    except:
                        pass
                datasets.append({
                    "video_id": video_id,
                    "files": files,
                    "total_pairs": total_pairs
                })
    return {"datasets": datasets, "total_datasets": len(datasets), "directory": TRAINING_DATASET_DIR}

@app.get("/api/local-movies")
def list_local_movies():
    """Lists video and movie files found in local directories for easy Channel 3 selection."""
    movies = []
    scan_dirs = ["donwloadedmovies", "downloadedmovies", "temp/videos", "backend/donwloadedmovies"]
    valid_extensions = (".mkv", ".mp4", ".mov", ".avi", ".webm")
    seen_paths = set()
    
    for d in scan_dirs:
        if os.path.exists(d) and os.path.isdir(d):
            for fname in sorted(os.listdir(d)):
                if fname.lower().endswith(valid_extensions):
                    fpath = os.path.join(d, fname)
                    abs_path = os.path.abspath(fpath)
                    if abs_path not in seen_paths:
                        seen_paths.add(abs_path)
                        try:
                            size_mb = round(os.path.getsize(abs_path) / (1024 * 1024), 1)
                            movies.append({
                                "name": fname,
                                "path": abs_path,
                                "size_mb": size_mb,
                                "folder": d
                            })
                        except Exception:
                            pass
    return {"movies": movies, "total": len(movies)}

def apply_watermarks_to_ffmpeg(stream, watermark_path, settings: WatermarkSettings, main_w="main_w", main_h="main_h"):
    """Helper to apply the watermark to an ffmpeg video stream at multiple corners."""
    import ffmpeg
    if not settings:
        return stream
        
    corners = {
        "topLeft": settings.topLeft,
        "topRight": settings.topRight,
        "bottomLeft": settings.bottomLeft,
        "bottomRight": settings.bottomRight
    }
    
    enabled_corners = [(pos, corner) for pos, corner in corners.items() if corner and corner.enabled]
    if not enabled_corners:
        return stream
        
    wm_input = ffmpeg.input(watermark_path, loop=1)
    # If multiple corners are enabled, we must split the input to avoid graph deduping errors
    splits = wm_input.split() if len(enabled_corners) > 1 else [wm_input]
    
    for i, (position, corner) in enumerate(enabled_corners):
        wm = splits[i].filter('scale', w=corner.size, h='-1')
        
        # Determine coordinates
        if position == "topLeft":
            x = corner.offsetX
            y = corner.offsetY
        elif position == "topRight":
            x = f"{main_w}-overlay_w-{corner.offsetX}"
            y = corner.offsetY
        elif position == "bottomLeft":
            x = corner.offsetX
            y = f"{main_h}-overlay_h-{corner.offsetY}"
        elif position == "bottomRight":
            x = f"{main_w}-overlay_w-{corner.offsetX}"
            y = f"{main_h}-overlay_h-{corner.offsetY}"
            
        stream = ffmpeg.overlay(stream, wm, x=x, y=y, shortest=1)
        
    return stream

@app.post("/api/snapshot")
def generate_snapshot(request: SnapshotRequest):
    import base64
    import tempfile
    
    is_local_file = os.path.exists(request.url) and os.path.isfile(request.url)
    
    if is_local_file:
        video_path = request.url
    else:
        video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", request.url)
        if not video_id_match:
            return {"error": "Invalid YouTube URL or Local File"}
        video_id = video_id_match.group(1)
        
        video_path = f"temp/videos/{video_id}.mp4"
        # Check if video is already fully downloaded
        if not os.path.exists(video_path) or os.path.getsize(video_path) < 1024 * 1024:
            # Check if an active download is currently in progress (.part file)
            part_files = [f for f in os.listdir("temp/videos") if f.startswith(f"{video_id}.") and f.endswith(".part")] if os.path.exists("temp/videos") else []
            if part_files:
                return {"error": "Video download is currently in progress. Please wait a moment before generating a preview snapshot."}

            os.makedirs("temp/videos", exist_ok=True)
            downloader = YouTubeDownloader(output_dir="temp/videos")
            try:
                video_path = downloader.download(request.url)
            except Exception as e:
                return {"error": f"Failed to download video: {str(e)}"}
            
    channel_type = getattr(request, 'channel_type', 'movie_recap').lower()
    if channel_type == "thriller_story":
        watermark_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/watermark thriller.png"
        text_watermark_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/textWatermark_thriller.png"
    else:
        watermark_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/watermark.png"
        text_watermark_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/textWatermark.png"
    
    try:
        # Determine duration to safely seek without hitting EOF
        try:
            probe = ffmpeg.probe(video_path)
            duration = float(probe.get('format', {}).get('duration', 0))
        except:
            duration = 0

        if duration > 70:
            seek_time = "00:01:00"
        elif duration > 5:
            seek_time = str(max(1, int(duration / 2)))
        else:
            seek_time = "0"

        # Extract 1 frame at safe seek position
        vid = ffmpeg.input(video_path, ss=seek_time).video
        
        # Scale to match the final video rendering dimensions (1280x720) 
        # so the X/Y coordinates in the snapshot exactly match the final video!
        vid = vid.filter("scale", 1280, 720).filter("setsar", 1)
        
        # Apply watermarks
        out_stream = apply_watermarks_to_ffmpeg(vid, watermark_path, request.watermark)
        out_stream = apply_watermarks_to_ffmpeg(out_stream, text_watermark_path, request.textWatermark)
        
        # Output to temp file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
            
        out_stream = out_stream.output(tmp_path, vframes=1, format='image2', vcodec='mjpeg', loglevel='error')
        ffmpeg.run(out_stream, overwrite_output=True)
        
        with open(tmp_path, "rb") as img_file:
            encoded_string = base64.b64encode(img_file.read()).decode('utf-8')
            
        os.remove(tmp_path)
        return {"image": f"data:image/jpeg;base64,{encoded_string}"}
        
    except ffmpeg.Error as e:
        err = e.stderr.decode('utf8') if e.stderr else str(e)
        return {"error": f"FFmpeg error: {err}"}
    except Exception as e:
        return {"error": str(e)}

class TestImageRequest(BaseModel):
    prompt: Optional[str] = None

@app.post("/api/test-generate-image")
def test_generate_image(request: Optional[TestImageRequest] = None):
    import random
    import urllib.request
    import json
    
    api_key = os.getenv("CLOUDFARE_API_KEY")
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    
    if not api_key:
        return {"error": "CLOUDFARE_API_KEY is not set in backend/.env"}
        
    # Auto-discover Account ID if not set
    if not account_id:
        try:
            req_acc = urllib.request.Request(
                "https://api.cloudflare.com/client/v4/accounts",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            with urllib.request.urlopen(req_acc, timeout=10) as resp:
                acc_data = json.loads(resp.read().decode('utf-8'))
                if acc_data.get("result"):
                    account_id = acc_data["result"][0]["id"]
        except Exception as e:
            return {"error": f"Failed to retrieve Cloudflare Account ID: {str(e)}"}
            
    if not account_id:
        return {"error": "Could not determine Cloudflare Account ID."}
        
    random_prompts = [
        "A cinematic moody 35mm film still of a dark abandoned police station at night, rain, neon reflection, 4k",
        "A suspenseful thriller scene, mysterious detective examining evidence under a desk lamp, noir style, 8k",
        "A hyper-realistic aerial view of a misty ancient mountain temple shrouded in fog, photorealistic, cinematic",
        "A retro 80s movie poster style scene, dramatic lighting, synthwave aesthetic, high detail, masterpiece",
        "An eerie empty interrogation room with single spotlight on a metal chair, cinematic atmosphere, 4k"
    ]
    
    selected_prompt = (request.prompt if request and request.prompt else random.choice(random_prompts)).strip()
    
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    payload = json.dumps({"prompt": selected_prompt}).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if not data.get("success"):
                return {"error": f"Cloudflare API error: {data.get('errors')}"}
            
            image_b64 = data["result"]["image"]
            return {
                "status": "success",
                "prompt": selected_prompt,
                "image": f"data:image/jpeg;base64,{image_b64}"
            }
    except Exception as e:
        return {"error": f"Failed to call Cloudflare API: {str(e)}"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
