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
from core.tts import PiperTTS
from core.sync import AudioSynchronizer

app = FastAPI(title="Movie Recap Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local dev (e.g. localhost:5173)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    url: str

# In-memory status store for MVP
job_status = {}

def process_pipeline(job_id: str, url: str):
    job_dir = f"temp/{job_id}"
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print("Warning: failed to load config.yaml, using defaults")
        config = {}
        
    try:
        # Check if we already have it cached
        video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if video_id_match:
            video_id = video_id_match.group(1)
            cached_path = f"temp/videos/{video_id}.mp4"
            if os.path.exists(cached_path):
                job_status[job_id] = "Video download skipped (using cache)"
                print(f"\n[JOB {job_id}] Step 1: Video {video_id} found in cache. Skipping download.")
            else:
                job_status[job_id] = "Downloading video..."
                print(f"\n[JOB {job_id}] Step 1: Downloading Video from {url}")
        else:
            job_status[job_id] = "Downloading video..."
            print(f"\n[JOB {job_id}] Step 1: Downloading Video from {url}")

        downloader = YouTubeDownloader(output_dir="temp/videos")
        video_path = downloader.download(url)
        print(f"[JOB {job_id}] Video stored at: {video_path}")
        
        job_status[job_id] = "Extracting audio..."
        print(f"\n[JOB {job_id}] Step 2: Extracting Audio...")
        extractor = AudioExtractor(output_dir=job_dir)
        raw_audio_path = extractor.extract_audio(video_path)
        print(f"[JOB {job_id}] Audio extracted to: {raw_audio_path}")
        
        job_status[job_id] = "Transcribing audio..."
        print(f"\n[JOB {job_id}] Step 3: Transcribing Audio via Groq Whisper...")
        transcriber = Transcriber(model_name=config.get("groq", {}).get("transcription_model", "whisper-large-v3-turbo"), output_dir=job_dir, chunk_minutes=config.get("transcription", {}).get("chunk_minutes", 10))
        transcript_path = transcriber.transcribe(raw_audio_path)
        print(f"[JOB {job_id}] Transcription complete. JSON stored at: {transcript_path}")
        
        job_status[job_id] = "Translating to Hindi..."
        print(f"\n[JOB {job_id}] Step 4: Translating English to Hindi...")
        translator = HindiTranslator(
            primary_provider=config.get("llm", {}).get("primary_provider", "groq"),
            fallback_provider=config.get("llm", {}).get("fallback_provider", "none"),
            translation_model=config.get("groq", {}).get("translation_model", "llama-3.1-70b-versatile"),
            batch_size=config.get("translation", {}).get("batch_size", 20)
        )
        hindi_transcript_path = translator.translate_transcript(transcript_path, output_dir=f"temp/{job_id}")
        print(f"[JOB {job_id}] Translation complete. JSON stored at: {hindi_transcript_path}")
        
        job_status[job_id] = "Generating Hindi voice..."
        print(f"\n[JOB {job_id}] Step 5: Generating Hindi Voice via Piper TTS...")
        tts = PiperTTS(output_dir=f"temp/{job_id}/segments")
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
            
            raw_audio = tts.generate_audio(seg["id"], seg["hindi"])
            target_duration = seg["end"] - seg["start"]
            
            aligned_path = os.path.join(f"temp/{job_id}/segments", f"{seg['id']:04d}_aligned.wav")
            
            # Simplified loop for MVP (no LLM rewrite fallback implemented here yet to prevent infinite loops)
            success = sync.process_segment(raw_audio, target_duration, aligned_path)
            if not success:
                # Fallback: force stretch even if it sounds a bit chipmunk-y for MVP
                stream = ffmpeg.input(raw_audio)
                speed_factor = sync.get_audio_duration(raw_audio) / target_duration
                stream = ffmpeg.filter(stream, 'atempo', speed_factor)
                stream = ffmpeg.output(stream, aligned_path, acodec='pcm_s16le', ac=1, ar='16k')
                ffmpeg.run(stream, quiet=True, overwrite_output=True)
                
            aligned_audio_segments.append({"start": seg["start"], "audio_path": aligned_path})
            
        job_status[job_id] = "Rendering final video..."
        print(f"\n[JOB {job_id}] Step 6: Rendering Final Video...")
        final_output = os.path.join(f"output", f"{job_id}_final.mp4")
        os.makedirs("output", exist_ok=True)
        sync.build_timeline(aligned_audio_segments, video_path, final_output)
        
        job_status[job_id] = f"Completed: {final_output}"
        print(f"\n[JOB {job_id}] ✅ DONE! Final video saved to {final_output}")
        
    except Exception as e:
        job_status[job_id] = f"Error: {str(e)}"

@app.post("/api/process")
def process_video(request: VideoRequest, background_tasks: BackgroundTasks):
    import uuid
    job_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(process_pipeline, job_id, request.url)
    return {"status": "started", "job_id": job_id}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    return {"job_id": job_id, "status": job_status.get(job_id, "Not found")}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
