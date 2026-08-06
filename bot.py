import asyncio
import logging
import os
import time
from fastapi import FastAPI, Request, Response
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv

from db.database import init_db, mark_done, get_user, add_or_update_user, remove_user
from scheduler import sync_and_notify, sync_user_data
from tg_bot.formatter import format_deadline_message, get_done_keyboard, format_grades_overview, get_course_grades_keyboard, format_grade_items
from moodle.auth import get_moodle_token
from moodle.courses import get_site_info, get_enrolled_courses, get_current_semester_courses
from moodle.grades import get_course_grades, get_grade_items

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = FastAPI()
application = None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = await get_user(chat_id)
    if user:
        await update.message.reply_text(
            "Xin chào! Bạn đã đăng nhập thành công vào hệ thống.\n\n"
            "Dùng lệnh /deadlines, /week hoặc /grades để bắt đầu nhé!"
        )
    else:
        await update.message.reply_text(
            "Xin chào! Mình là Bot nhắc deadline & thông báo điểm LMS IUH 🎓\n\n"
            "Để bắt đầu, bạn cần đăng nhập bằng tài khoản sinh viên. Hãy gõ lệnh sau:\n\n"
            "`/login mssv mậtkhẩu`\n\n"
            "_VD: /login 21000000 123456_\n\n"
            "**LƯU Ý BẢO MẬT:** Bot KHÔNG lưu mật khẩu của bạn. Bot chỉ dùng 1 lần để lấy Token từ trường, sau đó tự động xóa tin nhắn chứa mật khẩu của bạn đi.",
            parse_mode="Markdown"
        )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("❌ Sai cú pháp. Vui lòng gõ: `/login mssv matkhau`", parse_mode="Markdown")
        return
        
    username = args[0]
    password = " ".join(args[1:])
    
    msg = await update.message.reply_text("⏳ Đang xác thực với hệ thống LMS, vui lòng đợi...")
    
    try:
        token = await get_moodle_token(username, password)
        site_info = await get_site_info(token)
        lms_userid = site_info.get("userid")
        
        if not lms_userid:
            raise Exception("Lỗi lấy thông tin User ID.")
            
        await add_or_update_user(chat_id, token, lms_userid)
        
        try:
            await update.message.delete()
        except:
            logger.warning(f"Không thể xóa tin nhắn chứa mật khẩu của {chat_id}, bot cần quyền Delete Messages.")
            
        await msg.edit_text("✅ Đăng nhập thành công! Bot đã bắt đầu theo dõi bài tập và điểm của bạn.\n\nGõ /deadlines để xem bài tập ngay!")
        
        # Chạy đồng bộ lần đầu ngay lập tức
        asyncio.create_task(sync_user_data(chat_id, token, lms_userid))
        
    except Exception as e:
        logger.error(f"Lỗi login {chat_id}: {e}")
        await msg.edit_text(f"❌ Đăng nhập thất bại: {e}")

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await remove_user(chat_id)
    await update.message.reply_text("👋 Đã đăng xuất thành công. Toàn bộ dữ liệu theo dõi của bạn đã bị xóa khỏi hệ thống bot.")

async def require_login(update: Update) -> tuple:
    chat_id = update.effective_chat.id
    user = await get_user(chat_id)
    if not user:
        await update.message.reply_text("❌ Bạn chưa đăng nhập. Vui lòng gõ `/login mssv matkhau`", parse_mode="Markdown")
        return None, None, None
    return user["chat_id"], user["moodle_token"], user["lms_userid"]

async def deadlines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, token, lms_userid = await require_login(update)
    if not token: return
    
    await update.message.reply_text("⏳ Đang đồng bộ dữ liệu từ LMS... Vui lòng đợi nhé!")
    await sync_user_data(chat_id, token, lms_userid, notify=False)
    
    current_time = int(time.time())
    count = 0
    from db.database import pool
    async with pool.acquire() as db:
        rows = await db.fetch(
            "SELECT id, name, course_name, duedate FROM assignments WHERE is_done = FALSE AND duedate > $1 AND chat_id = $2 ORDER BY duedate ASC",
            current_time, chat_id
        )
        for row in rows:
            assign_id, name, course_name, duedate = row["id"], row["name"], row["course_name"], row["duedate"]
            msg = format_deadline_message(
                {"name": name, "duedate": duedate, "cmid": assign_id},
                course_name
            )
            if msg:
                keyboard = get_done_keyboard(assign_id)
                await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
                count += 1
                    
    if count == 0:
        await update.message.reply_text("🎉 Đã đồng bộ xong! Bạn đang KHÔNG có deadline nào chưa nộp.")
    else:
        await update.message.reply_text(f"✅ Đã đồng bộ xong! Bạn có {count} deadline đang chờ nộp.")

async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, token, lms_userid = await require_login(update)
    if not token: return
    
    await update.message.reply_text("⏳ Đang kiểm tra deadline trong 7 ngày tới...")
    current_time = int(time.time())
    week_later = current_time + (7 * 24 * 3600)
    
    count = 0
    from db.database import pool
    async with pool.acquire() as db:
        rows = await db.fetch(
            "SELECT id, name, course_name, duedate FROM assignments WHERE is_done = FALSE AND duedate > $1 AND duedate <= $2 AND chat_id = $3 ORDER BY duedate ASC",
            current_time, week_later, chat_id
        )
        for row in rows:
            assign_id, name, course_name, duedate = row["id"], row["name"], row["course_name"], row["duedate"]
            msg = format_deadline_message(
                {"name": name, "duedate": duedate, "cmid": assign_id},
                course_name
            )
            if msg:
                keyboard = get_done_keyboard(assign_id)
                await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
                count += 1
                    
    if count == 0:
        await update.message.reply_text("🎉 Tuyệt vời! Bạn không có deadline nào trong 7 ngày tới.")

async def grades_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, token, lms_userid = await require_login(update)
    if not token: return
    
    await update.message.reply_text("⏳ Đang tải bảng điểm từ LMS...")
    
    all_courses = await get_enrolled_courses(lms_userid, token)
    if not all_courses:
        await update.message.reply_text("Không tìm thấy môn học nào.")
        return
        
    current_courses = get_current_semester_courses(all_courses)
    course_grades = await get_course_grades(lms_userid, token)
    
    msg = format_grades_overview(current_courses, course_grades)
    keyboard = get_course_grades_keyboard(current_courses)
    
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    user = await get_user(chat_id)
    if not user:
        await query.edit_message_text("❌ Phiên đăng nhập đã hết hạn. Vui lòng gõ `/login` lại.")
        return
        
    token, lms_userid = user["moodle_token"], user["lms_userid"]
    data = query.data
    
    if data.startswith("done_"):
        assign_id = int(data.split("_")[1])
        await mark_done(assign_id, chat_id)
        
        original_text = query.message.text
        new_text = f"✅ **BẠN ĐÃ NỘP BÀI NÀY!**\n\n~{original_text}~"
        await query.edit_message_text(text=new_text, parse_mode="Markdown")
        
    elif data.startswith("grade_"):
        course_id = int(data.split("_")[1])
        course_name = "Môn học"
        for row in query.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data == data:
                    course_name = btn.text.replace("📘 ", "")
                    
        await query.edit_message_text(f"⏳ Đang lấy chi tiết điểm cho môn: {course_name}...")
        grade_items = await get_grade_items(course_id, lms_userid, token)
        msg = format_grade_items(course_name, grade_items)
        await query.edit_message_text(text=msg, parse_mode="Markdown")

async def fallback_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Chào bạn! Mình chỉ hiểu các lệnh bắt đầu bằng dấu `/` thôi nhé.\n"
        "Hãy gõ `/` để xem danh sách lệnh, ví dụ `/login`, `/deadlines`, `/week`."
    )

@app.on_event("startup")
async def startup():
    global application
    if not TOKEN:
        raise ValueError("Chưa cấu hình TELEGRAM_TOKEN")
        
    await init_db()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("logout", logout_command))
    application.add_handler(CommandHandler("deadlines", deadlines_command))
    application.add_handler(CommandHandler("week", week_command))
    application.add_handler(CommandHandler("grades", grades_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_message))
    
    await application.initialize()
    await application.start()
    
    commands = [
        BotCommand("start", "Hướng dẫn sử dụng bot"),
        BotCommand("login", "Đăng nhập LMS"),
        BotCommand("logout", "Đăng xuất khỏi bot"),
        BotCommand("deadlines", "Xem toàn bộ deadline"),
        BotCommand("week", "Xem deadline 7 ngày tới"),
        BotCommand("grades", "Xem điểm học kỳ hiện tại")
    ]
    await application.bot.set_my_commands(commands)
    
    if WEBHOOK_URL:
        webhook_path = f"{WEBHOOK_URL}/telegram"
        await application.bot.set_webhook(webhook_path)
        logger.info(f"Đã set Webhook tại: {webhook_path}")
    else:
        logger.warning("Không có WEBHOOK_URL. Telegram Webhook chưa được thiết lập!")

@app.on_event("shutdown")
async def shutdown():
    if application:
        await application.stop()
        await application.shutdown()

@app.post("/telegram")
async def telegram_webhook(request: Request):
    if not application:
        return Response(status_code=500)
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return Response(status_code=200)

@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "Bot is awake"}

@app.get("/sync")
async def sync_endpoint():
    asyncio.create_task(sync_and_notify())
    return {"status": "ok", "message": "Sync job triggered"}
