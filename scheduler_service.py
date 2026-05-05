"""
scheduler_service.py — ระบบตั้งเวลาดึง Video ล่าสุดจาก YouTube Playlist อัตโนมัติ

ใช้ APScheduler + JSON file เก็บ schedules
เมื่อพบวิดีโอใหม่จะ run highlight pipeline + quiz pipeline อัตโนมัติ
"""

import os
import json
import uuid
import logging
import time
import random
from datetime import datetime
from typing import Optional, Dict, Any, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from playlist_scraper import scrape_playlist_videos, get_channel_playlists

# Lazy-imported at execution time to avoid startup failures
# from highlight_store import get_processed_video_ids
# from quiz_pipeline import run_quiz_pipeline

logger = logging.getLogger(__name__)

SCHEDULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedules.json")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule_history.json")
TIMEZONE = "Asia/Bangkok"


class SchedulerService:
    """ระบบจัดการ Scheduled Jobs สำหรับดึงวิดีโอจาก Playlist อัตโนมัติ"""

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=TIMEZONE)
        self.schedules: Dict[str, dict] = {}
        self.running_jobs: Dict[str, dict] = {}  # track currently running jobs
        self._load_schedules()

    def start(self):
        """เริ่มต้น Scheduler และโหลด jobs ที่บันทึกไว้"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("⏰ Scheduler Service เริ่มทำงาน (Timezone: Asia/Bangkok)")

            # โหลด schedules ที่เปิดใช้งานอยู่
            for schedule_id, config in self.schedules.items():
                if config.get("enabled", True):
                    self._register_job(schedule_id, config)

            active_count = sum(1 for s in self.schedules.values() if s.get("enabled", True))
            logger.info(f"📋 โหลด {active_count}/{len(self.schedules)} schedules ที่เปิดใช้งาน")

    def shutdown(self):
        """หยุด Scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("⏰ Scheduler Service หยุดทำงาน")

    # ─────────────────────────────────────────────
    # CRUD Operations
    # ─────────────────────────────────────────────

    def add_schedule(self, config: dict) -> dict:
        """
        เพิ่ม schedule ใหม่

        config: {
            "playlist_url": "https://www.youtube.com/playlist?list=PLxxx",
            "playlist_name": "My Playlist",
            "channel_name": "Channel Name",
            "schedule_type": "cron" | "interval",
            "cron_days": ["mon", "wed", "fri"],  # สำหรับ cron
            "cron_time": "08:00",                 # สำหรับ cron
            "interval_hours": 6,                   # สำหรับ interval
            "max_videos": 5,
            "auto_quiz": true,
        }
        """
        schedule_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        schedule = {
            "id": schedule_id,
            "playlist_url": config.get("playlist_url", ""),
            "playlist_name": config.get("playlist_name", "Unknown Playlist"),
            "channel_name": config.get("channel_name", ""),
            "schedule_type": config.get("schedule_type", "cron"),
            "cron_days": config.get("cron_days", ["mon"]),
            "cron_time": config.get("cron_time", "08:00"),
            "interval_hours": config.get("interval_hours", 6),
            "max_videos": config.get("max_videos", 5),
            "auto_quiz": config.get("auto_quiz", True),
            "enabled": True,
            "created_at": now,
            "last_run": None,
            "last_status": None,
        }

        self.schedules[schedule_id] = schedule
        self._save_schedules()

        # Register job
        self._register_job(schedule_id, schedule)

        logger.info(f"✅ สร้าง schedule ใหม่: {schedule_id} — {schedule['playlist_name']}")
        return schedule

    def remove_schedule(self, schedule_id: str) -> bool:
        """ลบ schedule"""
        if schedule_id not in self.schedules:
            return False

        # ลบ job จาก scheduler
        job_id = f"playlist_{schedule_id}"
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

        del self.schedules[schedule_id]
        self._save_schedules()

        logger.info(f"🗑️ ลบ schedule: {schedule_id}")
        return True

    def toggle_schedule(self, schedule_id: str) -> Optional[dict]:
        """เปิด/ปิด schedule"""
        if schedule_id not in self.schedules:
            return None

        schedule = self.schedules[schedule_id]
        schedule["enabled"] = not schedule.get("enabled", True)

        job_id = f"playlist_{schedule_id}"

        if schedule["enabled"]:
            self._register_job(schedule_id, schedule)
            logger.info(f"▶️ เปิด schedule: {schedule_id}")
        else:
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                pass
            logger.info(f"⏸️ ปิด schedule: {schedule_id}")

        self._save_schedules()
        return schedule

    def get_schedules(self) -> List[dict]:
        """ดึงรายการ schedules ทั้งหมด"""
        result = []
        for schedule_id, config in self.schedules.items():
            item = config.copy()
            # เพิ่มข้อมูลว่ากำลังรันอยู่หรือไม่
            item["is_running"] = schedule_id in self.running_jobs
            # เพิ่มข้อมูล next run time
            job_id = f"playlist_{schedule_id}"
            try:
                job = self.scheduler.get_job(job_id)
                if job and job.next_run_time:
                    item["next_run"] = job.next_run_time.strftime("%Y-%m-%d %H:%M")
                else:
                    item["next_run"] = None
            except Exception:
                item["next_run"] = None
            result.append(item)

        # เรียงตามวันที่สร้าง
        result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return result

    def run_now(self, schedule_id: str) -> dict:
        """รัน schedule ทันที"""
        if schedule_id not in self.schedules:
            return {"status": "error", "message": "ไม่พบ schedule นี้"}

        if schedule_id in self.running_jobs:
            return {"status": "error", "message": "กำลังทำงานอยู่แล้ว"}

        config = self.schedules[schedule_id]
        logger.info(f"🚀 Run Now: {schedule_id} — {config['playlist_name']}")

        # รันใน thread pool ของ scheduler
        self.scheduler.add_job(
            self._execute_job,
            args=[schedule_id],
            id=f"manual_{schedule_id}_{int(time.time())}",
            replace_existing=False,
        )

        return {"status": "accepted", "message": "เริ่มดึงวิดีโอแล้ว"}

    def get_history(self, schedule_id: str = None, limit: int = 20) -> List[dict]:
        """ดึงประวัติการรัน"""
        history = self._load_history()

        if schedule_id:
            history = [h for h in history if h.get("schedule_id") == schedule_id]

        # เรียงตามเวลา (ล่าสุดก่อน)
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return history[:limit]

    def get_running_status(self, schedule_id: str) -> Optional[dict]:
        """ดึงสถานะ job ที่กำลังรันอยู่"""
        return self.running_jobs.get(schedule_id)

    # ─────────────────────────────────────────────
    # Job Execution
    # ─────────────────────────────────────────────

    def _execute_job(self, schedule_id: str):
        """ฟังก์ชันหลักที่ทำงานเมื่อถึงเวลา schedule"""
        # Lazy imports to avoid startup dependency issues
        from highlight_store import get_processed_video_ids
        from quiz_pipeline import run_quiz_pipeline

        if schedule_id not in self.schedules:
            return

        config = self.schedules[schedule_id]
        playlist_url = config["playlist_url"]
        max_videos = config.get("max_videos", 5)
        auto_quiz = config.get("auto_quiz", True)

        run_result = {
            "schedule_id": schedule_id,
            "playlist_name": config.get("playlist_name", ""),
            "timestamp": datetime.now().isoformat(),
            "status": "running",
            "videos_found": 0,
            "new_videos": 0,
            "processed": 0,
            "errors": 0,
            "details": [],
        }

        self.running_jobs[schedule_id] = run_result

        try:
            logger.info(f"⏰ เริ่มดึงวิดีโอจาก Playlist: {config['playlist_name']}")

            # Step 1: ดึงวิดีโอจาก Playlist หรือ Channel
            is_all_channel = "วิดีโอทั้ง Channel" in config.get("playlist_name", "")
            videos = []

            if is_all_channel:
                channel_url = playlist_url.replace('/videos', '')
                logger.info(f"📋 ดึง Playlists ทั้งหมดจาก Channel: {channel_url}")
                channel_data = get_channel_playlists(channel_url)
                
                if channel_data.get("status") == "success":
                    playlists = channel_data.get("playlists", [])
                    logger.info(f"🔍 พบ {len(playlists)} Playlists, จะดึง Playlist ละ {max_videos} วิดีโอ")
                    for p in playlists:
                        logger.info(f"  ➡️ กำลังดึงจาก: {p['title']}")
                        scrape_result = scrape_playlist_videos(p["url"], max_videos=max_videos)
                        if scrape_result.get("status") == "success":
                            videos.extend(scrape_result.get("videos", []))
                            
                    # Remove duplicates (by video_id)
                    unique_videos = []
                    seen_ids = set()
                    for v in videos:
                        if v["video_id"] not in seen_ids:
                            unique_videos.append(v)
                            seen_ids.add(v["video_id"])
                    
                    videos = unique_videos
                    run_result["videos_found"] = len(videos)
                else:
                    run_result["status"] = "error"
                    run_result["message"] = channel_data.get("message", "ดึง Playlists ไม่สำเร็จ")
                    logger.error(f"❌ {run_result['message']}")
                    self._save_history_entry(run_result)
                    return
            else:
                scrape_result = scrape_playlist_videos(playlist_url, max_videos=max_videos)

                if scrape_result.get("status") != "success":
                    run_result["status"] = "error"
                    run_result["message"] = scrape_result.get("message", "ดึงข้อมูลไม่สำเร็จ")
                    logger.error(f"❌ {run_result['message']}")
                    self._save_history_entry(run_result)
                    return

                videos = scrape_result.get("videos", [])
                run_result["videos_found"] = len(videos)

            if not videos:
                run_result["status"] = "success"
                run_result["message"] = "ไม่พบวิดีโอใน Playlist"
                self._save_history_entry(run_result)
                return

            # Step 2: ตรวจสอบว่าวิดีโอไหนเคยประมวลผลแล้ว
            video_ids = [v["video_id"] for v in videos]
            try:
                processed_ids = get_processed_video_ids(video_ids)
            except Exception as e:
                logger.warning(f"⚠️ ตรวจสอบ processed IDs ไม่สำเร็จ: {e}")
                processed_ids = []

            new_videos = [v for v in videos if v["video_id"] not in processed_ids]
            run_result["new_videos"] = len(new_videos)

            if not new_videos:
                run_result["status"] = "success"
                run_result["message"] = f"ไม่มีวิดีโอใหม่ (พบ {len(videos)} วิดีโอ, ประมวลผลแล้วทั้งหมด)"
                logger.info(f"✅ {run_result['message']}")
                self._save_history_entry(run_result)
                return

            logger.info(f"🆕 พบวิดีโอใหม่ {len(new_videos)}/{len(videos)} รายการ")

            # Step 3: ประมวลผลแต่ละวิดีโอใหม่
            for i, video in enumerate(new_videos):
                video_url = video["url"]
                video_title = video["title"]
                video_id = video["video_id"]

                detail = {
                    "video_id": video_id,
                    "title": video_title,
                    "status": "processing",
                    "quiz_status": None,
                }

                logger.info(f"🎬 [{i+1}/{len(new_videos)}] กำลังประมวลผล: {video_title}")

                # Delay ระหว่างวิดีโอ (ป้องกัน rate limit)
                if i > 0:
                    jitter = random.uniform(15, 25)
                    logger.info(f"⏳ หน่วงเวลา {jitter:.0f} วินาที...")
                    time.sleep(jitter)

                # สร้าง Quiz จากคลิปเต็ม
                if auto_quiz:
                    try:
                        logger.info(f"  📝 Running Quiz Pipeline (Full Clip)...")
                        quiz_result = run_quiz_pipeline(youtube_url=video_url)
                        if quiz_result.get("status") == "success":
                            q_count = len(quiz_result.get("quiz", []))
                            detail["quiz_status"] = f"success ({q_count} questions)"
                            logger.info(f"  ✅ Quiz สำเร็จ: {q_count} questions")
                        else:
                            detail["quiz_status"] = f"error: {quiz_result.get('message', '')}"
                            logger.error(f"  ❌ Quiz ล้มเหลว: {quiz_result.get('message', '')}")
                    except Exception as e:
                        detail["quiz_status"] = f"error: {str(e)}"
                        logger.error(f"  ❌ Quiz error: {e}")

                # Determine video status
                qz_ok = detail.get("quiz_status", "").startswith("success") if auto_quiz else True

                if qz_ok:
                    detail["status"] = "success"
                    run_result["processed"] += 1
                else:
                    detail["status"] = "error"
                    run_result["errors"] += 1

                run_result["details"].append(detail)

                # อัพเดต running status
                self.running_jobs[schedule_id] = run_result.copy()

            # สรุปผล
            run_result["status"] = "success"
            run_result["message"] = (
                f"เสร็จสิ้น: พบ {len(new_videos)} วิดีโอใหม่, "
                f"สำเร็จ {run_result['processed']}, ข้อผิดพลาด {run_result['errors']}"
            )
            logger.info(f"🎉 {run_result['message']}")

        except Exception as e:
            run_result["status"] = "error"
            run_result["message"] = f"เกิดข้อผิดพลาดร้ายแรง: {str(e)}"
            logger.error(f"❌ {run_result['message']}", exc_info=True)

        finally:
            # Update schedule metadata
            self.schedules[schedule_id]["last_run"] = datetime.now().isoformat()
            self.schedules[schedule_id]["last_status"] = run_result["status"]
            self._save_schedules()

            # Save history
            self._save_history_entry(run_result)

            # Remove from running
            self.running_jobs.pop(schedule_id, None)

    # ─────────────────────────────────────────────
    # Internal Helpers
    # ─────────────────────────────────────────────

    def _register_job(self, schedule_id: str, config: dict):
        """ลงทะเบียน APScheduler job"""
        job_id = f"playlist_{schedule_id}"

        # ลบ job เก่าถ้ามี
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

        schedule_type = config.get("schedule_type", "cron")

        if schedule_type == "cron":
            days = config.get("cron_days", ["mon"])
            time_str = config.get("cron_time", "08:00")
            hour, minute = time_str.split(":")

            # แปลงวันเป็น APScheduler format
            day_of_week = ",".join(days)

            trigger = CronTrigger(
                day_of_week=day_of_week,
                hour=int(hour),
                minute=int(minute),
                timezone=TIMEZONE,
            )
            logger.info(
                f"📅 ตั้ง CRON job: {config['playlist_name']} "
                f"ทุกวัน {day_of_week} เวลา {time_str}"
            )

        elif schedule_type == "interval":
            hours = config.get("interval_hours", 6)
            trigger = IntervalTrigger(hours=hours, timezone=TIMEZONE)
            logger.info(
                f"🔄 ตั้ง Interval job: {config['playlist_name']} "
                f"ทุก {hours} ชั่วโมง"
            )
        else:
            logger.error(f"❌ Schedule type ไม่ถูกต้อง: {schedule_type}")
            return

        self.scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            args=[schedule_id],
            id=job_id,
            replace_existing=True,
            name=f"Playlist: {config.get('playlist_name', schedule_id)}",
        )

    def _load_schedules(self):
        """โหลด schedules จากไฟล์ JSON"""
        if os.path.exists(SCHEDULES_FILE):
            try:
                with open(SCHEDULES_FILE, 'r', encoding='utf-8') as f:
                    self.schedules = json.load(f)
                logger.info(f"📂 โหลด {len(self.schedules)} schedules จากไฟล์")
            except Exception as e:
                logger.error(f"⚠️ โหลด schedules ไม่สำเร็จ: {e}")
                self.schedules = {}
        else:
            self.schedules = {}

    def _save_schedules(self):
        """บันทึก schedules ลงไฟล์ JSON"""
        try:
            with open(SCHEDULES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.schedules, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"⚠️ บันทึก schedules ไม่สำเร็จ: {e}")

    def _load_history(self) -> List[dict]:
        """โหลดประวัติการรัน"""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_history_entry(self, entry: dict):
        """บันทึกประวัติการรัน (เก็บสูงสุด 100 รายการ)"""
        try:
            history = self._load_history()
            history.append(entry)
            # เก็บสูงสุด 100 รายการ
            if len(history) > 100:
                history = history[-100:]
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"⚠️ บันทึกประวัติไม่สำเร็จ: {e}")


# Global instance
scheduler_service = SchedulerService()
