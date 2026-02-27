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
OPENCLAW_API_URL: str = os.getenv("OPENCLAW_API_URL", "http://localhost:3000")
OPENCLAW_AGENT_ID: str = os.getenv("OPENCLAW_AGENT_ID", "unjai")
OPENCLAW_API_KEY: str = os.getenv("OPENCLAW_API_KEY", "")
