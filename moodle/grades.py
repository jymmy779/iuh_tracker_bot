from .auth import LMS_URL
import logging
from proxy_manager import get_lms_client

logger = logging.getLogger(__name__)

async def get_course_grades(user_id: int, token: str):
    """
    Lấy điểm tổng quát của tất cả các môn học
    Trả về dict: {course_id: grade_formatted}
    """
    params = {
        "wstoken": token,
        "wsfunction": "gradereport_overview_get_course_grades",
        "moodlewsrestformat": "json",
        "userid": user_id
    }
    
    try:
        async with get_lms_client(timeout=30.0) as client:
            response = await client.get(f"{LMS_URL}/webservice/rest/server.php", params=params)
            data = response.json()
        
        result = {}
        for item in data.get("grades", []):
            result[item["courseid"]] = item.get("grade", "-")
            
        return result
    except Exception as e:
        logger.error(f"Error fetching course grades: {e}")
        return {}

async def get_grade_items(course_id: int, user_id: int, token: str):
    """
    Lấy điểm chi tiết từng cột của một môn học
    Trả về danh sách các grade item
    """
    params = {
        "wstoken": token,
        "wsfunction": "gradereport_user_get_grade_items",
        "moodlewsrestformat": "json",
        "userid": user_id,
        "courseid": course_id
    }
    
    try:
        async with get_lms_client(timeout=30.0) as client:
            response = await client.get(f"{LMS_URL}/webservice/rest/server.php", params=params)
            data = response.json()
        
        items = []
        usergrades = data.get("usergrades", [])
        if usergrades:
            for item in usergrades[0].get("gradeitems", []):
                # Bỏ qua các cột không có tên (thường là điểm tổng kết môn - course type)
                if item.get("itemname") is None and item.get("itemtype") != "course":
                    continue
                items.append(item)
                
        return items
    except Exception as e:
        logger.error(f"Error fetching grade items for course {course_id}: {e}")
        return []
