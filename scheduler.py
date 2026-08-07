import asyncio
import logging
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
import os

from db.database import pool
from moodle.courses import get_site_info, get_enrolled_courses, get_current_semester_courses
from moodle.assignments import get_assignments
from tg_bot.formatter import format_deadline_message, get_done_keyboard

logger = logging.getLogger(__name__)

async def sync_user_data(chat_id: int, token: str, lms_userid: int, notify: bool = True):
    """
    Hàm đồng bộ dữ liệu cho 1 user.
    """
    try:
        all_courses = await get_enrolled_courses(lms_userid, token)
        if not all_courses:
            return
            
        current_courses = get_current_semester_courses(all_courses)
        course_ids = [c["id"] for c in current_courses]
        
        assignments = await get_assignments(course_ids, token)
        
        from moodle.assignments import get_activity_completion_statuses
        completion_cache = {}
        for cid in course_ids:
            completion_cache[cid] = await get_activity_completion_statuses(cid, lms_userid, token)
        
        current_time = int(time.time())
        bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
        
        async with pool.acquire() as db:
            for assign in assignments:
                cmid = assign["cmid"]
                name = assign["name"]
                duedate = assign["duedate"]
                course_id = assign["course"]
                
                course_name = next((c["fullname"] for c in current_courses if c["id"] == course_id), "Môn học")
                
                # Bỏ qua deadline cũ
                if duedate < current_time:
                    continue
                    
                # Kiểm tra xem đã có trong DB chưa
                row = await db.fetchrow("SELECT id, is_done FROM assignments WHERE id = $1 AND chat_id = $2", cmid, chat_id)
                
                if not row:
                    from moodle.assignments import check_submission_status
                    # Kiểm tra xem đã nộp trên LMS chưa (cả submission lẫn activity completion)
                    is_submitted = await check_submission_status(assign["id"], token)
                    is_activity_done = completion_cache.get(course_id, {}).get(cmid, False)
                    is_done = is_submitted or is_activity_done
                    # Deadline mới! Lưu vào DB
                    await db.execute(
                        "INSERT INTO assignments (id, chat_id, name, course_name, duedate, is_done) VALUES ($1, $2, $3, $4, $5, $6)",
                        cmid, chat_id, name, course_name, duedate, is_done
                    )
                    logger.info(f"Đã thêm deadline mới: {name} cho user {chat_id} (is_done={is_done})")
                    
                    # Thông báo nếu chưa nộp
                    if notify and not is_done:
                        msg = format_deadline_message(
                            {"name": name, "duedate": duedate, "cmid": cmid},
                            course_name
                        )
                        if msg:
                            keyboard = get_done_keyboard(cmid)
                            try:
                                await bot.send_message(
                                    chat_id=chat_id, 
                                    text=f"🚨 **CÓ DEADLINE MỚI!**\n\n{msg}", 
                                    parse_mode="Markdown", 
                                    reply_markup=keyboard
                                )
                            except Exception as e:
                                logger.error(f"Lỗi gửi tin nhắn tới {chat_id}: {e}")
                else:
                    # Đã có trong DB, nếu đang chưa nộp thì check lại trên LMS
                    if not row["is_done"]:
                        from moodle.assignments import check_submission_status
                        is_submitted = await check_submission_status(assign["id"], token)
                        is_activity_done = completion_cache.get(course_id, {}).get(cmid, False)
                        if is_submitted or is_activity_done:
                            await db.execute(
                                "UPDATE assignments SET is_done = TRUE WHERE id = $1 AND chat_id = $2",
                                cmid, chat_id
                            )
                            logger.info(f"Đã tự động đánh dấu hoàn thành deadline: {name} cho user {chat_id}")
    except Exception as e:
        logger.error(f"Lỗi đồng bộ dữ liệu cho {chat_id}: {e}")

async def run_sync_all_users():
    """
    Hàm được gọi định kỳ bởi APScheduler để quét toàn bộ user.
    """
    logger.info("Bắt đầu tiến trình quét và đồng bộ điểm định kỳ...")
    if not pool:
        logger.warning("Database pool chưa được khởi tạo. Bỏ qua lần quét này.")
        return
        
    async with pool.acquire() as db:
        users = await db.fetch("SELECT chat_id, moodle_token, lms_userid FROM users")
        
    for user in users:
        await sync_user_data(user["chat_id"], user["moodle_token"], user["lms_userid"], notify=True)
        # Nghỉ 2s giữa các user để tránh Rate Limit của Telegram/Moodle
        await asyncio.sleep(2)
        
    logger.info("Đã hoàn thành tiến trình quét điểm.")

def start_scheduler():
    scheduler = AsyncIOScheduler()
    # Chạy hàm run_sync_all_users mỗi 2 giờ
    scheduler.add_job(run_sync_all_users, 'interval', hours=2)
    scheduler.start()
    logger.info("Đã khởi động APScheduler chạy ngầm (2h/lần).")
