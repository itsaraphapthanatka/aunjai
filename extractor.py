"""
extractor.py — Module 1: Data Extraction (YouTube Transcription)

ดึงคำบรรยาย (Transcript) จากวิดีโอ YouTube
รองรับภาษาไทย โดยมี fallback เป็นภาษาอังกฤษ

ใช้ youtube-transcript-api v1.x (instance-based API)
"""

import logging
import time
import random
import os
import requests
from http.cookiejar import MozillaCookieJar
from youtube_transcript_api import YouTubeTranscriptApi
from config import get_yt_proxy_config, YOUTUBE_COOKIES_FILE

# ตั้งค่า Logger
logger = logging.getLogger(__name__)

# Exponential Backoff Configuration
MAX_RETRIES = 3
BASE_DELAY = 2

# สร้าง Session พร้อม Cookies (ถ้ามี)
def _create_session():
    session = requests.Session()
    # เพิ่ม User-Agent เพื่อให้ดูเหมือน Browser จริงมากขึ้น
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'th,en-US;q=0.9,en;q=0.8',
    })
    
    if YOUTUBE_COOKIES_FILE and os.path.exists(YOUTUBE_COOKIES_FILE):
        cj = MozillaCookieJar(YOUTUBE_COOKIES_FILE)
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies.update(cj)
            logger.info(f"🍪 โหลด YouTube Cookies จาก {YOUTUBE_COOKIES_FILE} (พบ {len(cj)} cookies)")
        except Exception as e:
            logger.warning(f"⚠️ ไม่สามารถโหลด Cookies ได้: {e}")
    else:
        logger.warning(f"⚠️ ไม่พบไฟล์ Cookies ที่ {YOUTUBE_COOKIES_FILE}")
        
    return session

# สร้าง API client พร้อม proxy และ cookies
_proxy_config = get_yt_proxy_config()
_session = _create_session()
_api = YouTubeTranscriptApi(proxy_config=_proxy_config, http_client=_session)

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
        fetched_data = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # ลองดึง Transcript list (ใช้ instance ที่มี session/cookies/proxy)
                transcript_list = _api.list(video_id)
                
                # พยายามหาภาษาไทยก่อน → ภาษาอังกฤษ
                try:
                    fetched_transcript = transcript_list.find_transcript(["th", "en"])
                except:
                    # ถ้าไม่เจอเลย ให้เอาตัวแรกที่มี
                    fetched_transcript = next(iter(transcript_list))

                fetched_data = fetched_transcript.fetch()
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

        if fetched_data:
            # แปลง snippets ให้อยู่ในรูปแบบ dict มาตรฐาน
            for snippet in fetched_data:
                # Handle both dict (old versions) and objects (new versions)
                if isinstance(snippet, dict):
                    text = snippet.get("text", "")
                    start = snippet.get("start", 0)
                    duration = snippet.get("duration", 0)
                else:
                    text = getattr(snippet, "text", "")
                    start = getattr(snippet, "start", 0)
                    duration = getattr(snippet, "duration", 0)
                    logger.debug(f"Snippet is object: {type(snippet)}, text={text[:20]}...")

                all_transcripts.append({
                    "text": text,
                    "start": start,
                    "duration": duration,
                    "video_id": video_id,
                })

            logger.info(
                f"✅ ดึง Transcript สำเร็จ: video_id={video_id} "
                f"({len(fetched_data)} ประโยค)"
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
