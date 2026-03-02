"""
video_processor.py — Module 2: Video Editor Processing Logic

Handles downloading video clips from YouTube and trimming them using FFmpeg.
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

def _get_video_url(video_id: str) -> Optional[str]:
    """Get the direct download URL for the best mp4 format of a YouTube video"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        # 'best' gets the best single file with BOTH video and audio (usually 720p).
        # This avoids the issue of separate video/audio DASH streams losing audio.
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

    # เพิ่ม Proxy ถ้าตั้งค่าไว้
    proxy = get_ytdlp_proxy()
    if proxy:
        ydl_opts['proxy'] = proxy

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('url')
        except Exception as e:
            if _is_retryable_error(e) and attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                logger.warning(
                    f"⏳ {video_id} — YouTube บล็อก, "
                    f"retry {attempt}/{MAX_RETRIES} หลัง {delay:.1f}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"Failed to extract video info for {video_id}: {e}")
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
        return {"status": "success", "file_url": f"/static/clips/{output_filename}"}
        
    logger.info(f"Processing clip for {video_id} from {start_time} to {end_time}")
    
    video_url = _get_video_url(video_id)
    if not video_url:
        return {"status": "error", "message": "Could not extract video URL"}
        
    try:
        # Add margin for smoother transitions
        actual_start = max(0, start_time - margin)
        duration = (end_time - start_time) + (margin * 2)
        
        # Use FFmpeg to download only the required segment and trim it
        stream = ffmpeg.input(video_url, ss=actual_start, t=duration)
        stream = ffmpeg.output(stream, output_path, c='copy')
        
        # Run FFmpeg command using the bundled executable if available
        out, err = ffmpeg.run(stream, cmd=FFMPEG_EXE, capture_stdout=True, capture_stderr=True, overwrite_output=True)
        logger.info(f"Successfully created clip: {output_path}")
        
        return {"status": "success", "file_url": f"/static/clips/{output_filename}"}
        
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
