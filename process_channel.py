"""
process_channel.py — สคริปต์สำหรับดึงและจัดคลิปวิดีโอจาก YouTube Channel แบบ Background

สคริปต์นี้เอาไว้รันบน Terminal หรือ Command Prompt เพื่อดึงวิดีโอทั้งหมดจาก Channel
และทำการวิเคราะห์หา Highlight พร้อมตัดวีดีโออัตโนมัติ โดยไม่ต้องรันผ่าน Web UI
"""

import sys
import argparse
import logging
from typing import Optional

from channel_scraper import scrape_channel_videos
from highlight_pipeline import run_highlight_pipeline

import os

# ตั้งค่า Logging ให้ออกทั้ง Console และไฟล์สำหรับ background processing
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "channel_process.log")
log_formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', datefmt="%Y-%m-%d %H:%M:%S")

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

try:
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    has_file_handler = True
except PermissionError:
    print(f"Warning: Permission denied to write to {log_file_path}. Logging to console only.")
    has_file_handler = False

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
if has_file_handler:
    logger.addHandler(file_handler)

def clean_progress(step: str, detail: str = ""):
    """Callback สำหรับพิมพ์ progress ลง Log"""
    msg = f"{step}: {detail}" if detail else step
    logger.info(f"   ➔ {msg}")

def main():
    parser = argparse.ArgumentParser(description="ดึงวิดีโอและตัด Highlight จาก YouTube Channel")
    parser.add_argument("url", help="URL ของ YouTube Channel")
    parser.add_argument("--max", type=int, default=0, help="จำนวนวิดีโอสูงสุดที่ต้องการดึง (0 = ทั้งหมด, ค่าเริ่มต้น: 0)")
    parser.add_argument("--no-clip", action="store_true", help="ไม่ทำการตัดวิดีโอ (แค่ดึงและวิเคราะห์ highlight)")
    
    args = parser.parse_args()
    channel_url = args.url
    max_videos = args.max
    auto_clip = not args.no_clip

    logger.info("=" * 60)
    logger.info("🚀 เริ่มต้นการประมวลผล Channel Background Job")
    logger.info(f"📍 URL: {channel_url}")
    logger.info(f"📦 Max Videos: {'Unlimited' if max_videos == 0 else max_videos}")
    logger.info(f"✂️  Auto-clip: {auto_clip}")
    logger.info("=" * 60)

    # 1. Scraping Channel
    logger.info("🔍 [Step 1] กำลังดึงรายชื่อวิดีโอจาก Channel...")
    scrape_result = scrape_channel_videos(channel_url, max_videos=max_videos)

    if scrape_result.get("status") != "success":
        logger.error(f"❌ Scraping Failed: {scrape_result.get('message', 'Unknown Error')}")
        sys.exit(1)

    videos = scrape_result.get("videos", [])
    channel_name = scrape_result.get("channel_name", "Unknown Channel")
    
    logger.info(f"✅ พบวิดีโอทั้งหมด {len(videos)} คลิป จากช่อง '{channel_name}'")
    
    if not videos:
        logger.warning("⚠️ ไม่มีวิดีโอที่จะต้องประมวลผล จบการทำงาน")
        sys.exit(0)

    # 2. Processing Each Video
    success_count = 0
    failed_count = 0
    
    for i, video in enumerate(videos, 1):
        video_url = video.get("url")
        video_title = video.get("title")
        
        logger.info("-" * 60)
        logger.info(f"🎬 กำลังประมวลผลคลิปที่ {i}/{len(videos)}")
        logger.info(f"📌 {video_title} ({video_url})")
        logger.info("-" * 60)
        
        try:
            pipeline_result = run_highlight_pipeline(
                youtube_url=video_url,
                auto_clip=auto_clip,
                on_progress=clean_progress
            )
            
            if pipeline_result.get("status") == "success":
                success_count += 1
                highlights = pipeline_result.get("highlights", [])
                logger.info(f"✅ ประมวลผลวิดีโอนี้สำเร็จ! ได้มา {len(highlights)} highlights")
            else:
                failed_count += 1
                logger.error(f"❌ ล้มเหลว: {pipeline_result.get('message', 'Unknown Error')}")
                
        except Exception as e:
            failed_count += 1
            logger.error(f"❌ เกิดข้อผิดพลาดร้ายแรงระหว่างประมวลผล: {e}")

    # Summary
    logger.info("=" * 60)
    logger.info("🎉 สรุปผลการประมวลผล Channel")
    logger.info(f"📺 Channel: {channel_name}")
    logger.info(f"📹 วิดีโอทั้งหมด: {len(videos)}")
    logger.info(f"✅ สำเร็จ: {success_count}")
    logger.info(f"❌ ล้มเหลว: {failed_count}")
    logger.info("=" * 60)

if __name__ == "__main__":
    # Ensure standard encodings
    if sys.stdout.encoding.lower() != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    main()
