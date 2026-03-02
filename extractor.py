"""
extractor.py — Module 1: Data Extraction (YouTube Transcription)

ดึงคำบรรยาย (Transcript) จากวิดีโอ YouTube
รองรับภาษาไทย โดยมี fallback เป็นภาษาอังกฤษ

ใช้ youtube-transcript-api v1.x (instance-based API)
"""

import logging
import time
import random
from youtube_transcript_api import YouTubeTranscriptApi
from config import get_yt_proxy_config

# ตั้งค่า Logger
logger = logging.getLogger(__name__)

# Exponential Backoff Configuration
MAX_RETRIES = 3
BASE_DELAY = 2  # วินาที (จะเพิ่มเป็น 2, 4, 8, ...)

# สร้าง API client พร้อม proxy (ถ้าตั้งค่าไว้)
_proxy_config = get_yt_proxy_config()
_api = YouTubeTranscriptApi(proxy_config=_proxy_config) if _proxy_config else YouTubeTranscriptApi()
if _proxy_config:
    logger.info("🔀 ใช้ Proxy สำหรับ YouTube Transcript API")


def _is_retryable_error(e: Exception) -> bool:
    """ตรวจสอบว่า error นี้ควร retry หรือไม่"""
    error_name = type(e).__name__
    return error_name in ("RequestBlocked", "IpBlocked", "TooManyRequests")


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
        fetched = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # ดึง Transcript โดยลองภาษาไทยก่อน → fallback เป็นอังกฤษ
                fetched = _api.fetch(video_id, languages=["th", "en"])
                break  # สำเร็จ ออกจาก retry loop

            except Exception as e:
                error_name = type(e).__name__

                if _is_retryable_error(e) and attempt < MAX_RETRIES:
                    # Exponential backoff with jitter
                    delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    logger.warning(
                        f"⏳ {video_id} — {error_name}, "
                        f"retry {attempt}/{MAX_RETRIES} หลัง {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.warning(f"⚠️ ข้ามวิดีโอ {video_id} — {error_name}: {e}")
                    break  # ไม่ retry (ไม่ใช่ retryable หรือ หมด retry)

        if fetched:
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
