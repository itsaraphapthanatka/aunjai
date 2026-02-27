"""
test_search.py — ทดสอบ Semantic Search

ทดสอบการค้นหาคลิปวิดีโอจาก Pinecone ด้วยคำถามภาษาไทย
ต้องมี PINECONE_API_KEY ใน .env และต้องรัน pipeline.py ก่อน
"""

import logging
from searcher import search_relevant_clip

# ตั้งค่า Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    """ทดสอบค้นหาด้วยคำถามตัวอย่าง"""
    # คำถามตัวอย่างจำลองสถานการณ์จริง (ผู้ใช้ระบายความในใจ)
    test_queries = [
        "ฉันเหนื่อยกับชีวิตมาก ไม่อยากทำอะไรเลย",
        "ทะเลาะกับแฟนทุกวัน ไม่รู้จะทำยังไง",
        "รู้สึกไม่มีค่า ไม่มีใครเข้าใจ",
        "อยากเริ่มต้นรักตัวเองใหม่",
        "เครียดเรื่องงานมาก นอนไม่หลับ",
    ]

    print("\n" + "=" * 70)
    print("🔍 ทดสอบ Semantic Search — น้องอุ่นใจ Knowledge Base")
    print("=" * 70)

    for query in test_queries:
        print(f"\n{'─' * 70}")
        print(f"💬 คำถาม: {query}")
        print(f"{'─' * 70}")

        try:
            results = search_relevant_clip(query, top_k=3)

            if not results:
                print("  ⚠️ ไม่พบผลลัพธ์")
                continue

            for i, clip in enumerate(results, 1):
                print(f"\n  📹 ผลลัพธ์ที่ {i} (คะแนน: {clip['score']}):")
                print(f"     Video ID:   {clip['video_id']}")
                print(f"     เวลาเริ่ม:   {clip['start_time']}s")
                print(f"     เวลาจบ:     {clip['end_time']}s")
                print(f"     URL:        {clip['original_url']}")
                print(f"     ข้อความ:    {clip['text'][:150]}...")

        except ValueError as e:
            print(f"  ❌ {e}")
            print("  💡 ตรวจสอบว่าตั้งค่า PINECONE_API_KEY ใน .env แล้ว")
            break
        except Exception as e:
            print(f"  ❌ เกิดข้อผิดพลาด: {e}")
            break

    print(f"\n{'=' * 70}")
    print("✅ ทดสอบเสร็จสิ้น")
    print("=" * 70)


if __name__ == "__main__":
    main()
