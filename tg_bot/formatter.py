import datetime

def format_deadline_message(assignment: dict, course_name: str) -> str:
    """
    Format tin nhắn deadline để gửi qua Telegram
    """
    assign_name = assignment.get("name", "Không tên")
    due_date_ts = assignment.get("duedate", 0)
    
    if due_date_ts == 0:
        return ""
        
    due_date = datetime.datetime.fromtimestamp(due_date_ts)
    now = datetime.datetime.now()
    
    time_left = due_date - now
    total_seconds = int(time_left.total_seconds())
    
    if total_seconds < 0:
        return "" # Đã quá hạn
        
    days_left = total_seconds // (24 * 3600)
    hours_left = (total_seconds % (24 * 3600)) // 3600
    
    if days_left > 0:
        time_left_str = f"{days_left} ngày {hours_left} giờ"
    else:
        time_left_str = f"{hours_left} giờ"
    
    # Quyết định emoji dựa trên thời gian còn lại
    if days_left < 1:
        urgency = "🔴 GẤP GẤP"
    elif days_left <= 3:
        urgency = "🟠 SẮP TỚI"
    else:
        urgency = "🟢 ĐANG THONG THẢ"
        
    time_str = due_date.strftime("%d/%m/%Y %H:%M")
    
    # ID của assignment thường được dùng để tạo link tới lms
    assign_id = assignment.get("cmid")
    link = f"https://lms.iuh.edu.vn/mod/assign/view.php?id={assign_id}" if assign_id else "Không có link"
    
    msg = f"⚠️ **DEADLINE {urgency}** — Còn {time_left_str}!\n\n"
    msg += f"📚 **Môn:** {course_name}\n"
    msg += f"📝 **Bài tập:** {assign_name}\n"
    msg += f"⏰ **Hạn nộp:** {time_str}\n"
    msg += f"🔗 **Link:** {link}\n\n"
    msg += "——————————————————\n"
    msg += "💡 Dùng /deadlines để xem tất cả deadline"
    
    return msg

def get_done_keyboard(assign_id: int):
    """
    Tạo nút bấm 'Đã nộp bài' đính kèm dưới tin nhắn
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = [
        [InlineKeyboardButton("✅ Đã nộp bài", callback_data=f"done_{assign_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_grades_overview(courses: list, course_grades: dict) -> str:
    """
    Format tin nhắn tổng quan điểm các môn học
    """
    msg = "📊 **BẢNG ĐIỂM HỌC KỲ HIỆN TẠI**\n\n"
    for c in courses:
        cid = c["id"]
        cname = c.get("fullname", "Unknown")
        grade = course_grades.get(cid, "-")
        msg += f"🔸 **{cname}**: {grade}\n"
    
    msg += "\n💡 Bấm vào nút bên dưới để xem chi tiết điểm từng môn."
    return msg

def get_course_grades_keyboard(courses: list):
    """
    Tạo nút bấm tra cứu điểm chi tiết cho từng môn
    """
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = []
    for c in courses:
        cid = c["id"]
        cname = c.get("fullname", "Unknown")
        # Giới hạn độ dài tên môn trên nút bấm
        short_name = cname[:30] + "..." if len(cname) > 30 else cname
        keyboard.append([InlineKeyboardButton(f"📘 {short_name}", callback_data=f"grade_{cid}")])
        
    return InlineKeyboardMarkup(keyboard)

def format_grade_items(course_name: str, grade_items: list) -> str:
    """
    Format chi tiết các cột điểm của 1 môn
    """
    msg = f"🏫 **Môn:** {course_name}\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    
    if not grade_items:
        return msg + "Chưa có cột điểm nào được ghi nhận."
        
    for item in grade_items:
        name = item.get("itemname", "Tổng kết")
        grade = item.get("gradeformatted", "-")
        percentage = item.get("percentageformatted", "-")
        
        # Xử lý các tag HTML nếu có trong grade
        grade = grade.replace("&ndash;", "-").replace("&nbsp;", " ")
        percentage = percentage.replace("&ndash;", "-").replace("&nbsp;", " ")
        
        msg += f"🔹 {name}:\n"
        msg += f"   └ Điểm: **{grade}** ({percentage})\n"
        
    return msg
