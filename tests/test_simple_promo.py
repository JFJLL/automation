# -*- coding: utf-8 -*-
import pytest
import json
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from sync_console.app.main import app
from sync_console.core.database import get_simple_promo_db, run_migrations
from sync_console.simple_promo.seed import seed_simple_promo_data
from sync_console.simple_promo.engine import (
    parse_cutoff_timestamp,
    parse_note_publish_time,
    DEFAULT_CUTOFF_STR
)

@pytest.fixture(autouse=True)
def init_promo_data():
    conn = get_simple_promo_db()
    run_migrations(conn, module="simple_promo")
    seed_simple_promo_data(conn)

@pytest.fixture
def client():
    return TestClient(app)

def test_cutoff_parser():
    dt, ts = parse_cutoff_timestamp("2026-01-01 00:00:00")
    assert dt.year == 2026
    assert dt.month == 1
    assert dt.day == 1
    # Timestamp for 2026-01-01 00:00:00 CST (UTC+8) is 1767196800
    assert ts == 1767196800

def test_note_publish_time_parser():
    cutoff_ts = 1767196800
    # 68625ca4000000000d019ace -> hex 68625ca4 = 1751275684 (2025-06-30 17:45:08 CST)
    info = parse_note_publish_time("68625ca4000000000d019ace", cutoff_ts)
    assert info["is_pre_cutoff"] is True
    assert info["year"] == 2025
    assert "2025-06-30" in info["datetime_str"]

    # Post cutoff test (future timestamp in 2026)
    # hex 696e7000 = 1768845312 (mid Jan 2026)
    info_post = parse_note_publish_time("696e70000000000000000000", cutoff_ts)
    assert info_post["is_pre_cutoff"] is False
    assert info_post["year"] == 2026

def test_auth_verify_api(client):
    # 1. Incorrect password
    r_fail = client.post("/api/simple-promo/auth/verify", json={"password": "wrong_password_999"})
    assert r_fail.status_code == 400

    # 2. Correct password (xinxiliu123)
    r_ok = client.post("/api/simple-promo/auth/verify", json={"password": "xinxiliu123"})
    assert r_ok.status_code == 200
    token = r_ok.json().get("token")
    assert token is not None

    # 3. Auth status with token
    r_status = client.get("/api/simple-promo/auth/status", headers={"x-simple-promo-token": token})
    assert r_status.status_code == 200
    assert r_status.json()["unlocked"] is True

def test_subaccounts_listing_api(client):
    r = client.get("/api/simple-promo/subaccounts")
    assert r.status_code == 200
    accounts = r.json()
    assert isinstance(accounts, list)
    assert len(accounts) > 0
    # Check account fields
    sample = accounts[0]
    assert "id" in sample
    assert "name" in sample
    assert "has_cookie" in sample

def test_seed_run_exists_and_detailed(client):
    # Verify Run #1 exists
    r = client.get("/api/simple-promo/runs")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) >= 1
    run1 = [r for r in runs if r["id"] == 1][0]
    assert run1["accounts_count"] == 4
    assert run1["total_notes_scanned"] == 1940
    assert run1["pre_cutoff_notes_count"] == 415
    assert run1["paused_success_count"] == 360
    assert run1["already_paused_count"] == 55

    # Verify detail items of Run #1
    r_det = client.get("/api/simple-promo/runs/1")
    assert r_det.status_code == 200
    det = r_det.json()
    items = det["items"]
    assert len(items) == 415
    first = items[0]
    assert first["account_name"] == "易美传播-凯乐石EX3-红京"
    assert first["creativity_id"] == "6572943284"
    assert first["note_id"] == "68625ca4000000000d019ace"
    assert first["result_status"] == "已暂停"
    assert "xiaohongshu.com/explore/68625ca4000000000d019ace" in first["note_url"]

def test_export_csv_endpoint(client):
    r = client.get("/api/simple-promo/runs/1/export")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    # Check CSV content contains BOM and headers
    text = r.content.decode("utf-8-sig")
    assert "子账号名称" in text
    assert "创意ID" in text
    assert "易美传播-凯乐石EX3-红京" in text
    assert "68625ca4000000000d019ace" in text

def test_task_lifecycle_api(client):
    # Obtain auth token
    r_token = client.post("/api/simple-promo/auth/verify", json={"password": "xinxiliu123"}).json()["token"]
    headers = {"x-simple-promo-token": r_token}

    # 1. Create task
    create_payload = {
        "name": "自动化测试简单投任务",
        "accounts": [
            {"id": "691d9a94252ae1001521f3d3", "name": "易美传播-凯乐石EX3-红京"},
            {"id": "6971f17051a1f100153a9d55", "name": "易美传播-凯乐石EX330-红京"}
        ],
        "cutoff_date": "2026-01-01 00:00:00",
        "whitelist_note_ids": ["68625ca4000000000d019ace"],
        "rrule": "RRULE:FREQ=DAILY;BYHOUR=10;BYMINUTE=30"
    }
    r_create = client.post("/api/simple-promo/tasks", json=create_payload, headers=headers)
    assert r_create.status_code == 200
    task_id = r_create.json()["id"]

    # 2. List tasks
    r_list = client.get("/api/simple-promo/tasks")
    assert r_list.status_code == 200
    tasks = r_list.json()
    created = [t for t in tasks if t["id"] == task_id][0]
    assert created["name"] == "自动化测试简单投任务"
    assert len(created["accounts"]) == 2
    assert created["whitelist_note_ids"] == ["68625ca4000000000d019ace"]
    assert created["status"] == "active"

    # 3. Update task (add account)
    r_update = client.put(f"/api/simple-promo/tasks/{task_id}", json={
        "name": "自动化测试简单投任务(已修改)",
        "accounts": [
            {"id": "691d9a94252ae1001521f3d3", "name": "易美传播-凯乐石EX3-红京"},
            {"id": "6971f17051a1f100153a9d55", "name": "易美传播-凯乐石EX330-红京"},
            {"id": "67d4046297c0d1001531a013", "name": "易美传播-凯乐石DU红京"}
        ]
    }, headers=headers)
    assert r_update.status_code == 200

    # Check updated
    r_list_after = client.get("/api/simple-promo/tasks")
    updated = [t for t in r_list_after.json() if t["id"] == task_id][0]
    assert updated["name"] == "自动化测试简单投任务(已修改)"
    assert len(updated["accounts"]) == 3

    # 4. Toggle task
    r_toggle = client.post(f"/api/simple-promo/tasks/{task_id}/toggle", headers=headers)
    assert r_toggle.status_code == 200
    assert r_toggle.json()["status"] == "paused"

    # 5. Delete task
    r_del = client.delete(f"/api/simple-promo/tasks/{task_id}", headers=headers)
    assert r_del.status_code == 200

    # Check deleted
    r_list_final = client.get("/api/simple-promo/tasks")
    assert not any(t["id"] == task_id for t in r_list_final.json())

def test_backups_and_rollback_api(client):
    # Obtain auth token
    r_token = client.post("/api/simple-promo/auth/verify", json={"password": "xinxiliu123"}).json()["token"]
    headers = {"x-simple-promo-token": r_token}

    # Check backups endpoint
    r_backups = client.get("/api/simple-promo/backups", headers=headers)
    assert r_backups.status_code == 200
    backups = r_backups.json()
    assert isinstance(backups, list)
    assert len(backups) > 0

    # Rollback without confirm -> 400
    r_rb_fail = client.post("/api/simple-promo/runs/1/rollback", json={"confirm": False}, headers=headers)
    assert r_rb_fail.status_code == 400

def test_inspect_and_execute_validation(client):
    # 1. Empty accounts on inspect -> 400
    r_empty = client.post("/api/simple-promo/inspect", json={"accounts": []})
    assert r_empty.status_code == 400

    # 2. Execute without auth -> 401
    r_no_auth = client.post("/api/simple-promo/execute", json={
        "accounts": [{"id": "691d9a94252ae1001521f3d3", "name": "易美传播-凯乐石EX3-红京"}],
        "confirm": True
    })
    assert r_no_auth.status_code == 401

    # 3. Execute with auth but without confirm -> 400
    r_token = client.post("/api/simple-promo/auth/verify", json={"password": "xinxiliu123"}).json()["token"]
    r_no_confirm = client.post("/api/simple-promo/execute", json={
        "accounts": [{"id": "691d9a94252ae1001521f3d3", "name": "易美传播-凯乐石EX3-红京"}],
        "confirm": False
    }, headers={"x-simple-promo-token": r_token})
    assert r_no_confirm.status_code == 400
