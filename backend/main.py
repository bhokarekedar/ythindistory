from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
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
import json

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
    size: int = 50

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
    watermark: Optional[WatermarkSettings] = None
    textWatermark: Optional[WatermarkSettings] = None
    skip_intervals: Optional[List[TimeRange]] = None
    webhook_url: Optional[str] = None

class SnapshotRequest(BaseModel):
    url: str
    watermark: WatermarkSettings
    textWatermark: Optional[WatermarkSettings] = None

# In-memory status store for MVP
job_status = {}

def process_pipeline(job_id: str, request: VideoRequest):
    url = request.url
    
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
    final_output = os.path.join(output_folder, f"{video_id}_final.mp4")
    metadata_output = os.path.join(output_folder, f"{video_id}_metadata.json")
    
    if os.path.exists(final_output) and os.path.exists(metadata_output):
        print(f"\n[JOB {job_id}] ⚡ FINAL VIDEO ALREADY EXISTS! Skipping generation and firing webhook directly.")
        job_status[job_id] = f"Completed: {final_output}"
        
        if request.webhook_url:
            import urllib.request
            import json
            print(f"  [Webhook] Sending completion POST to {request.webhook_url}...")
            try:
                abs_video_path = os.path.abspath(final_output)
                abs_metadata_path = os.path.abspath(metadata_output)
                
                with open(abs_metadata_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                
                payload = {
                    "job_id": job_id,
                    "video_id": video_id,
                    "status": "success",
                    "final_video_path": abs_video_path,
                    "metadata_path": abs_metadata_path,
                    "download_url": f"http://127.0.0.1:8000/output/{video_id}/{video_id}_final.mp4",
                    "url": url,
                    "title": meta.get("title", f"Movie Recap {video_id}"),
                    "description": meta.get("description", ""),
                    "tags": meta.get("keywords", [])
                }
                
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(request.webhook_url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
                urllib.request.urlopen(req, timeout=10)
                print("  [Webhook] Success!")
            except Exception as e:
                print(f"  [Webhook] Failed to send webhook: {e}")
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
            if os.path.exists(video_path):
                job_status[job_id] = "Video download skipped (using cache)"
                print(f"\n[JOB {job_id}] Step 1: Video found in cache. Skipping download.")
            else:
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
            job_status[job_id] = "Transcribing audio..."
            print(f"\n[JOB {job_id}] Step 3: Transcribing Audio (Trying YouTube API first, then Groq Whisper)...")
            transcriber = Transcriber(
                model_name=config.get("groq", {}).get("transcription_model", "whisper-large-v3-turbo"), 
                output_dir=job_dir, 
                chunk_minutes=config.get("transcription", {}).get("chunk_minutes", 10),
                api_key=groq_api_key
            )
            transcript_path = transcriber.transcribe(raw_audio_path, youtube_url=url)
            print(f"[JOB {job_id}] Transcription complete. JSON stored at: {transcript_path}")
            
        # Step 4: Translation / Script Rewrite
        target_lang = request.target_language.lower()
        script_path = os.path.join(job_dir, f"{video_id}_audio_{target_lang}_transcript.json")
        if os.path.exists(script_path):
            job_status[job_id] = f"Script generation skipped (using cache)"
            print(f"\n[JOB {job_id}] Step 4: {target_lang.capitalize()} script found in cache. Skipping.")
        else:
            job_status[job_id] = f"Generating {target_lang} script..."
            print(f"\n[JOB {job_id}] Step 4: Generating {target_lang} script...")
            translator = StoryTranslator(
                primary_provider=config.get("llm", {}).get("primary_provider", "groq"),
                fallback_provider=config.get("llm", {}).get("fallback_provider", "none"),
                translation_model=config.get("groq", {}).get("translation_model", "llama-3.1-70b-versatile"),
                batch_size=config.get("translation", {}).get("batch_size", 20),
                api_key=groq_api_key
            )
            script_path = translator.translate_transcript(transcript_path, target_language=target_lang, output_dir=job_dir)
            print(f"[JOB {job_id}] Script generation complete. JSON stored at: {script_path}")
            
        # Step 5: TTS Generation
        tts_provider = config.get("tts", {}).get("provider", "gemini")
        job_status[job_id] = f"Generating {target_lang.capitalize()} voice via {tts_provider.capitalize()}..."
        print(f"\n[JOB {job_id}] Step 5: Generating {target_lang.capitalize()} Voice via {tts_provider.capitalize()}...")
        
        if tts_provider == "kokoro":
            # For Hindi, default to hf_alpha. For English, default to af_heart
            default_voice = "hf_alpha" if target_lang == "hindi" else "af_heart"
            # We override if the config specifically sets a voice, but maybe we should ignore config voice if it mismatches?
            # Let's just use defaults based on language for now if not strictly configured for both.
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
            
        aligned_audio_segments = []
        for i, seg in enumerate(segments):
            text = seg.get(target_lang, "Error").strip()
            
            # Skip empty segments (filtered out by LLM)
            if not text:
                print(f"  [TTS] Skipping segment {seg['id']} (Empty text - likely filtered by LLM)")
                continue

            audio_path = os.path.join(f"{job_dir}/segments", f"{seg['id']:04d}.wav")
            
            if not os.path.exists(audio_path):
                print(f"  [TTS] Generating Audio for Segment {seg['id']} ({i+1}/{len(segments)})...")
                tts.generate_audio(seg["id"], text)
                
            aligned_audio_segments.append({
                "id": seg["id"],
                "start": seg["start"],
                "end": seg["end"],
                "audio_path": audio_path
            })
            
        output_folder = os.path.join("output", video_id)
        os.makedirs(output_folder, exist_ok=True)
        final_output = os.path.join(output_folder, f"{video_id}_final.mp4")

        job_status[job_id] = "Rendering final video..."
        print(f"\n[JOB {job_id}] Step 6: Rendering Final Video...")
        
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
        
        sync.build_timeline(aligned_audio_segments, video_path, final_output, job_dir=job_dir, watermark_settings=request.watermark, text_watermark_settings=request.textWatermark, skip_intervals=request.skip_intervals)
        
        job_status[job_id] = "Generating SEO Metadata..."
        print(f"\n[JOB {job_id}] Step 7: Generating SEO Metadata...")
        metadata_generator = MetadataGenerator(api_key=groq_api_key)
        metadata_output = os.path.join(output_folder, f"{video_id}_metadata.json")
        metadata_generator.generate(script_path, metadata_output, target_lang=target_lang)
        
        job_status[job_id] = f"Completed: {final_output}"
        print(f"\n[JOB {job_id}] ✅ DONE! Final video and metadata saved to {output_folder}")
        
        if request.webhook_url:
            import urllib.request
            print(f"  [Webhook] Sending completion POST to {request.webhook_url}...")
            try:
                abs_video_path = os.path.abspath(final_output)
                abs_metadata_path = os.path.abspath(metadata_output)
                
                # Load metadata to send it directly in the webhook!
                with open(abs_metadata_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                
                payload = {
                    "job_id": job_id,
                    "video_id": video_id,
                    "status": "success",
                    "final_video_path": abs_video_path,
                    "metadata_path": abs_metadata_path,
                    "download_url": f"http://127.0.0.1:8000/output/{video_id}/{video_id}_final.mp4",
                    "url": url,
                    "title": meta.get("title", f"Movie Recap {video_id}"),
                    "description": meta.get("description", ""),
                    "tags": meta.get("keywords", [])
                }
                
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(request.webhook_url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
                urllib.request.urlopen(req, timeout=10)
                print("  [Webhook] Success!")
            except Exception as e:
                print(f"  [Webhook] Failed to send webhook: {e}")
        
    except ffmpeg.Error as e:
        err_msg = e.stderr.decode('utf8') if e.stderr else str(e)
        job_status[job_id] = f"FFmpeg Error: {err_msg}"
        print(f"\n[JOB {job_id}] FFmpeg Error:\n{err_msg}")
    except Exception as e:
        job_status[job_id] = f"Error: {str(e)}"
        print(f"\n[JOB {job_id}] Exception: {str(e)}")

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
        if not os.path.exists(video_path):
            os.makedirs("temp/videos", exist_ok=True)
            downloader = YouTubeDownloader(output_dir="temp/videos")
            try:
                video_path = downloader.download(request.url)
            except Exception as e:
                return {"error": f"Failed to download video: {str(e)}"}
            
    watermark_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/watermark.png"
    
    try:
        # Extract 1 frame at 00:01:00 (explicitly grab the video stream)
        vid = ffmpeg.input(video_path, ss="00:01:00").video
        
        # Scale to match the final video rendering dimensions (1280x720) 
        # so the X/Y coordinates in the snapshot exactly match the final video!
        vid = vid.filter("scale", 1280, 720).filter("setsar", 1)
        
        # Apply watermarks
        text_watermark_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/textWatermark.png"
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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
