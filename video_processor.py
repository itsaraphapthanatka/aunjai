"""
video_processor.py — Module 2: Video Editor Processing Logic

Handles downloading video clips from YouTube and trimming them using FFmpeg.
Strategy: Download full video with yt-dlp first, then trim locally with FFmpeg.
"""

import os
import logging
import time
import random
import ffmpeg
import yt_dlp
from config import get_ytdlp_proxy
from typing import Optional, Dict

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_EXE = "ffmpeg"  # Fallback to system ffmpeg

logger = logging.getLogger(__name__)

# Exponential Backoff Configuration
MAX_RETRIES = 3
BASE_DELAY = 2  # วินาที

# Output directory for trimmed clips
OUTPUT_DIR = "static/clips"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def _is_retryable_error(e: Exception) -> bool:
    """ตรวจสอบว่า error ควร retry (บล็อก IP / rate limit)"""
    err_str = str(e).lower()
    return any(kw in err_str for kw in ("429", "too many", "blocked", "sign in"))

def _download_video(video_id: str) -> Optional[str]:
    """Download YouTube video to a temp file using yt-dlp. Returns the file path."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    temp_path = os.path.join(OUTPUT_DIR, f"_temp_{video_id}.mp4")

    # If temp file already exists from a previous download, reuse it
    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
        logger.info(f"♻️ Reusing existing temp file: {temp_path}")
        return temp_path

    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': temp_path,
    }

    # เพิ่ม Proxy ถ้าตั้งค่าไว้
    proxy = get_ytdlp_proxy()
    if proxy:
        ydl_opts['proxy'] = proxy

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                logger.info(f"✅ Downloaded video to: {temp_path}")
                return temp_path
            else:
                logger.error(f"Download produced empty file for {video_id}")
                return None
        except Exception as e:
            if _is_retryable_error(e) and attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                logger.warning(
                    f"⏳ {video_id} — YouTube บล็อก, "
                    f"retry {attempt}/{MAX_RETRIES} หลัง {delay:.1f}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"Failed to download video {video_id}: {e}")
                return None


def process_video_clip(video_id: str, start_time: float, end_time: float, margin: float = 1.0) -> Dict[str, str]:
    """
    Downloads and trims a specific segment of a YouTube video.
    Returns a dictionary with the status and the output file path.
    """
    output_filename = f"{video_id}_{int(start_time)}_{int(end_time)}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # Check if the clip already exists
    if os.path.exists(output_path):
        logger.info(f"Clip already exists: {output_path}")
        return {"status": "success", "file_url": f"/static/clips/{output_filename}", "local_path": output_path}
        
    logger.info(f"Processing clip for {video_id} from {start_time} to {end_time}")
    
    # Step 1: Download full video with yt-dlp
    temp_path = _download_video(video_id)
    if not temp_path:
        return {"status": "error", "message": "Could not download video"}
        
    try:
        # Step 2: Trim the local file with FFmpeg
        actual_start = max(0, start_time - margin)
        duration = (end_time - start_time) + (margin * 2)
        
        # Try stream copy first (fast)
        try:
            stream = ffmpeg.input(temp_path, ss=actual_start, t=duration)
            stream = ffmpeg.output(stream, output_path, c='copy')
            ffmpeg.run(stream, cmd=FFMPEG_EXE, capture_stdout=True, capture_stderr=True, overwrite_output=True)
            logger.info(f"✅ Created clip (stream copy): {output_filename}")
            return {"status": "success", "file_url": f"/static/clips/{output_filename}", "local_path": output_path}
        except ffmpeg.Error:
            logger.warning(f"Stream copy failed, falling back to re-encode...")
            if os.path.exists(output_path):
                os.remove(output_path)

        # Fallback: Re-encode
        stream = ffmpeg.input(temp_path, ss=actual_start, t=duration)
        stream = ffmpeg.output(stream, output_path, vcodec='libx264', acodec='aac', preset='fast')
        ffmpeg.run(stream, cmd=FFMPEG_EXE, capture_stdout=True, capture_stderr=True, overwrite_output=True)
        logger.info(f"✅ Created clip (re-encoded): {output_filename}")
        
        return {"status": "success", "file_url": f"/static/clips/{output_filename}", "local_path": output_path}
        
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg error: {e.stderr.decode('utf-8') if e.stderr else str(e)}")
        return {"status": "error", "message": f"FFmpeg error: {str(e)}"}
    except FileNotFoundError as e:
        logger.error(f"FFmpeg not found: {str(e)}")
        return {"status": "error", "message": "FFmpeg ไม่พร้อมใช้งาน กรุณาติดตั้ง imageio-ffmpeg หรือเพิ่ม ffmpeg ลงใน PATH"}
    except Exception as e:
        logger.error(f"Unexpected error processing video: {str(e)}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # Standard testing
    logging.basicConfig(level=logging.INFO)
    test_id = "dQw4w9WgXcQ"
    print(process_video_clip(test_id, start_time=42, end_time=45))
