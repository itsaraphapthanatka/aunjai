"""
extractor.py — Module 1: Data Extraction (YouTube Transcription)

ดึงคำบรรยาย (Transcript) จากวิดีโอ YouTube
รองรับภาษาไทย โดยมี fallback เป็นภาษาอังกฤษ

ใช้ youtube-transcript-api v1.x (instance-based API)
"""

import logging
from youtube_transcript_api import YouTubeTranscriptApi

# ตั้งค่า Logger
logger = logging.getLogger(__name__)

# สร้าง API client (ใช้ร่วมกันทั้งโมดูล)
_api = YouTubeTranscriptApi()


def extract_transcripts(video_id_list: list[str]) -> list[dict]:
    """
    ดึง Transcript จากรายการ video_id ที่กำหนด

    Args:
        video_id_list: รายการ YouTube Video ID เช่น ["dQw4w9WgXcQ", "abc123"]

    Returns:
        รายการ dict แต่ละตัวมี keys: text, start, duration, video_id

    ตัวอย่าง Output:
        [
            {
                "text": "สวัสดีครับ วันนี้เราจะมาพูดถึง...",
                "start": 0.0,
                "duration": 4.5,
                "video_id": "dQw4w9WgXcQ"
            },
            ...
        ]
    """
    all_transcripts: list[dict] = []

    for video_id in video_id_list:
        try:
            # ดึง Transcript โดยลองภาษาไทยก่อน → fallback เป็นอังกฤษ
            fetched = _api.fetch(video_id, languages=["th", "en"])

            # แปลง snippets ให้อยู่ในรูปแบบ dict มาตรฐาน
            for snippet in fetched.snippets:
                all_transcripts.append({
                    "text": snippet.text,
                    "start": snippet.start,
                    "duration": snippet.duration,
                    "video_id": video_id,
                })

            logger.info(
                f"✅ ดึง Transcript สำเร็จ: video_id={video_id} "
                f"(ภาษา: {fetched.language}, {len(fetched.snippets)} ประโยค)"
            )

        except Exception as e:
            # youtube-transcript-api v1.x ใช้ exception hierarchy ต่างๆ เช่น
            # TranscriptsDisabled, NoTranscriptFound, VideoUnavailable ฯลฯ
            # จับทั้งหมดแล้ว log เพื่อไม่ให้ pipeline หยุด
            error_name = type(e).__name__
            logger.warning(f"⚠️ ข้ามวิดีโอ {video_id} — {error_name}: {e}")

    logger.info(f"📊 รวมทั้งหมด: {len(all_transcripts)} ประโยคจาก {len(video_id_list)} วิดีโอ")
    return all_transcripts


# ──────────────────────────────────────────────
# ทดสอบแบบ standalone
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ใส่ video_id ตัวอย่างเพื่อทดสอบ
    test_ids = ["dQw4w9WgXcQ"]
    results = extract_transcripts(test_ids)

    print(f"\n{'='*60}")
    print(f"ผลลัพธ์: {len(results)} ประโยค")
    for item in results[:5]:
        print(f"  [{item['start']:.1f}s] {item['text'][:80]}")
