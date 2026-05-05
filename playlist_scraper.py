"""
playlist_scraper.py — ดึงรายชื่อวิดีโอจาก YouTube Playlist

ใช้ yt-dlp เพื่อดึงข้อมูลวิดีโอ (title, video_id, duration, thumbnail, upload_date)
โดยไม่ต้องดาวน์โหลดวิดีโอจริง รองรับทั้ง Playlist URL และ Channel Playlists
"""

import logging
import time
import random
import re
from typing import Optional, List
import yt_dlp
from config import get_ytdlp_proxy

logger = logging.getLogger(__name__)

# Exponential Backoff Configuration
MAX_RETRIES = 3
BASE_DELAY = 2  # วินาที


def _is_retryable_error(e: Exception) -> bool:
    """ตรวจสอบว่า error ควร retry (บล็อก IP / rate limit)"""
    err_str = str(e).lower()
    return any(kw in err_str for kw in ("429", "too many", "blocked", "sign in"))


def _get_ydl_opts(max_videos: int = 0) -> dict:
    """สร้าง yt-dlp options มาตรฐาน"""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "cookiefile": "cookies.txt",
        "ignoreerrors": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
        },
        "nocheckcertificate": True,
        "geo_bypass": True,
    }
    if max_videos > 0:
        opts["playlistend"] = max_videos

    proxy = get_ytdlp_proxy()
    if proxy:
        opts["proxy"] = proxy
        logger.info(f"🔀 ใช้ Proxy สำหรับ yt-dlp: {proxy[:30]}...")

    return opts


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


def _parse_video_entry(entry: dict) -> Optional[dict]:
    """แปลง entry จาก yt-dlp เป็น video dict"""
    if not entry:
        return None

    video_id = entry.get("id", "")
    if not video_id:
        return None

    duration = entry.get("duration") or 0

    return {
        "video_id": video_id,
        "title": entry.get("title", "ไม่มีชื่อ"),
        "duration": duration,
        "duration_text": _format_duration(duration),
        "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
        "upload_date": entry.get("upload_date", ""),
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def extract_playlist_id(url: str) -> Optional[str]:
    """
    ดึง Playlist ID จาก URL
    
    รองรับ:
    - https://www.youtube.com/playlist?list=PLxxxxxxx
    - https://www.youtube.com/watch?v=xxx&list=PLxxxxxxx
    - PLxxxxxxx (ID ตรงๆ)
    """
    if not url:
        return None

    # Pattern: ?list=PLxxxx or &list=PLxxxx
    match = re.search(r'[?&]list=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)

    # Pattern: Playlist ID ตรงๆ (เริ่มด้วย PL, UU, FL, etc.)
    if re.match(r'^(PL|UU|FL|LL|RD|OL)[a-zA-Z0-9_-]+$', url):
        return url

    return None


def scrape_playlist_videos(
    playlist_url: str,
    max_videos: int = 0,
) -> dict:
    """
    ดึงรายชื่อวิดีโอจาก YouTube Playlist

    Args:
        playlist_url: URL ของ Playlist หรือ Playlist ID
        max_videos: จำนวนวิดีโอสูงสุดที่จะดึง (0 = ทั้งหมด)

    Returns:
        dict: {
            "status": "success" | "error",
            "playlist_name": "...",
            "playlist_id": "...",
            "videos": [{ "video_id", "title", "duration", "thumbnail", "upload_date" }],
            "message": "..."
        }
    """
    result = {
        "status": "error",
        "playlist_name": "",
        "playlist_id": "",
        "videos": [],
        "message": "",
    }

    # สร้าง URL ที่ถูกต้อง
    playlist_id = extract_playlist_id(playlist_url)
    if playlist_id:
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        result["playlist_id"] = playlist_id
    else:
        url = playlist_url

    ydl_opts = _get_ydl_opts(max_videos)

    info = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"🔍 กำลังดึงวิดีโอจาก Playlist: {url} (ครั้งที่ {attempt})")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            break

        except Exception as e:
            if _is_retryable_error(e) and attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                logger.warning(
                    f"⏳ YouTube บล็อก, retry {attempt}/{MAX_RETRIES} "
                    f"หลัง {delay:.1f}s..."
                )
                time.sleep(delay)
            else:
                result["message"] = f"ดึงข้อมูล Playlist ไม่สำเร็จ: {str(e)}"
                logger.error(f"❌ {result['message']}")
                return result

    if not info:
        result["message"] = "ไม่พบข้อมูล Playlist"
        return result

    playlist_name = info.get("title", "") or info.get("playlist_title", "") or "Unknown Playlist"
    result["playlist_name"] = playlist_name
    if not result["playlist_id"]:
        result["playlist_id"] = info.get("id", "")

    entries = info.get("entries", [])
    if not entries:
        result["message"] = f"ไม่พบวิดีโอใน Playlist: {playlist_name}"
        return result

    videos = []
    for entry in entries:
        video = _parse_video_entry(entry)
        if video:
            videos.append(video)

    result["status"] = "success"
    result["videos"] = videos
    result["message"] = f"พบ {len(videos)} วิดีโอจาก {playlist_name}"

    logger.info(f"✅ {result['message']}")
    return result


def get_channel_playlists(channel_url: str) -> dict:
    """
    ดึงรายการ Playlists ทั้งหมดจาก YouTube Channel

    Args:
        channel_url: URL ของ Channel

    Returns:
        dict: {
            "status": "success" | "error",
            "channel_name": "...",
            "playlists": [{ "playlist_id", "title", "video_count", "url" }],
            "message": "..."
        }
    """
    result = {
        "status": "error",
        "channel_name": "",
        "playlists": [],
        "message": "",
    }

    # yt-dlp options สำหรับดึง playlists
    ydl_opts = _get_ydl_opts()

    # ตรวจสอบ URL เป็น /playlists
    url = channel_url.rstrip("/")
    if "/playlists" not in url:
        # แทนที่ /videos, /shorts, /streams ด้วย /playlists
        url = re.sub(r'/(videos|shorts|streams|featured|about)$', '/playlists', url)
        if "/playlists" not in url:
            url = url + "/playlists"

    info = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"🔍 กำลังดึง Playlists จาก Channel: {url} (ครั้งที่ {attempt})")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            break

        except Exception as e:
            if _is_retryable_error(e) and attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                logger.warning(
                    f"⏳ YouTube บล็อก, retry {attempt}/{MAX_RETRIES} "
                    f"หลัง {delay:.1f}s..."
                )
                time.sleep(delay)
            else:
                result["message"] = f"ดึง Playlists ไม่สำเร็จ: {str(e)}"
                logger.error(f"❌ {result['message']}")
                return result

    if not info:
        result["message"] = "ไม่พบข้อมูล Channel"
        return result

    channel_name = info.get("channel", "") or info.get("uploader", "") or info.get("title", "Unknown")
    result["channel_name"] = channel_name

    entries = info.get("entries", [])
    if not entries:
        result["message"] = f"ไม่พบ Playlists ใน Channel: {channel_name}"
        return result

    playlists = []
    for entry in entries:
        if not entry:
            continue

        playlist_id = entry.get("id", "")
        if not playlist_id:
            continue

        playlists.append({
            "playlist_id": playlist_id,
            "title": entry.get("title", "ไม่มีชื่อ"),
            "video_count": entry.get("playlist_count") or entry.get("n_entries") or 0,
            "url": f"https://www.youtube.com/playlist?list={playlist_id}",
        })

    result["status"] = "success"
    result["playlists"] = playlists
    result["message"] = f"พบ {len(playlists)} Playlists จาก {channel_name}"

    logger.info(f"✅ {result['message']}")
    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python playlist_scraper.py <PLAYLIST_URL_OR_CHANNEL_URL>")
        print("  playlist: python playlist_scraper.py 'https://www.youtube.com/playlist?list=PLxxx'")
        print("  channel:  python playlist_scraper.py --playlists 'https://www.youtube.com/@ChannelName'")
        sys.exit(1)

    if sys.argv[1] == "--playlists":
        result = get_channel_playlists(sys.argv[2])
        print(f"\n{'='*60}")
        print(f"📺 Channel: {result['channel_name']}")
        print(f"📊 Status: {result['status']}")
        print(f"💬 {result['message']}")
        for p in result.get("playlists", []):
            print(f"\n  📁 {p['title']} ({p['video_count']} videos)")
            print(f"     ID: {p['playlist_id']}")
    else:
        result = scrape_playlist_videos(sys.argv[1], max_videos=10)
        print(f"\n{'='*60}")
        print(f"📁 Playlist: {result['playlist_name']}")
        print(f"📊 Status: {result['status']}")
        print(f"💬 {result['message']}")
        for v in result.get("videos", []):
            print(f"\n  🎬 {v['title']}")
            print(f"     ID: {v['video_id']} | ⏱️ {v['duration_text']}")
