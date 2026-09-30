import sqlite3
from datetime import timedelta

import pytest
from core.business_time import now_business_tz
from core.database import acquire_task_lease, release_task_lease, renew_task_lease, run_migrations


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn, module="sync")
    yield conn
    conn.close()

def test_lease_concurrency_race(db_conn):
    # 第一个 worker 获取锁成功
    ok1 = acquire_task_lease(db_conn, "task_100", owner="worker_A", lease_seconds=600)
    assert ok1 is True

    # 并发竞争：第二个 worker 获取失败
    ok2 = acquire_task_lease(db_conn, "task_100", owner="worker_B", lease_seconds=600)
    assert ok2 is False

def test_lease_expiration_and_owner_isolation(db_conn):
    # 模拟获取一个已过期的锁 (过期时间在过去)
    past = (now_business_tz() - timedelta(seconds=10)).isoformat()
    with db_conn:
        db_conn.execute(
            "INSERT INTO task_leases (task_key, owner, acquired_at, expires_at) VALUES ('task_expired', 'worker_A', ?, ?)",
            (past, past)
        )

    # worker_B 成功抢到过期锁
    ok_b = acquire_task_lease(db_conn, "task_expired", owner="worker_B", lease_seconds=600)
    assert ok_b is True

    # 旧 owner (worker_A) 尝试释放锁，不能误删 worker_B 的锁！
    release_task_lease(db_conn, "task_expired", owner="worker_A")
    cur = db_conn.cursor()
    cur.execute("SELECT owner FROM task_leases WHERE task_key = 'task_expired'")
    row = cur.fetchone()
    assert row is not None
    assert row["owner"] == "worker_B"

    # 正确的 owner 释放成功
    release_task_lease(db_conn, "task_expired", owner="worker_B")
    cur.execute("SELECT owner FROM task_leases WHERE task_key = 'task_expired'")
    assert cur.fetchone() is None

def test_lease_renew(db_conn):
    acquire_task_lease(db_conn, "task_renew", owner="worker_A", lease_seconds=100)
    ok = renew_task_lease(db_conn, "task_renew", owner="worker_A", lease_seconds=500)
    assert ok is True

    # 错误 owner 续租失败
    bad = renew_task_lease(db_conn, "task_renew", owner="wrong_worker", lease_seconds=500)
    assert bad is False
