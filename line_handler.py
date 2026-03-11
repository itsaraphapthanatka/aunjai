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
    TextMessage
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
    OPENCLAW_API_KEY
)

from db_handler import DatabaseHandler

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


def process_ai_response_background(line_user_id: str, user_message: str):
    """
    ฟังก์ชันสำหรับทำงานใน Background: จัดการประวัติ, เรียก OpenClaw และส่งคำตอบ
    """
    try:
        # 1. บันทึกข้อความผู้ใช้ลงฐานข้อมูล
        db.add_chat_message(line_user_id, "user", user_message)
        
        # 2. ดึงประวัติการสนทนาล่าสุด (30 ข้อความ)
        history = db.get_chat_history(line_user_id, limit=30)
        
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

