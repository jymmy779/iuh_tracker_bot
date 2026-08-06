import asyncpg
import logging
import os

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL")
pool = None

async def init_db():
    global pool
    if not DB_URL:
        logger.error("Chưa cấu hình DATABASE_URL trong .env!")
        return
        
    pool = await asyncpg.create_pool(DB_URL)
    
    async with pool.acquire() as db:
        # Create tables if not exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id BIGINT PRIMARY KEY,
                moodle_token TEXT NOT NULL,
                lms_userid BIGINT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS assignments (
                id BIGINT,
                chat_id BIGINT,
                name TEXT NOT NULL,
                course_name TEXT NOT NULL,
                duedate BIGINT NOT NULL,
                reminded_7d BOOLEAN DEFAULT FALSE,
                reminded_3d BOOLEAN DEFAULT FALSE,
                reminded_1d BOOLEAN DEFAULT FALSE,
                reminded_3h BOOLEAN DEFAULT FALSE,
                is_done BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (id, chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS grades (
                id BIGINT,
                chat_id BIGINT,
                course_id BIGINT NOT NULL,
                item_name TEXT NOT NULL,
                grade_formatted TEXT,
                PRIMARY KEY (course_id, item_name, chat_id)
            )
        """)
        logger.info("Database PostgreSQL initialized.")

async def add_or_update_user(chat_id: int, moodle_token: str, lms_userid: int):
    async with pool.acquire() as db:
        await db.execute("""
            INSERT INTO users (chat_id, moodle_token, lms_userid) 
            VALUES ($1, $2, $3)
            ON CONFLICT(chat_id) DO UPDATE SET
            moodle_token=EXCLUDED.moodle_token,
            lms_userid=EXCLUDED.lms_userid
        """, chat_id, moodle_token, lms_userid)

async def get_user(chat_id: int):
    async with pool.acquire() as db:
        return await db.fetchrow("SELECT chat_id, moodle_token, lms_userid FROM users WHERE chat_id = $1", chat_id)

async def get_all_users():
    async with pool.acquire() as db:
        return await db.fetch("SELECT chat_id, moodle_token, lms_userid FROM users")

async def remove_user(chat_id: int):
    async with pool.acquire() as db:
        await db.execute("DELETE FROM users WHERE chat_id = $1", chat_id)
        await db.execute("DELETE FROM assignments WHERE chat_id = $1", chat_id)
        await db.execute("DELETE FROM grades WHERE chat_id = $1", chat_id)

async def get_known_grades(course_id: int, chat_id: int):
    async with pool.acquire() as db:
        rows = await db.fetch("SELECT item_name, grade_formatted FROM grades WHERE course_id = $1 AND chat_id = $2", course_id, chat_id)
        return {row["item_name"]: row["grade_formatted"] for row in rows}

async def insert_or_update_grade(item_id: int, course_id: int, item_name: str, grade_formatted: str, chat_id: int):
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT item_name FROM grades WHERE course_id = $1 AND item_name = $2 AND chat_id = $3", course_id, item_name, chat_id)
        if row is None:
            await db.execute(
                "INSERT INTO grades (id, chat_id, course_id, item_name, grade_formatted) VALUES ($1, $2, $3, $4, $5)",
                item_id, chat_id, course_id, item_name, grade_formatted
            )
        else:
            await db.execute(
                "UPDATE grades SET grade_formatted = $1, id = $2 WHERE course_id = $3 AND item_name = $4 AND chat_id = $5",
                grade_formatted, item_id, course_id, item_name, chat_id
            )

async def insert_or_update_assignment(assign_id: int, name: str, course_name: str, duedate: int, chat_id: int):
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT id, duedate FROM assignments WHERE id = $1 AND chat_id = $2", assign_id, chat_id)
        
        if row is None:
            await db.execute(
                "INSERT INTO assignments (id, chat_id, name, course_name, duedate) VALUES ($1, $2, $3, $4, $5)",
                assign_id, chat_id, name, course_name, duedate
            )
        elif row["duedate"] != duedate:
            await db.execute(
                """UPDATE assignments 
                   SET name = $1, course_name = $2, duedate = $3, 
                       reminded_7d = FALSE, reminded_3d = FALSE, reminded_1d = FALSE, reminded_3h = FALSE 
                   WHERE id = $4 AND chat_id = $5""",
                name, course_name, duedate, assign_id, chat_id
            )
        else:
            await db.execute(
                "UPDATE assignments SET name = $1, course_name = $2 WHERE id = $3 AND chat_id = $4",
                name, course_name, assign_id, chat_id
            )

async def get_pending_reminders(current_time: int):
    query = """
        SELECT id, chat_id, name, course_name, duedate, reminded_7d, reminded_3d, reminded_1d, reminded_3h
        FROM assignments
        WHERE is_done = FALSE AND duedate > $1
    """
    
    pending = []
    async with pool.acquire() as db:
        rows = await db.fetch(query, current_time)
        for row in rows:
            assign_id, chat_id, name, course_name, duedate, r7, r3, r1, r3h = row["id"], row["chat_id"], row["name"], row["course_name"], row["duedate"], row["reminded_7d"], row["reminded_3d"], row["reminded_1d"], row["reminded_3h"]
            
            time_left = duedate - current_time
            days_left = time_left / (24 * 3600)
            hours_left = time_left / 3600
            
            needs_remind = False
            remind_type = ""
            
            if days_left <= 7 and not r7:
                needs_remind, remind_type = True, "reminded_7d"
            if days_left <= 3 and not r3:
                needs_remind, remind_type = True, "reminded_3d"
            if days_left <= 1 and not r1:
                needs_remind, remind_type = True, "reminded_1d"
            if hours_left <= 3 and not r3h:
                needs_remind, remind_type = True, "reminded_3h"
                
            if needs_remind:
                pending.append({
                    "id": assign_id,
                    "chat_id": chat_id,
                    "name": name,
                    "course_name": course_name,
                    "duedate": duedate,
                    "remind_type": remind_type
                })
    return pending

async def mark_reminded(assign_id: int, chat_id: int, remind_type: str):
    valid_columns = ["reminded_7d", "reminded_3d", "reminded_1d", "reminded_3h"]
    if remind_type not in valid_columns:
        return
        
    if remind_type == "reminded_3h":
        query = "UPDATE assignments SET reminded_3h = TRUE, reminded_1d = TRUE, reminded_3d = TRUE, reminded_7d = TRUE WHERE id = $1 AND chat_id = $2"
    elif remind_type == "reminded_1d":
        query = "UPDATE assignments SET reminded_1d = TRUE, reminded_3d = TRUE, reminded_7d = TRUE WHERE id = $1 AND chat_id = $2"
    elif remind_type == "reminded_3d":
        query = "UPDATE assignments SET reminded_3d = TRUE, reminded_7d = TRUE WHERE id = $1 AND chat_id = $2"
    else:
        query = "UPDATE assignments SET reminded_7d = TRUE WHERE id = $1 AND chat_id = $2"
        
    async with pool.acquire() as db:
        await db.execute(query, assign_id, chat_id)

async def mark_done(assign_id: int, chat_id: int):
    async with pool.acquire() as db:
        await db.execute("UPDATE assignments SET is_done = TRUE WHERE id = $1 AND chat_id = $2", assign_id, chat_id)
