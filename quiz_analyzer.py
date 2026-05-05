"""
quiz_analyzer.py — ส่ง Transcript เต็มไปให้ OpenClaw สร้าง Quiz 7-10 ข้อ

ดัดแปลงจาก highlight_analyzer.py โดยเปลี่ยน prompt
"""

import json
import logging
import re
import httpx
from typing import Optional

from config import OPENCLAW_API_URL, OPENCLAW_AGENT_ID, OPENCLAW_API_KEY

logger = logging.getLogger(__name__)

# Timeout สำหรับ OpenClaw API
OPENCLAW_TIMEOUT = 300.0
MAX_TRANSCRIPT_CHARS = 12000  # ให้ยาวขึ้นหน่อยเพราะต้องครอบคลุมทั้งคลิป

def _build_transcript_text(transcript_data: list[dict]) -> str:
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

def _build_quiz_prompt(transcript_text: str) -> str:
    return f"""วิเคราะห์ transcript ของวิดีโอ YouTube ข้างล่างนี้ แล้วสร้างแบบทดสอบความเข้าใจ (Quiz) จำนวน 7-10 ข้อ จากเนื้อหาทั้งหมดในคลิป

พิจารณาจาก:
- ใจความสำคัญของคลิป
- ข้อมูลสำคัญที่เป็นแก่นของเรื่อง
- ไม่ถามเรื่องจุกจิกที่ไม่มีประโยชน์ เอาเนื้อหาสำคัญที่คนฟังสรุปได้

ตอบเป็น **JSON array เท่านั้น** ตามรูปแบบนี้:
```json
[
  {{
    "question": "คำถามเกี่ยวกับเนื้อหา",
    "options": ["ตัวเลือก 1", "ตัวเลือก 2", "ตัวเลือก 3", "ตัวเลือก 4"],
    "answer": "ตัวเลือก 2"
  }},
  ... (อีก 6-9 ข้อ)
]
```

กฎ:
- สร้าง Quiz อย่างน้อย 7 ข้อ ไม่เกิน 10 ข้อ
- ต้องเป็นคำถามแบบมี 4 ตัวเลือก (options) ทุกข้อ
- ระบุคำตอบที่ถูกต้องให้ตรงกับ 1 ในตัวเลือกอย่างชัดเจน (answer)
- คำถาม ตัวเลือก และคำตอบ ต้องเป็นภาษาไทยเท่านั้น
- ตอบกลับมาแค่ JSON Array เท่านั้น ห้ามพิมพ์คำอธิบายอื่นผสมมาเด็ดขาด

=== TRANSCRIPT ===
{transcript_text}
=== END TRANSCRIPT ==="""

def _parse_quiz_response(response_text: str) -> list[dict]:
    # ลองตรง parse JSON ก่อน
    try:
        data = json.loads(response_text.strip())
        if isinstance(data, list):
            return _validate_quiz(data)
    except json.JSONDecodeError:
        pass

    # ลองหา JSON array ใน code block
    code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response_text, re.DOTALL)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1).strip())
            if isinstance(data, list):
                return _validate_quiz(data)
        except json.JSONDecodeError:
            pass

    # ลองหา JSON array โดยตรง ([ ... ])
    array_match = re.search(r'\[[\s\S]*?\](?=\s*$|\s*[^,\]\}])', response_text)
    if array_match:
        try:
            data = json.loads(array_match.group(0))
            if isinstance(data, list):
                return _validate_quiz(data)
        except json.JSONDecodeError:
            pass

    logger.error(f"❌ ไม่สามารถ parse quiz จาก response: {response_text[:200]}...")
    return []

def _validate_quiz(quiz_data: list[dict]) -> list[dict]:
    valid = []
    for q in quiz_data:
        if "question" in q and "options" in q and "answer" in q:
            if isinstance(q["options"], list) and len(q["options"]) == 4:
                valid.append({
                    "question": str(q["question"]),
                    "options": [str(o) for o in q["options"]],
                    "answer": str(q["answer"])
                })
    return valid

def analyze_full_clip_quiz(
    transcript_data: list[dict],
    api_url: Optional[str] = None,
    agent_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    ส่ง transcript ให้ OpenClaw วิเคราะห์ Quiz

    Returns:
        รายการ dict แต่ละตัวมี keys: question, options, answer
    """
    url = api_url or OPENCLAW_API_URL
    agent = agent_id or OPENCLAW_AGENT_ID
    key = api_key or OPENCLAW_API_KEY

    if not transcript_data:
        logger.warning("⚠️ ไม่มี transcript สำหรับสร้าง Quiz")
        return []

    transcript_text = _build_transcript_text(transcript_data)
    logger.info(f"📝 สร้าง transcript text: {len(transcript_text)} ตัวอักษร สำหรับ Quiz")

    prompt = _build_quiz_prompt(transcript_text)

    chat_url = f"{url.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    payload = {
        "model": f"openclaw:{agent}",
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.3,
    }

    logger.info(f"🚀 ส่ง request ไป OpenClaw เพื่อสร้าง Quiz: {chat_url} (agent: {agent})")

    try:
        with httpx.Client(timeout=OPENCLAW_TIMEOUT) as client:
            response = client.post(chat_url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()

            ai_text = ""
            if isinstance(result, dict):
                choices = result.get("choices", [])
                if choices and isinstance(choices, list):
                    message = choices[0].get("message", {})
                    ai_text = message.get("content", "")

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
                logger.error(f"❌ OpenClaw ไม่ได้ตอบข้อความ: {json.dumps(result, ensure_ascii=False)[:300]}")
                return []

            quiz_items = _parse_quiz_response(ai_text)
            logger.info(f"🎯 สร้างสําเร็จ {len(quiz_items)} ข้อ")
            return quiz_items

    except httpx.TimeoutException:
        logger.error(f"❌ OpenClaw timeout ({OPENCLAW_TIMEOUT}s) - วิดีโออาจยาวเกินไป")
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ OpenClaw HTTP error {e.response.status_code}: {e.response.text[:200]}")
        return []
    except Exception as e:
        logger.error(f"❌ OpenClaw error: {type(e).__name__}: {e}")
        return []
