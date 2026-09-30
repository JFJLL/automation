import tempfile
from pathlib import Path
from core.database import (
    get_db_connection,
    run_migrations,
    acquire_task_lease,
    release_task_lease
)

def test_sqlite_pragmas_and_migrations():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_app.db"
        conn = get_db_connection(db_file)
        
        # Verify foreign keys ON
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk == 1
        
        # Verify journal mode WAL
        jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert jm.upper() == "WAL"
        
        # Run migrations
        run_migrations(conn, module="sync")
        run_migrations(conn, module="keyword")
        
        # Re-running migrations should be idempotent
        run_migrations(conn, module="sync")
        run_migrations(conn, module="keyword")
        
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
        assert "tasks" in tables
        assert "runs" in tables
        assert "task_leases" in tables
        assert "keyword_tasks" in tables
        assert "keyword_runs" in tables
        conn.close()

def test_task_lease_concurrency():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_lease.db"
        conn = get_db_connection(db_file)
        run_migrations(conn, module="sync")
        
        # 1. Acquire lease
        acquired = acquire_task_lease(conn, "sync_task_1", owner="proc_A", lease_seconds=10)
        assert acquired is True
        
        # 2. Second acquire fails while lease active
        acquired2 = acquire_task_lease(conn, "sync_task_1", owner="proc_B", lease_seconds=10)
        assert acquired2 is False
        
        # 3. Release lease
        release_task_lease(conn, "sync_task_1")
        
        # 4. Now acquire succeeds
        acquired3 = acquire_task_lease(conn, "sync_task_1", owner="proc_B", lease_seconds=10)
        assert acquired3 is True
        conn.close()
