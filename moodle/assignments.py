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
            
            logger.info(f"AssignID {assign_id} status: {status}, full submission data: {submission}")
            
            # Nếu status là 'submitted' hoặc 'graded' (đã chấm điểm)
            # Hoặc có plugin file/onlinetext được upload mà chưa bấm submit (draft) nhưng user coi như đã nộp
            is_done = status in ["submitted", "graded", "draft"]
            
            # Nếu có điểm thì chắc chắn là nộp rồi
            grading_status = last_attempt.get("gradingstatus", "")
            if grading_status in ["graded"]:
                is_done = True
                
            logger.info(f"AssignID {assign_id} is_done: {is_done}")
            return is_done
            
    except Exception as e:
        logger.error(f"Lỗi kết nối khi check status {assign_id}: {e}")
        return False

async def get_activity_completion_statuses(course_id: int, user_id: int, token: str) -> Dict[int, bool]:
    """
    Lấy danh sách trạng thái completion (đánh dấu hoàn thành) của các activity trong một khoá học.
    Trả về dictionary map cmid -> bool (is_completed)
    """
    url = f"{LMS_URL}/webservice/rest/server.php"
    
    params = {
        "wstoken": token,
        "wsfunction": "core_completion_get_activities_completion_status",
        "moodlewsrestformat": "json",
        "courseid": course_id,
        "userid": user_id
    }
    
    try:
        async with get_lms_client(timeout=30.0) as client:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, dict) and "exception" in data:
                # Có thể khoá học không bật tính năng completion
                return {}
                
            result = {}
            statuses = data.get("statuses", [])
            for item in statuses:
                cmid = item.get("cmid")
                state = item.get("state", 0)
                # state > 0 (1: complete, 2: complete pass, 3: complete fail)
                if cmid is not None:
                    result[cmid] = (state > 0)
                    
            return result
    except Exception as e:
        logger.error(f"Lỗi lấy completion status course {course_id}: {e}")
        return {}
