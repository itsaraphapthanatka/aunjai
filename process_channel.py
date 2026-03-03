import sys
import argparse
import logging
import json
import time
import random
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List

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

def get_checkpoint_path(url: str) -> str:
    """สร้างพาธไฟล์ checkpoint จาก hash ของ URL"""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f"checkpoint_{url_hash}.json")

def load_checkpoint(url: str) -> Optional[Dict[str, Any]]:
    """โหลดข้อมูล checkpoint ถ้ามี"""
    path = get_checkpoint_path(url)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"⚠️ โหลด checkpoint ไม่สำเร็จ: {e}")
    return None

def save_checkpoint(url: str, data: Dict[str, Any]):
    """บันทึกข้อมูล checkpoint"""
    path = get_checkpoint_path(url)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"⚠️ บันทึก checkpoint ไม่สำเร็จ: {e}")

def clean_progress(step: str, detail: str = ""):
    """Callback สำหรับพิมพ์ progress ลง Log"""
    msg = f"{step}: {detail}" if detail else step
    logger.info(f"   ➔ {msg}")

def main():
    parser = argparse.ArgumentParser(description="ดึงวิดีโอและตัด Highlight จาก YouTube Channel")
    parser.add_argument("url", help="URL ของ YouTube Channel")
    parser.add_argument("--max", type=int, default=0, help="จำนวนวิดีโอสูงสุด (0 = ทั้งหมด)")
    parser.add_argument("--no-clip", action="store_true", help="ไม่ทำการตัดวิดีโอ (แค่ดึงและวิเคราะห์ highlight)")
    parser.add_argument("--batch-size", type=int, default=50, help="ขนาดชุดวิดีโอต่อหนึ่งรอบ (ค่าเริ่มต้น: 50)")
    parser.add_argument("--delay-min", type=int, default=30, help="เวลาหยุดพักระหว่างชุดเป็นนาที (ค่าเริ่มต้น: 30)")
    parser.add_argument("--reset", action="store_true", help="ล้าง checkpoint และเริ่มใหม่ทั้งหมด")
    
    args = parser.parse_args()
    channel_url = args.url
    max_videos = args.max
    auto_clip = not args.no_clip
    batch_size = args.batch_size
    delay_min = args.delay_min
    reset_checkpoint = args.reset

    logger.info("=" * 60)
    logger.info("🚀 เริ่มต้นการประมวลผล Channel Background Job")
    logger.info(f"📍 URL: {channel_url}")
    logger.info(f"📦 Batch Size: {batch_size} | Delay: {delay_min} min")
    logger.info(f"✂️  Auto-clip: {auto_clip}")
    logger.info("=" * 60)

    # โหลด Checkpoint
    checkpoint = None
    if not reset_checkpoint:
        checkpoint = load_checkpoint(channel_url)

    if checkpoint:
        logger.info(f"🔄 พบข้อมูลเดิม! กำลังดำเนินการต่อจากวิดีโอที่ {checkpoint['last_index'] + 1}")
        videos = checkpoint["videos"]
        channel_name = checkpoint.get("channel_name", "Unknown Channel")
        start_index = checkpoint["last_index"] + 1
        success_count = checkpoint.get("success_count", 0)
        failed_count = checkpoint.get("failed_count", 0)
    else:
        # 1. Scraping Channel
        logger.info("🔍 [Step 1] กำลังดึงรายชื่อวิดีโอจาก Channel...")
        scrape_result = scrape_channel_videos(channel_url, max_videos=max_videos)

        if scrape_result.get("status") != "success":
            logger.error(f"❌ Scraping Failed: {scrape_result.get('message', 'Unknown Error')}")
            sys.exit(1)

        videos = scrape_result.get("videos", [])
        channel_name = scrape_result.get("channel_name", "Unknown Channel")
        start_index = 0
        success_count = 0
        failed_count = 0
        
        # บันทึก checkpoint เริ่มต้น
        save_checkpoint(channel_url, {
            "channel_url": channel_url,
            "channel_name": channel_name,
            "videos": videos,
            "last_index": -1,
            "success_count": 0,
            "failed_count": 0,
            "timestamp": datetime.now().isoformat()
        })
    
    logger.info(f"✅ จำนวนวิดีโอทั้งหมดในรายการ: {len(videos)} คลิป")
    
    if start_index >= len(videos):
        logger.info("🏁 ประมวลผลเสร็จสิ้นทุกวิดีโอแล้ว")
        sys.exit(0)

    # 2. Processing Each Video
    processed_this_run = 0
    
    for i in range(start_index, len(videos)):
        video = videos[i]
        video_url = video.get("url")
        video_title = video.get("title")
        
        # ตรวจสอบ Batch Logic
        if processed_this_run > 0 and processed_this_run % batch_size == 0:
            # สุ่มเวลาพักเล็กน้อย (Jitter +/- 20% จากเวลาที่ตั้งไว้)
            jitter_min = delay_min * random.uniform(0.8, 1.2)
            logger.info("=" * 60)
            logger.info(f"😴 ครบชุด {batch_size} คลิปแล้ว... หยุดพักประมาณ {jitter_min:.1f} นาทีเพื่อป้องกัน Rate Limit")
            logger.info("=" * 60)
            time.sleep(jitter_min * 60)
            logger.info("⏰ ตื่นแล้ว! เริ่มประมวลผลชุดต่อไป...")
        elif processed_this_run > 0:
            # สุ่มหน่วงเวลาระหว่างคลิป (15-25 วินาที) ตามคำแนะนำ
            video_jitter = random.uniform(15, 25)
            logger.info(f"⏳ หน่วงเวลาสุ่ม {video_jitter:.1f} วินาทีก่อนเริ่มคลิปถัดไป...")
            time.sleep(video_jitter)

        logger.info("-" * 60)
        logger.info(f"🎬 กำลังประมวลผลคลิปที่ {i+1}/{len(videos)} (ชุดนี้: {processed_this_run + 1}/{batch_size})")
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
                logger.info(f"✅ สำเร็จ! ได้มา {len(highlights)} highlights")
            else:
                failed_count += 1
                logger.error(f"❌ ล้มเหลว: {pipeline_result.get('message', 'Unknown Error')}")
                
        except Exception as e:
            failed_count += 1
            logger.error(f"❌ เกิดข้อผิดพลาดร้ายแรงระหว่างประมวลผล: {e}")

        # Update Checkpoint
        save_checkpoint(channel_url, {
            "channel_url": channel_url,
            "channel_name": channel_name,
            "videos": videos,
            "last_index": i,
            "success_count": success_count,
            "failed_count": failed_count,
            "timestamp": datetime.now().isoformat()
        })
        
        processed_this_run += 1

    # Summary
    logger.info("=" * 60)
    logger.info("🎉 สรุปผลการประมวลผล Channel")
    logger.info(f"📺 Channel: {channel_name}")
    logger.info(f"📹 วิดีโอทั้งหมด: {len(videos)}")
    logger.info(f"✅ สำเร็จ: {success_count}")
    logger.info(f"❌ ล้มเหลว: {failed_count}")
    logger.info("=" * 60)

    # เมื่อเสร็จสิ้นอาจจะลบ checkpoint หรือจะเก็บไว้ดูประวัติก็ได้ 
    # ในที่นี้เก็บไว้เผื่อเช็คประวัติ แต่ถ้ามีการรันใหม่อาจจะต้องใช้ --reset

if __name__ == "__main__":
    # Ensure stdout is utf-8
    try:
        if sys.stdout.encoding.lower() != 'utf-8':
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass
    main()
