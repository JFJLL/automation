import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "keyword_data.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            keywords_json TEXT NOT NULL,
            removed_keywords_json TEXT NOT NULL DEFAULT '[]',
            folder_token TEXT,
            spreadsheet_token TEXT NOT NULL,
            spreadsheet_url TEXT NOT NULL,
            update_mode TEXT NOT NULL DEFAULT 'overwrite', -- 'overwrite' 或 'append'
            days_range INTEGER NOT NULL DEFAULT 90,
            rrule TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', -- 'active', 'paused', 'archived'
            next_run_at TEXT,
            last_run_at TEXT,
            last_status TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            task_name TEXT NOT NULL,
            trigger_type TEXT NOT NULL, -- 'direct_create', 'manual', 'scheduled'
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL, -- 'running', 'success', 'failed'
            keywords_count INTEGER DEFAULT 0,
            days_count INTEGER DEFAULT 0,
            spreadsheet_url TEXT,
            message TEXT,
            error_detail TEXT
        )
        """)
        cursor.execute("PRAGMA table_info(keyword_tasks)")
        cols = [r[1] for r in cursor.fetchall()]
        if "removed_keywords_json" not in cols:
            cursor.execute("ALTER TABLE keyword_tasks ADD COLUMN removed_keywords_json TEXT NOT NULL DEFAULT '[]'")
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("Keyword database initialized at", DB_PATH)

