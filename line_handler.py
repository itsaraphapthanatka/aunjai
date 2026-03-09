import logging
import httpx
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from aunjai.config import (
    LINE_CHANNEL_SECRET, 
    LINE_CHANNEL_ACCESS_TOKEN,
    OPENCLAW_API_URL,
    OPENCLAW_AGENT_ID,
    OPENCLAW_API_KEY
)

logger = logging.getLogger(__name__)

# Initialize LINE API configuration
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

async def call_openclaw(user_message: str, line_user_id: str) -> str:
    """
    เรียกใช้งาน OpenClaw API เพื่อตอบคำถามผู้ใช้
    """
    chat_url = f"{OPENCLAW_API_URL.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_API_KEY:
        headers["Authorization"] = f"Bearer {OPENCLAW_API_KEY}"
        
    payload = {
        "model": f"openclaw:{OPENCLAW_AGENT_ID}",
        "messages": [
            {
                "role": "user",
                "content": user_message,
            }
        ],
        "user_id": line_user_id
    }
    
    logger.info(f"🚀 กำลังส่งข้อความของ {line_user_id} ไปยัง OpenClaw (agent: {OPENCLAW_AGENT_ID})")
    
    try:
        # ใช้ httpx.AsyncClient สำหรับการเรียก API แบบ async
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(chat_url, json=payload, headers=headers)
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
            
    except httpx.TimeoutException:
        logger.error("❌ OpenClaw API timeout")
        return "ขออภัยค่ะ อุ่นใจใช้เวลาคิดนานเกินไป กรุณาลองใหม่อีกครั้งนะคะ"
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการเรียก OpenClaw: {e}")
        return "ขออภัยค่ะ ระบบกำลังขัดข้อง อุ่นใจจะรีบกลับมาให้บริการโดยเร็วนะคะ"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    """
    จัดการข้อความที่ได้รับจาก LINE
    """
    line_user_id = event.source.user_id
    user_message = event.message.text
    reply_token = event.reply_token
    
    logger.info(f"ได้รับข้อความ LINE จาก {line_user_id}: {user_message}")
    
    # เนื่องจาก handle_text_message จาก line-bot-sdk ทำงานแบบ sync
    # เราจึงใช้วิธีรัน async function (call_openclaw) ภายในลูปย่อย
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    reply_text = loop.run_until_complete(call_openclaw(user_message, line_user_id))
    
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
            logger.info(f"ส่งข้อความตอบกลับไปยัง {line_user_id} สำเร็จ")
    except Exception as e:
        logger.error(f"เกิดข้อผิดพลาดในการตอบกลับ LINE: {e}")

