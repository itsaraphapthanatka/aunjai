"""
channel_scraper.py — ดึงรายชื่อวิดีโอทั้งหมดจาก YouTube Channel

ใช้ yt-dlp เพื่อดึงข้อมูลวิดีโอ (title, video_id, duration, thumbnail, upload_date)
โดยไม่ต้องดาวน์โหลดวิดีโอจริง
"""

import logging
from typing import Optional
import yt_dlp

logger = logging.getLogger(__name__)


def scrape_channel_videos(
    channel_url: str,
    max_videos: int = 0,
) -> dict:
    """
    ดึงรายชื่อวิดีโอจาก YouTube Channel

    Args:
        channel_url: URL ของ channel เช่น
            - https://www.youtube.com/@ChannelName
            - https://www.youtube.com/channel/UCxxxxxxxx
            - https://www.youtube.com/c/ChannelName
        max_videos: จำนวนวิดีโอสูงสุดที่จะดึง (default: 50)

    Returns:
        dict: {
            "status": "success" | "error",
            "channel_name": "...",
            "videos": [{ "video_id", "title", "duration", "thumbnail", "upload_date" }],
            "message": "..."
        }
    """
    result = {
        "status": "error",
        "channel_name": "",
        "videos": [],
        "message": "",
    }

    # yt-dlp options: extract info only, no download
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,       # don't download, just list
        "ignoreerrors": True,
    }
    if max_videos > 0:
        ydl_opts["playlistend"] = max_videos

    try:
        logger.info(f"🔍 กำลังดึงรายชื่อวิดีโอจาก: {channel_url}")

        # Ensure URL points to channel videos
        url = channel_url.rstrip("/")
        if "/videos" not in url:
            url = url + "/videos"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            result["message"] = "ไม่พบข้อมูล channel"
            return result

        channel_name = info.get("channel", "") or info.get("uploader", "") or info.get("title", "Unknown")
        result["channel_name"] = channel_name

        entries = info.get("entries", [])
        if not entries:
            result["message"] = f"ไม่พบวิดีโอใน channel: {channel_name}"
            return result

        videos = []
        for entry in entries:
            if not entry:
                continue

            video_id = entry.get("id", "")
            if not video_id:
                continue

            # Duration comes in seconds from yt-dlp
            duration = entry.get("duration") or 0

            videos.append({
                "video_id": video_id,
                "title": entry.get("title", "ไม่มีชื่อ"),
                "duration": duration,
                "duration_text": _format_duration(duration),
                "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                "upload_date": entry.get("upload_date", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })

        result["status"] = "success"
        result["videos"] = videos
        result["message"] = f"พบ {len(videos)} วิดีโอจาก {channel_name}"

        logger.info(f"✅ {result['message']}")
        return result

    except Exception as e:
        result["message"] = f"ดึงข้อมูล channel ไม่สำเร็จ: {str(e)}"
        logger.error(f"❌ {result['message']}")
        return result


def _format_duration(seconds) -> str:
    """แปลง seconds เป็น mm:ss หรือ hh:mm:ss"""
    if not seconds:
        return "N/A"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python channel_scraper.py <CHANNEL_URL>")
        sys.exit(1)

    result = scrape_channel_videos(sys.argv[1], max_videos=10)
    print(f"\n{'='*60}")
    print(f"📺 Channel: {result['channel_name']}")
    print(f"📊 Status: {result['status']}")
    print(f"💬 {result['message']}")

    for v in result["videos"]:
        print(f"\n  🎬 {v['title']}")
        print(f"     ID: {v['video_id']} | ⏱️ {v['duration_text']}")
