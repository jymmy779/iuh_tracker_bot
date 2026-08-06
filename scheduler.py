import asyncio
import time
import logging

from moodle.courses import get_enrolled_courses, get_current_semester_courses
from moodle.assignments import get_assignments, check_submission_status
from moodle.grades import get_course_grades, get_grade_items
from db.database import (
    get_all_users, insert_or_update_assignment, get_pending_reminders, 
    mark_reminded, mark_done, get_known_grades, insert_or_update_grade
)
from tg_bot.client import send_telegram_message
from tg_bot.formatter import format_deadline_message, get_done_keyboard

logger = logging.getLogger(__name__)

async def sync_user_data(chat_id: int, token: str, user_id: int, notify: bool = True):
    """
    Đồng bộ dữ liệu và gửi thông báo cho 1 user
    """
    logger.info(f"Đang đồng bộ cho user chat_id={chat_id}")
    try:
        # 1. ĐỒNG BỘ BÀI TẬP (DEADLINES)
        courses = await get_enrolled_courses(user_id, token)
        if courses:
            course_ids = [c["id"] for c in courses]
            course_map = {c["id"]: c.get("fullname", c.get("shortname", f"Course {c['id']}")) for c in courses}
            
            assignments = await get_assignments(course_ids, token)
            count = 0
            for assign in assignments:
                assign_id = assign.get("cmid") or assign.get("id")
                name = assign.get("name", "Unknown")
                duedate = assign.get("duedate", 0)
                course_id = assign.get("course")
                
                if not name or duedate == 0 or assign.get("nosubmissions") == 1:
                    continue
                    
                name_lower = name.lower()
                if any(keyword in name_lower for keyword in ["xem điểm", "thông báo", "cột điểm"]):
                    continue

                course_name = course_map.get(course_id, f"Môn học {course_id}")
                
                if duedate > 0:
                    await insert_or_update_assignment(assign_id, name, course_name, duedate, chat_id)
                    count += 1
                    
            logger.info(f"User {chat_id}: Đã đồng bộ {count} assignments vào DB.")

        # 2. KIỂM TRA NHẮC NHỞ DEADLINE
        current_time = int(time.time())
        pending = await get_pending_reminders(current_time)
        
        # Chỉ lấy những nhắc nhở thuộc về user này
        user_pending = [p for p in pending if p["chat_id"] == chat_id]
        
        for p in user_pending:
            assign_id = p["id"]
            is_submitted = await check_submission_status(assign_id, token)
            if is_submitted:
                logger.info(f"User {chat_id}: Bài tập {assign_id} đã nộp, đánh dấu hoàn thành.")
                await mark_done(assign_id, chat_id)
                continue
            
            msg = format_deadline_message(
                assignment={"name": p["name"], "duedate": p["duedate"], "cmid": assign_id},
                course_name=p["course_name"]
            )
            
            if msg and notify:
                keyboard = get_done_keyboard(assign_id)
                success = await send_telegram_message(chat_id, msg, reply_markup=keyboard)
                if success:
                    await mark_reminded(p["id"], chat_id, p["remind_type"])
                await asyncio.sleep(1)

        # 3. KIỂM TRA ĐIỂM MỚI (CHỈ HỌC KỲ HIỆN TẠI)
        logger.info(f"User {chat_id}: Đang kiểm tra điểm mới...")
        if courses:
            current_courses = get_current_semester_courses(courses)
            for course in current_courses:
                course_id = course["id"]
                course_name = course.get("fullname", f"Môn {course_id}")
                
                known_grades = await get_known_grades(course_id, chat_id)
                current_items = await get_grade_items(course_id, user_id, token)
                
                for item in current_items:
                    item_id = item["id"]
                    item_name = item.get("itemname") or "Tổng kết"
                    grade_formatted = item.get("gradeformatted", "-")
                    
                    if grade_formatted == "-":
                        continue
                        
                    old_grade = known_grades.get(item_name)
                    if old_grade != grade_formatted:
                        action = "VỪA CÓ ĐIỂM" if old_grade is None else "VỪA CẬP NHẬT ĐIỂM"
                        grade = grade_formatted.replace("&ndash;", "-").replace("&nbsp;", " ")
                        percent = item.get("percentageformatted", "-").replace("&ndash;", "-").replace("&nbsp;", " ")
                        
                        msg = f"🔔 **TING TING! {action}**\n\n"
                        msg += f"🏫 **Môn:** {course_name}\n"
                        msg += f"📝 **Cột điểm:** {item_name}\n"
                        msg += f"💯 **Điểm số:** {grade} ({percent})\n"
                        if old_grade:
                            msg += f"_(Điểm cũ: {old_grade})_\n"
                        
                        grade_link = f"https://lms.iuh.edu.vn/grade/report/user/index.php?id={course_id}"
                        msg += f"\n🔗 **Link:** [Xem chi tiết tại đây]({grade_link})\n\n"
                        msg += "Nhanh tay vào xem ngay bạn ơi! 🎉"
                        
                        if notify:
                            await send_telegram_message(chat_id, msg)
                            await asyncio.sleep(1)
                        
                        await insert_or_update_grade(item_id, course_id, item_name, grade_formatted, chat_id)
    except Exception as e:
        logger.error(f"Lỗi đồng bộ cho user {chat_id}: {e}")

async def sync_and_notify():
    """
    Hàm chính gọi từ Webhook (/sync) quét tất cả user trong DB
    """
    logger.info("Bắt đầu chu kỳ quét toàn bộ người dùng từ Webhook...")
    try:
        users = await get_all_users()
        if not users:
            logger.info("Chưa có user nào trong hệ thống.")
            return
            
        for user in users:
            chat_id, token, lms_userid = user["chat_id"], user["moodle_token"], user["lms_userid"]
            await sync_user_data(chat_id, token, lms_userid)
            
        logger.info("Hoàn thành chu kỳ quét.")
    except Exception as e:
        logger.error(f"Lỗi hệ thống trong sync_and_notify: {e}")
