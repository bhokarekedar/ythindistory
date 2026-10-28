from fastapi import FastAPI, BackgroundTasks
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

class SnapshotRequest(BaseModel):
    url: str
    channel_type: str = "movie_recap"
    watermark: WatermarkSettings
    textWatermark: Optional[WatermarkSettings] = None

# In-memory status store for MVP
job_status = {}

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

def cleanup_job_temp(video_id: str):
    """Removes all heavy intermediate temp files (video chunks, resampled audio, mixed temp files) for this job."""
    import shutil
    try:
        if video_id:
            job_temp = os.path.join("temp", video_id)
            if os.path.exists(job_temp):
                shutil.rmtree(job_temp, ignore_errors=True)
                print(f"  [Cleanup] 🧹 Cleared intermediate temp directory: {job_temp}")
        raw_videos = "temp/videos"
        if os.path.exists(raw_videos):
            shutil.rmtree(raw_videos, ignore_errors=True)
            os.makedirs(raw_videos, exist_ok=True)
    except Exception as e:
        print(f"  [Cleanup] Warning while clearing temp files: {e}")

def schedule_delayed_output_cleanup(video_id: str, delay_seconds: int = 180):
    """Gives n8n 3 minutes to finish reading/uploading the final output before deleting it."""
    import threading
    import shutil
    
    def worker():
        time.sleep(delay_seconds)
        output_dir = os.path.join("output", video_id)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)
            print(f"  [Cleanup] 🧹 Automatically cleared final output folder after n8n upload: {output_dir}")
            
    t = threading.Thread(target=worker, daemon=True)
    t.start()

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

        if request.webhook_url:
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
        return
    
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print("Warning: failed to load config.yaml, using defaults")
        config = {}
        
    try:
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
            
        # Step 5: TTS Generation
        tts_provider = config.get("tts", {}).get("provider", "gemini")
        job_status[job_id] = f"Generating {target_lang.capitalize()} voice via {tts_provider.capitalize()}..."
        print(f"\n[JOB {job_id}] Step 5: Generating {target_lang.capitalize()} Voice via {tts_provider.capitalize()}...")
        
        if tts_provider == "kokoro":
            # For Hindi, default to hf_alpha. For English, default to af_heart
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
        
        with open(script_path, "r") as f:
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
            
            # Skip empty segments or error placeholders to ensure TTS never speaks errors aloud
            if not text or text.lower() in ["translation/rewrite failed", "error", "failed"]:
                print(f"  [TTS] Skipping segment {seg['id']} (Empty text or error placeholder: '{text}')")
                continue

            audio_path = os.path.join(f"{job_dir}/segments", f"{seg['id']:04d}.wav")
            
            if not os.path.exists(audio_path):
                print(f"  [TTS] Generating Audio for Segment {seg['id']} ({i+1}/{len(segments)})...")
                tts.generate_audio(seg["id"], text)
                
            aligned_audio_segments.append({
                "id": seg["id"],
                "start": seg["start"],
                "end": seg["end"],
                "audio_path": audio_path,
                "use_ai_image": seg.get("use_ai_image", False),
                "ai_image_path": seg.get("ai_image_path", None)
            })
            
        output_folder = os.path.join("output", video_id)
        os.makedirs(output_folder, exist_ok=True)

        job_status[job_id] = f"Rendering final video ({channel_type})..."
        print(f"\n[JOB {job_id}] Step 6: Rendering Final Video for {channel_type}...")
        
        # Clear stale render artifacts so we always regenerate with current code.
        # (TTS WAVs and translation JSON are intentionally kept — they are expensive to regenerate.)
        import shutil
        for stale in ["video_only.mp4", "mixed_temp.mp4", "narrator_audio_track.wav"]:
            p = os.path.join(job_dir, stale)
            if os.path.exists(p):
                os.remove(p)
                print(f"  [Cache] Removed stale: {stale}")
        for stale_dir in ["video_chunks", "resampled_wavs"]:
            p = os.path.join(job_dir, stale_dir)
            if os.path.exists(p):
                shutil.rmtree(p)
                print(f"  [Cache] Removed stale dir: {stale_dir}/")
        
        sync.build_timeline(
            aligned_audio_segments, video_path, final_output,
            job_dir=job_dir,
            watermark_settings=request.watermark,
            text_watermark_settings=request.textWatermark,
            skip_intervals=request.skip_intervals,
            channel_type=channel_type
        )
        
        job_status[job_id] = "Generating SEO Metadata..."
        print(f"\n[JOB {job_id}] Step 7: Generating SEO Metadata...")
        metadata_generator = MetadataGenerator(api_key=groq_api_key)
        metadata_generator.generate(script_path, metadata_output, target_lang=target_lang)
        
        job_status[job_id] = f"Completed: {final_output}"
        print(f"\n[JOB {job_id}] ✅ DONE! Final video and metadata saved to {output_folder}")
        
        if request.webhook_url:
            abs_video_path = os.path.abspath(final_output)
            abs_metadata_path = os.path.abspath(metadata_output)
            
            # Load metadata to send it directly in the webhook!
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
        
        # Immediately clean up heavy scratch files (video chunks, resampled audio, mixed temp files)
        cleanup_job_temp(video_id)
        
        # If webhook was sent, schedule output folder deletion after n8n has finished uploading it (3 mins)
        if request.webhook_url:
            schedule_delayed_output_cleanup(video_id, delay_seconds=180)
        
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

@app.post("/api/process")
def process_video(request: VideoRequest, background_tasks: BackgroundTasks):
    import uuid
    job_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(process_pipeline, job_id, request)
    return {"status": "started", "job_id": job_id}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    return {"job_id": job_id, "status": job_status.get(job_id, "Not found")}

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
        if not os.path.exists(video_path) or os.path.getsize(video_path) < 1024 * 1024:
            if os.path.exists(video_path):
                try: os.remove(video_path)
                except: pass
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
