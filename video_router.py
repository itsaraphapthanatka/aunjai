"""
video_router.py — FastAPI Router for Video Editor Web Interface
"""

import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import asyncio
import os
import re

from searcher import search_multiple_queries
from video_processor import process_video_clip
from pipeline import run_pipeline
from highlight_pipeline import run_highlight_pipeline
from channel_scraper import scrape_channel_videos
from highlight_store import get_processed_video_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/editor", tags=["Video Editor"])

# Store processing status 
# In a real app, use Redis or a database. For this demo, a simple dict works.
processing_status = {}

class SearchRequest(BaseModel):
    query: str
    top_k: int = 3

class ImportRequest(BaseModel):
    url: str
    task_id: str

class ClipRequest(BaseModel):
    video_id: str
    start_time: float
    end_time: float
    task_id: str  # Added to track progress

class HighlightRequest(BaseModel):
    url: str
    task_id: str
    auto_clip: bool = True

class ChannelRequest(BaseModel):
    url: str
    max_videos: int = 0

class ProcessedCheckRequest(BaseModel):
    video_ids: list[str]

@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def editor_ui():
    """Serves the video editor HTML page"""
    try:
        with open("video_editor.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Video Editor Template Not Found</h1><p>Please check if video_editor.html exists.</p>"

@router.post("/api/search")
async def search_video(req: SearchRequest):
    """Semantic search against the Knowledge Base, with optional URL filtering"""
    logger.info(f"Editor searching for: {req.query}")
    try:
        query_text = req.query
        video_filter = None
        
        # Extract YouTube URL if present
        url_match = re.search(r'(https?://[^\s]+)', query_text)
        if url_match:
            url = url_match.group(1)
            # Simple extraction: get 'v=' param or last part of path
            vid = None
            if "youtube.com/watch" in url and "v=" in url:
                try:
                    vid = url.split("v=")[1].split("&")[0]
                except IndexError:
                    pass
            elif "youtu.be/" in url:
                try:
                    vid = url.split("youtu.be/")[1].split("?")[0]
                except IndexError:
                    pass
                    
            if vid:
                video_filter = {"video_id": vid}
                # Remove URL from the query text used for semantic search
                query_text = query_text.replace(url, "").strip()
                # If only URL was provided, use a default broad query or empty string
                if not query_text:
                    # In Pinecone, an empty vector query isn't great, but we still need to pass something.
                    # Or we just use a generic term if they only pasted the URL.
                    query_text = "ทุกอย่าง" # "Everything" 
                
                logger.info(f"Filtered search for Video ID: {vid} with query: '{query_text}'")

        # Run in a threadpool to avoid blocking event loop
        results = await asyncio.to_thread(search_multiple_queries, [query_text], req.top_k, video_filter)
        clips = results.get(query_text, [])
        return {"status": "success", "results": clips}
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/import")
async def import_video(req: ImportRequest, background_tasks: BackgroundTasks):
    """Import a new YouTube video into the Knowledge Base"""
    if req.task_id in processing_status and processing_status[req.task_id] == "processing":
        return {"status": "error", "message": "Task already processing"}
        
    # Extract video ID
    vid = None
    url = req.url
    if "youtube.com/watch" in url and "v=" in url:
        try:
            vid = url.split("v=")[1].split("&")[0]
        except IndexError:
            pass
    elif "youtu.be/" in url:
        try:
            vid = url.split("youtu.be/")[1].split("?")[0]
        except IndexError:
            pass
            
    if not vid:
        # User might have just pasted the ID directly
        if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
            vid = url
        else:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL or Video ID")
            
    processing_status[req.task_id] = "processing"
    
    def background_import():
        try:
            logger.info(f"Starting real-time import for video ID: {vid}")
            # False means do NOT dry_run, we want to upsert to Pinecone
            summary = run_pipeline([vid], dry_run=False)
            
            if summary.get("total_vectors_upserted", 0) > 0:
                processing_status[req.task_id] = {
                    "status": "success", 
                    "message": f"Successfully imported {summary['total_vectors_upserted']} segments.",
                    "video_id": vid
                }
            else:
                processing_status[req.task_id] = {
                    "status": "error", 
                    "message": "Failed to extract or embed transcripts for this video."
                }
        except Exception as e:
            logger.error(f"Error in background import process: {e}")
            processing_status[req.task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(background_import)
    return {"status": "accepted", "message": "Import started in background", "video_id": vid}

@router.post("/api/clip")
async def start_clipping(req: ClipRequest, background_tasks: BackgroundTasks):
    """Starts a background task to download and trim the video"""
    if req.task_id in processing_status and processing_status[req.task_id] == "processing":
        return {"status": "error", "message": "Task already processing"}

    processing_status[req.task_id] = "processing"
    
    def background_process():
        try:
            result = process_video_clip(req.video_id, req.start_time, req.end_time)
            processing_status[req.task_id] = result
        except Exception as e:
            logger.error(f"Error in background process: {e}")
            processing_status[req.task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(background_process)
    return {"status": "accepted", "message": "Clipping started in background"}

@router.post("/api/highlight")
async def start_highlight(req: HighlightRequest, background_tasks: BackgroundTasks):
    """Starts highlight analysis: extract transcript → OpenClaw analysis → auto-clip"""
    if req.task_id in processing_status and processing_status[req.task_id] == "processing":
        return {"status": "error", "message": "Task already processing"}

    processing_status[req.task_id] = "processing"

    def background_highlight():
        try:
            def on_progress(step, detail):
                processing_status[req.task_id + "_progress"] = f"{step} {detail}"

            result = run_highlight_pipeline(
                youtube_url=req.url,
                auto_clip=req.auto_clip,
                on_progress=on_progress,
            )
            processing_status[req.task_id] = result
        except Exception as e:
            logger.error(f"Error in highlight pipeline: {e}")
            processing_status[req.task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(background_highlight)
    return {"status": "accepted", "message": "Highlight analysis started"}

@router.get("/api/status/{task_id}")
async def check_status(task_id: str):
    """Checks the status of a clipping or highlight task"""
    if task_id not in processing_status:
        return {"status": "unknown"}
    
    status_data = processing_status[task_id]
    if isinstance(status_data, str) and status_data == "processing":
         # Include progress message if available
         progress = processing_status.get(task_id + "_progress", "")
         return {"status": "processing", "progress": progress}
    else:
         return status_data

@router.post("/api/channel")
async def get_channel_videos(req: ChannelRequest):
    """ดึงรายชื่อวิดีโอจาก YouTube Channel"""
    try:
        result = await asyncio.to_thread(
            scrape_channel_videos, req.url, req.max_videos
        )
        return result
    except Exception as e:
        logger.error(f"Channel scrape error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/channel/check_processed")
async def check_processed_videos(req: ProcessedCheckRequest):
    """ตรวจสอบว่าวิดีโอชุดไหนเคยประมวลผลไปแล้วบ้าง"""
    try:
        processed_ids = await asyncio.to_thread(
            get_processed_video_ids, req.video_ids
        )
        return {"status": "success", "processed_ids": processed_ids}
    except Exception as e:
        logger.error(f"Check processed error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
