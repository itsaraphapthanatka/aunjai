"""
highlight_pipeline.py — Orchestrator: YouTube URL → Transcript → OpenClaw Analysis → Video Clips

Flow:
1. Extract video ID จาก YouTube URL
2. ถอด Transcript ด้วย extractor.py
3. ส่ง Transcript ให้ OpenClaw วิเคราะห์ highlight ด้วย highlight_analyzer.py
4. ตัดวิดีโอแต่ละ highlight ด้วย video_processor.py
5. Return รายการ clips ที่ตัดสำเร็จ
"""

import re
import os
import logging
from typing import Optional, Callable

from extractor import extract_transcripts
from highlight_analyzer import analyze_highlights
from video_processor import process_video_clip
from highlight_store import store_highlights
from google_drive_uploader import upload_local_file_to_drive

logger = logging.getLogger(__name__)


def extract_video_id(url: str) -> Optional[str]:
    """
    ดึง Video ID จาก YouTube URL ที่หลากหลายรูปแบบ

    รองรับ:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://youtube.com/watch?v=VIDEO_ID&t=123
    - VIDEO_ID (11 ตัวอักษร)
    """
    if not url:
        return None

    # Pattern: youtube.com/watch?v=xxx
    match = re.search(r'(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)

    # Pattern: youtu.be/xxx
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)

    # Pattern: youtube.com/embed/xxx
    match = re.search(r'youtube\.com/embed/([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)

    # Pattern: เป็น video ID ตรงๆ (11 ตัว)
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url

    return None


def run_highlight_pipeline(
    youtube_url: str,
    auto_clip: bool = True,
    clip_margin: float = 3.0,
    on_progress: Callable = None,
    check_stop: Callable = None,
) -> dict:
    """
    รัน Highlight Pipeline ครบทุกขั้นตอน

    Args:
        youtube_url: YouTube URL หรือ Video ID
        auto_clip: ถ้า True จะตัดวิดีโออัตโนมัติ (ค่าเริ่มต้น True)
        clip_margin: margin เพิ่มก่อน/หลังแต่ละ highlight (วินาที)
        on_progress: callback function สำหรับรายงานความคืบหน้า

    Returns:
        dict สรุปผล:
        {
            "status": "success" | "error",
            "video_id": "xxx",
            "transcript_count": 42,
            "highlights": [...],
            "message": "สรุปผล..."
        }
    """

    def report(step: str, detail: str = ""):
        """Helper สำหรับ log + callback"""
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
        "transcript_count": 0,
        "highlights": [],
        "message": "",
    }

    try:
        # ──────────────────────────────────────────
        # Step 1: Extract Video ID
        # ──────────────────────────────────────────
        report("🔗 กำลังดึง Video ID...")
        video_id = extract_video_id(youtube_url)
        if not video_id:
            result["message"] = f"ไม่สามารถดึง Video ID จาก URL: {youtube_url}"
            logger.error(f"❌ {result['message']}")
            return result

        result["video_id"] = video_id
        report("✅ Video ID", video_id)

        # ──────────────────────────────────────────
        # Step 2: Extract Transcript
        # ──────────────────────────────────────────
        report("📝 กำลังถอด Transcript...", video_id)
        transcripts = extract_transcripts([video_id])

        if not transcripts:
            result["status"] = "skipped"
            result["message"] = f"ไม่พบ transcript สำหรับวิดีโอ {video_id} — อาจไม่มีคำบรรยาย (ข้ามการตัดวิดีโอ)"
            logger.warning(f"⏩ {result['message']}")
            return result

        result["transcript_count"] = len(transcripts)
        report("✅ ถอด Transcript สำเร็จ", f"{len(transcripts)} segments")

        # คำนวณความยาววิดีโอจาก transcript
        total_duration = 0.0
        if transcripts:
            last_seg = transcripts[-1]
            total_duration = last_seg.get("start", 0) + last_seg.get("duration", 0)

        # ──────────────────────────────────────────
        # Step 3: Analyze Highlights or Use Full Video
        # ──────────────────────────────────────────
        highlights = None

        if total_duration > 0 and total_duration < 60:
            report("⚡ วิดีโอสั้นกว่า 1 นาที", f"ใช้คลิปเต็มความยาว {total_duration:.1f}s โดยไม่ผ่าน OpenClaw")
            highlights = [{
                "start_time": 0.0,
                "end_time": total_duration,
                "reason": f"วิดีโอสั้นกว่า 1 นาที ({total_duration:.1f}s) ใช้คลิปเต็ม",
                "score": 1.0,
                "quiz": []
            }]
        else:
            report("🤖 กำลังวิเคราะห์ Highlight ด้วย OpenClaw...")
            max_retries = 3

            for attempt in range(1, max_retries + 1):
                report(f"🤖 วิเคราะห์ Highlight... (ครั้งที่ {attempt}/{max_retries})")
                highlights = analyze_highlights(transcripts)
                if highlights:
                    break
                if attempt < max_retries:
                    report(f"⚠️ ลองใหม่... ({attempt}/{max_retries})")
                    import time
                    time.sleep(3)

            if not highlights:
                result["message"] = f"OpenClaw ไม่สามารถวิเคราะห์ highlight ได้หลัง {max_retries} ครั้ง — ตรวจสอบ OpenClaw server หรือลองวิดีโออื่น"
                logger.warning(f"⚠️ {result['message']}")
                return result

            report("✅ วิเคราะห์ Highlight สำเร็จ", f"{len(highlights)} highlights")

        # แนบ transcript text ให้แต่ละ highlight
        for highlight in highlights:
            matching_segments = [
                seg for seg in transcripts
                if seg["start"] + seg.get("duration", 0) > highlight["start_time"]
                and seg["start"] < highlight["end_time"]
            ]
            highlight["transcript"] = " ".join(
                seg["text"].strip() for seg in matching_segments if seg["text"].strip()
            )

        # ──────────────────────────────────────────
        # Step 4: Auto-clip (ถ้าเปิดใช้งาน)
        # ──────────────────────────────────────────
        if auto_clip:
            report("✂️ กำลังตัดวิดีโอ...", f"{len(highlights)} clips")

            for i, highlight in enumerate(highlights):
                clip_label = f"Clip {i+1}/{len(highlights)}"
                report(f"✂️ กำลังตัด {clip_label}...",
                       f"{highlight['start_time']:.1f}s - {highlight['end_time']:.1f}s")

                try:
                    clip_result = process_video_clip(
                        video_id=video_id,
                        start_time=highlight["start_time"],
                        end_time=highlight["end_time"],
                        margin=clip_margin,
                    )

                    if clip_result.get("status") == "success":
                        local_path = clip_result.get("local_path")
                        file_url = clip_result.get("file_url", "")
                        
                        if local_path and os.path.exists(local_path):
                            report(f"☁️ กำลังอัปโหลด {clip_label} ขึ้น Google Drive...")
                            drive_link = upload_local_file_to_drive(local_path, video_id=video_id)
                            if drive_link:
                                highlight["clip_url"] = drive_link
                                highlight["clip_status"] = "success"
                                report(f"✅ {clip_label} อัปโหลดสำเร็จ", drive_link)
                                
                                # ลบไฟล์ local ทิ้งเพื่อประหยัดพื้นที่
                                try:
                                    os.remove(local_path)
                                    report(f"🗑️ ลบไฟล์ local แล้ว", local_path)
                                except Exception as e:
                                    logger.warning(f"ไม่สามารถลบไฟล์ local ได้: {e}")
                            else:
                                highlight["clip_url"] = file_url  # fallback to local
                                highlight["clip_status"] = "success_local_only"
                                report(f"⚠️ {clip_label} อัปโหลดไม่สำเร็จ ใช้ไฟล์ local", file_url)
                        else:
                            highlight["clip_url"] = file_url
                            highlight["clip_status"] = "success"
                            report(f"✅ {clip_label} สำเร็จ (Local)", highlight["clip_url"])
                    else:
                        highlight["clip_url"] = ""
                        highlight["clip_status"] = "error"
                        highlight["clip_error"] = clip_result.get("message", "Unknown error")
                        report(f"⚠️ {clip_label} ล้มเหลว", highlight.get("clip_error", ""))

                except StopRequested:
                    raise
                except Exception as e:
                    highlight["clip_url"] = ""
                    highlight["clip_status"] = "error"
                    highlight["clip_error"] = str(e)
                    report(f"❌ {clip_label} error", str(e))
        else:
            # ไม่ตัดวิดีโอ — แค่ส่ง highlights กลับ
            for highlight in highlights:
                highlight["clip_url"] = ""
                highlight["clip_status"] = "pending"

        # ──────────────────────────────────────────
        # Step 5: Store in Pinecone
        # ──────────────────────────────────────────
        report("💾 กำลังบันทึกลง Pinecone...")
        try:
            id_map = store_highlights(video_id, highlights)
            if id_map:
                for h in highlights:
                    h["pinecone_id"] = id_map.get(h.get("start_time", 0), "")
                report("✅ บันทึก Pinecone สำเร็จ", f"{len(id_map)} records")
            else:
                report("⚠️ บันทึก Pinecone ไม่สำเร็จ")
        except StopRequested:
            raise
        except Exception as e:
            report("⚠️ บันทึก Pinecone ไม่สำเร็จ", str(e))
            logger.warning(f"Pinecone store error: {e}")

        # ──────────────────────────────────────────
        # สรุปผล
        # ──────────────────────────────────────────
        success_count = sum(1 for h in highlights if h.get("clip_status") == "success")
        result["status"] = "success"
        result["highlights"] = highlights
        result["message"] = (
            f"วิเคราะห์สำเร็จ: {len(highlights)} highlights"
            + (f", ตัดคลิปสำเร็จ {success_count}/{len(highlights)}" if auto_clip else "")
        )

        report("🎉 Pipeline เสร็จสมบูรณ์!", result["message"])
        return result
    except StopRequested:
        result["status"] = "stopped"
        result["message"] = "ถูกหยุดโดยผู้ใช้งาน"
        logger.warning(f"🛑 {result['message']}")
        return result
    except Exception as e:
        logger.error(f"Unexpected error in highlight pipeline: {e}")
        result["message"] = f"Error: {str(e)}"
        return result
    except StopRequested:
        result["status"] = "stopped"
        result["message"] = "ถูกหยุดโดยผู้ใช้งาน"
        logger.warning(f"🛑 {result['message']}")
        return result
    except Exception as e:
        result["message"] = f"Unexpected error: {str(e)}"
        logger.error(f"❌ {result['message']}")
        return result


# ──────────────────────────────────────────────
# ทดสอบแบบ standalone
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")

    if len(sys.argv) < 2:
        print("Usage: python highlight_pipeline.py <YOUTUBE_URL> [--no-clip]")
        print("Example: python highlight_pipeline.py https://www.youtube.com/watch?v=xxx")
        sys.exit(1)

    url = sys.argv[1]
    should_clip = "--no-clip" not in sys.argv

    print(f"\n{'='*60}")
    print(f"🎬 YouTube Highlight Extractor")
    print(f"{'='*60}")
    print(f"   URL: {url}")
    print(f"   Auto-clip: {'Yes' if should_clip else 'No'}")
    print(f"{'='*60}\n")

    result = run_highlight_pipeline(url, auto_clip=should_clip)

    print(f"\n{'='*60}")
    print(f"📊 ผลลัพธ์: {result['status']}")
    print(f"   {result['message']}")

    for i, h in enumerate(result.get("highlights", []), 1):
        print(f"\n--- Highlight {i} ---")
        print(f"  ⏱️  {h['start_time']:.1f}s - {h['end_time']:.1f}s")
        print(f"  📊 Score: {h['score']}")
        print(f"  💡 {h['reason']}")
        if h.get("clip_url"):
            print(f"  🎬 {h['clip_url']}")
