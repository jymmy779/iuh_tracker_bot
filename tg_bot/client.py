import os
import logging
from telegram import Bot
from telegram.constants import ParseMode
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")

logger = logging.getLogger(__name__)

async def send_telegram_message(chat_id: int, text: str, reply_markup=None) -> bool:
    """
    Gửi tin nhắn qua Telegram
    """
    if not TOKEN or not chat_id:
        logger.warning("Bỏ qua gửi Telegram do thiếu TOKEN hoặc chat_id")
        return False
        
    try:
        bot = Bot(token=TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        logger.info(f"Đã gửi tin nhắn đến Telegram chat_id {chat_id} thành công.")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi gửi tin nhắn Telegram: {e}")
        return False
