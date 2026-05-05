import logging
import requests
import threading
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    FlexMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from config import (
    LINE_CHANNEL_SECRET, 
    LINE_CHANNEL_ACCESS_TOKEN,
    OPENCLAW_API_URL,
    OPENCLAW_AGENT_ID,
    OPENCLAW_API_KEY,
    LINE_ADMIN_GROUP_ID,
    SPIRITUAL_SOS_ENABLED,
    SPIRITUAL_C3_SLA_MINUTES
)

from db_handler import DatabaseHandler

# Spiritual SOS imports (lazy to avoid startup failures if files missing)
_unified_classifier = None
_spiritual_scripts = None
_alert_card_spiritual = None
_alert_card_physical = None

def _load_sos_modules():
    """Lazy-load SOS modules and templates."""
    global _unified_classifier, _spiritual_scripts, _alert_card_spiritual, _alert_card_physical
    import json
    import os
    if _unified_classifier is None:
        try:
            from unified_classifier import classify
            _unified_classifier = classify
        except Exception as e:
            logger.error(f"Failed to load unified_classifier: {e}")
            _unified_classifier = False
    if _spiritual_scripts is None:
        try:
            with open(os.path.join(os.path.dirname(__file__), "spiritual_scripts.json"), "r", encoding="utf-8") as f:
                _spiritual_scripts = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load spiritual_scripts.json: {e}")
            _spiritual_scripts = {}
    if _alert_card_spiritual is None:
        try:
            with open(os.path.join(os.path.dirname(__file__), "alert_card_spiritual.json"), "r", encoding="utf-8") as f:
                _alert_card_spiritual = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load alert_card_spiritual.json: {e}")
            _alert_card_spiritual = {}
    if _alert_card_physical is None:
        try:
            with open(os.path.join(os.path.dirname(__file__), "alert_card_physical.json"), "r", encoding="utf-8") as f:
                _alert_card_physical = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load alert_card_physical.json: {e}")
            _alert_card_physical = {}
    return _unified_classifier, _spiritual_scripts, _alert_card_spiritual, _alert_card_physical

logger = logging.getLogger(__name__)

# Initialize LINE API configuration
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
db = DatabaseHandler()

def call_openclaw(messages: list, line_user_id: str) -> str:
    """
    เรียกใช้งาน OpenClaw API โดยส่งประวัติการสนทนา (OpenAI format)
    """
    chat_url = f"{OPENCLAW_API_URL.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_API_KEY:
        headers["Authorization"] = f"Bearer {OPENCLAW_API_KEY}"
        
    payload = {
        "model": f"openclaw:{OPENCLAW_AGENT_ID}",
        "messages": messages,
        "user_id": line_user_id
    }
    
    logger.info(f"🚀 กำลังส่งข้อความของ {line_user_id} ไปยัง OpenClaw (context: {len(messages)} messages)")
    
    try:
        # ปรับเพิ่ม timeout เป็น 120 วินาที (เนื่องจากทำงานใน background แล้ว)
        response = requests.post(chat_url, json=payload, headers=headers, timeout=120.0)
        response.raise_for_status()
        result = response.json()
        
        ai_text = ""
        if isinstance(result, dict) and "choices" in result:
            choices = result.get("choices", [])
            if choices and isinstance(choices, list):
                ai_text = choices[0].get("message", {}).get("content", "")
        
        if not ai_text:
            ai_text = "ขออภัยค่ะ อุ่นใจไม่สามารถประมวลผลคำตอบได้ในขณะนี้"
            logger.error(f"❌ OpenClaw ไม่ได้ตอบข้อความ: {result}")
            
        return ai_text
            
    except requests.exceptions.Timeout:
        logger.error("❌ OpenClaw API timeout (120s)")
        return "TIMEOUT_ERROR"
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการเรียก OpenClaw: {e}")
        return "SYSTEM_ERROR"


def _get_header_color(sos_type: str, level: str) -> str:
    """Return header color based on SOS type and level."""
    if sos_type == "spiritual":
        return {"C3": "#FF4444", "C2": "#FFCC00", "C1": "#FF8800"}.get(level, "#999999")
    else:
        return {"CRITICAL": "#FF4444", "HIGH": "#FFCC00", "MEDIUM": "#FF8800", "LOW": "#00AA00"}.get(level, "#999999")


def _get_c_stage_label(c_stage: str) -> str:
    """Human-readable C-Stage label."""
    return {"C1": "Engage/Soft", "C2": "Connect", "C3": "Transform", "C4": "Send"}.get(c_stage, c_stage or "")


def _get_spiritual_script(c_stage: str) -> dict:
    """Get the admin guide script for a given C-stage."""
    classify_mod, scripts_data, _, _ = _load_sos_modules()
    scripts = scripts_data.get("scripts", [])
    for script in scripts:
        if script.get("c_stage") == c_stage and script.get("type") == "admin_guide":
            return script
    return {}


def send_sos_alert(line_user_id: str, sos_result: dict, trigger_message: str):
    """Send SOS alert Flex Message to admin group."""
    import json
    from datetime import datetime

    classify_mod, scripts_data, card_spiritual, card_physical = _load_sos_modules()

    if not LINE_ADMIN_GROUP_ID:
        logger.warning("LINE_ADMIN_GROUP_ID not set, skipping SOS alert")
        return

    sos_type = sos_result.get("type", "unknown")
    level = sos_result.get("level", "unknown")
    c_stage = sos_result.get("c_stage")
    response_time = sos_result.get("response_time_minutes", 60)

    # Choose template
    if sos_type == "spiritual":
        template = card_spiritual.get("contents") if card_spiritual else None
    else:
        template = card_physical.get("contents") if card_physical else None

    if not template:
        logger.error(f"No alert card template found for type={sos_type}")
        return

    # Build template variables
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_color = _get_header_color(sos_type, level)
    script = _get_spiritual_script(c_stage) if sos_type == "spiritual" else {}
    script_content = script.get("content", "")

    # Serialize template back to string for replacement, then parse
    template_str = json.dumps(template, ensure_ascii=False)

    # Replace variables
    template_str = template_str.replace("{name}", line_user_id[:20])
    template_str = template_str.replace("{time}", now_str)
    template_str = template_str.replace("{C_STAGE}", c_stage or "")
    template_str = template_str.replace("{LEVEL}", level)
    template_str = template_str.replace("{trigger_message}", trigger_message[:200])
    template_str = template_str.replace("{HEADER_COLOR}", header_color)
    template_str = template_str.replace("{case_id}", f"{sos_type}_{line_user_id}_{int(datetime.now().timestamp())}")
    template_str = template_str.replace("{RESPONSE_TIME}", str(response_time))
    template_str = template_str.replace("{C_STAGE_LABEL}", _get_c_stage_label(c_stage))
    template_str = template_str.replace("{spiritual_script_content_or_link}", script_content[:100] + "..." if len(script_content) > 100 else script_content)
    template_str = template_str.replace("{spiritual_script_link}", "https://nongaunjai.febradio.org/admin/scripts")
    template_str = template_str.replace("{psychology_script_link}", "https://nongaunjai.febradio.org/admin/scripts")

    try:
        flex_contents = json.loads(template_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse alert card JSON after replacement: {e}")
        return

    alt_text = "🙏 Spiritual SOS Alert" if sos_type == "spiritual" else "🆘 Physical SOS Alert"

    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=LINE_ADMIN_GROUP_ID,
                    messages=[FlexMessage(altText=alt_text, contents=flex_contents)]
                )
            )
        logger.info(f"✅ SOS alert sent to admin group for {line_user_id} (type={sos_type}, level={level})")
    except Exception as e:
        logger.error(f"❌ Failed to send SOS alert: {e}")


def process_ai_response_background(line_user_id: str, user_message: str):
    """
    ฟังก์ชันสำหรับทำงานใน Background: จัดการประวัติ, เรียก OpenClaw และส่งคำตอบ
    """
    try:
        # 1. บันทึกข้อความผู้ใช้ลงฐานข้อมูล
        db.add_chat_message(line_user_id, "user", user_message)

        # ── SOS Detection (after saving user message, before fetching history) ──
        if SPIRITUAL_SOS_ENABLED.lower() == "true":
            try:
                classify_mod, _, _, _ = _load_sos_modules()
                if classify_mod and classify_mod is not False:
                    context_messages = db.get_context_window(line_user_id, limit=5)
                    sos_result = classify_mod(user_message, context_messages)

                    if sos_result.get("escalate"):
                        # Log to DB
                        case_id = db.log_sos_case(
                            line_uid=line_user_id,
                            sos_type=sos_result["type"],
                            level=sos_result["level"],
                            c_stage=sos_result.get("c_stage"),
                            trigger_message=user_message,
                            confidence=sos_result["confidence"]
                        )
                        logger.warning(
                            f"🚨 SOS DETECTED: type={sos_result['type']}, level={sos_result['level']}, "
                            f"c_stage={sos_result.get('c_stage')}, case_id={case_id}"
                        )

                        # Send alert to admin (background thread — fire-and-forget)
                        threading.Thread(
                            target=send_sos_alert,
                            args=(line_user_id, sos_result, user_message),
                            daemon=True
                        ).start()

                        # Update spiritual state if spiritual
                        if sos_result["type"] == "spiritual":
                            db.upsert_spiritual_state(line_user_id, sos_result["c_stage"])
            except Exception as e:
                logger.error(f"SOS detection error (non-blocking): {e}")
        # ── End SOS Detection ──

        # 2. ดึงประวัติการสนทนาล่าสุด (10 ข้อความ)
        history = db.get_chat_history(line_user_id, limit=10)

        # 3. ดึงคำตอบจาก OpenClaw โดยใช้ History
        reply_text = call_openclaw(history, line_user_id)
        
        # จัดการข้อความ Error
        final_text = reply_text
        is_error = False
        if reply_text == "TIMEOUT_ERROR":
            final_text = "ขออภัยค่ะ อุ่นใจใช้เวลาคิดนานเกินไป กรุณาลองใหม่อีกครั้งนะคะ"
            is_error = True
        elif reply_text == "SYSTEM_ERROR":
            final_text = "ขออภัยค่ะ ระบบกำลังขัดข้อง อุ่นใจจะรีบกลับมาให้บริการโดยเร็วนะคะ"
            is_error = True
        
        # 4. บันทึกคำตอบของ AI ลงฐานข้อมูล (บันทึกเฉพาะคำตอบปกติ ไม่บันทึก Error ลง History)
        if not is_error:
            db.add_chat_message(line_user_id, "assistant", final_text)
        
        # 5. ส่ง Push Message กลับไปหาผู้ใช้
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=line_user_id,
                    messages=[TextMessage(text=final_text)]
                )
            )
            
        if is_error:
            logger.warning(f"ส่งข้อความแจ้งเตือนข้อผิดพลาดไปยัง {line_user_id} เรียบร้อย")
        else:
            logger.info(f"ส่งคำตอบ AI (Push) ไปยัง {line_user_id} สำเร็จ")
            
    except Exception as e:
        logger.error(f"เกิดข้อผิดพลาดในกระบวนการ Background: {e}")


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    """
    จัดการข้อความที่ได้รับจาก LINE: ส่ง Acknowledge ทันที และประมวลผลต่อใน Background
    """
    line_user_id = event.source.user_id
    user_message = event.message.text
    reply_token = event.reply_token
    
    logger.info(f"ได้รับข้อความ LINE จาก {line_user_id}: {user_message}")
    
    # 1. ส่งข้อความรับทราบ (Acknowledgment) ทันทีด้วย Reply Token
    # เพื่อให้ผู้ใช้รู้ว่าระบบได้รับข้อความแล้ว และไม่ให้ Token หมดอายุ
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="อุ่นใจรับข้อความแล้วค่ะ กำลังคิดหาคำตอบให้อยู่นะคะ รอสักครู่ค่ะ... ⏳")]
                )
            )
        logger.info(f"ส่ง Acknowledgment (Reply) ไปยัง {line_user_id} สำเร็จ")
    except Exception as e:
        logger.error(f"ไม่สามารถส่ง Acknowledgment ได้: {e}")
        # ถ้าส่ง Reply ไม่ได้ (เช่น Token หมดอายุเร็วมาก) จะยังทำขั้นตอนถัดไปต่อ

    # 2. เริ่มทำงานใน Thread แยกต่างหาก เพื่อให้ฟังก์ชันนี้จบการทำงานและคืนค่า 200 OK ให้ LINE ทันที
    thread = threading.Thread(
        target=process_ai_response_background, 
        args=(line_user_id, user_message)
    )
    thread.start()

