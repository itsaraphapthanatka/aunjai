"""
chunker.py — Module 2: Semantic Chunking Logic

รวมประโยคเล็กๆ จาก Transcript เข้าด้วยกันเป็น Chunk ขนาด ~300-500 ตัวอักษร
โดยมี Overlap ~10-15% เพื่อรักษาบริบทระหว่าง Chunk
"""

import logging
from config import CHUNK_SIZE, CHUNK_OVERLAP_RATIO

# ตั้งค่า Logger
logger = logging.getLogger(__name__)


def create_chunks(
    transcript_data: list[dict],
    chunk_size: int = CHUNK_SIZE,
    overlap_ratio: float = CHUNK_OVERLAP_RATIO,
) -> list[dict]:
    """
    แบ่ง Transcript ออกเป็น Chunks ที่มีขนาดเหมาะสมสำหรับ Embedding

    Args:
        transcript_data: รายการ dict จาก extractor (ต้องมี text, start, duration, video_id)
        chunk_size: จำนวนตัวอักษรเป้าหมายต่อ Chunk (ค่าเริ่มต้น 400)
        overlap_ratio: สัดส่วนการคาบเกี่ยว (ค่าเริ่มต้น 0.12 = 12%)

    Returns:
        รายการ dict แต่ละตัวมี keys:
        - text: ข้อความรวมของ Chunk
        - video_id: รหัสวิดีโอ
        - start_time: เวลาเริ่มต้นของประโยคแรกใน Chunk (วินาที)
        - end_time: เวลาสิ้นสุดของประโยคสุดท้ายใน Chunk (วินาที)
    """
    if not transcript_data:
        logger.warning("⚠️ ไม่มีข้อมูล Transcript สำหรับทำ Chunking")
        return []

    # จัดกลุ่มตาม video_id เพื่อไม่ให้ Chunk ข้ามวิดีโอ
    grouped = _group_by_video(transcript_data)
    all_chunks: list[dict] = []

    for video_id, sentences in grouped.items():
        video_chunks = _chunk_single_video(sentences, video_id, chunk_size, overlap_ratio)
        all_chunks.extend(video_chunks)
        logger.info(
            f"✅ สร้าง {len(video_chunks)} chunks จากวิดีโอ {video_id}"
        )

    logger.info(f"📊 รวมทั้งหมด: {len(all_chunks)} chunks")
    return all_chunks


def _group_by_video(transcript_data: list[dict]) -> dict[str, list[dict]]:
    """จัดกลุ่ม Transcript ตาม video_id"""
    grouped: dict[str, list[dict]] = {}
    for entry in transcript_data:
        vid = entry["video_id"]
        if vid not in grouped:
            grouped[vid] = []
        grouped[vid].append(entry)
    return grouped


def _chunk_single_video(
    sentences: list[dict],
    video_id: str,
    chunk_size: int,
    overlap_ratio: float,
) -> list[dict]:
    """
    สร้าง Chunks จากประโยคของวิดีโอเดียว

    ใช้วิธี sliding window:
    1. เพิ่มประโยคทีละตัวจนกว่าจะเกิน chunk_size
    2. บันทึก Chunk ปัจจุบัน
    3. ย้อนกลับตาม overlap_ratio แล้วเริ่ม Chunk ใหม่
    """
    chunks: list[dict] = []
    overlap_chars = int(chunk_size * overlap_ratio)

    # ตัวแปรสำหรับ Chunk ปัจจุบัน
    current_texts: list[str] = []
    current_start: float = sentences[0]["start"]
    current_end: float = sentences[0]["start"]
    current_length: int = 0

    # เก็บ index ของประโยคที่เริ่มต้น Chunk ปัจจุบัน
    chunk_start_idx: int = 0

    for i, sentence in enumerate(sentences):
        text = sentence["text"].strip()
        if not text:
            continue

        text_len = len(text)

        # ถ้าเพิ่มประโยคนี้แล้วเกิน chunk_size → บันทึก Chunk ก่อน
        if current_length + text_len > chunk_size and current_texts:
            chunk = _build_chunk(current_texts, video_id, current_start, current_end)
            chunks.append(chunk)

            # คำนวณจุดเริ่มต้นใหม่ด้วย overlap
            new_start_idx = _find_overlap_start(
                sentences, chunk_start_idx, i, overlap_chars
            )
            chunk_start_idx = new_start_idx

            # เริ่ม Chunk ใหม่จากจุด overlap
            current_texts = []
            current_length = 0
            for j in range(new_start_idx, i):
                overlap_text = sentences[j]["text"].strip()
                if overlap_text:
                    current_texts.append(overlap_text)
                    current_length += len(overlap_text)
            current_start = sentences[new_start_idx]["start"]

        # เพิ่มประโยคปัจจุบัน
        current_texts.append(text)
        current_length += text_len
        current_end = sentence["start"] + sentence.get("duration", 0)

    # บันทึก Chunk สุดท้าย (ถ้ามี)
    if current_texts:
        chunk = _build_chunk(current_texts, video_id, current_start, current_end)
        chunks.append(chunk)

    return chunks


def _build_chunk(
    texts: list[str],
    video_id: str,
    start_time: float,
    end_time: float,
) -> dict:
    """สร้าง Chunk dict จากข้อมูลที่รวบรวมมา"""
    return {
        "text": " ".join(texts),
        "video_id": video_id,
        "start_time": round(start_time, 2),
        "end_time": round(end_time, 2),
    }


def _find_overlap_start(
    sentences: list[dict],
    chunk_start_idx: int,
    current_idx: int,
    overlap_chars: int,
) -> int:
    """
    หาจุดเริ่มต้นของ overlap โดยนับจากท้าย Chunk ย้อนกลับ
    จนกว่าจะได้ตัวอักษรอย่างน้อย overlap_chars ตัว
    """
    accumulated = 0
    start = current_idx

    for j in range(current_idx - 1, chunk_start_idx - 1, -1):
        text = sentences[j]["text"].strip()
        accumulated += len(text)
        start = j
        if accumulated >= overlap_chars:
            break

    return start


# ──────────────────────────────────────────────
# ทดสอบแบบ standalone
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ข้อมูลตัวอย่างสำหรับทดสอบ
    sample_data = [
        {"text": f"ประโยคที่ {i} " * 10, "start": i * 5.0, "duration": 5.0, "video_id": "test123"}
        for i in range(20)
    ]

    chunks = create_chunks(sample_data)

    print(f"\n{'='*60}")
    print(f"จำนวน Chunks: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        print(f"\n--- Chunk {i+1} ---")
        print(f"  start_time: {chunk['start_time']}s")
        print(f"  end_time:   {chunk['end_time']}s")
        print(f"  ความยาว:    {len(chunk['text'])} ตัวอักษร")
        print(f"  ข้อความ:    {chunk['text'][:100]}...")
