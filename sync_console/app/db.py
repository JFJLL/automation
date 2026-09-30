import sqlite3
from app.config import DB_PATH
from core.database import get_sync_db, run_migrations

def get_db():
    return get_sync_db(DB_PATH)

def init_db():
    conn = get_db()
    run_migrations(conn, module="sync")

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
