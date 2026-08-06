import os
import logging
import httpx

logger = logging.getLogger(__name__)

_proxies = []
_current_index = 0

def load_proxies():
    """Đọc danh sách proxy từ .env, hỗ trợ HTTP, SOCKS4, SOCKS5."""
    global _proxies
    raw = os.getenv("VN_PROXIES", "")
    if not raw:
        logger.warning("Không tìm thấy VN_PROXIES trong .env. Bot sẽ kết nối LMS trực tiếp (có thể bị chặn).")
        return
    entries = [p.strip() for p in raw.split(",") if p.strip()]
    for entry in entries:
        # Tự thêm prefix http:// nếu người dùng chỉ gõ ip:port
        if not entry.startswith(("http://", "https://", "socks4://", "socks5://")):
            entry = "http://" + entry
        _proxies.append(entry)
    logger.info(f"Đã tải {len(_proxies)} proxy VN: {[p[:20]+'...' for p in _proxies]}")

def get_lms_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """
    Trả về httpx.AsyncClient đã được cấu hình với proxy VN.
    Tự động xoay vòng sang proxy tiếp theo mỗi lần gọi.
    """
    global _current_index
    if not _proxies:
        return httpx.AsyncClient(verify=False, timeout=timeout)
    
    proxy = _proxies[_current_index % len(_proxies)]
    _current_index += 1
    logger.debug(f"Dùng proxy: {proxy[:25]}...")
    return httpx.AsyncClient(proxy=proxy, verify=False, timeout=timeout)
