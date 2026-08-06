import os
import httpx
from dotenv import load_dotenv
import sys
# Add parent directory to path to import moodle
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from moodle.auth import get_moodle_token

load_dotenv()

BASE_URL = "https://lms.iuh.edu.vn/webservice/rest/server.php"

import asyncio

async def test_grades():
    token = await get_moodle_token()
    params = {
        "wstoken": token,
        "wsfunction": "gradereport_user_get_grade_items",
        "moodlewsrestformat": "json",
        "userid": 1706769,
        "courseid": 45900
    }
    
    response = httpx.get(BASE_URL, params=params, verify=False)
    data = response.json()
    import json
    print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(test_grades())
