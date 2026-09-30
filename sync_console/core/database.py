import sqlite3
import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from app.config import DATA_DIR, DB_PATH

KEYWORD_DB_PATH = Path(os.getenv("KEYWORD_DB_PATH", str(DATA_DIR / "keyword_data.db")))
LINGXI_DB_PATH = Path(os.getenv("LINGXI_DB_PATH", str(DATA_DIR / "lingxi_data.db")))

def get_db_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

def get_sync_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    return get_db_connection(path)

def get_keyword_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    if db_path:
        return get_db_connection(db_path)
    
    # 优先使用配置的 DATA_DIR / keyword_data.db；若不存在但旧目录存在，则迁移/复用
    if not KEYWORD_DB_PATH.exists():
        legacies = [
            BASE_DIR / "keyword_service" / "keyword_data.db",
            BASE_DIR.parent / "keyword_service" / "keyword_data.db",
            Path(__file__).resolve().parent.parent.parent / "keyword_service" / "keyword_data.db"
        ]
        for legacy in legacies:
            if legacy.exists():
                try:
                    import shutil
                    KEYWORD_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(legacy, KEYWORD_DB_PATH)
                    break
                except Exception:
                    return get_db_connection(legacy)
    return get_db_connection(KEYWORD_DB_PATH)

def get_lingxi_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    if db_path:
        return get_db_connection(db_path)
    return get_db_connection(LINGXI_DB_PATH)

def run_migrations(conn: sqlite3.Connection, module: str = "sync"):
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER NOT NULL,
                module TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                PRIMARY KEY (version, module)
            )
        """)
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_migrations WHERE module = ?", (module,))
        applied = {r[0] for r in cur.fetchall()}

        if module == "sync":
            # Migration 1: Base tables
            if 1 not in applied:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    folder_token TEXT,
                    spreadsheet_token TEXT NOT NULL,
                    spreadsheet_url TEXT NOT NULL,
                    update_mode TEXT NOT NULL DEFAULT 'append',
                    calibration_days INTEGER NOT NULL DEFAULT 2,
                    rrule TEXT NOT NULL,
                    sub_account_id TEXT,
                    sub_account_name TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    next_run_at TEXT,
                    last_run_at TEXT,
                    last_status TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """)
                conn.execute("""
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
                conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    trigger_type TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    rows_fetched INTEGER DEFAULT 0,
                    rows_appended INTEGER DEFAULT 0,
                    rows_updated INTEGER DEFAULT 0,
                    message TEXT,
                    error_detail TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
                """)
                conn.execute("""
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
                conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """)
                conn.execute("INSERT INTO schema_migrations (version, module, applied_at) VALUES (1, 'sync', ?)", (datetime.now().isoformat(),))

            # Migration 2: Task leases for concurrency guard
            if 2 not in applied:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS task_leases (
                    task_key TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """)
                conn.execute("INSERT INTO schema_migrations (version, module, applied_at) VALUES (2, 'sync', ?)", (datetime.now().isoformat(),))

            # Migration 3: Observability columns in runs table
            if 3 not in applied:
                cur.execute("PRAGMA table_info(runs)")
                cols = [r[1] for r in cur.fetchall()]
                if "duration_ms" not in cols:
                    conn.execute("ALTER TABLE runs ADD COLUMN duration_ms INTEGER DEFAULT 0")
                if "provider_status" not in cols:
                    conn.execute("ALTER TABLE runs ADD COLUMN provider_status TEXT DEFAULT 'ok'")
                if "rollback_status" not in cols:
                    conn.execute("ALTER TABLE runs ADD COLUMN rollback_status TEXT")
                conn.execute("INSERT INTO schema_migrations (version, module, applied_at) VALUES (3, 'sync', ?)", (datetime.now().isoformat(),))

        elif module == "keyword":
            # Migration 1: Base tables
            if 1 not in applied:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS keyword_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    removed_keywords_json TEXT NOT NULL DEFAULT '[]',
                    folder_token TEXT,
                    spreadsheet_token TEXT NOT NULL,
                    spreadsheet_url TEXT NOT NULL,
                    update_mode TEXT NOT NULL DEFAULT 'overwrite',
                    days_range INTEGER NOT NULL DEFAULT 90,
                    rrule TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    next_run_at TEXT,
                    last_run_at TEXT,
                    last_status TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS keyword_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    task_name TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    keywords_count INTEGER DEFAULT 0,
                    days_count INTEGER DEFAULT 0,
                    spreadsheet_url TEXT,
                    message TEXT,
                    error_detail TEXT
                )
                """)
                conn.execute("INSERT INTO schema_migrations (version, module, applied_at) VALUES (1, 'keyword', ?)", (datetime.now().isoformat(),))

            # Migration 2: Observability columns
            if 2 not in applied:
                cur.execute("PRAGMA table_info(keyword_runs)")
                cols = [r[1] for r in cur.fetchall()]
                if "duration_ms" not in cols:
                    conn.execute("ALTER TABLE keyword_runs ADD COLUMN duration_ms INTEGER DEFAULT 0")
                if "successful_keywords" not in cols:
                    conn.execute("ALTER TABLE keyword_runs ADD COLUMN successful_keywords TEXT")
                if "empty_keywords" not in cols:
                    conn.execute("ALTER TABLE keyword_runs ADD COLUMN empty_keywords TEXT")
                if "failed_keywords" not in cols:
                    conn.execute("ALTER TABLE keyword_runs ADD COLUMN failed_keywords TEXT")
                conn.execute("INSERT INTO schema_migrations (version, module, applied_at) VALUES (2, 'keyword', ?)", (datetime.now().isoformat(),))

            # Migration 3: Keyword task leases
            if 3 not in applied:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS task_leases (
                    task_key TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """)
                conn.execute("INSERT INTO schema_migrations (version, module, applied_at) VALUES (3, 'keyword', ?)", (datetime.now().isoformat(),))

        elif module == "lingxi":
            # Migration 1: Base tables for lingxi keyword tasks
            if 1 not in applied:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS lingxi_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    removed_keywords_json TEXT NOT NULL DEFAULT '[]',
                    folder_token TEXT,
                    spreadsheet_token TEXT NOT NULL,
                    spreadsheet_url TEXT NOT NULL,
                    update_mode TEXT NOT NULL DEFAULT 'overwrite',
                    rrule TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    next_run_at TEXT,
                    last_run_at TEXT,
                    last_status TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS lingxi_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    task_name TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    keywords_count INTEGER DEFAULT 0,
                    duration_ms INTEGER DEFAULT 0,
                    successful_keywords TEXT,
                    empty_keywords TEXT,
                    failed_keywords TEXT,
                    spreadsheet_url TEXT,
                    message TEXT,
                    error_detail TEXT
                )
                """)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS task_leases (
                    task_key TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """)
                conn.execute("INSERT INTO schema_migrations (version, module, applied_at) VALUES (1, 'lingxi', ?)", (datetime.now().isoformat(),))

def acquire_task_lease(conn: sqlite3.Connection, task_key: str, owner: str = "worker", lease_seconds: int = 600) -> bool:
    """
    获取任务并发排他锁 (基于 SQLite lease 表)
    如果锁已被其他运行占用且未过期，返回 False
    如果锁不存在或已过期，原子性获取并返回 True
    """
    now_dt = datetime.now()
    now_str = now_dt.isoformat()
    expires_str = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
    with conn:
        cur = conn.cursor()
        cur.execute("SELECT owner, expires_at FROM task_leases WHERE task_key = ?", (task_key,))
        row = cur.fetchone()
        if row:
            current_expires = row[1]
            if current_expires > now_str:
                return False # Still active lease
            # Lease expired, overwrite
            cur.execute(
                "UPDATE task_leases SET owner = ?, acquired_at = ?, expires_at = ? WHERE task_key = ?",
                (owner, now_str, expires_str, task_key)
            )
            return True
        else:
            try:
                cur.execute(
                    "INSERT INTO task_leases (task_key, owner, acquired_at, expires_at) VALUES (?, ?, ?, ?)",
                    (task_key, owner, now_str, expires_str)
                )
                return True
            except sqlite3.IntegrityError:
                return False

def release_task_lease(conn: sqlite3.Connection, task_key: str):
    try:
        with conn:
            conn.execute("DELETE FROM task_leases WHERE task_key = ?", (task_key,))
    except Exception:
        pass
