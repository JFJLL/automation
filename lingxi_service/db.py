import sqlite3
from pathlib import Path
from core.database import get_lingxi_db, run_migrations, LINGXI_DB_PATH

DB_PATH = LINGXI_DB_PATH

def get_db():
    return get_lingxi_db()

def init_db():
    conn = get_db()
    run_migrations(conn, module="lingxi")

if __name__ == "__main__":
    init_db()
    print("Lingxi database initialized at", DB_PATH)
