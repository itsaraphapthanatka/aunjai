"""
pinecone_router.py — FastAPI Router for direct Pinecone data retrieval
"""

import logging
import asyncio
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any

from searcher import search_relevant_clip
from highlight_store import search_highlights, _get_index, HIGHLIGHT_NAMESPACE
from quiz_store import get_quiz_from_pinecone, QUIZ_NAMESPACE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pinecone", tags=["Pinecone Retrieval"])

@router.get("/search")
async def search_segments(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(5, description="Number of results"),
    video_id: Optional[str] = Query(None, description="Optional video_id filter"),
    namespace: Optional[str] = Query(None, description="Pinecone namespace (e.g., '', 'highlights', 'full_clip')")
):
    """Semantic search against video segments in the knowledge base"""
    try:
        filter_dict = {"video_id": video_id} if video_id else None
        results = await asyncio.to_thread(search_relevant_clip, q, top_k, filter=filter_dict, namespace=namespace)
        return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"Pinecone search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/{namespace}")
async def search_by_namespace_path(
    namespace: str,
    q: str = Query(..., description="Search query"),
    top_k: int = Query(5, description="Number of results"),
    video_id: Optional[str] = Query(None, description="Optional video_id filter")
):
    """Semantic search against a specific namespace via path parameter"""
    # Use empty string for 'default' if the user literally type 'default'
    ns = "" if namespace.lower() == "default" else namespace
    try:
        filter_dict = {"video_id": video_id} if video_id else None
        results = await asyncio.to_thread(search_relevant_clip, q, top_k, filter=filter_dict, namespace=ns)
        return {"status": "success", "namespace": ns, "results": results}
    except Exception as e:
        logger.error(f"Pinecone path search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/highlights")
async def search_video_highlights(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(5, description="Number of results"),
    video_id: Optional[str] = Query(None, description="Optional video_id filter")
):
    """Semantic search against processed highlights"""
    try:
        results = await asyncio.to_thread(search_highlights, q, top_k, video_id)
        return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"Pinecone highlights search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/quiz/{video_id}")
async def get_video_quiz(video_id: str):
    """Fetch stored full clip quiz for a video ID"""
    try:
        quiz_data = await asyncio.to_thread(get_quiz_from_pinecone, video_id)
        if quiz_data:
            return {"status": "success", "quiz": quiz_data}
        else:
            return {"status": "not_found", "message": "No quiz found for this video"}
    except Exception as e:
        logger.error(f"Pinecone quiz fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/full-clip")
async def list_full_clip(
    page_token: Optional[str] = Query(None, description="Pagination token from previous response"),
    limit: int = Query(50, ge=1, le=100, description="Records per page (default 50)")
):
    """List records in the full_clip namespace, 50 per page with cursor-based pagination"""
    try:
        index = await asyncio.to_thread(_get_index)

        def _fetch_page():
            kwargs = {"namespace": "full_clip", "limit": limit}
            if page_token:
                kwargs["pagination_token"] = page_token
            listed = index.list_paginated(**kwargs)
            ids = [v.id for v in (listed.vectors or [])]
            next_token = listed.pagination.next if listed.pagination else None

            if not ids:
                return [], next_token

            fetched = index.fetch(ids=ids, namespace="full_clip")
            records = []
            for vid_id, vec in fetched.vectors.items():
                records.append({"id": vid_id, "metadata": vec.metadata or {}})
            return records, next_token

        records, next_token = await asyncio.to_thread(_fetch_page)
        return {
            "status": "success",
            "namespace": "full_clip",
            "count": len(records),
            "next_page_token": next_token,
            "records": records,
        }
    except Exception as e:
        logger.error(f"Pinecone full_clip list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/video/{video_id}")
async def get_all_video_data(video_id: str):
    """Fetch all data related to a video ID across all namespaces"""
    try:
        index = await asyncio.to_thread(_get_index)
        
        # 1. Fetch segments (default namespace)
        segments_res = await asyncio.to_thread(
            index.query,
            vector=[0.0] * 384,
            filter={"video_id": video_id},
            top_k=1000,
            include_metadata=True
        )
        segments = [
            {
                "id": m["id"],
                "start_time": m["metadata"].get("start_time"),
                "end_time": m["metadata"].get("end_time"),
                "text": m["metadata"].get("text"),
            }
            for m in segments_res.get("matches", [])
        ]
        # Sort by start time
        segments.sort(key=lambda x: x["start_time"] if x["start_time"] is not None else 0)

        # 2. Fetch highlights
        highlights = await asyncio.to_thread(search_highlights, "retrieve all", 100, video_id)
        
        # 3. Fetch quiz
        quiz = await asyncio.to_thread(get_quiz_from_pinecone, video_id)

        return {
            "status": "success",
            "video_id": video_id,
            "data": {
                "segments": segments,
                "highlights": highlights,
                "quiz": quiz
            }
        }
    except Exception as e:
        logger.error(f"Pinecone video data fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
