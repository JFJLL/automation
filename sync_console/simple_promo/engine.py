# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import sqlite3
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple, Set

from app.config import DATA_DIR, BASE_DIR
from core.database import (
    get_simple_promo_db,
    acquire_task_lease,
    release_task_lease
)
from core.errors import TaskNotFoundError, TaskAlreadyRunningError

SHANGHAI_TZ = timezone(timedelta(hours=8))
DEFAULT_CUTOFF_STR = "2026-01-01 00:00:00"

def parse_cutoff_timestamp(cutoff_str: str) -> Tuple[datetime, int]:
    """解析截止时间字符串为上海时区 datetime 和秒级时间戳"""
    s = (cutoff_str or DEFAULT_CUTOFF_STR).strip()
    dt = None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d"
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(s, fmt)
            dt = parsed.replace(tzinfo=SHANGHAI_TZ)
            break
        except ValueError:
            continue
    if dt is None:
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=SHANGHAI_TZ)
    return dt, int(dt.timestamp())

def parse_note_publish_time(note_id: str, cutoff_ts: int) -> dict:
    """解析小红书 NoteId 的发布时间戳 (24位十六进制前8位)"""
    if not note_id or len(note_id) < 8:
        return {"timestamp": 0, "datetime_str": "未知", "year": 0, "is_pre_cutoff": False}
    try:
        ts = int(note_id[:8], 16)
        dt = datetime.fromtimestamp(ts, tz=SHANGHAI_TZ)
        return {
            "timestamp": ts,
            "datetime_str": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "year": dt.year,
            "is_pre_cutoff": ts < cutoff_ts
        }
    except Exception:
        return {"timestamp": 0, "datetime_str": "解析失败", "year": 0, "is_pre_cutoff": False}

_cookie_ids_cache = {"timestamp": 0.0, "ids": set()}

def get_available_cookie_subaccount_ids(force_refresh: bool = False) -> Set[str]:
    """极速获取当前本地及缓存中存在有效 Cookie 的子账号 ID 集合 (毫秒级响应，兼容 Linux/Windows 与 OSS 缓存)"""
    now = time.time()
    if not force_refresh and _cookie_ids_cache["ids"] and (now - _cookie_ids_cache["timestamp"] < 300):
        return _cookie_ids_cache["ids"]

    ids = set()
    local_dir = Path(r"D:\download\pic-vec\oss-upload\cookies\juguang")
    if local_dir.exists():
        for fname in os.listdir(local_dir):
            if fname.endswith(".txt") and len(fname) == 28:
                ids.add(fname[:-4])

    for base_p in [BASE_DIR / "tokens", BASE_DIR / "data"]:
        if base_p.exists():
            for fname in os.listdir(base_p):
                if fname.endswith(".txt") and len(fname) == 28:
                    ids.add(fname[:-4])

    # 跨平台兼容：读取 data/juguang_subaccounts_cache.json 中已由 OSS 校验的活跃子账号
    cache_file = BASE_DIR / "data" / "juguang_subaccounts_cache.json"
    if cache_file.exists():
        try:
            items = json.loads(cache_file.read_text(encoding="utf-8"))
            for item in items:
                sid = item.get("id") or item.get("subId")
                if sid:
                    ids.add(sid)
        except Exception:
            pass

    _cookie_ids_cache["timestamp"] = now
    _cookie_ids_cache["ids"] = ids
    return ids

def load_subaccount_cookie(sub_id: str) -> str:
    """加载子账号 Cookie (优先本地磁盘 0ms 读取，避免重复打远程 OSS 接口)"""
    sub_id = sub_id.strip()
    local_candidates = [
        Path(r"D:\download\pic-vec\oss-upload\cookies\juguang") / f"{sub_id}.txt",
        BASE_DIR / "tokens" / f"{sub_id}.txt",
        BASE_DIR / "data" / f"{sub_id}.txt",
    ]
    for p in local_candidates:
        if p.exists() and p.is_file():
            c = p.read_text(encoding="utf-8").strip()
            if c:
                return c

    # 备选：通过 platforms 模块拉取
    try:
        from platforms.juguang import get_juguang_subaccount_headers
        h = get_juguang_subaccount_headers(sub_id)
        if h and h.get("cookie"):
            return h["cookie"].strip()
    except Exception:
        pass

    raise ValueError(f"未找到子账号 [{sub_id}] 的有效 Cookie 凭据")

def check_subaccount_cookie_exists(sub_id: str) -> bool:
    """极速检查子账号 Cookie 是否存在 (内存 + 本地文件检查，毫秒级响应)"""
    sub_id = sub_id.strip()
    available = get_available_cookie_subaccount_ids()
    if sub_id in available:
        return True
    candidates = [
        Path(r"D:\download\pic-vec\oss-upload\cookies\juguang") / f"{sub_id}.txt",
        BASE_DIR / "tokens" / f"{sub_id}.txt",
        BASE_DIR / "data" / f"{sub_id}.txt",
    ]
    return any(p.exists() and p.is_file() for p in candidates)

class JuguangSimplePromotionClient:
    def __init__(self, sub_id: str, name: str):
        self.sub_id = sub_id.strip()
        self.name = name.strip()
        self.cookie_str = load_subaccount_cookie(self.sub_id)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Cookie": self.cookie_str,
            "v-seller-id": self.sub_id,
            "x-seller-id": self.sub_id,
            "Origin": "https://ad.xiaohongshu.com",
            "Referer": f"https://ad.xiaohongshu.com/aurora/ad/manage/createsimple?vSellerId={self.sub_id}",
            "Content-Type": "application/json"
        })

    def get_campaign_groups(self) -> List[Dict[str, Any]]:
        url = "https://ad.xiaohongshu.com/api/light/campaigngroup/data/list"
        payload = {
            "page": {"pageIndex": 1, "pageSize": 100},
            "filter": {},
            "columns": [],
            "startTime": datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d"),
            "endTime": datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d"),
            "isEasyPromotion": 1,
            "bizSource": "EASY_PROMOTION"
        }
        resp = self.session.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        res_data = resp.json()
        if not res_data.get("success"):
            raise RuntimeError(f"获取推广标的列表失败: {res_data.get('msg')}")
        return res_data.get("data", {}).get("dataList", [])

    def get_all_creativities(self, campaign_group_ids: List[str]) -> List[Dict[str, Any]]:
        if not campaign_group_ids:
            return []
        url = "https://ad.xiaohongshu.com/api/leona/rtb/creativity/list"
        all_items = []
        page_num = 1
        page_size = 100
        today_str = datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d")

        while True:
            payload = {
                "pageNum": page_num,
                "pageSize": page_size,
                "campaignGroupIdList": campaign_group_ids,
                "isEasyPromotion": 1,
                "orderClauses": [{"column": "fee", "sort": "desc"}],
                "startTime": today_str,
                "endTime": today_str,
                "dataCaliber": 0
            }
            resp = self.session.post(url, json=payload, timeout=25)
            resp.raise_for_status()
            res_data = resp.json()
            if not res_data.get("success"):
                raise RuntimeError(f"获取笔记创意列表失败: {res_data.get('msg')}")
            data = res_data.get("data", {})
            total = data.get("total", 0)
            items = data.get("list", [])
            all_items.extend(items)
            if len(all_items) >= total or not items:
                break
            page_num += 1
            time.sleep(0.15)
        return all_items

    def check_batch_pause(self, creativity_ids: List[str]) -> bool:
        if not creativity_ids:
            return True
        url = "https://ad.xiaohongshu.com/api/leona/rtb/creativity/batch/status/check"
        payload = {"ids": creativity_ids, "actionType": 2}
        resp = self.session.put(url, json=payload, timeout=20)
        resp.raise_for_status()
        res_data = resp.json()
        return res_data.get("success") is True

    def check_batch_resume(self, creativity_ids: List[str]) -> bool:
        if not creativity_ids:
            return True
        url = "https://ad.xiaohongshu.com/api/leona/rtb/creativity/batch/status/check"
        payload = {"ids": creativity_ids, "actionType": 1} # 1: 开启投放
        resp = self.session.put(url, json=payload, timeout=20)
        resp.raise_for_status()
        res_data = resp.json()
        return res_data.get("success") is True

    def batch_resume_creativities(self, creativity_ids: List[str], chunk_size: int = 50) -> Dict[str, Any]:
        """分批恢复开启投放创意 (actionType=1)，包含安全校验与指数退避"""
        if not creativity_ids:
            return {"total_requested": 0, "success_count": 0, "failed_count": 0, "errors": []}

        url = "https://ad.xiaohongshu.com/api/leona/rtb/creativity/batch/status"
        success_count = 0
        failed_count = 0
        errors = []

        for i in range(0, len(creativity_ids), chunk_size):
            chunk = creativity_ids[i:i + chunk_size]
            payload = {"ids": chunk, "actionType": 1} # 1: 开启
            chunk_ok = False

            for attempt in range(1, 4):
                try:
                    try:
                        self.check_batch_resume(chunk)
                    except Exception:
                        pass
                    resp = self.session.put(url, json=payload, timeout=25)
                    resp.raise_for_status()
                    res_data = resp.json()
                    if res_data.get("success"):
                        success_count += len(chunk)
                        chunk_ok = True
                        break
                    else:
                        msg = res_data.get("msg", "未知错误")
                        if attempt < 3:
                            delay = 3.0 * (1.5 ** (attempt - 1))
                            time.sleep(delay)
                        else:
                            errors.append(f"分批恢复请求被拒: {msg}")
                except Exception as e:
                    if attempt < 3:
                        delay = 3.0 * (1.5 ** (attempt - 1))
                        time.sleep(delay)
                    else:
                        errors.append(f"分批恢复网络异常: {str(e)}")

            if not chunk_ok:
                failed_count += len(chunk)
            time.sleep(1.0)

        return {
            "total_requested": len(creativity_ids),
            "success_count": success_count,
            "failed_count": failed_count,
            "errors": errors
        }

    def batch_pause_creativities(self, creativity_ids: List[str], chunk_size: int = 50) -> Dict[str, Any]:
        """分批暂停创意，包含安全预检和指数退避重试"""
        if not creativity_ids:
            return {"total_requested": 0, "success_count": 0, "failed_count": 0, "errors": []}

        url = "https://ad.xiaohongshu.com/api/leona/rtb/creativity/batch/status"
        success_count = 0
        failed_count = 0
        errors = []

        for i in range(0, len(creativity_ids), chunk_size):
            chunk = creativity_ids[i:i + chunk_size]
            payload = {"ids": chunk, "actionType": 2}
            chunk_ok = False

            for attempt in range(1, 4):
                try:
                    try:
                        self.check_batch_pause(chunk)
                    except Exception:
                        pass
                    resp = self.session.put(url, json=payload, timeout=25)
                    resp.raise_for_status()
                    res_data = resp.json()
                    if res_data.get("success"):
                        success_count += len(chunk)
                        chunk_ok = True
                        break
                    else:
                        msg = res_data.get("msg", "未知错误")
                        if attempt < 3:
                            delay = 3.0 * (1.5 ** (attempt - 1))
                            time.sleep(delay)
                        else:
                            errors.append(f"分批暂停请求被拒: {msg}")
                except Exception as e:
                    if attempt < 3:
                        delay = 3.0 * (1.5 ** (attempt - 1))
                        time.sleep(delay)
                    else:
                        errors.append(f"分批暂停网络异常: {str(e)}")

            if not chunk_ok:
                failed_count += len(chunk)
            time.sleep(1.0)

        return {
            "total_requested": len(creativity_ids),
            "success_count": success_count,
            "failed_count": failed_count,
            "errors": errors
        }

def execute_simple_promo_plan(
    accounts: List[Dict[str, str]],
    cutoff_date: str = DEFAULT_CUTOFF_STR,
    whitelist_note_ids: Optional[List[str]] = None,
    mode: str = "DRY_RUN",
    trigger_type: str = "manual",
    task_id: Optional[int] = None,
    task_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    执行简单投笔记巡检或暂停全流程
    mode: 'DRY_RUN' (仅巡检预览) 或 'EXECUTE' (实际执行暂停写操作)
    """
    conn = get_simple_promo_db()
    cur = conn.cursor()

    t_name = task_name or (f"手动执行任务 ({len(accounts)}个账号)" if mode == "EXECUTE" else f"巡检预览 ({len(accounts)}个账号)")
    task_key = f"simple_promo_task_{task_id}" if task_id else "simple_promo_manual"

    if not acquire_task_lease(conn, task_key, owner=f"run_{trigger_type}", lease_seconds=600):
        raise TaskAlreadyRunningError("当前已有相同简单投巡检/暂停任务正在运行中，请勿重复触发")

    start_time = datetime.now()
    cutoff_dt, cutoff_ts = parse_cutoff_timestamp(cutoff_date)
    whitelist_set: Set[str] = set(s.strip() for s in (whitelist_note_ids or []) if s.strip())

    # 写入初始运行记录
    with conn:
        cur.execute("""
            INSERT INTO simple_promo_runs (
                task_id, task_name, trigger_type, mode, cutoff_date,
                started_at, status, accounts_count
            ) VALUES (?, ?, ?, ?, ?, ?, 'running', ?)
        """, (task_id, t_name, trigger_type, mode, cutoff_date, start_time.strftime("%Y-%m-%d %H:%M:%S"), len(accounts)))
        run_id = cur.lastrowid

    summary_map: Dict[str, Any] = {}
    all_run_items: List[Tuple] = []
    total_scanned = 0
    total_pre_cutoff = 0
    total_to_pause = 0
    total_paused_success = 0
    total_already_paused = 0
    has_error = False
    error_messages = []

    try:
        for acc in accounts:
            acc_id = acc.get("id", "").strip()
            acc_name = acc.get("name", "").strip() or acc_id

            # 容错处理：若该账号凭据缺失或异常，不中断整体批次，标记该账号异常后继续巡检其他账号
            try:
                client = JuguangSimplePromotionClient(acc_id, acc_name)
            except Exception as e:
                has_error = True
                err_str = f"账号 [{acc_name}] 凭据异常: {str(e)}"
                error_messages.append(err_str)
                summary_map[acc_name] = {
                    "account": acc_name,
                    "subId": acc_id,
                    "status": "COOKIE_ERROR",
                    "error": str(e),
                    "total": 0, "pre_cutoff": 0, "to_pause": 0, "paused": 0, "already_paused": 0
                }
                continue

            try:
                groups = client.get_campaign_groups()
                group_ids = [str(g.get("campaignGroupId")) for g in groups if "campaignGroupId" in g]
                if not group_ids:
                    summary_map[acc_name] = {
                        "account": acc_name,
                        "subId": acc_id,
                        "status": "NO_GROUPS",
                        "total": 0, "pre_cutoff": 0, "to_pause": 0, "paused": 0, "already_paused": 0
                    }
                    continue

                creativities = client.get_all_creativities(group_ids)
                total_scanned += len(creativities)

                to_pause_ids = []
                acc_pre_cutoff = 0
                acc_to_pause = 0
                acc_already_paused = 0
                acc_items = []

                for c in creativities:
                    cid = str(c.get("creativityId", ""))
                    nid = str(c.get("noteId", "")).strip()
                    title = c.get("noteTitle", "")
                    enable = c.get("creativityEnable") # 1: 开启, 0: 暂停
                    gid = str(c.get("campaignGroupId", ""))
                    pub_info = parse_note_publish_time(nid, cutoff_ts)
                    note_url = f"https://www.xiaohongshu.com/explore/{nid}" if nid else ""
                    orig_status = "有效投放" if enable == 1 else "已暂停"

                    if pub_info["is_pre_cutoff"]:
                        acc_pre_cutoff += 1
                        # 白名单跳过保护
                        if nid in whitelist_set:
                            acc_items.append({
                                "account_name": acc_name, "account_id": acc_id, "group_id": gid,
                                "creativity_id": cid, "note_id": nid, "title": title,
                                "publish_time": pub_info["datetime_str"], "note_url": note_url,
                                "orig_status": orig_status, "action": "白名单跳过",
                                "result_status": "跳过", "error": ""
                            })
                        elif enable == 1:
                            acc_to_pause += 1
                            to_pause_ids.append(cid)
                            acc_items.append({
                                "account_name": acc_name, "account_id": acc_id, "group_id": gid,
                                "creativity_id": cid, "note_id": nid, "title": title,
                                "publish_time": pub_info["datetime_str"], "note_url": note_url,
                                "orig_status": orig_status,
                                "action": "暂停投放" if mode == "EXECUTE" else "待暂停",
                                "result_status": "待处理" if mode == "EXECUTE" else "未执行",
                                "error": ""
                            })
                        else:
                            acc_already_paused += 1
                            acc_items.append({
                                "account_name": acc_name, "account_id": acc_id, "group_id": gid,
                                "creativity_id": cid, "note_id": nid, "title": title,
                                "publish_time": pub_info["datetime_str"], "note_url": note_url,
                                "orig_status": orig_status, "action": "保持暂停",
                                "result_status": "无需操作", "error": ""
                            })

                total_pre_cutoff += acc_pre_cutoff
                total_to_pause += acc_to_pause
                total_already_paused += acc_already_paused

                # 执行真实批量暂停
                acc_paused_success = 0
                if mode == "EXECUTE" and to_pause_ids:
                    pause_res = client.batch_pause_creativities(to_pause_ids, chunk_size=50)
                    acc_paused_success = pause_res["success_count"]
                    total_paused_success += acc_paused_success

                    # 回读复核状态
                    time.sleep(1.0)
                    try:
                        refreshed = client.get_all_creativities(group_ids)
                        status_dict = {str(item.get("creativityId")): item.get("creativityEnable") for item in refreshed}
                        for item in acc_items:
                            if item["creativity_id"] in to_pause_ids:
                                if status_dict.get(item["creativity_id"]) == 0:
                                    item["result_status"] = "已暂停"
                                else:
                                    item["result_status"] = "未生效"
                                    item["error"] = "回读复核开关未转为暂停"
                    except Exception as verify_err:
                        for item in acc_items:
                            if item["creativity_id"] in to_pause_ids:
                                item["result_status"] = "已暂停" if acc_paused_success > 0 else "失败"
                                item["error"] = str(verify_err)

                summary_map[acc_name] = {
                    "account": acc_name,
                    "subId": acc_id,
                    "status": "SUCCESS",
                    "total": len(creativities),
                    "pre_cutoff": acc_pre_cutoff,
                    "to_pause": acc_to_pause,
                    "paused": acc_paused_success if mode == "EXECUTE" else 0,
                    "already_paused": acc_already_paused,
                    "post_cutoff": len(creativities) - acc_pre_cutoff
                }

                for it in acc_items:
                    all_run_items.append((
                        run_id, it["account_name"], it["account_id"], it["group_id"],
                        it["creativity_id"], it["note_id"], it["title"], it["publish_time"],
                        it["note_url"], it["orig_status"], it["action"], it["result_status"], it["error"]
                    ))

            except Exception as acc_err:
                has_error = True
                err_msg = f"处理子账号 [{acc_name}] 失败: {str(acc_err)}"
                error_messages.append(err_msg)
                summary_map[acc_name] = {
                    "account": acc_name,
                    "subId": acc_id,
                    "status": "FAILED",
                    "error": str(acc_err),
                    "total": 0, "pre_cutoff": 0, "to_pause": 0, "paused": 0, "already_paused": 0
                }

        finish_time = datetime.now()
        duration_ms = int((finish_time - start_time).total_seconds() * 1000)
        final_status = "success"
        if has_error:
            final_status = "partial" if (total_paused_success > 0 or total_scanned > 0) else "failed"

        if mode == "EXECUTE":
            msg = f"执行完成: 扫描 {len(accounts)} 个账号共 {total_scanned} 篇笔记，发现 {total_pre_cutoff} 篇老笔记，成功暂停 {total_paused_success} 篇，{total_already_paused} 篇原已处于暂停。"
        else:
            msg = f"巡检预览完成: 扫描 {len(accounts)} 个账号共 {total_scanned} 篇笔记，发现 {total_pre_cutoff} 篇老笔记，其中 {total_to_pause} 篇需暂停投放，{total_already_paused} 篇当前已处于暂停。"

        with conn:
            if all_run_items:
                cur.executemany("""
                    INSERT INTO simple_promo_run_items (
                        run_id, account_name, account_id, campaign_group_id,
                        creativity_id, note_id, note_title, note_publish_time,
                        note_url, original_status, action, result_status, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, all_run_items)

            cur.execute("""
                UPDATE simple_promo_runs SET
                    finished_at = ?,
                    duration_ms = ?,
                    status = ?,
                    total_notes_scanned = ?,
                    pre_cutoff_notes_count = ?,
                    to_pause_count = ?,
                    paused_success_count = ?,
                    already_paused_count = ?,
                    message = ?,
                    error_detail = ?,
                    summary_json = ?
                WHERE id = ?
            """, (
                finish_time.strftime("%Y-%m-%d %H:%M:%S"),
                duration_ms,
                final_status,
                total_scanned,
                total_pre_cutoff,
                total_to_pause,
                total_paused_success,
                total_already_paused,
                msg,
                "\n".join(error_messages) if error_messages else None,
                json.dumps(summary_map, ensure_ascii=False),
                run_id
            ))

            if task_id:
                cur.execute("""
                    UPDATE simple_promo_tasks SET
                        last_run_at = ?,
                        last_status = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    finish_time.strftime("%Y-%m-%d %H:%M:%S"),
                    final_status,
                    "\n".join(error_messages) if error_messages else None,
                    finish_time.isoformat(),
                    task_id
                ))

        # 实际写操作完成后，自动在本地写入不可篡改备份快照 (永久保留，即使数据库任务被删也能一键恢复)
        if mode == "EXECUTE" and all_run_items:
            try:
                from simple_promo.backup import save_promo_execution_snapshot
                item_dicts = []
                for it in all_run_items:
                    item_dicts.append({
                        "run_id": it[0],
                        "account_name": it[1],
                        "account_id": it[2],
                        "campaign_group_id": it[3],
                        "creativity_id": it[4],
                        "note_id": it[5],
                        "note_title": it[6],
                        "note_publish_time": it[7],
                        "note_url": it[8],
                        "original_status": it[9],
                        "action": it[10],
                        "result_status": it[11],
                        "error_message": it[12]
                    })
                save_promo_execution_snapshot(
                    run_id=run_id,
                    task_id=task_id,
                    task_name=t_name,
                    mode=mode,
                    cutoff_date=cutoff_date,
                    accounts_summary=summary_map,
                    paused_items=item_dicts,
                    action_type="PAUSE_EXECUTION"
                )
            except Exception as snap_err:
                print(f"[Backup] Save execution snapshot error: {snap_err}")

            # 自动将巡检与暂停记录同步到飞书在线多维/电子表格
            try:
                from simple_promo.feishu_sync import sync_run_to_feishu
                sync_run_to_feishu(run_id)
            except Exception as feishu_err:
                print(f"[FeishuSync] Auto sync error: {feishu_err}")

        return {
            "run_id": run_id,
            "status": final_status,
            "mode": mode,
            "duration_ms": duration_ms,
            "message": msg,
            "summary": summary_map,
            "counts": {
                "total_scanned": total_scanned,
                "pre_cutoff": total_pre_cutoff,
                "to_pause": total_to_pause,
                "paused_success": total_paused_success,
                "already_paused": total_already_paused
            }
        }

    finally:
        release_task_lease(conn, task_key)

def run_simple_promo_task(task_id: int, trigger_type: str = "scheduled") -> Dict[str, Any]:
    """执行后台配置好的定时简单投巡检暂停任务"""
    conn = get_simple_promo_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM simple_promo_tasks WHERE id = ?", (task_id,))
    task = cur.fetchone()
    if not task:
        raise TaskNotFoundError(f"未找到简单投任务 ID={task_id}")
    t_dict = dict(task)
    accounts = json.loads(t_dict["accounts_json"])
    cutoff_date = t_dict.get("cutoff_date") or DEFAULT_CUTOFF_STR
    whitelist = json.loads(t_dict.get("whitelist_note_ids_json") or "[]")

    return execute_simple_promo_plan(
        accounts=accounts,
        cutoff_date=cutoff_date,
        whitelist_note_ids=whitelist,
        mode="EXECUTE",
        trigger_type=trigger_type,
        task_id=task_id,
        task_name=t_dict["name"]
    )
