"""
config.py — การตั้งค่าระบบทั้งหมดสำหรับ Module 1: Knowledge Base Engine
โหลดค่าจากไฟล์ .env แล้วเก็บเป็นค่าคงที่ (Constants)
"""

import os
from dotenv import load_dotenv

# โหลด Environment Variables จากไฟล์ .env
load_dotenv()

# ──────────────────────────────────────────────
# Pinecone Configuration
# ──────────────────────────────────────────────
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "aunjai-knowledge")

# ──────────────────────────────────────────────
# Embedding Model Configuration
# ──────────────────────────────────────────────
# ใช้โมเดล multilingual ที่รองรับภาษาไทย
EMBEDDING_MODEL_NAME: str = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSION: int = 384  # มิติของ Vector จากโมเดลนี้

# ──────────────────────────────────────────────
# Chunking Configuration
# ──────────────────────────────────────────────
CHUNK_SIZE: int = 400          # จำนวนตัวอักษรเป้าหมายต่อ Chunk (~300-500)
CHUNK_OVERLAP_RATIO: float = 0.12  # สัดส่วนการคาบเกี่ยว (~10-15%)

# ──────────────────────────────────────────────
# YouTube URL Template
# ──────────────────────────────────────────────
YOUTUBE_URL_TEMPLATE: str = "https://www.youtube.com/watch?v={video_id}"

# ──────────────────────────────────────────────
# OpenClaw Configuration
# ──────────────────────────────────────────────
OPENCLAW_API_URL: str = os.getenv("OPENCLAW_API_URL", "https://openclaw.appreview.cloud")
OPENCLAW_AGENT_ID: str = os.getenv("OPENCLAW_AGENT_ID", "unjai")
OPENCLAW_API_KEY: str = os.getenv("OPENCLAW_API_KEY", "")

# ──────────────────────────────────────────────
# LINE Messaging API Configuration
# ──────────────────────────────────────────────
LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

# ──────────────────────────────────────────────
# Proxy Configuration (แก้ปัญหา YouTube บล็อก IP)
# ──────────────────────────────────────────────
PROXY_HTTP: str = os.getenv("PROXY_HTTP", "")
PROXY_HTTPS: str = os.getenv("PROXY_HTTPS", "")
YOUTUBE_COOKIES_FILE: str = os.getenv("YOUTUBE_COOKIES_FILE", "cookies.txt")

# ──────────────────────────────────────────────
# Google Drive Configuration
# ──────────────────────────────────────────────
GOOGLE_DRIVE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_DRIVE_CREDENTIALS_FILE", "gdrive_credentials.json")
GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "16xSVMLqNbo-aVqzGQ0SkiIx4OBaqr-xy")


def get_yt_proxy_config():
    """
    สร้าง GenericProxyConfig สำหรับ youtube-transcript-api
    Return None ถ้าไม่ได้ตั้งค่า proxy
    """
    if not PROXY_HTTP and not PROXY_HTTPS:
        return None
    from youtube_transcript_api.proxies import GenericProxyConfig
    return GenericProxyConfig(
        http_url=PROXY_HTTP or None,
        https_url=PROXY_HTTPS or None,
    )


def get_ytdlp_proxy() -> str:
    """
    Return proxy URL สำหรับ yt-dlp (ใช้ตัวเดียว)
    Return "" ถ้าไม่ได้ตั้งค่า proxy
    """
    return PROXY_HTTPS or PROXY_HTTP or ""
