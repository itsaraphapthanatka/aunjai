"""
highlight_store.py — บันทึก Highlight data ลง Pinecone

เก็บข้อมูล highlight ทั้งหมด:
- transcript text
- video link
- start_time, end_time
- reason, score
- quiz (คำถาม-คำตอบ)

ใช้ SentenceTransformer embedding เดียวกับ embedder.py
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

# Namespace สำหรับแยก highlight data จาก knowledge base ปกติ
HIGHLIGHT_NAMESPACE = "highlights"

# Cache model
_model = None


def _get_model() -> SentenceTransformer:
    """โหลด/cache embedding model"""
    global _model
    if _model is None:
        logger.info(f"🧠 โหลดโมเดล embedding: {EMBEDDING_MODEL_NAME}")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def _get_index():
    """เชื่อมต่อ Pinecone index"""
    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(PINECONE_INDEX_NAME)


def _generate_highlight_id(video_id: str, start_time: float) -> str:
    """สร้าง unique ID สำหรับ highlight"""
    raw = f"hl_{video_id}_{start_time}"
    return hashlib.md5(raw.encode()).hexdigest()


def store_highlights(video_id: str, highlights: list[dict]) -> int:
    """
    บันทึก highlights ลง Pinecone

    Args:
        video_id: YouTube video ID
        highlights: list ของ highlight dict ที่มี:
            - start_time, end_time, reason, score
            - transcript (optional)
            - quiz (optional): [{"question": "...", "answer": "..."}]
            - clip_url (optional)

    Returns:
        จำนวน vectors ที่บันทึกสำเร็จ
    """
    if not highlights:
        return 0

    if not PINECONE_API_KEY:
        logger.warning("⚠️ ไม่มี PINECONE_API_KEY — ข้าม Pinecone storage")
        return 0

    model = _get_model()
    index = _get_index()

    video_url = YOUTUBE_URL_TEMPLATE.format(video_id=video_id)
    vectors = []

    for h in highlights:
        # สร้าง text สำหรับ embedding — รวม transcript + reason + quiz
        embed_parts = []
        if h.get("transcript"):
            embed_parts.append(h["transcript"])
        if h.get("reason"):
            embed_parts.append(h["reason"])
        if h.get("quiz"):
            for q in h["quiz"]:
                embed_parts.append(f"Q: {q.get('question', '')}")
                if q.get("options"):
                    embed_parts.append(f"Options: {', '.join(q['options'])}")
                embed_parts.append(f"A: {q.get('answer', '')}")

        embed_text = " ".join(embed_parts) if embed_parts else h.get("reason", "highlight")

        # สร้าง embedding
        embedding = model.encode(embed_text).tolist()

        # เตรียม metadata
        metadata = {
            "type": "highlight",
            "video_id": video_id,
            "video_url": video_url,
            "start_time": h.get("start_time", 0),
            "end_time": h.get("end_time", 0),
            "reason": h.get("reason", ""),
            "score": h.get("score", 0),
            "transcript": h.get("transcript", "")[:1000],  # จำกัด Pinecone metadata size
            "clip_url": h.get("clip_url", ""),
        }

        # บันทึก quiz เป็น JSON string
        if h.get("quiz"):
            metadata["quiz"] = json.dumps(h["quiz"], ensure_ascii=False)[:1000]

        vector_id = _generate_highlight_id(video_id, h.get("start_time", 0))
        vectors.append({
            "id": vector_id,
            "values": embedding,
            "metadata": metadata,
        })

    # Upsert ลง Pinecone (namespace: highlights)
    try:
        index.upsert(vectors=vectors, namespace=HIGHLIGHT_NAMESPACE)
        logger.info(f"✅ บันทึก {len(vectors)} highlights ลง Pinecone (namespace: {HIGHLIGHT_NAMESPACE})")
        # Return mapping: start_time -> vector_id
        id_map = {}
        for v_data, h in zip(vectors, highlights):
            id_map[h.get("start_time", 0)] = v_data["id"]
        return id_map
    except Exception as e:
        logger.error(f"❌ Pinecone upsert error: {e}")
        return {}


def search_highlights(query: str, top_k: int = 5, video_id: str = None) -> list[dict]:
    """
    ค้นหา highlights จาก Pinecone

    Args:
        query: คำค้นหา
        top_k: จำนวนผลลัพธ์สูงสุด
        video_id: (optional) กรอง video_id

    Returns:
        list ของ highlight results
    """
    if not PINECONE_API_KEY:
        return []

    model = _get_model()
    index = _get_index()

    query_embedding = model.encode(query).tolist()

    filter_dict = {"type": "highlight"}
    if video_id:
        filter_dict["video_id"] = video_id

    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True,
        namespace=HIGHLIGHT_NAMESPACE,
        filter=filter_dict,
    )

    highlights = []
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        item = {
            "video_id": meta.get("video_id", ""),
            "video_url": meta.get("video_url", ""),
            "start_time": meta.get("start_time", 0),
            "end_time": meta.get("end_time", 0),
            "reason": meta.get("reason", ""),
            "score": meta.get("score", 0),
            "transcript": meta.get("transcript", ""),
            "clip_url": meta.get("clip_url", ""),
            "similarity": match.get("score", 0),
        }

        # Parse quiz JSON
        if meta.get("quiz"):
            try:
                item["quiz"] = json.loads(meta["quiz"])
            except json.JSONDecodeError:
                item["quiz"] = []

        highlights.append(item)

    return highlights


def get_processed_video_ids(video_ids: list[str]) -> list[str]:
    """
    ตรวจสอบว่า video_id ไหนมีข้อมูลใน Pinecone แล้วบ้าง (ตรวจได้ทีละหลาย ID)
    """
    if not PINECONE_API_KEY or not video_ids:
        return []

    index = _get_index()
    processed_ids = set()

    # Pinecone filter รองรับ $in สำหรับ metadata
    # แต่ถ้า video_ids เยอะเกินไป (เช่น > 100) อาจจะต้องแบ่งชุด (Batch)
    batch_size = 100
    for i in range(0, len(video_ids), batch_size):
        batch = video_ids[i:i + batch_size]
        try:
            results = index.query(
                vector=[0.0] * 384, # Dummy vector (เราใช้ filter อย่างเดียว)
                top_k=1000,
                namespace=HIGHLIGHT_NAMESPACE,
                filter={
                    "type": "highlight",
                    "video_id": {"$in": batch}
                },
                include_metadata=True
            )
            for match in results.get("matches", []):
                v_id = match.get("metadata", {}).get("video_id")
                if v_id:
                    processed_ids.add(v_id)
        except Exception as e:
            logger.error(f"❌ Error checking processed IDs: {e}")

    return list(processed_ids)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ทดสอบ search
    results = search_highlights("เทคนิคจัดการความเครียด", top_k=3)
    print(f"\nพบ {len(results)} highlights")
    for r in results:
        print(f"  🎬 {r['video_id']} [{r['start_time']:.0f}s-{r['end_time']:.0f}s] — {r['reason']}")
        if r.get("quiz"):
            for q in r["quiz"]:
                print(f"     ❓ {q['question']}")
                if q.get("options"):
                    for i, opt in enumerate(q["options"]):
                        print(f"        {chr(65+i)}. {opt}")
                print(f"     ✅ {q['answer']}")
