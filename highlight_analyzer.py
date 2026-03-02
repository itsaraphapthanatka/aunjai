"""
highlight_analyzer.py — ส่ง Transcript ไปให้ OpenClaw วิเคราะห์ Highlight

รับ transcript segments แล้วสร้าง prompt ให้ AI วิเคราะห์หา
ช่วงเวลาที่น่าสนใจ (highlight shots) พร้อมเหตุผลและคะแนน
"""

import json
import logging
import re
import httpx
from typing import Optional

from config import OPENCLAW_API_URL, OPENCLAW_AGENT_ID, OPENCLAW_API_KEY

logger = logging.getLogger(__name__)

# Timeout สำหรับ OpenClaw API (วิเคราะห์อาจใช้เวลานาน)
OPENCLAW_TIMEOUT = 300.0

# จำกัดความยาว transcript ที่ส่งไป AI (ตัวอักษร)
MAX_TRANSCRIPT_CHARS = 8000


def _build_transcript_text(transcript_data: list[dict]) -> str:
    """
    แปลง transcript segments เป็นข้อความที่อ่านง่าย พร้อม timestamp

    Example output:
        [0:00] สวัสดีครับ วันนี้เราจะมาพูดถึง...
        [0:04] เรื่องที่สำคัญมากๆ คือ...
    """
    lines = []
    total_chars = 0
    for seg in transcript_data:
        start = seg.get("start", 0)
        minutes = int(start // 60)
        seconds = int(start % 60)
        text = seg.get("text", "").strip()
        if text:
            line = f"[{minutes}:{seconds:02d}] {text}"
            if total_chars + len(line) > MAX_TRANSCRIPT_CHARS:
                lines.append(f"[...ตัดทอน — transcript ยาวเกิน {MAX_TRANSCRIPT_CHARS} ตัวอักษร...]")
                break
            lines.append(line)
            total_chars += len(line)
    return "\n".join(lines)


def _build_prompt(transcript_text: str) -> str:
    """สร้าง prompt สำหรับให้ OpenClaw วิเคราะห์ highlight"""
    return f"""วิเคราะห์ transcript ของวิดีโอ YouTube ข้างล่างนี้ แล้วหาช่วงเวลาที่เป็น highlight หรือ shot ที่น่าสนใจที่สุด

พิจารณาจาก:
- เนื้อหาสำคัญ (key points, insights)
- ช่วงที่มีอารมณ์ (ตลก ซึ้ง ดราม่า)
- ข้อมูลที่เป็นประโยชน์ (tips, how-to)
- จุดพีคของเรื่อง (climax, turning point)
- ช่วงที่มี engagement สูง (hook, call-to-action)

ตอบเป็น **JSON array เท่านั้น** (ไม่ต้องมีข้อความอื่น) ตามรูปแบบนี้:
```json
[
  {{
    "start_time": 42.5,
    "end_time": 68.0,
    "reason": "อธิบายสั้นๆ ว่าทำไมช่วงนี้เป็น highlight",
    "score": 0.95,
    "quiz": [
      {{
        "question": "คำถามเกี่ยวกับเนื้อหาในช่วงนี้",
        "options": ["ตัวเลือกที่ 1", "ตัวเลือกที่ 2", "ตัวเลือกที่ 3", "ตัวเลือกที่ 4"],
        "answer": "ตัวเลือกที่ 2"
      }},
      {{
        "question": "คำถามที่ 2 เกี่ยวกับเนื้อหาในช่วงนี้",
        "options": ["ตัวเลือกที่ 1", "ตัวเลือกที่ 2", "ตัวเลือกที่ 3", "ตัวเลือกที่ 4"],
        "answer": "ตัวเลือกที่ 3"
      }}
    ]
  }}
]
```

กฎ:
- เลือก 3-7 highlights (ไม่ต้องมากเกิน)
- score อยู่ระหว่าง 0.0-1.0 (1.0 = น่าสนใจที่สุด)
- เรียงตาม start_time จากน้อยไปมาก
- start_time และ end_time เป็นวินาที
- แต่ละ highlight ต้องยาวอย่างน้อย 30 วินาทีและไม่เกิน 120 วินาที
- สำคัญมาก: start_time และ end_time ต้องอยู่ตรงจุดเริ่มต้น/จบประโยค ห้ามตัดกลางประโยคเด็ดขาด
- quiz: สร้าง 2 คำถามต่อ highlight ในรูปแบบ **ตัวเลือก 4 ข้อ** (options) และระบุคำตอบที่ถูกต้อง (answer) คำถามและตัวเลือกเป็นภาษาไทย

=== TRANSCRIPT ===
{transcript_text}
=== END TRANSCRIPT ==="""


def _parse_highlights_response(response_text: str) -> list[dict]:
    """
    Parse response จาก OpenClaw — ดึง JSON array ออกจากข้อความ

    รองรับทั้งกรณีที่ตอบเป็น JSON ล้วน และกรณีที่มีข้อความห่อ
    """
    # ลองตรง parse JSON ก่อน
    try:
        data = json.loads(response_text.strip())
        if isinstance(data, list):
            return _validate_highlights(data)
    except json.JSONDecodeError:
        pass

    # ลองหา JSON array ใน code block
    code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response_text, re.DOTALL)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1).strip())
            if isinstance(data, list):
                return _validate_highlights(data)
        except json.JSONDecodeError:
            pass

    # ลองหา JSON array โดยตรง ([ ... ])
    array_match = re.search(r'\[[\s\S]*?\](?=\s*$|\s*[^,\]\}])', response_text)
    if array_match:
        try:
            data = json.loads(array_match.group(0))
            if isinstance(data, list):
                return _validate_highlights(data)
        except json.JSONDecodeError:
            pass

    logger.error(f"❌ ไม่สามารถ parse highlights จาก response: {response_text[:200]}...")
    return []


def _validate_highlights(highlights: list[dict]) -> list[dict]:
    """ตรวจสอบและ normalize ข้อมูล highlights"""
    valid = []
    for h in highlights:
        try:
            entry = {
                "start_time": float(h.get("start_time", 0)),
                "end_time": float(h.get("end_time", 0)),
                "reason": str(h.get("reason", "N/A")),
                "score": min(1.0, max(0.0, float(h.get("score", 0.5)))),
            }
            # เก็บ quiz ถ้ามี
            if h.get("quiz") and isinstance(h["quiz"], list):
                entry["quiz"] = h["quiz"]
            # ตรวจสอบว่า end > start
            if entry["end_time"] > entry["start_time"]:
                valid.append(entry)
            else:
                logger.warning(f"⚠️ ข้าม highlight — end_time <= start_time: {entry}")
        except (ValueError, TypeError) as e:
            logger.warning(f"⚠️ ข้าม highlight ที่ parse ไม่ได้: {h} — {e}")

    # เรียงตาม score (สูงสุดก่อน)
    valid.sort(key=lambda x: x["score"], reverse=True)
    return valid


def analyze_highlights(
    transcript_data: list[dict],
    api_url: Optional[str] = None,
    agent_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    ส่ง transcript ให้ OpenClaw วิเคราะห์ highlight

    Args:
        transcript_data: รายการ dict จาก extractor (ต้องมี text, start, duration, video_id)
        api_url: OpenClaw API URL (ถ้าไม่ส่งจะใช้จาก config)
        agent_id: OpenClaw Agent ID (ถ้าไม่ส่งจะใช้จาก config)
        api_key: OpenClaw API Key (ถ้าไม่ส่งจะใช้จาก config)

    Returns:
        รายการ dict แต่ละตัวมี keys: start_time, end_time, reason, score
    """
    url = api_url or OPENCLAW_API_URL
    agent = agent_id or OPENCLAW_AGENT_ID
    key = api_key or OPENCLAW_API_KEY

    if not transcript_data:
        logger.warning("⚠️ ไม่มี transcript สำหรับวิเคราะห์")
        return []

    # สร้าง transcript text พร้อม timestamps
    transcript_text = _build_transcript_text(transcript_data)
    logger.info(f"📝 สร้าง transcript text: {len(transcript_text)} ตัวอักษร จาก {len(transcript_data)} segments")

    # สร้าง prompt
    prompt = _build_prompt(transcript_text)

    # ส่งไป OpenClaw API (OpenAI-compatible endpoint)
    chat_url = f"{url.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    # OpenClaw ใช้ OpenAI-compatible format
    # model = "openclaw:<agentId>" เพื่อระบุ agent
    payload = {
        "model": f"openclaw:{agent}",
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.3,  # ต่ำ = ตอบตรงประเด็นมากขึ้น
    }

    logger.info(f"🚀 ส่ง request ไป OpenClaw: {chat_url} (agent: {agent})")

    try:
        with httpx.Client(timeout=OPENCLAW_TIMEOUT) as client:
            response = client.post(chat_url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()

            # OpenAI-compatible response format:
            # { "choices": [{ "message": { "content": "..." } }] }
            ai_text = ""
            if isinstance(result, dict):
                choices = result.get("choices", [])
                if choices and isinstance(choices, list):
                    message = choices[0].get("message", {})
                    ai_text = message.get("content", "")

                # Fallback: ลองหา content แบบอื่น
                if not ai_text:
                    ai_text = (
                        result.get("response", "")
                        or result.get("message", "")
                        or result.get("content", "")
                        or result.get("text", "")
                    )
            elif isinstance(result, str):
                ai_text = result

            if not ai_text:
                logger.error(f"❌ OpenClaw ไม่ได้ตอบข้อความ — response: {json.dumps(result, ensure_ascii=False)[:300]}")
                return []

            logger.info(f"✅ OpenClaw ตอบกลับ: {len(ai_text)} ตัวอักษร")

            # Parse highlights จาก response
            highlights = _parse_highlights_response(ai_text)
            logger.info(f"🎯 วิเคราะห์ได้ {len(highlights)} highlights")
            return highlights

    except httpx.TimeoutException:
        logger.error(f"❌ OpenClaw timeout ({OPENCLAW_TIMEOUT}s) — วิดีโออาจยาวเกินไป")
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ OpenClaw HTTP error {e.response.status_code}: {e.response.text[:200]}")
        return []
    except Exception as e:
        logger.error(f"❌ OpenClaw error: {type(e).__name__}: {e}")
        return []


# ──────────────────────────────────────────────
# ทดสอบแบบ standalone
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ข้อมูลตัวอย่าง
    sample_transcript = [
        {"text": "สวัสดีครับ วันนี้เราจะมาพูดถึงเรื่องสำคัญ", "start": 0.0, "duration": 4.0, "video_id": "test"},
        {"text": "เรื่องแรกคือ วิธีจัดการกับความเครียด", "start": 4.0, "duration": 3.5, "video_id": "test"},
        {"text": "สิ่งที่สำคัญที่สุดคือ ต้องเข้าใจตัวเอง", "start": 7.5, "duration": 4.0, "video_id": "test"},
        {"text": "เทคนิคที่ผมแนะนำคือการหายใจลึกๆ", "start": 11.5, "duration": 3.0, "video_id": "test"},
        {"text": "ลองทำตามแบบนี้ หายใจเข้า นับ 1 2 3 4", "start": 14.5, "duration": 5.0, "video_id": "test"},
    ]

    print("📤 ส่ง transcript ไป OpenClaw...")
    highlights = analyze_highlights(sample_transcript)

    print(f"\n{'='*60}")
    print(f"🎯 พบ {len(highlights)} highlights:")
    for i, h in enumerate(highlights, 1):
        print(f"\n--- Highlight {i} ---")
        print(f"  ⏱️  {h['start_time']}s - {h['end_time']}s")
        print(f"  📊 Score: {h['score']}")
        print(f"  💡 เหตุผล: {h['reason']}")
