#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝星河订单管理推广效果明细导出
================================

面向飞书表格写入的数据准备脚本：
- 从「订单管理」按订单名称关键词搜索订单。
- 过滤总金额为 0.01 或项目信息含「作废」的订单。
- 根据各订单投放截止日期跳过已结束区间，跨截止日时只抓到截止日。
- 抓取每个订单「推广效果」Tab 下的「数据明细」。
- 归因周期固定为 30 天。
- 输出第一列为「任务组名称」，后续列对应网页数据明细。
"""

from __future__ import annotations

import argparse
import json
import os
import time
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

warnings.filterwarnings("ignore", message="Pandas requires version .*")

import pandas as pd
import requests

from taobaoxinghe_scraper import (
    ApiError,
    TaobaoXingheScraperV5,
    first_value,
    list_from_model,
    load_cookies,
    to_number,
    value_if_present,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_KEYWORD = "启萃"


EFFECT_COLUMNS = [
    ("阅读/播放UV", "readUv1d"),
    ("点赞UV", "likeUv1d"),
    ("评论UV", "commentUv1d"),
    ("收藏UV", "favoriteUv1d"),
    ("转发UV", "forwardUv1d"),
    ("互动UV", "engagementUv1d"),
    ("内容互动率", "contentEngagementRate"),
    ("搜索曝光UV", "slrAttrItmSeImpsUv1d"),
    ("搜索进店UV", "slrAttrSlrSeVstUv1d"),
    ("进店UV", "slrAttrSlrVstUv1d"),
    ("新客进店UV", "slrAttrSlrVstUv1dNew"),
    ("商品收藏UV", "slrAttrItmCltUv1d"),
    ("商品加购UV", "slrAttrItmCltCartUv1d"),
    ("关注店铺UV", "slrAttrSlrSubUv1d"),
    ("店铺会员UV", "slrAttrSlrMbrUv1d"),
    ("成交UV", "slrAttrItmOrdUv1d"),
    ("商家GMV", "slrAttrItmOrdGmv1d"),
    ("订单商品成交GMV", "slrAttrItmOrdGmv1d1bpOrd"),
    ("非订单商品成交GMV", "slrAttrItmOrdGmv1dNot1bpOrd"),
    ("新客成交UV", "slrAttrItmOrdUv1dNew"),
    ("订单商品新客成交GMV", "slrAttrItmOrdGmv1d1bpOrdNew"),
    ("预售付定GMV", "slrAttrItmOrdSubpayGmv1d"),
    ("预售整单预估GMV", "slrAttrItmOrdSubpayGmv1dPredAll"),
    ("预售付定UV", "slrAttrItmOrdSubpayUv1d"),
    ("成交转化率", "conversionRate"),
]

OUTPUT_COLUMNS = ["任务组名称", "日期", "订单ID", "流量类型", "归因周期"] + [label for label, _key in EFFECT_COLUMNS]


def normalize_datetime(value: str, default_time: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) == 10:
        return f"{value} {default_time}"
    return value


def yesterday_date() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def cutoff_time_range(date_text: str = "") -> Dict[str, str]:
    target_date = (date_text or yesterday_date()).strip()
    return {
        "cutoffDate": target_date,
        "startTime": f"{target_date} 00:00:00",
        "endTime": f"{target_date} 00:00:00",
    }


def order_start_time(order: Dict[str, Any]) -> str:
    start_date = str(first_value(order, ("startTime",), "") or "")[:10]
    if start_date:
        return f"{start_date} 00:00:00"
    return (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00")


def order_end_date(order: Dict[str, Any]) -> Optional[date]:
    return parse_date_value(
        first_value(order, ("endTime", "orderEndTime", "deliveryEndTime", "gmtEnd"), "")
    )


def format_date(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}/{text[4:6]}/{text[6:8]}"
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10].replace("-", "/")
    return text


def parse_date_value(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 20000:
        # Feishu normally returns text for this sheet, but this handles Excel-style serial dates.
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10:
        text = text[:10]
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def display_date(value: date) -> str:
    return value.strftime("%Y/%m/%d")


def api_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def safe_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    return safe[:60] or "orders"


def default_output_path(keyword: str) -> Path:
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"feishu_order_effect_{safe_filename(keyword)}_{stamp}.xlsx"


def json_output_path(output_path: Path, explicit_path: str = "") -> Path:
    if explicit_path:
        return Path(explicit_path)
    return output_path.with_suffix(".json")


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def normalize_row_value(value: Any) -> Any:
    if value is None:
        return ""
    return value


def row_identity(row: Dict[str, Any]) -> tuple:
    return (
        str(row.get("任务组名称", "")).strip(),
        str(row.get("日期", "")).strip(),
        str(row.get("订单ID", "")).strip(),
        str(row.get("流量类型", "")).strip(),
        str(row.get("归因周期", "")).strip(),
    )


def row_match_key(row: Dict[str, Any]) -> tuple:
    return (
        str(row.get("任务组名称", "")).strip(),
        str(row.get("日期", "")).strip(),
        str(row.get("流量类型", "")).strip(),
        str(row.get("归因周期", "")).strip(),
    )


def row_is_blank(row: Dict[str, Any]) -> bool:
    return not any(str(row.get(column, "")).strip() for column in OUTPUT_COLUMNS)


def sort_rows_for_sheet(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    group_order: Dict[str, int] = {}
    for row in rows:
        group_name = str(row.get("任务组名称", "")).strip()
        if group_name and group_name not in group_order:
            group_order[group_name] = len(group_order)

    def sort_key(row: Dict[str, Any]) -> tuple:
        group_name = str(row.get("任务组名称", "")).strip()
        row_date = parse_date_value(row.get("日期"))
        date_key = -row_date.toordinal() if row_date else 0
        order_id = str(row.get("订单ID", "")).strip()
        return (group_order.get(group_name, len(group_order)), date_key, order_id)

    return sorted(rows, key=sort_key)


def row_date_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[date, int] = {}
    for row in rows:
        row_date = parse_date_value(row.get("日期"))
        if row_date:
            counts[row_date] = counts.get(row_date, 0) + 1
    if not counts:
        return {"minDate": None, "maxDate": None, "dateCounts": {}}
    return {
        "minDate": display_date(min(counts)),
        "maxDate": display_date(max(counts)),
        "dateCounts": {
            display_date(row_date): count
            for row_date, count in sorted(counts.items())
        },
    }


def merge_sheet_rows(existing_rows: List[Dict[str, Any]], new_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[tuple, Dict[str, Any]] = {}
    ordered_rows: List[Dict[str, Any]] = []
    new_match_keys = {row_match_key(row) for row in new_rows if row_match_key(row)[0] and row_match_key(row)[1]}
    source_rows = [row for row in existing_rows if row_match_key(row) not in new_match_keys] + new_rows
    for source_row in source_rows:
        row = {column: normalize_row_value(source_row.get(column, "")) for column in OUTPUT_COLUMNS}
        if row_is_blank(row):
            continue
        identity = row_identity(row)
        if not identity[0] or not identity[1] or not identity[2]:
            continue
        if identity not in merged:
            ordered_rows.append(row)
        merged[identity] = row
    return sort_rows_for_sheet([merged[row_identity(row)] for row in ordered_rows if row_identity(row) in merged])


def display_order_id_from_order(order: Dict[str, Any]) -> str:
    return str(first_value(order, ("settleSeqId", "buyOrderId", "orderId", "id"), "") or "")


def internal_order_id_from_order(order: Dict[str, Any]) -> str:
    return str(first_value(order, ("orderId", "buyOrderId", "id"), "") or "")


def order_id_corrections_from_orders(orders: List[Dict[str, Any]]) -> Dict[tuple, str]:
    corrections: Dict[tuple, str] = {}
    display_ids_by_name: Dict[str, set] = {}
    for order in orders:
        order_name = str(first_value(order, ("orderName",), "") or "").strip()
        internal_id = internal_order_id_from_order(order)
        display_id = display_order_id_from_order(order)
        if order_name and display_id:
            display_ids_by_name.setdefault(order_name, set()).add(display_id)
        if order_name and internal_id and display_id and internal_id != display_id:
            corrections[(order_name, internal_id)] = display_id
    for order_name, display_ids in display_ids_by_name.items():
        if len(display_ids) == 1:
            corrections[(order_name, "*")] = next(iter(display_ids))
    return corrections


def apply_order_id_corrections(rows: List[Dict[str, Any]], corrections: Dict[tuple, str]) -> tuple:
    if not corrections:
        return rows, 0
    corrected_rows: List[Dict[str, Any]] = []
    corrected_count = 0
    for source_row in rows:
        row = dict(source_row)
        task_name = str(row.get("任务组名称", "")).strip()
        order_id = str(row.get("订单ID", "")).strip()
        corrected_id = corrections.get((task_name, order_id)) or corrections.get((task_name, "*"))
        if corrected_id and corrected_id != order_id:
            row["订单ID"] = corrected_id
            corrected_count += 1
        corrected_rows.append(row)
    return corrected_rows, corrected_count


def api_response_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    model = data.get("model")
    if isinstance(model, dict):
        model_summary: Any = {
            key: model.get(key)
            for key in ("totalCount", "hasNext", "pageNo", "pageSize")
            if key in model
        }
        if not model_summary:
            model_summary = {"keys": list(model.keys())[:20]}
    elif isinstance(model, list):
        model_summary = {"listLength": len(model)}
    else:
        model_summary = type(model).__name__ if model is not None else None

    summary = {
        key: data.get(key)
        for key in ("success", "code", "msg", "message", "ret", "httpStatus")
        if key in data
    }
    summary["model"] = model_summary
    return summary


def column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def load_env_file(path: Path = SCRIPT_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def parse_feishu_sheet_url(url: str) -> Dict[str, str]:
    if not url:
        return {"spreadsheetToken": "", "sheetId": "", "wikiToken": ""}
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    token = ""
    wiki_token = ""
    for index, part in enumerate(parts):
        if part == "sheets" and index + 1 < len(parts):
            token = parts[index + 1]
            break
        if part == "wiki" and index + 1 < len(parts):
            wiki_token = parts[index + 1]
            break
    params = parse_qs(parsed.query)
    sheet_id = (params.get("sheet") or params.get("sheet_id") or params.get("gid") or [""])[0]
    return {"spreadsheetToken": token, "sheetId": sheet_id, "wikiToken": wiki_token}


def feishu_tenant_access_token(app_id: str, app_secret: str) -> str:
    response = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=30,
    )
    data = response.json()
    if data.get("code") != 0:
        raise ApiError(f"获取飞书 tenant_access_token 失败: {json.dumps(data, ensure_ascii=False)[:1000]}")
    token = data.get("tenant_access_token")
    if not token:
        raise ApiError("获取飞书 tenant_access_token 失败: 响应中没有 token")
    return token


def resolve_wiki_sheet(app_id: str, app_secret: str, wiki_token: str) -> Dict[str, str]:
    if not wiki_token:
        return {"spreadsheetToken": "", "sheetId": ""}
    token = feishu_tenant_access_token(app_id, app_secret)
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node",
        headers=headers,
        params={"token": wiki_token},
        timeout=30,
    )
    data = response.json()
    if data.get("code") != 0:
        raise ApiError(f"解析飞书 Wiki 节点失败: {json.dumps(data, ensure_ascii=False)[:1000]}")
    node = (data.get("data") or {}).get("node") or {}
    if node.get("obj_type") != "sheet":
        raise ApiError(f"飞书 Wiki 节点不是电子表格: obj_type={node.get('obj_type')}")
    spreadsheet_token = node.get("obj_token") or ""
    if not spreadsheet_token:
        raise ApiError("飞书 Wiki 节点没有返回电子表格 token")
    return {"spreadsheetToken": spreadsheet_token, "sheetId": ""}


def resolve_first_sheet_id(app_id: str, app_secret: str, spreadsheet_token: str) -> str:
    if not spreadsheet_token:
        return ""
    token = feishu_tenant_access_token(app_id, app_secret)
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query",
        headers=headers,
        timeout=30,
    )
    data = response.json()
    if data.get("code") != 0:
        raise ApiError(f"读取飞书工作表信息失败: {json.dumps(data, ensure_ascii=False)[:1000]}")
    sheets = (data.get("data") or {}).get("sheets") or []
    if not sheets:
        raise ApiError("飞书电子表格没有可写入的工作表")
    return sheets[0].get("sheet_id") or ""


class FeishuSheetsClient:
    def __init__(self, *, app_id: str, app_secret: str, spreadsheet_token: str, sheet_id: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.spreadsheet_token = spreadsheet_token
        self.sheet_id = sheet_id
        self.base_url = "https://open.feishu.cn/open-apis"
        self.session = requests.Session()

    def tenant_access_token(self) -> str:
        return feishu_tenant_access_token(self.app_id, self.app_secret)

    def read_values(self, range_a1: str) -> List[List[Any]]:
        token = self.tenant_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = self.session.get(
            f"{self.base_url}/sheets/v2/spreadsheets/{self.spreadsheet_token}/values/{range_a1}",
            headers=headers,
            timeout=60,
        )
        data = response.json()
        if data.get("code") != 0:
            raise ApiError(f"读取飞书电子表格失败: {json.dumps(data, ensure_ascii=False)[:1500]}")
        value_range = (data.get("data") or {}).get("valueRange") or {}
        return value_range.get("values") or []

    def existing_date_state(self, *, min_task_groups: int) -> Dict[str, Any]:
        values = self.read_values(f"{self.sheet_id}!A:B")
        if not values:
            return {
                "dataRowCount": 0,
                "dateGroupCounts": {},
                "rawMaxDate": None,
                "confirmedMaxDate": None,
                "confirmedGroupCount": 0,
            }

        header = [str(item).strip() for item in values[0]]
        task_col = header.index("任务组名称") if "任务组名称" in header else 0
        date_col = header.index("日期") if "日期" in header else 1
        groups_by_date: Dict[date, set] = {}
        data_row_count = 0

        for row in values[1:]:
            if len(row) <= max(task_col, date_col):
                continue
            task_name = str(row[task_col]).strip()
            row_date = parse_date_value(row[date_col])
            if not task_name or not row_date:
                continue
            data_row_count += 1
            groups_by_date.setdefault(row_date, set()).add(task_name)

        raw_max_date = max(groups_by_date) if groups_by_date else None
        confirmed_dates = [
            row_date
            for row_date, task_groups in groups_by_date.items()
            if len(task_groups) >= max(1, min_task_groups)
        ]
        confirmed_max_date = max(confirmed_dates) if confirmed_dates else None
        confirmed_group_count = len(groups_by_date.get(confirmed_max_date, set())) if confirmed_max_date else 0
        return {
            "dataRowCount": data_row_count,
            "dateGroupCounts": {
                display_date(row_date): len(task_groups)
                for row_date, task_groups in sorted(groups_by_date.items())
            },
            "rawMaxDate": display_date(raw_max_date) if raw_max_date else None,
            "confirmedMaxDate": display_date(confirmed_max_date) if confirmed_max_date else None,
            "confirmedGroupCount": confirmed_group_count,
            "minTaskGroups": max(1, min_task_groups),
        }

    def read_sheet_rows(self) -> List[Dict[str, Any]]:
        end_col = column_letter(len(OUTPUT_COLUMNS))
        values = self.read_values(f"{self.sheet_id}!A:{end_col}")
        if not values:
            return []

        header = [str(item).strip() for item in values[0]]
        column_indexes: Dict[str, int] = {}
        for column in OUTPUT_COLUMNS:
            if column in header:
                column_indexes[column] = header.index(column)
        if not column_indexes:
            column_indexes = {column: index for index, column in enumerate(OUTPUT_COLUMNS)}

        rows: List[Dict[str, Any]] = []
        for value_row in values[1:]:
            row: Dict[str, Any] = {}
            for column in OUTPUT_COLUMNS:
                index = column_indexes.get(column)
                row[column] = value_row[index] if index is not None and index < len(value_row) else ""
            if not row_is_blank(row):
                rows.append(row)
        return rows

    def replace_rows(self, rows: List[Dict[str, Any]], *, previous_row_count: int = 0) -> int:
        token = self.tenant_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        end_col = column_letter(len(OUTPUT_COLUMNS))
        total_rows = max(previous_row_count + 1, len(rows) + 1, 1)
        values: List[List[Any]] = [OUTPUT_COLUMNS]
        values.extend([[row.get(column, "") for column in OUTPUT_COLUMNS] for row in rows])
        blank_width = len(OUTPUT_COLUMNS)
        while len(values) < total_rows:
            values.append([""] * blank_width)

        payload = {
            "valueRange": {
                "range": f"{self.sheet_id}!A1:{end_col}{total_rows}",
                "values": values,
            }
        }
        response = self.session.put(
            f"{self.base_url}/sheets/v2/spreadsheets/{self.spreadsheet_token}/values",
            headers=headers,
            json=payload,
            timeout=60,
        )
        data = response.json()
        if data.get("code") != 0:
            raise ApiError(f"覆盖飞书电子表格失败: {json.dumps(data, ensure_ascii=False)[:1500]}")
        return len(rows)

    def upsert_rows(self, rows: List[Dict[str, Any]], *, order_id_corrections: Optional[Dict[tuple, str]] = None) -> int:
        existing_rows = self.read_sheet_rows()
        existing_rows, corrected_count = apply_order_id_corrections(existing_rows, order_id_corrections or {})
        if corrected_count:
            print(f"飞书历史订单ID修正: {corrected_count} 行", flush=True)
        merged_rows = merge_sheet_rows(existing_rows, rows)
        return self.replace_rows(merged_rows, previous_row_count=len(existing_rows))

    def append_rows(self, rows: List[Dict[str, Any]], *, batch_size: int = 500) -> int:
        if not rows:
            return 0
        token = self.tenant_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        total = 0
        end_col = column_letter(len(OUTPUT_COLUMNS))
        for batch in chunked(rows, batch_size):
            values = [[row.get(column, "") for column in OUTPUT_COLUMNS] for row in batch]
            payload = {
                "valueRange": {
                    "range": f"{self.sheet_id}!A:{end_col}",
                    "values": values,
                }
            }
            response = self.session.post(
                f"{self.base_url}/sheets/v2/spreadsheets/{self.spreadsheet_token}/values_append",
                headers=headers,
                json=payload,
                timeout=60,
            )
            data = response.json()
            if data.get("code") != 0:
                raise ApiError(f"写入飞书电子表格失败: {json.dumps(data, ensure_ascii=False)[:1500]}")
            total += len(batch)
        return total


class FeishuBitableClient:
    def __init__(self, *, app_id: str, app_secret: str, app_token: str, table_id: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.base_url = "https://open.feishu.cn/open-apis"
        self.session = requests.Session()

    def tenant_access_token(self) -> str:
        return feishu_tenant_access_token(self.app_id, self.app_secret)

    def batch_create_records(self, rows: List[Dict[str, Any]], *, batch_size: int = 500) -> int:
        if not rows:
            return 0
        token = self.tenant_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        total = 0
        for batch in chunked(rows, batch_size):
            payload = {"records": [{"fields": row} for row in batch]}
            response = self.session.post(
                f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/batch_create",
                headers=headers,
                json=payload,
                timeout=60,
            )
            data = response.json()
            if data.get("code") != 0:
                raise ApiError(f"写入飞书多维表格失败: {json.dumps(data, ensure_ascii=False)[:1500]}")
            total += len(batch)
        return total


def feishu_sheets_client_from_args(args: argparse.Namespace) -> FeishuSheetsClient:
    sheet_url = args.feishu_url or env_first("FEISHU_SPREADSHEET_URL", "FEISHU_SHEET_URL", "spreadsheet_url")
    parsed_sheet = parse_feishu_sheet_url(sheet_url)
    app_id = args.feishu_app_id or env_first("FEISHU_APP_ID", "appid", "APP_ID")
    app_secret = args.feishu_app_secret or env_first("FEISHU_APP_SECRET", "app_secret", "APP_SECRET")
    spreadsheet_token = (
        args.feishu_spreadsheet_token
        or env_first("FEISHU_SPREADSHEET_TOKEN", "spreadsheet_token", "SHEET_TOKEN")
        or parsed_sheet["spreadsheetToken"]
    )
    if not spreadsheet_token and parsed_sheet["wikiToken"] and app_id and app_secret:
        resolved = resolve_wiki_sheet(app_id, app_secret, parsed_sheet["wikiToken"])
        spreadsheet_token = resolved["spreadsheetToken"]
    sheet_id = (
        args.feishu_sheet_id
        or env_first("FEISHU_SHEET_ID", "sheet_id", "SHEET_ID")
        or parsed_sheet["sheetId"]
    )
    if not sheet_id and spreadsheet_token and app_id and app_secret:
        sheet_id = resolve_first_sheet_id(app_id, app_secret, spreadsheet_token)
    missing = [
        name
        for name, value in (
            ("FEISHU_APP_ID", app_id),
            ("FEISHU_APP_SECRET", app_secret),
            ("FEISHU_SPREADSHEET_TOKEN", spreadsheet_token),
            ("FEISHU_SHEET_ID", sheet_id),
        )
        if not value
    ]
    if missing:
        raise ApiError(f"缺少飞书配置: {', '.join(missing)}")
    return FeishuSheetsClient(
        app_id=app_id,
        app_secret=app_secret,
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
    )


def feishu_bitable_client_from_args(args: argparse.Namespace) -> FeishuBitableClient:
    app_id = args.feishu_app_id or env_first("FEISHU_APP_ID", "appid", "APP_ID")
    app_secret = args.feishu_app_secret or env_first("FEISHU_APP_SECRET", "app_secret", "APP_SECRET")
    app_token = args.feishu_app_token or env_first("FEISHU_APP_TOKEN", "app_token", "APP_TOKEN")
    table_id = args.feishu_table_id or env_first("FEISHU_TABLE_ID", "table_id", "TABLE_ID")
    missing = [
        name
        for name, value in (
            ("FEISHU_APP_ID", app_id),
            ("FEISHU_APP_SECRET", app_secret),
            ("FEISHU_APP_TOKEN", app_token),
            ("FEISHU_TABLE_ID", table_id),
        )
        if not value
    ]
    if missing:
        raise ApiError(f"缺少飞书配置: {', '.join(missing)}")
    return FeishuBitableClient(app_id=app_id, app_secret=app_secret, app_token=app_token, table_id=table_id)


class FeishuOrderEffectExporter:
    def __init__(self, scraper: TaobaoXingheScraperV5, *, sleep_seconds: float = 0.2):
        self.scraper = scraper
        self.sleep_seconds = sleep_seconds

    def search_orders(self, *, keyword: str, page_size: int, allow_empty_orders: bool = False) -> List[Dict[str, Any]]:
        self.scraper.log(f"\n[OrderSearch] 订单管理搜索 keyword={keyword}")
        orders: List[Dict[str, Any]] = []
        page_no = 1
        first_response: Optional[Dict[str, Any]] = None
        while True:
            data = self.scraper.get_json(
                "/api/one/order/list",
                {
                    "saleType": 1,
                    "pageNo": page_no,
                    "pageSize": page_size,
                    "keyword": keyword,
                    "keywordType": 103,
                },
                timeout=30,
            )
            if first_response is None:
                first_response = data
            page_orders, model = list_from_model(data.get("model"))
            orders.extend(page_orders)
            total_count = model.get("totalCount", "") if isinstance(model, dict) else ""
            self.scraper.log(f"   page {page_no}: {len(page_orders)} 个订单，总数 {total_count or '-'}")
            has_next = bool(model.get("hasNext")) if isinstance(model, dict) else len(page_orders) >= page_size
            if not has_next or len(page_orders) < page_size:
                break
            page_no += 1
            time.sleep(self.sleep_seconds)
        if not orders and not allow_empty_orders:
            summary = api_response_summary(first_response or {})
            raise ApiError(
                "订单管理搜索返回 0 个订单，已停止写入飞书。"
                "这通常不是网站未更新，而是 Cookie 过期、账号角色/权限不对、接口风控或搜索接口返回结构变化。"
                f"接口摘要: {json.dumps(summary, ensure_ascii=False)}"
            )
        return orders

    def filter_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for order in orders:
            project_name = str(first_value(order, ("projectName",), ""))
            amount = to_number(first_value(order, ("orderBudget", "budget", "orderSeedBudget"), 0))
            if abs(amount - 0.01) < 0.000001:
                continue
            if "作废" in project_name:
                continue
            filtered.append(order)
        self.scraper.log(f"   filter: {len(filtered)}/{len(orders)} 个订单保留")
        return filtered

    def build_detail_ext(self, order: Dict[str, Any], *, cycle_days: int) -> str:
        return json.dumps(
            {
                "settleSeqId": int(first_value(order, ("settleSeqId",), 0)),
                "projectId": int(first_value(order, ("projectId",), 0)),
                "media": first_value(order, ("media",), "RED_BOOK"),
                "saleType": int(first_value(order, ("saleType",), 1)),
                "businessMode": int(first_value(order, ("businessMode",), 88)),
                "deliveryMode": "cptSeedDaily",
                "dataBatch": "order",
                "flowType": "all",
                "cycleStr": str(cycle_days),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def get_effect_detail_rows(
        self,
        *,
        order: Dict[str, Any],
        start_time: str,
        end_time: str,
        page_size: int,
        cycle_days: int,
    ) -> List[Dict[str, Any]]:
        internal_order_id = internal_order_id_from_order(order)
        display_order_id = display_order_id_from_order(order)
        order_name = str(first_value(order, ("orderName",), ""))
        if internal_order_id and display_order_id and internal_order_id != display_order_id:
            self.scraper.log(f"\n[EffectDetail] {display_order_id} {order_name} (internal {internal_order_id})")
        else:
            self.scraper.log(f"\n[EffectDetail] {display_order_id or internal_order_id} {order_name}")
        rows: List[Dict[str, Any]] = []
        page_no = 1
        while True:
            data = self.scraper.get_json(
                "/api/report/multiscene/query/detail/data",
                {
                    "bizType": "selfOfficial_orderInfo_detail",
                    "dataBatch": "order",
                    "ext": self.build_detail_ext(order, cycle_days=cycle_days),
                    "pageNo": page_no,
                    "pageSize": page_size,
                    "orderByColumn": "",
                    "orderByDirection": "",
                    "startTime": start_time,
                    "endTime": end_time,
                },
                timeout=30,
            )
            page_rows, _model = list_from_model(data.get("model"))
            self.scraper.log(f"   page {page_no}: {len(page_rows)} 条")
            for item in page_rows:
                row = {
                    "任务组名称": order_name,
                    "日期": format_date(first_value(item, ("ds", "theDate"))),
                    "订单ID": display_order_id or internal_order_id,
                    "流量类型": "全部流量",
                    "归因周期": cycle_days,
                }
                for label, key in EFFECT_COLUMNS:
                    row[label] = value_if_present(item, key)
                rows.append(row)
            if len(page_rows) < page_size:
                break
            page_no += 1
            time.sleep(self.sleep_seconds)
        return rows

    def export(
        self,
        *,
        keyword: str,
        start_time: str,
        end_time: str,
        page_size: int,
        cycle_days: int,
        max_orders: int,
        range_mode: str,
        cutoff_date: str,
        allow_empty_orders: bool,
    ) -> Dict[str, Any]:
        found_orders = self.search_orders(keyword=keyword, page_size=page_size, allow_empty_orders=allow_empty_orders)
        qualified_orders = self.filter_orders(found_orders)
        rows: List[Dict[str, Any]] = []
        cutoff_start_time = f"{cutoff_date} 00:00:00"
        cutoff_end_time = f"{cutoff_date} 00:00:00"
        order_plans: List[Dict[str, Any]] = []
        skipped_ended_count = 0
        capped_at_end_count = 0
        for order in qualified_orders:
            if range_mode == "full":
                order_start = normalize_datetime(start_time, "00:00:00") or order_start_time(order)
            elif range_mode == "catchup":
                order_start = normalize_datetime(start_time, "00:00:00") or cutoff_start_time
            else:
                order_start = normalize_datetime(start_time, "00:00:00") or cutoff_start_time
            order_end = normalize_datetime(end_time, "00:00:00") or cutoff_end_time
            delivery_end_date = order_end_date(order)
            requested_start_date = parse_date_value(order_start)
            requested_end_date = parse_date_value(order_end)
            if delivery_end_date and requested_start_date and requested_start_date > delivery_end_date:
                skipped_ended_count += 1
                continue
            if delivery_end_date and requested_end_date and requested_end_date > delivery_end_date:
                order_end = f"{delivery_end_date.isoformat()} 00:00:00"
                capped_at_end_count += 1
            order_plans.append({"order": order, "startTime": order_start, "endTime": order_end})

        if max_orders > 0:
            order_plans = order_plans[:max_orders]
        filtered_orders = [plan["order"] for plan in order_plans]
        self.scraper.log(
            f"   period filter: {len(filtered_orders)}/{len(qualified_orders)} 个订单待抓取，"
            f"已截止跳过 {skipped_ended_count} 个，截止日裁剪 {capped_at_end_count} 个"
        )

        for index, plan in enumerate(order_plans, 1):
            order = plan["order"]
            order_start = plan["startTime"]
            order_end = plan["endTime"]
            display_order_id = display_order_id_from_order(order)
            internal_order_id = internal_order_id_from_order(order)
            if display_order_id and internal_order_id and display_order_id != internal_order_id:
                self.scraper.log(f"\n[Order] {index}/{len(filtered_orders)} {display_order_id} (internal {internal_order_id})")
            else:
                self.scraper.log(f"\n[Order] {index}/{len(filtered_orders)} {display_order_id or internal_order_id}")
            detail_rows = self.get_effect_detail_rows(
                order=order,
                start_time=order_start,
                end_time=order_end,
                page_size=page_size,
                cycle_days=cycle_days,
            )
            if range_mode == "daily":
                target_display_date = cutoff_date.replace("-", "/")
                detail_rows = [row for row in detail_rows if row.get("日期") == target_display_date]
            rows.extend(detail_rows)
            time.sleep(self.sleep_seconds)

        return {
            "version": "1.0",
            "scrapeTime": datetime.now().isoformat(timespec="seconds"),
            "input": {
                "keyword": keyword,
                "startTime": start_time,
                "endTime": end_time,
                "pageSize": page_size,
                "cycleDays": cycle_days,
                "maxOrders": max_orders,
                "rangeMode": range_mode,
                "cutoffDate": cutoff_date,
            },
            "status": {
                "foundOrderCount": len(found_orders),
                "qualifiedOrderCount": len(qualified_orders),
                "exportedOrderCount": len(filtered_orders),
                "skippedEndedOrderCount": skipped_ended_count,
                "cappedAtEndOrderCount": capped_at_end_count,
                "detailRowCount": len(rows),
            },
            "orders": filtered_orders,
            "rows": rows,
        }


def write_outputs(result: Dict[str, Any], output_path: Path, json_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    rows = result.get("rows") or []
    pd.DataFrame(rows, columns=OUTPUT_COLUMNS).to_excel(output_path, sheet_name="数据明细", index=False)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def empty_result(
    *,
    keyword: str,
    start_time: str,
    end_time: str,
    page_size: int,
    cycle_days: int,
    max_orders: int,
    range_mode: str,
    cutoff_date: str,
    reason: str,
    date_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "scrapeTime": datetime.now().isoformat(timespec="seconds"),
        "input": {
            "keyword": keyword,
            "startTime": start_time,
            "endTime": end_time,
            "pageSize": page_size,
            "cycleDays": cycle_days,
            "maxOrders": max_orders,
            "rangeMode": range_mode,
            "cutoffDate": cutoff_date,
            "dateState": date_state or {},
        },
        "status": {
            "foundOrderCount": 0,
            "qualifiedOrderCount": 0,
            "exportedOrderCount": 0,
            "detailRowCount": 0,
            "skipReason": reason,
        },
        "orders": [],
        "rows": [],
    }


def resolve_auto_range(
    *,
    sheets_client: FeishuSheetsClient,
    latest_allowed_date: date,
    min_task_groups: int,
) -> Dict[str, Any]:
    date_state = sheets_client.existing_date_state(min_task_groups=min_task_groups)
    confirmed_max_text = date_state.get("confirmedMaxDate")
    raw_max_text = date_state.get("rawMaxDate")
    data_row_count = int(date_state.get("dataRowCount") or 0)

    if confirmed_max_text:
        confirmed_max_date = parse_date_value(confirmed_max_text)
        if not confirmed_max_date:
            raise ApiError(f"飞书表格最大日期无法解析: {confirmed_max_text}")
        target_date = confirmed_max_date + timedelta(days=1)
        if target_date > latest_allowed_date:
            return {
                "rangeMode": "skip",
                "startDate": api_date(target_date),
                "cutoffDate": api_date(target_date),
                "dateState": date_state,
                "reason": (
                    f"飞书已确认同步到 {confirmed_max_text}，下一天 {display_date(target_date)} "
                    f"超过当前允许截止日期 {display_date(latest_allowed_date)}"
                ),
            }
        return {
            "rangeMode": "catchup",
            "startDate": api_date(target_date),
            "cutoffDate": api_date(latest_allowed_date),
            "dateState": date_state,
            "reason": "",
        }

    if data_row_count == 0:
        return {
            "rangeMode": "full",
            "startDate": "",
            "cutoffDate": api_date(latest_allowed_date),
            "dateState": date_state,
            "reason": "飞书表格没有历史数据，执行首次全量初始化",
        }

    raise ApiError(
        "飞书表格已有数据，但没有找到可确认的最大日期；"
        f"要求同一天至少 {date_state.get('minTaskGroups')} 个任务组，"
        f"当前原始最大日期是 {raw_max_text or '-'}。"
        "如果这是测试表，可临时传 --min-date-task-groups 1。"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="淘宝星河订单管理推广效果明细导出")
    parser.add_argument("keyword", nargs="?", default=DEFAULT_KEYWORD, help="订单名称搜索关键词，默认：启萃")
    parser.add_argument("--date", default="", help="自动模式的最晚允许日期或手动模式的数据日期，格式 YYYY-MM-DD；默认昨天")
    parser.add_argument("--range-mode", choices=("auto", "daily", "full"), default="auto", help="auto 读取飞书最大日期后抓缺口区间；daily 抓指定日期当天；full 抓订单投放开始至截止日期")
    parser.add_argument("--min-date-task-groups", type=int, default=2, help="auto 模式确认最大日期所需的最少任务组数量，默认 2")
    parser.add_argument("--start-time", default="", help="明细开始时间；为空时 daily 使用 --date，full 使用各订单投放开始日期")
    parser.add_argument("--end-time", default="", help="明细结束时间；为空时使用 --date 00:00:00")
    parser.add_argument("--cycle-days", type=int, default=30, help="归因周期，默认 30")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-orders", type=int, default=0, help="仅用于测试；0 表示不限制")
    parser.add_argument("--allow-empty-orders", action="store_true", help="允许订单搜索结果为空；默认空结果会报错并停止写入飞书")
    parser.add_argument("--save-local", action="store_true", help="保存本地 Excel 和 JSON")
    parser.add_argument("--output", default="")
    parser.add_argument("--json-output", default="")
    parser.add_argument("--write-feishu", action="store_true", help="写入飞书；保留兼容参数，默认已写入飞书")
    parser.add_argument("--dry-run", action="store_true", help="只抓取和可选保存本地文件，不写入飞书")
    parser.add_argument("--feishu-target", choices=("sheets", "bitable"), default="sheets", help="默认写入飞书电子表格")
    parser.add_argument("--feishu-write-mode", choices=("upsert", "append"), default="upsert", help="写入电子表格方式；upsert 会合并去重并按任务组、日期重排，append 只追加")
    parser.add_argument("--feishu-app-id", default="")
    parser.add_argument("--feishu-app-secret", default="")
    parser.add_argument("--feishu-url", default="", help="飞书电子表格 URL，可用于自动解析 spreadsheetToken 和 sheetId")
    parser.add_argument("--feishu-spreadsheet-token", default="", help="飞书电子表格 spreadsheetToken")
    parser.add_argument("--feishu-sheet-id", default="", help="飞书电子表格工作表 sheetId")
    parser.add_argument("--feishu-app-token", default="", help="飞书多维表格 app_token，仅 --feishu-target bitable 使用")
    parser.add_argument("--feishu-table-id", default="", help="飞书多维表格 table_id，仅 --feishu-target bitable 使用")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_env_file()
    args = parse_args()
    cookies, cookie_path = load_cookies()
    scraper = TaobaoXingheScraperV5(cookies=cookies, debug=not args.quiet)
    if not scraper.tb_token:
        raise ApiError("Cookie 中未找到 _tb_token_，请重新复制登录后的 Cookie")

    if not args.quiet:
        print("=" * 72)
        print("  淘宝星河订单管理推广效果明细导出")
        print("=" * 72)
        print(f"Cookie: {cookie_path} ({len(cookies)} fields)")
        print(f"Keyword: {args.keyword} | Cycle: {args.cycle_days} days | Range: {args.range_mode}")

    range_info = cutoff_time_range(args.date)
    latest_allowed_date = parse_date_value(range_info["cutoffDate"])
    if not latest_allowed_date:
        raise ApiError(f"日期格式错误: {range_info['cutoffDate']}")
    page_size = max(1, min(args.page_size, 200))
    max_orders = max(0, args.max_orders)
    should_write_feishu = not args.dry_run
    sheets_client: Optional[FeishuSheetsClient] = None
    date_state: Dict[str, Any] = {}
    effective_range_mode = args.range_mode

    if args.range_mode == "auto":
        if args.feishu_target != "sheets":
            raise ApiError("auto 模式需要读取飞书电子表格日期列，目前不支持 bitable")
        sheets_client = feishu_sheets_client_from_args(args)
        auto_range = resolve_auto_range(
            sheets_client=sheets_client,
            latest_allowed_date=latest_allowed_date,
            min_task_groups=max(1, args.min_date_task_groups),
        )
        effective_range_mode = auto_range["rangeMode"]
        range_start_date = auto_range.get("startDate") or auto_range["cutoffDate"]
        range_info["cutoffDate"] = auto_range["cutoffDate"]
        range_info["startTime"] = f"{range_start_date} 00:00:00"
        range_info["endTime"] = f"{range_info['cutoffDate']} 00:00:00"
        date_state = auto_range.get("dateState") or {}
        if not args.quiet:
            print(f"Feishu confirmed max date: {date_state.get('confirmedMaxDate') or '-'}")
            print(
                f"Target range: {range_start_date} -> {range_info['cutoffDate']} "
                f"| Effective range: {effective_range_mode}"
            )
        if effective_range_mode == "skip":
            result = empty_result(
                keyword=args.keyword,
                start_time=args.start_time,
                end_time=args.end_time,
                page_size=page_size,
                cycle_days=args.cycle_days,
                max_orders=max_orders,
                range_mode=args.range_mode,
                cutoff_date=range_info["cutoffDate"],
                reason=auto_range.get("reason") or "没有需要抓取的新日期",
                date_state=date_state,
            )
        else:
            result = None
    else:
        result = None

    start_time = normalize_datetime(args.start_time, "00:00:00")
    if not start_time and effective_range_mode == "catchup":
        start_time = range_info["startTime"]
    end_time = normalize_datetime(args.end_time, "00:00:00") or range_info["endTime"]
    exporter = FeishuOrderEffectExporter(scraper)
    if result is None:
        result = exporter.export(
            keyword=args.keyword,
            start_time=start_time,
            end_time=end_time,
            page_size=page_size,
            cycle_days=args.cycle_days,
            max_orders=max_orders,
            range_mode=effective_range_mode,
            cutoff_date=range_info["cutoffDate"],
            allow_empty_orders=args.allow_empty_orders,
        )
        result["input"]["requestedRangeMode"] = args.range_mode
        result["input"]["effectiveRangeMode"] = effective_range_mode
        result["input"]["dateState"] = date_state

    returned_date_state = row_date_summary(result.get("rows") or [])
    result["status"]["returnedDateState"] = returned_date_state

    should_save_local = args.save_local or bool(args.output or args.json_output) or args.dry_run
    output_path: Optional[Path] = None
    json_path: Optional[Path] = None
    if should_save_local:
        output_path = Path(args.output) if args.output else default_output_path(args.keyword)
        json_path = json_output_path(output_path, args.json_output)
        write_outputs(result, output_path, json_path)

    feishu_written = 0
    feishu_write_skipped_reason = ""
    rows_to_write = result.get("rows") or []
    if should_write_feishu:
        if not rows_to_write:
            feishu_write_skipped_reason = "本次没有新明细行"
        elif args.feishu_target == "bitable":
            bitable_client = feishu_bitable_client_from_args(args)
            feishu_written = bitable_client.batch_create_records(rows_to_write)
        else:
            if sheets_client is None:
                sheets_client = feishu_sheets_client_from_args(args)
            if args.feishu_write_mode == "append":
                feishu_written = sheets_client.append_rows(rows_to_write)
            else:
                corrections = order_id_corrections_from_orders(result.get("orders") or [])
                feishu_written = sheets_client.upsert_rows(rows_to_write, order_id_corrections=corrections)

    status = result["status"]
    print("\n" + "=" * 72)
    print("导出完成")
    print(f"搜索订单: {status['foundOrderCount']} 个")
    print(f"符合条件订单: {status['qualifiedOrderCount']} 个")
    print(f"导出订单: {status['exportedOrderCount']} 个")
    if status.get("skippedEndedOrderCount"):
        print(f"投放已截止跳过: {status['skippedEndedOrderCount']} 个")
    if status.get("cappedAtEndOrderCount"):
        print(f"按投放截止日裁剪: {status['cappedAtEndOrderCount']} 个")
    print(f"明细行数: {status['detailRowCount']} 行")
    if returned_date_state["maxDate"]:
        print(f"接口返回日期: {returned_date_state['minDate']} -> {returned_date_state['maxDate']}")
        cutoff_row_date = parse_date_value(range_info["cutoffDate"])
        max_returned_date = parse_date_value(returned_date_state["maxDate"])
        if cutoff_row_date and max_returned_date and max_returned_date < cutoff_row_date:
            print(f"提示: 星河接口暂未返回目标日期 {display_date(cutoff_row_date)} 的明细，后续自动任务会继续补抓。")
    else:
        print("接口返回日期: 无明细行")
        cutoff_row_date = parse_date_value(range_info["cutoffDate"])
        if cutoff_row_date and effective_range_mode in ("catchup", "daily"):
            print(f"提示: 星河接口暂未返回目标日期 {display_date(cutoff_row_date)} 的明细，飞书日期不会推进。")
    if output_path and json_path:
        print(f"Excel文件: {output_path}")
        print(f"JSON文件: {json_path}")
    else:
        print("本地文件: 未输出")
    if should_write_feishu:
        if feishu_write_skipped_reason:
            print(f"飞书写入: 已跳过（{feishu_write_skipped_reason}）")
        else:
            print(f"飞书写入: {feishu_written} 行")
    else:
        print("飞书写入: 已跳过")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
