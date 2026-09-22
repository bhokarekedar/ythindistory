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
from core.translator import HindiTranslator
from core.tts import GeminiTTS
from core.sync import AudioSynchronizer

app = FastAPI(title="Movie Recap Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local dev (e.g. localhost:5173)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from typing import Optional

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

class VideoRequest(BaseModel):
    url: str
    watermark: Optional[WatermarkSettings] = None

class SnapshotRequest(BaseModel):
    url: str
    watermark: WatermarkSettings

# In-memory status store for MVP
job_status = {}

def process_pipeline(job_id: str, request: VideoRequest):
    url = request.url
    # Try to extract video ID for caching
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    video_id = video_id_match.group(1) if video_id_match else job_id
    job_dir = f"temp/{video_id}"
    os.makedirs(job_dir, exist_ok=True)
    
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print("Warning: failed to load config.yaml, using defaults")
        config = {}
        
    try:
        # Step 1: Video Download
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
            print(f"\n[JOB {job_id}] Step 3: Transcribing Audio via Groq Whisper...")
            transcriber = Transcriber(model_name=config.get("groq", {}).get("transcription_model", "whisper-large-v3-turbo"), output_dir=job_dir, chunk_minutes=config.get("transcription", {}).get("chunk_minutes", 10))
            transcript_path = transcriber.transcribe(raw_audio_path)
            print(f"[JOB {job_id}] Transcription complete. JSON stored at: {transcript_path}")
            
        # Step 4: Translation
        hindi_transcript_path = os.path.join(job_dir, f"{video_id}_audio_hindi_transcript.json")
        if os.path.exists(hindi_transcript_path):
            job_status[job_id] = "Translation skipped (using cache)"
            print(f"\n[JOB {job_id}] Step 4: Hindi transcript found in cache. Skipping.")
        else:
            job_status[job_id] = "Translating to Hindi..."
            print(f"\n[JOB {job_id}] Step 4: Translating English to Hindi...")
            translator = HindiTranslator(
                primary_provider=config.get("llm", {}).get("primary_provider", "groq"),
                fallback_provider=config.get("llm", {}).get("fallback_provider", "none"),
                translation_model=config.get("groq", {}).get("translation_model", "llama-3.1-70b-versatile"),
                batch_size=config.get("translation", {}).get("batch_size", 20)
            )
            hindi_transcript_path = translator.translate_transcript(transcript_path, output_dir=job_dir)
            print(f"[JOB {job_id}] Translation complete. JSON stored at: {hindi_transcript_path}")
            
        # Step 5: TTS Generation
        job_status[job_id] = "Generating Hindi voice..."
        print(f"\n[JOB {job_id}] Step 5: Generating Hindi Voice via Google Cloud TTS...")
        
        speaker = config.get("gemini_tts", {}).get("voice", "Zephyr")
        model = config.get("gemini_tts", {}).get("model", "gemini-3.1-flash-tts-preview")
        tts = GeminiTTS(output_dir=f"{job_dir}/segments", voice_name=speaker, model=model)
        
        sync = AudioSynchronizer(
            max_speed_change=config.get("sync", {}).get("max_speed_change", 0.15),
            rewrite_threshold=config.get("sync", {}).get("rewrite_threshold", 1.15)
        )
        
        # Load transcript
        import json
        with open(hindi_transcript_path, "r") as f:
            segments = json.load(f)
            
        aligned_audio_segments = []
        for i, seg in enumerate(segments):
            print(f"  -> Segment {seg['id']}: [{seg['start']:.2f}s - {seg['end']:.2f}s]")
            print(f"     English : {seg['english']}")
            print(f"     Hindi   : {seg['hindi']}")
            
            # We use the natural audio length, no more stretching!
            raw_audio_path_tts = os.path.join(f"{job_dir}/segments", f"{seg['id']:04d}.wav")
            if not os.path.exists(raw_audio_path_tts):
                tts.generate_audio(seg["id"], seg["hindi"])
                
            aligned_audio_segments.append({
                "id": seg["id"],
                "start": seg["start"],
                "end": seg["end"],
                "audio_path": raw_audio_path_tts
            })
            
        job_status[job_id] = "Rendering final video..."
        print(f"\n[JOB {job_id}] Step 6: Rendering Final Video...")
        final_output = os.path.join(f"output", f"{job_id}_final.mp4")
        os.makedirs("output", exist_ok=True)
        
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
        
        sync.build_timeline(aligned_audio_segments, video_path, final_output, job_dir=job_dir, watermark_settings=request.watermark)
        
        job_status[job_id] = f"Completed: {final_output}"
        print(f"\n[JOB {job_id}] ✅ DONE! Final video saved to {final_output}")
        
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
        
    wm_input = ffmpeg.input(watermark_path)
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
            
        stream = ffmpeg.overlay(stream, wm, x=x, y=y)
        
    return stream

@app.post("/api/snapshot")
def generate_snapshot(request: SnapshotRequest):
    import base64
    import tempfile
    
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", request.url)
    if not video_id_match:
        return {"error": "Invalid YouTube URL"}
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
        out_stream = apply_watermarks_to_ffmpeg(vid, watermark_path, request.watermark)
        
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
