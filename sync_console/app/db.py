import sqlite3
import json
from datetime import datetime
from app.config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            folder_token TEXT,
            spreadsheet_token TEXT NOT NULL,
            spreadsheet_url TEXT NOT NULL,
            update_mode TEXT NOT NULL DEFAULT 'append', -- 'append' 或 'overwrite'
            calibration_days INTEGER NOT NULL DEFAULT 2,
            rrule TEXT NOT NULL,
            sub_account_id TEXT,
            sub_account_name TEXT,
            status TEXT NOT NULL DEFAULT 'active', -- 'active', 'paused', 'archived'
            next_run_at TEXT,
            last_run_at TEXT,
            last_status TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        cursor.execute("PRAGMA table_info(tasks)")
        task_cols = [row[1] for row in cursor.fetchall()]
        if "sub_account_id" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN sub_account_id TEXT")
        if "sub_account_name" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN sub_account_name TEXT")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_sheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            sheet_title TEXT NOT NULL,
            worksheet_id TEXT NOT NULL,
            dimension TEXT,
            id_column TEXT NOT NULL,
            date_column TEXT NOT NULL DEFAULT '日期',
            header_json TEXT NOT NULL,
            column_map_json TEXT NOT NULL,
            entity_ids_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            trigger_type TEXT NOT NULL, -- 'scheduled', 'manual', 'preview_commit'
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL, -- 'running', 'success', 'failed'
            rows_fetched INTEGER DEFAULT 0,
            rows_appended INTEGER DEFAULT 0,
            rows_updated INTEGER DEFAULT 0,
            message TEXT,
            error_detail TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            worksheet_id TEXT NOT NULL,
            backup_path TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
