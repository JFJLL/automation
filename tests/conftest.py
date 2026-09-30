import os
import sys
import tempfile
import sqlite3
import pytest
from pathlib import Path

# 确保 repo root 和 sync_console 在 sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SYNC_CONSOLE_DIR = REPO_ROOT / "sync_console"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SYNC_CONSOLE_DIR) not in sys.path:
    sys.path.insert(0, str(SYNC_CONSOLE_DIR))

# 创建全局测试临时目录并在任何应用模块导入前注入环境变量
_TEST_TMP_DIR = tempfile.TemporaryDirectory()
_TMP_PATH = Path(_TEST_TMP_DIR.name)

_TEST_SYNC_DB = _TMP_PATH / "isolated_sync_test.db"
_TEST_KEYWORD_DB = _TMP_PATH / "isolated_keyword_test.db"

os.environ["SYNC_DB_PATH"] = str(_TEST_SYNC_DB)
os.environ["KEYWORD_DB_PATH"] = str(_TEST_KEYWORD_DB)
os.environ["AUTH_MODE"] = "token"
os.environ["ACCESS_TOKEN"] = "test_admin_token_2026"
os.environ["SESSION_SECRET"] = "test-session-secret-32-bytes-long-key-12345"
os.environ["TIMEZONE"] = "Asia/Shanghai"

from core.database import get_db_connection, run_migrations

# 初始化测试数据库结构
conn_s = get_db_connection(_TEST_SYNC_DB)
run_migrations(conn_s, module="sync")
conn_s.close()

conn_k = get_db_connection(_TEST_KEYWORD_DB)
run_migrations(conn_k, module="keyword")
conn_k.close()

@pytest.fixture(scope="session", autouse=True)
def guard_production_database():
    """
    零污染保护：记录生产真实数据库的状态，并在所有测试跑完后断言生产库未受任何污染。
    """
    prod_dbs = [
        SYNC_CONSOLE_DIR / "data" / "sync_console.db",
        SYNC_CONSOLE_DIR / "data" / "keyword_data.db",
        REPO_ROOT / "keyword_service" / "keyword_data.db"
    ]
    initial_stats = {}
    for p in prod_dbs:
        if p.exists():
            initial_stats[str(p)] = (p.stat().st_mtime, p.stat().st_size)

    yield

    for p in prod_dbs:
        if p.exists() and str(p) in initial_stats:
            init_mtime, init_size = initial_stats[str(p)]
            curr_size = p.stat().st_size
            # 允许只读操作，但文件大小和实际数据记录绝不增加
            assert curr_size == init_size, f"生产数据库被测试修改污染: {p}"

