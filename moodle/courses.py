import httpx
import logging
from typing import List, Dict
from .auth import LMS_URL

logger = logging.getLogger(__name__)

async def get_enrolled_courses(user_id: int, token: str) -> List[Dict]:
    """
    Lấy danh sách các môn học (courses) mà user đang học
    """
    url = f"{LMS_URL}/webservice/rest/server.php"
    
    params = {
        "wstoken": token,
        "wsfunction": "core_enrol_get_users_courses",
        "userid": user_id,
        "moodlewsrestformat": "json"
    }

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, dict) and "exception" in data:
            logger.error(f"Lỗi API LMS: {data['message']}")
            return []
            
        return data

import re

def get_current_semester_courses(courses: List[Dict]) -> List[Dict]:
    """
    Tự động phân tích shortname để tìm học kỳ mới nhất và lọc các môn thuộc học kỳ đó.
    Ví dụ shortname: 420300362101_HK1_2026_-_2027
    """
    semester_pattern = re.compile(r"HK(\d+)_(\d{4})")
    
    # Extract (year, semester, course)
    course_semesters = []
    for c in courses:
        shortname = c.get("shortname", "")
        match = semester_pattern.search(shortname)
        if match:
            hk = int(match.group(1))
            year = int(match.group(2))
            course_semesters.append((year, hk, c))
        else:
            # Nếu không parse được, có thể môn này cấu trúc khác, lưu tạm với (0,0)
            course_semesters.append((0, 0, c))
            
    if not course_semesters:
        return courses
        
    # Tìm year lớn nhất, sau đó hk lớn nhất
    max_year = max([cs[0] for cs in course_semesters])
    if max_year == 0:
        return courses
        
    max_hk = max([cs[1] for cs in course_semesters if cs[0] == max_year])
    
    # Lọc ra các môn thuộc học kỳ mới nhất
    current_courses = [cs[2] for cs in course_semesters if cs[0] == max_year and cs[1] == max_hk]
    return current_courses

async def get_site_info(token: str) -> Dict:
    """
    Lấy thông tin chung của site và user (để lấy userid)
    """
    url = f"{LMS_URL}/webservice/rest/server.php"
    
    params = {
        "wstoken": token,
        "wsfunction": "core_webservice_get_site_info",
        "moodlewsrestformat": "json"
    }

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        return data
