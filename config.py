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
# Quiz LLM (2026-10-28) — ควิซเต็มคลิปเรียก vLLM ของเราเองตรง ๆ ไม่ผ่าน OpenClaw gateway
#   เจ้าของตัดสินใจ 28 ต.ค. ให้ย้ายก่อนปิด gateway · ค่าว่างใน .env = ใช้ค่าเริ่มต้น
#   QUIZ_LLM_BACKEND=openclaw ⇒ กลับไปทางเดิม (สวิตช์ถอยกลับ ใช้ได้ตราบที่ gateway ยังอยู่)
# ──────────────────────────────────────────────
def _env(name: str, default: str) -> str:
    value = os.getenv(name, "")
    return value.strip() if value and value.strip() else default


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(_env(name, str(default)))
    except ValueError:
        value = default
    return max(lo, min(hi, value))


QUIZ_LLM_BACKEND: str = _env("QUIZ_LLM_BACKEND", "vllm").lower()
QUIZ_LLM_BASE_URL: str = _env("QUIZ_LLM_BASE_URL", "http://10.10.10.1:8010/v1")
QUIZ_LLM_MODEL: str = _env("QUIZ_LLM_MODEL", "aunjai-120b")
QUIZ_LLM_API_KEY: str = os.getenv("QUIZ_LLM_API_KEY", "")
# "none" = ไม่ส่ง reasoning_effort (ให้ vLLM ใช้ค่าของโมเดลเอง)
QUIZ_LLM_REASONING_EFFORT: str = _env("QUIZ_LLM_REASONING_EFFORT", "low").lower()
QUIZ_LLM_MAX_TOKENS: int = _int_env("QUIZ_LLM_MAX_TOKENS", 6000, 1000, 16000)
# vLLM ตัวเดียวใช้ร่วมกับ prod middleware ⇒ เพดานแข็ง 2 สายพร้อมกัน
QUIZ_LLM_MAX_CONCURRENCY: int = _int_env("QUIZ_LLM_MAX_CONCURRENCY", 1, 1, 2)

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

# ──────────────────────────────────────────────
# Spiritual SOS Configuration
# ──────────────────────────────────────────────
LINE_ADMIN_GROUP_ID: str = os.getenv("LINE_ADMIN_GROUP_ID", "")
SPIRITUAL_SOS_ENABLED: str = os.getenv("SPIRITUAL_SOS_ENABLED", "true")
SPIRITUAL_C3_SLA_MINUTES: str = os.getenv("SPIRITUAL_C3_SLA_MINUTES", "5")


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
