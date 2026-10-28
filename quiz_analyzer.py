"""
quiz_analyzer.py — ส่ง Transcript เต็มไปให้ LLM สร้าง Quiz 7-10 ข้อ

ดัดแปลงจาก highlight_analyzer.py โดยเปลี่ยน prompt

ปลายทาง (2026-10-28): ค่าเริ่มต้นเรียก vLLM ของเรา (QUIZ_LLM_BASE_URL) ตรง ๆ
    เดิมยิง OpenClaw gateway เป็น "openclaw:unjai" — agent unjai ไม่มีใน agents.list
    จึงวิ่งด้วยค่า defaults = openai/gpt-5-mini thinking:low + system prompt ผู้ช่วยทั่วไป
    ของ OpenClaw (~15k โทเคน เครื่องมือ/heartbeat/ความจำผู้ใช้) ซึ่งไม่มีอะไรเกี่ยวกับควิซ
    ⇒ ที่ต้องพกมามีแค่ prompt ควิซเดิม (อยู่ใน user message ครบแล้ว) + effort low
    QUIZ_LLM_BACKEND=openclaw ⇒ ทางเดิมทุกอย่าง (สวิตช์ถอยกลับ)

★ กับดัก reasoning ของ gpt-oss: ถ้างบ max_tokens หมดระหว่างคิด vLLM คืน
    content=null + finish_reason="length" ซึ่งไม่ใช่ HTTP error
    ⇒ ตรวจเนื้อความว่างเอง แล้วลองใหม่หนึ่งครั้งด้วยงบสองเท่า · ห้ามเอา reasoning มาแทน content
"""

import json
import logging
import re
import threading
import httpx
from typing import Optional

from config import (
    OPENCLAW_API_URL, OPENCLAW_AGENT_ID, OPENCLAW_API_KEY,
    QUIZ_LLM_BACKEND, QUIZ_LLM_BASE_URL, QUIZ_LLM_MODEL, QUIZ_LLM_API_KEY,
    QUIZ_LLM_REASONING_EFFORT, QUIZ_LLM_MAX_TOKENS, QUIZ_LLM_MAX_CONCURRENCY,
)

logger = logging.getLogger(__name__)

# Timeout สำหรับ OpenClaw API
OPENCLAW_TIMEOUT = 300.0
# Timeout ต่อหนึ่งคำขอไป vLLM และเวลารอคิวสูงสุดก่อนยอมแพ้ (ไม่ยิงเกินเพดานพร้อมกัน)
QUIZ_LLM_TIMEOUT = 300.0
QUIZ_LLM_QUEUE_WAIT = 900.0
QUIZ_LLM_TOKEN_CEILING = 16000

# vLLM ตัวเดียวใช้ร่วมกับ prod ⇒ ทุกทางที่สร้างควิซ (cron / POST /api/quiz) ผ่านประตูเดียวนี้
_vllm_gate = threading.BoundedSemaphore(QUIZ_LLM_MAX_CONCURRENCY)

QUIZ_SYSTEM_PROMPT = (
    "คุณสร้างแบบทดสอบความเข้าใจภาษาไทยจาก transcript วิดีโอ "
    "ตอบเป็น JSON array ตามรูปแบบที่ผู้ใช้กำหนดเท่านั้น ไม่มีคำอธิบายหรือข้อความอื่นนอก JSON "
    'ค่า "answer" ต้องคัดลอกมาจากหนึ่งในสี่ "options" ทุกตัวอักษร'
)

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

def _unwrap_quiz_list(data) -> Optional[list]:
    """รับทั้ง [..] และ {"quiz": [..]} / {"questions": [..]} — โมเดลบางตัวห่อ array ไว้ใน object"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("quiz", "questions", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return None

def _parse_quiz_response(response_text: str) -> list[dict]:
    # ลองตรง parse JSON ก่อน
    try:
        data = _unwrap_quiz_list(json.loads(response_text.strip()))
        if data is not None:
            return _validate_quiz(data)
    except json.JSONDecodeError:
        pass

    # ลองหา JSON array ใน code block
    code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response_text, re.DOTALL)
    if code_block_match:
        try:
            data = _unwrap_quiz_list(json.loads(code_block_match.group(1).strip()))
            if data is not None:
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

def _match_answer(answer: str, options: list[str]) -> Optional[str]:
    """คืนตัวเลือกที่ตรงกับ answer (เทียบหลังตัดช่องว่างหัวท้าย) หรือ None
    ปลายทางตรวจคำตอบด้วยการเทียบข้อความกับตัวเลือก ⇒ answer ที่ไม่ตรงตัวเลือกใดเลย
    คือข้อที่ไม่มีใครตอบถูกได้ ต้องทิ้ง · จงใจไม่แปลง "B"/"2" เป็นตัวเลือก เพราะเดาผิดได้
    เมื่อตัวเลือกเองเป็นตัวเลข (ข้อมูลเดิมจาก gpt-5-mini ตรงตัวเลือก 304/304 ข้อ)"""
    a = answer.strip()
    return a if a in options else None

def _validate_quiz(quiz_data: list[dict]) -> list[dict]:
    valid = []
    dropped = 0
    for q in quiz_data:
        if isinstance(q, dict) and "question" in q and "options" in q and "answer" in q:
            if isinstance(q["options"], list) and len(q["options"]) == 4:
                options = [str(o).strip() for o in q["options"]]
                answer = _match_answer(str(q["answer"]), options)
                if answer is None:
                    dropped += 1
                    continue
                valid.append({
                    "question": str(q["question"]).strip(),
                    "options": options,
                    "answer": answer
                })
    if dropped:
        logger.warning(f"⚠️ ทิ้ง {dropped} ข้อที่ answer ไม่ตรงกับตัวเลือกใดเลย")
    return valid

def analyze_full_clip_quiz(
    transcript_data: list[dict],
    api_url: Optional[str] = None,
    agent_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    ส่ง transcript ให้ LLM วิเคราะห์ Quiz (vLLM ตรง หรือ OpenClaw ตาม QUIZ_LLM_BACKEND)
    api_url / agent_id / api_key ใช้กับทาง OpenClaw เท่านั้น

    Returns:
        รายการ dict แต่ละตัวมี keys: question, options, answer
    """
    if not transcript_data:
        logger.warning("⚠️ ไม่มี transcript สำหรับสร้าง Quiz")
        return []

    transcript_text = _build_transcript_text(transcript_data)
    logger.info(f"📝 สร้าง transcript text: {len(transcript_text)} ตัวอักษร สำหรับ Quiz")

    prompt = _build_quiz_prompt(transcript_text)

    if QUIZ_LLM_BACKEND == "openclaw":
        return _analyze_via_openclaw(prompt, api_url, agent_id, api_key)
    if QUIZ_LLM_BACKEND != "vllm":
        logger.warning(f"⚠️ QUIZ_LLM_BACKEND={QUIZ_LLM_BACKEND!r} ไม่รู้จัก — ใช้ vllm")
    return _analyze_via_vllm(prompt)


def _analyze_via_vllm(prompt: str) -> list[dict]:
    """เรียก vLLM (OpenAI-compatible) ตรง · ผ่านประตู _vllm_gate เสมอ"""
    chat_url = f"{QUIZ_LLM_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if QUIZ_LLM_API_KEY:
        headers["Authorization"] = f"Bearer {QUIZ_LLM_API_KEY}"
    effort = None if QUIZ_LLM_REASONING_EFFORT in ("none", "off") else QUIZ_LLM_REASONING_EFFORT
    budget = QUIZ_LLM_MAX_TOKENS

    if not _vllm_gate.acquire(timeout=QUIZ_LLM_QUEUE_WAIT):
        logger.error(f"❌ รอคิว vLLM เกิน {QUIZ_LLM_QUEUE_WAIT:.0f}s (เพดาน {QUIZ_LLM_MAX_CONCURRENCY} สาย) — ข้ามรอบนี้")
        return []
    try:
        with httpx.Client(timeout=QUIZ_LLM_TIMEOUT) as client:
            for attempt in (1, 2):
                payload = {
                    "model": QUIZ_LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": budget,
                }
                if effort:
                    payload["reasoning_effort"] = effort

                logger.info(f"🚀 ส่ง request ไป vLLM เพื่อสร้าง Quiz: {chat_url} "
                            f"(model={QUIZ_LLM_MODEL} effort={effort} max_tokens={budget})")
                response = client.post(chat_url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()

                choices = result.get("choices") if isinstance(result, dict) else None
                choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                message = choice.get("message") or {}
                content = message.get("content")
                if not isinstance(content, str):
                    content = ""
                finish = choice.get("finish_reason")

                # งบหมด (ระหว่างคิด หรือกลาง JSON) ⇒ ลองใหม่ครั้งเดียวด้วยงบสองเท่า
                if finish == "length" and attempt == 1 and budget < QUIZ_LLM_TOKEN_CEILING:
                    thinking = message.get("reasoning_content") or message.get("reasoning") or ""
                    logger.warning(f"⚠️ vLLM ใช้งบโทเคนหมด (finish=length max_tokens={budget} "
                                   f"content={len(content)} ตัวอักษร reasoning={len(thinking)} ตัวอักษร) "
                                   f"— ลองใหม่ด้วยงบ {min(budget * 2, QUIZ_LLM_TOKEN_CEILING)}")
                    budget = min(budget * 2, QUIZ_LLM_TOKEN_CEILING)
                    continue

                if not content.strip():
                    # ไม่เอา reasoning มาแทน — มันคือความคิด ไม่ใช่ควิซ
                    logger.error(f"❌ vLLM ตอบว่าง (finish={finish} max_tokens={budget})")
                    return []

                quiz_items = _parse_quiz_response(content)
                logger.info(f"🎯 สร้างสําเร็จ {len(quiz_items)} ข้อ (finish={finish})")
                return quiz_items
        return []

    except httpx.TimeoutException:
        logger.error(f"❌ vLLM timeout ({QUIZ_LLM_TIMEOUT}s)")
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ vLLM HTTP error {e.response.status_code}: {e.response.text[:200]}")
        return []
    except Exception as e:
        logger.error(f"❌ vLLM error: {type(e).__name__}: {e}")
        return []
    finally:
        _vllm_gate.release()


def _analyze_via_openclaw(prompt: str, api_url: Optional[str], agent_id: Optional[str],
                          api_key: Optional[str]) -> list[dict]:
    """ทางเดิม — OpenClaw gateway "openclaw:<agent>" (สวิตช์ QUIZ_LLM_BACKEND=openclaw)"""
    url = api_url or OPENCLAW_API_URL
    agent = agent_id or OPENCLAW_AGENT_ID
    key = api_key or OPENCLAW_API_KEY

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
