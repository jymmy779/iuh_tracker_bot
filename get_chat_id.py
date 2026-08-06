import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")

def get_updates():
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    print("Đang kiểm tra tin nhắn gửi đến Bot...")
    try:
        response = httpx.get(url)
        data = response.json()
        
        if data.get("ok"):
            results = data.get("result", [])
            if not results:
                print("Chưa có tin nhắn nào! Hãy vào Telegram, tìm Bot của bạn và nhắn '/start' hoặc 'hello', sau đó chạy lại script này.")
                return
                
            for res in results:
                message = res.get("message", {})
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                first_name = chat.get("first_name", "Unknown")
                text = message.get("text", "")
                
                print(f"Bắt được tin nhắn từ {first_name} (Chat ID: {chat_id}): '{text}'")
                print(f"\n=> CHAT ID CỦA BẠN LÀ: {chat_id}")
                print("Hãy copy số này dán vào file .env với biến TELEGRAM_CHAT_ID=...")
                return
        else:
            print("Lỗi từ Telegram API:", data)
    except Exception as e:
        print("Lỗi kết nối:", e)

if __name__ == "__main__":
    get_updates()
