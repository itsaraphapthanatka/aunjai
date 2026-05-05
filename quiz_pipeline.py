"""
quiz_pipeline.py — Orchestrator for Full Clip Quiz
1. รับ Youtube URL
2. Extract ID
3. Extract Transcripts
4. Analyze Quizด้วย OpenClaw
5. Store in Pinecone namespace "full_clip"
"""

import logging
from typing import Optional, Callable

from highlight_pipeline import extract_video_id
from extractor import extract_transcripts
from quiz_analyzer import analyze_full_clip_quiz
from quiz_store import store_full_clip_quiz

logger = logging.getLogger(__name__)

def run_quiz_pipeline(
    youtube_url: str,
    on_progress: Callable = None,
    check_stop: Callable = None,
) -> dict:
    
    class StopRequested(Exception):
        pass

    def report(step: str, detail: str = ""):
        if check_stop and check_stop():
            raise StopRequested("Stop requested by user")
            
        msg = f"{step}: {detail}" if detail else step
        logger.info(msg)
        if on_progress:
            try:
                on_progress(step, detail)
            except Exception:
                pass

    result = {
        "status": "error",
        "video_id": None,
        "quiz": [],
        "message": "",
    }

    try:
        # Step 1: Video ID
        report("🔗 กำลังดึง Video ID สำหรับ Quiz...")
        video_id = extract_video_id(youtube_url)
        if not video_id:
            result["message"] = f"ไม่สามารถดึง Video ID จาก URL: {youtube_url}"
            logger.error(f"❌ {result['message']}")
            return result

        result["video_id"] = video_id
        report("✅ Video ID", video_id)

        # Step 2: Transcript
        report("📝 กำลังถอด Transcript เต็มคลิป...", video_id)
        transcripts = extract_transcripts([video_id])

        if not transcripts:
            result["message"] = f"ไม่พบ transcript สำหรับวิดีโอ {video_id}"
            logger.error(f"❌ {result['message']}")
            return result

        report("✅ ถอด Transcript สำเร็จ", f"{len(transcripts)} segments")
        
        # Text snippet สำหรับ Pinecone
        transcript_summary = " ".join([t.get("text", "") for t in transcripts[:20]]) + "..."

        # Step 3: Analyze
        report("🤖 กำลังสร้าง Quiz (7-10 ข้อ) ด้วย OpenClaw...")
        quiz_data = []

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            report(f"🤖 สร้าง Quiz... (ครั้งที่ {attempt}/{max_retries})")
            quiz_data = analyze_full_clip_quiz(transcripts)
            if quiz_data and len(quiz_data) >= 5: # อนุโลมให้ถ้าตอบมา 5-10 ข้อ
                break
            if attempt < max_retries:
                report(f"⚠️ ลองใหม่... ({attempt}/{max_retries})")
                import time
                time.sleep(3)

        if not quiz_data:
            result["message"] = f"OpenClaw ไม่สามารถสร้าง Quiz ได้ อาจเพราะวิดีโอไม่มีเนื้อหาพอ หรือเซิร์ฟเวอร์ตอบกลับไม่ถูก"
            logger.warning(f"⚠️ {result['message']}")
            return result

        report("✅ สร้าง Quiz สำเร็จ", f"ได้มา {len(quiz_data)} ข้อ")

        # Step 4: Store in Pinecone
        report("💾 กำลังบันทึก Quiz ลง Pinecone...")
        try:
            is_success = store_full_clip_quiz(video_id, quiz_data, transcript_summary)
            if is_success:
                report("✅ บันทึก Pinecone (full_clip) สำเร็จ")
            else:
                report("⚠️ บันทึก Pinecone ไม่สำเร็จ")
        except Exception as e:
            report("⚠️ บันทึก Pinecone ไม่สำเร็จ", str(e))
            logger.warning(f"Pinecone store error: {e}")

        result["status"] = "success"
        result["quiz"] = quiz_data
        result["message"] = f"สร้าง Quiz สำเร็จ {len(quiz_data)} ข้อ"

        report("🎉 Pipeline เสร็จสมบูรณ์!", result["message"])
        return result
    except StopRequested:
        result["status"] = "stopped"
        result["message"] = "ถูกหยุดโดยผู้ใช้งาน"
        logger.warning(f"🛑 {result['message']}")
        return result
    except Exception as e:
        logger.error(f"Unexpected error in quiz pipeline: {e}")
        result["message"] = f"Error: {str(e)}"
        return result

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")

    if len(sys.argv) < 2:
        print("Usage: python quiz_pipeline.py <YOUTUBE_URL>")
        sys.exit(1)

    res = run_quiz_pipeline(sys.argv[1])
    print(res)
