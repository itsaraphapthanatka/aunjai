"""
searcher.py — Module 4: Semantic Search

ค้นหาคลิปวิดีโอที่เกี่ยวข้องกับคำถามของผู้ใช้
โดยใช้ Semantic Search ผ่าน Pinecone Vector Database
"""

import logging
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

from config import (
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    EMBEDDING_MODEL_NAME,
)

# ตั้งค่า Logger
logger = logging.getLogger(__name__)


def search_relevant_clip(
    query: str,
    top_k: int = 1,
    model: SentenceTransformer | None = None,
    index: object | None = None,
    filter: dict | None = None,
) -> list[dict]:
    """
    ค้นหาคลิปวิดีโอที่เกี่ยวข้องกับคำถาม (Semantic Search)

    Args:
        query: คำถามหรือข้อความจากผู้ใช้ (ภาษาไทยหรืออังกฤษ)
        top_k: จำนวนผลลัพธ์ที่ต้องการ (ค่าเริ่มต้น 1)
        model: SentenceTransformer model (ถ้าไม่ส่งจะโหลดใหม่)
        index: Pinecone Index object (ถ้าไม่ส่งจะเชื่อมต่อใหม่)
        filter: Dictionary สำหรับ filter metadata ใน Pinecone (เช่น {"video_id": "xxx"})

    Returns:
        รายการ dict แต่ละตัวมี keys:
        - video_id: รหัสวิดีโอ YouTube
        - start_time: เวลาเริ่มต้น (วินาที) สำหรับสั่งตัด FFmpeg
        - end_time: เวลาสิ้นสุด (วินาที)
        - text: ข้อความที่ตรงกัน
        - original_url: ลิงก์ YouTube
        - score: คะแนนความเกี่ยวข้อง (0-1)

    ตัวอย่าง:
        >>> results = search_relevant_clip("ฉันเหนื่อยกับชีวิตมาก")
        >>> print(results[0]["video_id"])
        "abc123"
        >>> print(results[0]["start_time"])
        125.5
    """
    # โหลดโมเดลถ้ายังไม่มี
    if model is None:
        logger.info("🧠 กำลังโหลดโมเดล Embedding...")
        model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    # เชื่อมต่อ Pinecone ถ้ายังไม่มี
    if index is None:
        if not PINECONE_API_KEY:
            raise ValueError(
                "❌ ไม่พบ PINECONE_API_KEY — กรุณาตั้งค่าในไฟล์ .env"
            )
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX_NAME)

    # สร้าง Embedding จากคำถาม
    logger.info(f"🔍 กำลังค้นหา: \"{query}\"")
    query_embedding = model.encode(query).tolist()

    # ค้นหาใน Pinecone พร้อม Filter
    query_kwargs = {
        "vector": query_embedding,
        "top_k": top_k,
        "include_metadata": True,
    }
    if filter:
        query_kwargs["filter"] = filter

    results = index.query(**query_kwargs)

    # แปลงผลลัพธ์ให้อยู่ในรูปแบบที่ใช้งานง่าย
    clips: list[dict] = []
    for match in results.get("matches", []):
        metadata = match.get("metadata", {})
        clips.append({
            "video_id": metadata.get("video_id", ""),
            "start_time": metadata.get("start_time", 0.0),
            "end_time": metadata.get("end_time", 0.0),
            "text": metadata.get("text", ""),
            "original_url": metadata.get("original_url", ""),
            "score": round(match.get("score", 0.0), 4),
        })

    logger.info(f"✅ พบ {len(clips)} ผลลัพธ์")
    return clips


def search_multiple_queries(
    queries: list[str],
    top_k: int = 1,
    filter: dict | None = None,
) -> dict[str, list[dict]]:
    """
    ค้นหาหลายคำถามพร้อมกัน โดยโหลดโมเดลและเชื่อมต่อ Pinecone เพียงครั้งเดียว

    Args:
        queries: รายการคำถาม
        top_k: จำนวนผลลัพธ์ต่อคำถาม
        filter: Metadata filter (เช่น {"video_id": "xxx"})


    Returns:
        dict ที่ key เป็นคำถามและ value เป็นรายการผลลัพธ์
    """
    # โหลดทรัพยากรครั้งเดียว
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)

    results: dict[str, list[dict]] = {}
    for query in queries:
        results[query] = search_relevant_clip(
            query=query,
            top_k=top_k,
            model=model,
            index=index,
            filter=filter,
        )

    return results


# ──────────────────────────────────────────────
# ทดสอบแบบ standalone
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ทดสอบค้นหา (ต้องมี PINECONE_API_KEY และข้อมูลใน Index แล้ว)
    test_queries = [
        "ฉันเหนื่อยกับชีวิตมาก",
        "วิธีรักตัวเอง",
        "ทะเลาะกับแฟน",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"🔍 คำถาม: {query}")
        try:
            results = search_relevant_clip(query, top_k=3)
            for i, clip in enumerate(results, 1):
                print(f"\n  📹 ผลลัพธ์ที่ {i}:")
                print(f"     Video ID:   {clip['video_id']}")
                print(f"     เวลาเริ่ม:   {clip['start_time']}s")
                print(f"     เวลาจบ:     {clip['end_time']}s")
                print(f"     คะแนน:      {clip['score']}")
                print(f"     ข้อความ:    {clip['text'][:100]}...")
                print(f"     URL:        {clip['original_url']}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
