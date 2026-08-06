import logging
from typing import List, Dict
from .auth import LMS_URL
from proxy_manager import get_lms_client

logger = logging.getLogger(__name__)

async def get_assignments(course_ids: List[int], token: str) -> List[Dict]:
    """
    Lấy danh sách các bài tập (assignments/deadlines) của các môn học
    """
    url = f"{LMS_URL}/webservice/rest/server.php"
    
    params = {
        "wstoken": token,
        "wsfunction": "mod_assign_get_assignments",
        "moodlewsrestformat": "json"
    }
    
    # Moodle API yêu cầu format array cho tham số courseids: courseids[0]=1, courseids[1]=2...
    for i, course_id in enumerate(course_ids):
        params[f"courseids[{i}]"] = course_id

    async with get_lms_client(timeout=30.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, dict) and "exception" in data:
            logger.error(f"Lỗi API LMS: {data['message']}")
            return []
            
        # Data trả về là dict chứa key "courses", bên trong là list các course, mỗi course có list "assignments"
        assignments = []
        if "courses" in data:
            for course in data["courses"]:
                for assign in course.get("assignments", []):
                    # Thêm course_name hoặc id vào để dễ tra cứu sau này (moodle trả về course ID trong từng assign)
                    assignments.append(assign)
                    
        return assignments

async def check_submission_status(assign_id: int, token: str) -> bool:
    """
    Kiểm tra xem assignment đã được nộp chưa.
    Trả về True nếu đã nộp hoặc đã chấm điểm, False nếu chưa nộp.
    """
    url = f"{LMS_URL}/webservice/rest/server.php"
    
    params = {
        "wstoken": token,
        "wsfunction": "mod_assign_get_submission_status",
        "moodlewsrestformat": "json",
        "assignid": assign_id
    }
    
    try:
        async with get_lms_client(timeout=30.0) as client:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, dict) and "exception" in data:
                logger.error(f"Lỗi API LMS khi check status {assign_id}: {data['message']}")
                return False
                
            # Lấy trạng thái
            last_attempt = data.get("lastattempt", {})
            submission = last_attempt.get("submission", {})
            status = submission.get("status", "")
            
            # Nếu status là 'submitted' hoặc 'graded' (đã chấm điểm)
            return status in ["submitted", "graded"]
            
    except Exception as e:
        logger.error(f"Lỗi kết nối khi check status {assign_id}: {e}")
        return False
