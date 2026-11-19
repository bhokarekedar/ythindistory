"""FastAPI Web Server for English Shadowing Video Studio.

Provides an intuitive browser UI to paste scripts, preview, render full videos,
and track real-time progress.
"""

import threading
import uuid
from pathlib import Path
from typing import Any, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from shadowing_pipeline.core.pipeline import ShadowingVideoPipeline


app = FastAPI(title="English Shadowing Video Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory jobs tracking
jobs: Dict[str, Dict[str, Any]] = {}

# Ensure output directory exists and is mounted
output_dir = Path("output").resolve()
output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")


class GenerateRequest(BaseModel):
    script: Dict[str, Any]
    preview: bool = False


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_file = Path("shadowing_pipeline/static/index.html")
    if html_file.exists():
        return FileResponse(html_file)
    return "UI index.html not found"


def run_pipeline_worker(job_id: str, script_data: dict, preview: bool):
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["status_text"] = "Parsing script & building timeline..."

        def progress_cb(rendered: int, total: int, pct: float):
            jobs[job_id]["progress"] = pct
            jobs[job_id]["status_text"] = f"Rendering frames: {rendered}/{total} ({pct:.0f}%)"

        pipeline = ShadowingVideoPipeline()
        results = pipeline.run(
            script_input=script_data,
            output_dir=str(output_dir),
            preview=preview,
            progress_callback=progress_cb,
        )

        vid_filename = Path(results["video"]).name
        srt_filename = Path(results["srt"]).name
        tl_filename = Path(results["timeline"]).name

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100.0
        jobs[job_id]["result"] = {
            "video_url": f"/output/{vid_filename}",
            "srt_url": f"/output/{srt_filename}",
            "timeline_url": f"/output/{tl_filename}",
            "duration": results["duration"],
        }
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.post("/api/generate")
async def start_generation(req: GenerateRequest):
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0.0,
        "status_text": "Queued",
        "error": None,
        "result": None,
    }

    t = threading.Thread(
        target=run_pipeline_worker,
        args=(job_id, req.script, req.preview),
        daemon=True,
    )
    t.start()

    return {"job_id": job_id, "message": "Rendering job started"}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting English Shadowing Video Studio UI at http://localhost:8000")
    uvicorn.run("shadowing_pipeline.server:app", host="0.0.0.0", port=8000, reload=False)

