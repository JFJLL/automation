import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _admin_headers(client: TestClient) -> dict:
    r = client.post("/api/simple-promo/auth/verify", json={"password": "xinxiliu123"})
    assert r.status_code == 200
    return {"x-admin-token": r.json()["token"]}


def test_sync_task_delete_archives_and_keeps_runs(client):
    headers = _admin_headers(client)
    from app.db import get_db

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tasks (
                name, platform, folder_token, spreadsheet_token, spreadsheet_url,
                update_mode, calibration_days, rrule, status, created_at, updated_at
            ) VALUES ('归档测试任务', 'jzt', 'fld', 'ss', 'https://example.com',
                      'append', 2, 'FREQ=DAILY;BYHOUR=9', 'active', '2026-01-01', '2026-01-01')
            """
        )
        task_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO runs (task_id, trigger_type, started_at, status)
            VALUES (?, 'manual', '2026-01-01T09:00:00', 'success')
            """,
            (task_id,),
        )
        run_id = cur.lastrowid
        conn.commit()

    r = client.delete(f"/api/tasks/{task_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["archived"] is True

    listed = client.get("/api/tasks").json()
    assert all(t["id"] != task_id for t in listed)

    with get_db() as conn:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        assert row["status"] == "archived"
        assert conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone() is not None

    # Archived tasks must not be runnable, editable, or re-activated by stale IDs.
    headers = _admin_headers(client)
    assert client.post(f"/api/tasks/{task_id}/run_now").status_code == 409
    assert client.post(f"/api/tasks/{task_id}/toggle_status").status_code == 409
    assert client.post(
        f"/api/tasks/{task_id}/update",
        json={"name": "不应生效"},
    ).status_code == 409

    audits = client.get("/api/admin/deletion-audits", headers=headers)
    assert audits.status_code == 200
    assert any(a["task_id"] == task_id and a["module"] == "sync" for a in audits.json())

    # A fresh, never-unlocked client must not see the audit trail.
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/admin/deletion-audits").status_code == 401


def test_delete_requires_admin_token(client):
    from app.db import get_db

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tasks (
                name, platform, folder_token, spreadsheet_token, spreadsheet_url,
                update_mode, calibration_days, rrule, status, created_at, updated_at
            ) VALUES ('无权限任务', 'jzt', 'fld', 'ss', 'https://example.com',
                      'append', 2, 'FREQ=DAILY;BYHOUR=9', 'active', '2026-01-01', '2026-01-01')
            """
        )
        task_id = cur.lastrowid
        conn.commit()

    r = client.delete(f"/api/tasks/{task_id}")
    assert r.status_code == 401

    with get_db() as conn:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        assert row["status"] == "active"
