import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

LMS_URL = os.getenv("LMS_URL")

logger = logging.getLogger(__name__)

async def get_moodle_token(username: str, password: str) -> str:
    url = f"{LMS_URL}/login/token.php"
    params = {
        "username": username,
        "password": password,
        "service": "moodle_mobile_app"
    }

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        try:
            logger.info("Đang lấy token mới từ LMS...")
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "token" in data:
                logger.info("Lấy token thành công!")
                return data["token"]
            else:
                logger.error(f"Lỗi đăng nhập: {data}")
                raise Exception("Không lấy được token. Sai tài khoản hoặc mật khẩu.")
        except Exception as e:
            logger.error(f"Lỗi khi kết nối LMS: {e}")
            raise
