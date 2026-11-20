import os
import glob
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .detector import get_stream_info, fetch_live_chat_messages, analyze_chat_velocity
from .clipper import StreamClipRenderer
from publishing.youtube_publisher import YouTubePublisher

router = APIRouter()
renderer = StreamClipRenderer(temp_dir="temp", output_dir="output")
publisher = YouTubePublisher()


class StreamAnalyzeRequest(BaseModel):
    url: str
    spike_threshold: float = 2.0
    max_clips: int = 6
    clip_duration: int = 45


class StreamRenderClipRequest(BaseModel):
    url: str
    moment_id: str
    start_time: float
    duration: float = 45.0
    layout: str = "blurred_stack"
    stream_title: Optional[str] = ""
    streamer: Optional[str] = ""
    top_keywords: Optional[List[str]] = []
    sample_chat: Optional[List[str]] = []


class StreamUploadRequest(BaseModel):
    clip_id: str
    title: str
    description: Optional[str] = ""
    tags: Optional[List[str]] = []
    privacy_status: Optional[str] = "unlisted"


class StreamAutoUploadRequest(BaseModel):
    url: str
    top_n: int = 3
    spike_threshold: float = 2.0
    clip_duration: int = 45
    layout: str = "blurred_stack"
    privacy_status: str = "public"


@router.post("/auto-upload-top-moments")
def auto_upload_top_moments(request: StreamAutoUploadRequest):
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Livestream URL cannot be empty")

    try:
        # 1. Fetch metadata
        info = get_stream_info(url)

        # 2. Extract chat & detect explosions
        messages = fetch_live_chat_messages(url, max_messages=40000, timeout_sec=45)
        analysis = analyze_chat_velocity(
            messages=messages,
            duration=info["duration"],
            spike_threshold=request.spike_threshold,
            max_clips=request.top_n,
            clip_duration=request.clip_duration
        )

        moments = analysis.get("moments", [])
        if not moments:
            raise HTTPException(status_code=404, detail="No explosive chat moments detected in stream")

        processed_results = []
        for moment in moments[:request.top_n]:
            moment_id = moment["id"]
            clip_id = f"stream_{moment_id}"

            # Download & vertical render
            raw_path = renderer.download_segment(
                url=url,
                start_time=moment["start_time"],
                duration=moment["duration"],
                clip_id=clip_id
            )
            final_mp4 = renderer.render_vertical(
                raw_video_path=raw_path,
                clip_id=clip_id,
                layout=request.layout
            )

            # Metadata
            meta = renderer.generate_ai_metadata(
                stream_title=info.get("title", ""),
                streamer=info.get("uploader", ""),
                top_keywords=moment.get("top_keywords", []),
                sample_chat=moment.get("sample_chat", [])
            )

            title = meta.get("title") or moment.get("suggested_title")
            desc = meta.get("description", "")
            tags = meta.get("tags", ["Shorts"])

            # Direct Upload to YouTube
            upload_res = publisher.upload_video(
                video_path=final_mp4,
                title=title,
                description=desc,
                tags=tags,
                privacy_status=request.privacy_status or "public"
            )

            processed_results.append({
                "moment_id": moment_id,
                "clip_id": clip_id,
                "peak_time_str": moment["peak_time_str"],
                "peak_velocity": moment["peak_velocity"],
                "title": title,
                "video_url": f"/output/stream_clips/{clip_id}.mp4",
                "upload_result": upload_res
            })

        return {
            "status": "success",
            "stream_info": info,
            "uploaded_count": len(processed_results),
            "results": processed_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-upload failed: {str(e)}")


@router.post("/analyze")
def analyze_livestream(request: StreamAnalyzeRequest):
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Livestream URL cannot be empty")

    try:
        # 1. Fetch Stream Metadata
        info = get_stream_info(url)

        # 2. Extract Live Chat Messages with exact timestamps
        messages = fetch_live_chat_messages(url, max_messages=40000, timeout_sec=45)

        # 3. Analyze Chat Velocity Spikes
        analysis = analyze_chat_velocity(
            messages=messages,
            duration=info["duration"],
            spike_threshold=request.spike_threshold,
            max_clips=request.max_clips,
            clip_duration=request.clip_duration
        )

        return {
            "status": "success",
            "stream_info": info,
            "moments": analysis["moments"],
            "timeline": analysis["timeline"],
            "stats": analysis["stats"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze stream: {str(e)}")


@router.post("/render-clip")
def render_moment_clip(request: StreamRenderClipRequest):
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Livestream URL cannot be empty")

    try:
        clip_id = f"stream_{request.moment_id}"

        # 1. Download only the section
        raw_path = renderer.download_segment(
            url=url,
            start_time=request.start_time,
            duration=request.duration,
            clip_id=clip_id
        )

        # 2. Convert to 9:16 vertical short
        final_mp4 = renderer.render_vertical(
            raw_video_path=raw_path,
            clip_id=clip_id,
            layout=request.layout
        )

        # 3. Generate viral metadata
        metadata = renderer.generate_ai_metadata(
            stream_title=request.stream_title or "Livestream Moment",
            streamer=request.streamer or "Streamer",
            top_keywords=request.top_keywords or [],
            sample_chat=request.sample_chat or []
        )

        return {
            "status": "success",
            "clip_id": clip_id,
            "video_url": f"/output/stream_clips/{clip_id}.mp4",
            "metadata": metadata
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render clip: {str(e)}")


@router.get("/youtube-status")
def get_youtube_status():
    status = publisher.get_auth_status()
    return {"status": "success", "auth": status}


@router.post("/upload")
def upload_stream_clip(request: StreamUploadRequest):
    clip_id = request.clip_id.strip()
    video_path = os.path.join("output", "stream_clips", f"{clip_id}.mp4")

    if not os.path.exists(video_path):
        # Check if alternative path
        alt = os.path.join("output", "stream_clips", f"{clip_id}")
        if os.path.exists(alt):
            video_path = alt
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Video file for {clip_id} not found at {video_path}. Please render first."
            )

    try:
        result = publisher.upload_video(
            video_path=video_path,
            title=request.title,
            description=request.description or "",
            tags=request.tags or [],
            privacy_status=request.privacy_status or "unlisted"
        )
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")

