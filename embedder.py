"""
embedder.py — Module 3: Embedding & Vector DB Sync

สร้าง Embedding จากข้อความ Chunk แล้ว Upsert ลง Pinecone Vector Database
ใช้โมเดล paraphrase-multilingual-MiniLM-L12-v2 ที่รองรับภาษาไทย
"""

import logging
import hashlib
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec

from config import (
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_DIMENSION,
    YOUTUBE_URL_TEMPLATE,
)

# ตั้งค่า Logger
logger = logging.getLogger(__name__)

# ขนาด Batch สำหรับ Upsert (Pinecone แนะนำไม่เกิน 100 vectors ต่อ batch)
UPSERT_BATCH_SIZE = 100


def load_model() -> SentenceTransformer:
    """
    โหลด Sentence Transformer Model สำหรับสร้าง Embedding
    จะ cache โมเดลไว้ในเครื่องอัตโนมัติหลังดาวน์โหลดครั้งแรก
    """
    logger.info(f"🧠 กำลังโหลดโมเดล: {EMBEDDING_MODEL_NAME}...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    logger.info("✅ โหลดโมเดลสำเร็จ")
    return model


def create_or_get_index(index_name: str = PINECONE_INDEX_NAME) -> object:
    """
    สร้าง Index ใน Pinecone ถ้ายังไม่มี หรือเชื่อมต่อกับ Index ที่มีอยู่แล้ว

    Args:
        index_name: ชื่อ Index ใน Pinecone

    Returns:
        Pinecone Index object พร้อมใช้งาน
    """
    if not PINECONE_API_KEY:
        raise ValueError(
            "❌ ไม่พบ PINECONE_API_KEY — กรุณาตั้งค่าในไฟล์ .env\n"
            "   ดูตัวอย่างใน .env.example"
        )

    # สร้าง Pinecone client
    pc = Pinecone(api_key=PINECONE_API_KEY)

    # ตรวจสอบว่า Index มีอยู่แล้วหรือไม่
    existing_indexes = [idx.name for idx in pc.list_indexes()]

    if index_name not in existing_indexes:
        logger.info(f"📦 กำลังสร้าง Index ใหม่: {index_name}...")
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1",
            ),
        )
        logger.info(f"✅ สร้าง Index '{index_name}' สำเร็จ")
    else:
        logger.info(f"✅ ใช้ Index ที่มีอยู่แล้ว: {index_name}")

    # เชื่อมต่อกับ Index
    index = pc.Index(index_name)
    return index


def embed_and_upsert(
    chunks: list[dict],
    model: SentenceTransformer | None = None,
    index: object | None = None,
) -> int:
    """
    สร้าง Embedding จาก Chunks แล้ว Upsert ลง Pinecone

    Args:
        chunks: รายการ dict จาก chunker (ต้องมี text, video_id, start_time, end_time)
        model: SentenceTransformer model (ถ้าไม่ส่งจะโหลดใหม่)
        index: Pinecone Index object (ถ้าไม่ส่งจะสร้าง/เชื่อมต่อใหม่)

    Returns:
        จำนวน vectors ที่ Upsert สำเร็จ
    """
    if not chunks:
        logger.warning("⚠️ ไม่มี Chunks สำหรับทำ Embedding")
        return 0

    # โหลดโมเดลถ้ายังไม่มี
    if model is None:
        model = load_model()

    # เชื่อมต่อ Pinecone Index ถ้ายังไม่มี
    if index is None:
        index = create_or_get_index()

    # ดึงข้อความจาก Chunks
    texts = [chunk["text"] for chunk in chunks]

    # สร้าง Embedding ทั้งหมด (แสดง progress bar)
    logger.info(f"🔄 กำลังสร้าง Embedding สำหรับ {len(texts)} chunks...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)

    # เตรียมข้อมูลสำหรับ Upsert
    vectors = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # สร้าง unique ID จาก video_id + start_time
        vector_id = _generate_id(chunk["video_id"], chunk["start_time"])

        vectors.append({
            "id": vector_id,
            "values": embedding.tolist(),
            "metadata": {
                "text": chunk["text"],
                "video_id": chunk["video_id"],
                "start_time": chunk["start_time"],
                "end_time": chunk["end_time"],
                "original_url": YOUTUBE_URL_TEMPLATE.format(video_id=chunk["video_id"]),
            },
        })

    # Upsert เป็น batch
    total_upserted = 0
    for i in tqdm(range(0, len(vectors), UPSERT_BATCH_SIZE), desc="📤 Upserting"):
        batch = vectors[i : i + UPSERT_BATCH_SIZE]
        index.upsert(vectors=batch)
        total_upserted += len(batch)

    logger.info(f"✅ Upsert สำเร็จ: {total_upserted} vectors")
    return total_upserted


def _generate_id(video_id: str, start_time: float) -> str:
    """สร้าง unique ID สำหรับ vector จาก video_id และ start_time"""
    raw = f"{video_id}_{start_time}"
    return hashlib.md5(raw.encode()).hexdigest()


# ──────────────────────────────────────────────
# ทดสอบแบบ standalone
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ทดสอบโหลดโมเดลและสร้าง Embedding
    model = load_model()

    test_chunks = [
        {
            "text": "เวลาเรารู้สึกเหนื่อย ต้องหัดพักผ่อนให้เป็น",
            "video_id": "test123",
            "start_time": 0.0,
            "end_time": 10.0,
        },
        {
            "text": "ความรักตัวเองเริ่มจากการยอมรับในสิ่งที่เราเป็น",
            "video_id": "test123",
            "start_time": 10.0,
            "end_time": 20.0,
        },
    ]

    # ทดสอบสร้าง Embedding อย่างเดียว (ไม่ต้อง Pinecone)
    texts = [c["text"] for c in test_chunks]
    embeddings = model.encode(texts)
    print(f"\n{'='*60}")
    print(f"สร้าง Embedding สำเร็จ: {len(embeddings)} vectors")
    print(f"มิติของ Vector: {len(embeddings[0])}")
    print(f"ตัวอย่าง Vector (5 ค่าแรก): {embeddings[0][:5]}")
