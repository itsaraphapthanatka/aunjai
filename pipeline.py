"""
pipeline.py — Main Pipeline: รันทั้ง Knowledge Base จาก YouTube → Pinecone

ขั้นตอน:
1. Extract — ดึง Transcript จาก YouTube
2. Chunk — แบ่งข้อความเป็น Chunks พร้อม Metadata
3. Embed & Upsert — สร้าง Embedding แล้วอัปโหลดเข้า Pinecone
"""

import sys
import logging
import argparse

from extractor import extract_transcripts
from chunker import create_chunks

# หมายเหตุ: import embedder แบบ lazy เพื่อให้ dry-run ทำงานได้โดยไม่ต้องใช้ torch
# (torch/sentence-transformers อาจมีปัญหากับ Python 3.14)

# ตั้งค่า Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_pipeline(
    video_ids: list[str],
    dry_run: bool = False,
) -> dict:
    """
    รัน Pipeline ทั้งหมด: Extract → Chunk → Embed → Upsert

    Args:
        video_ids: รายการ YouTube Video ID
        dry_run: ถ้า True จะทำแค่ Extract + Chunk (ไม่ต้องใช้ Pinecone API Key)

    Returns:
        dict สรุปผลลัพธ์ของแต่ละขั้นตอน
    """
    summary = {
        "video_ids": video_ids,
        "total_sentences": 0,
        "total_chunks": 0,
        "total_vectors_upserted": 0,
        "dry_run": dry_run,
    }

    # ──────────────────────────────────────────
    # ขั้นตอนที่ 1: Extract Transcripts
    # ──────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("📥 ขั้นตอนที่ 1: ดึง Transcript จาก YouTube")
    logger.info("=" * 60)

    transcripts = extract_transcripts(video_ids)
    summary["total_sentences"] = len(transcripts)

    if not transcripts:
        logger.error("❌ ไม่พบ Transcript ใดๆ — หยุดการทำงาน")
        return summary

    # แสดงตัวอย่างข้อมูลที่ดึงมา
    logger.info(f"📊 ดึงมาได้ {len(transcripts)} ประโยค")
    for item in transcripts[:3]:
        logger.info(f"   [{item['start']:.1f}s] {item['text'][:60]}...")

    # ──────────────────────────────────────────
    # ขั้นตอนที่ 2: Semantic Chunking
    # ──────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("✂️ ขั้นตอนที่ 2: แบ่งข้อความเป็น Chunks")
    logger.info("=" * 60)

    chunks = create_chunks(transcripts)
    summary["total_chunks"] = len(chunks)

    if not chunks:
        logger.error("❌ ไม่สามารถสร้าง Chunks ได้ — หยุดการทำงาน")
        return summary

    # แสดงตัวอย่าง Chunks
    logger.info(f"📊 สร้าง {len(chunks)} chunks")
    for i, chunk in enumerate(chunks[:3]):
        logger.info(
            f"   Chunk {i+1}: [{chunk['start_time']:.1f}s - {chunk['end_time']:.1f}s] "
            f"({len(chunk['text'])} ตัวอักษร)"
        )

    # ──────────────────────────────────────────
    # ขั้นตอนที่ 3: Embed & Upsert
    # ──────────────────────────────────────────
    if dry_run:
        logger.info("\n" + "=" * 60)
        logger.info("🏃 โหมด Dry Run — ข้ามขั้นตอน Embedding & Upsert")
        logger.info("=" * 60)
        logger.info("💡 หากต้องการ Upsert จริง ให้ตั้งค่า PINECONE_API_KEY ใน .env")
        logger.info("   แล้วรันใหม่โดยไม่ใช้ --dry-run")
    else:
        logger.info("\n" + "=" * 60)
        logger.info("🚀 ขั้นตอนที่ 3: สร้าง Embedding & Upsert ลง Pinecone")
        logger.info("=" * 60)

        # Lazy import — โหลด sentence_transformers/torch เฉพาะเมื่อต้องใช้จริง
        from embedder import embed_and_upsert
        upserted = embed_and_upsert(chunks)
        summary["total_vectors_upserted"] = upserted

    # ──────────────────────────────────────────
    # สรุปผลลัพธ์
    # ──────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("🎉 Pipeline เสร็จสมบูรณ์!")
    logger.info("=" * 60)
    logger.info(f"   📹 วิดีโอ:       {len(video_ids)} ไฟล์")
    logger.info(f"   📝 ประโยค:       {summary['total_sentences']} ประโยค")
    logger.info(f"   📦 Chunks:       {summary['total_chunks']} ชิ้น")
    logger.info(f"   📤 Upserted:     {summary['total_vectors_upserted']} vectors")

    return summary


def main():
    """Entry point — รับ Video IDs จาก command line"""
    parser = argparse.ArgumentParser(
        description="🧠 น้องอุ่นใจ — Knowledge Base Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ตัวอย่างการใช้งาน:
  python pipeline.py VIDEO_ID_1 VIDEO_ID_2
  python pipeline.py VIDEO_ID_1 --dry-run
  python pipeline.py --file video_ids.txt
        """,
    )
    parser.add_argument(
        "video_ids",
        nargs="*",
        help="YouTube Video IDs (อย่างน้อย 1 ตัว)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ทำแค่ Extract + Chunk (ไม่ต้องใช้ Pinecone API Key)",
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="ไฟล์ข้อความที่มี Video IDs (บรรทัดละ 1 ID)",
    )

    args = parser.parse_args()

    # รวบรวม Video IDs จาก arguments และไฟล์
    video_ids = list(args.video_ids) if args.video_ids else []

    if args.file:
        try:
            # Try utf-8 first, fallback to cp1252 (Windows default) if fails
            encodings = ["utf-8", "cp1252"]
            file_ids = []
            
            for encoding in encodings:
                try:
                    with open(args.file, "r", encoding=encoding) as f:
                        file_ids = [line.strip() for line in f if line.strip()]
                    break  # Success
                except UnicodeDecodeError:
                    continue
            
            if not file_ids:
                # If still empty after trying encodings, maybe empty file or binary
                logger.warning(f"⚠️ ไม่สามารถอ่านไฟล์ {args.file} ได้ หรือไฟล์ว่างเปล่า")
            else:
                video_ids.extend(file_ids)
                logger.info(f"📄 โหลด {len(file_ids)} รายการจากไฟล์ {args.file}")
                
        except FileNotFoundError:
            logger.error(f"❌ ไม่พบไฟล์: {args.file}")
            sys.exit(1)

    # Clean up video IDs (extract ID from URL if necessary)
    cleaned_ids = []
    for vid in video_ids:
        # Simple extraction: if URL, get 'v=' param or last part of path
        if "youtube.com/watch" in vid and "v=" in vid:
            try:
                vid = vid.split("v=")[1].split("&")[0]
            except IndexError:
                pass
        elif "youtu.be/" in vid:
            try:
                vid = vid.split("youtu.be/")[1].split("?")[0]
            except IndexError:
                pass
        cleaned_ids.append(vid)
    video_ids = cleaned_ids

    if not video_ids:
        parser.error("❌ กรุณาระบุ Video IDs อย่างน้อย 1 ตัว")

    # รัน Pipeline
    run_pipeline(video_ids, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
