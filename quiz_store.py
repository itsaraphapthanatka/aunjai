"""
quiz_store.py — บันทึก Quiz data ลง Pinecone ใน namespace 'full_clip'
"""

import logging
import hashlib
import json
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

from config import (
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    EMBEDDING_MODEL_NAME,
    YOUTUBE_URL_TEMPLATE,
)

logger = logging.getLogger(__name__)

# Namespace ตามที่ User กำหนด
QUIZ_NAMESPACE = "full_clip"

_model = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"🧠 โหลดโมเดล embedding: {EMBEDDING_MODEL_NAME}")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model

def _get_index():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(PINECONE_INDEX_NAME)

def _generate_quiz_id(video_id: str) -> str:
    raw = f"quiz_{video_id}"
    return hashlib.md5(raw.encode()).hexdigest()

def store_full_clip_quiz(video_id: str, quiz_data: list[dict], transcript_summary: str = "") -> bool:
    """
    บันทึก Quiz แบบเต็มคลิปลง Pinecone 
    ใช้ namespace 'full_clip'
    """
    if not quiz_data:
        return False

    if not PINECONE_API_KEY:
        logger.warning("⚠️ ไม่มี PINECONE_API_KEY — ข้าม Pinecone storage")
        return False

    model = _get_model()
    index = _get_index()

    video_url = YOUTUBE_URL_TEMPLATE.format(video_id=video_id)
    
    # สร้าง embedding text จากข้อมูลคำถาม
    embed_parts = ["Full Clip Quiz for video: " + video_id]
    for q in quiz_data:
        embed_parts.append(f"Q: {q.get('question', '')}")

    embed_text = " // ".join(embed_parts)[:2000] # สรุปรวมๆ แค่คำถาม

    embedding = model.encode(embed_text).tolist()

    metadata = {
        "type": "full_clip_quiz",
        "video_id": video_id,
        "video_url": video_url,
        "quiz": json.dumps(quiz_data, ensure_ascii=False)[:30000], # เก็บ JSON ไปใน metadata (Pinecone limits metadata to 40KB)
        "transcript_summary": transcript_summary[:1000]
    }

    vector_id = _generate_quiz_id(video_id)
    vector_record = {
        "id": vector_id,
        "values": embedding,
        "metadata": metadata,
    }

    try:
        index.upsert(vectors=[vector_record], namespace=QUIZ_NAMESPACE)
        logger.info(f"✅ บันทึก Quiz สำหรับคลิป {video_id} ลง Pinecone (namespace: {QUIZ_NAMESPACE})")
        return True
    except Exception as e:
        logger.error(f"❌ Pinecone upsert error: {e}")
        return False

def get_quiz_from_pinecone(video_id: str) -> list[dict]:
    """
    ดึงข้อมูล Quiz จาก Pinecone ด้วย video_id
    เนื่องจากเราไม่แน่ใจว่าตัว embedding อะไร ให้ใช้วิธี dummy fetch จาก video_id
    """
    if not PINECONE_API_KEY:
        return []

    index = _get_index()
    vector_id = _generate_quiz_id(video_id)

    try:
        response = index.fetch(ids=[vector_id], namespace=QUIZ_NAMESPACE)
        match = response.get("vectors", {}).get(vector_id)
        if match:
            meta = match.get("metadata", {})
            if meta.get("quiz"):
                try:
                    return json.loads(meta["quiz"])
                except json.JSONDecodeError:
                    return []
    except Exception as e:
        logger.error(f"❌ Error fetching quiz for {video_id}: {e}")
        
    return []
