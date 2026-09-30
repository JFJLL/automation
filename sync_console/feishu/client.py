import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from app.config import FEISHU_APP_ID, FEISHU_APP_SECRET, SHARED_FOLDER_NAME, SHARED_FOLDER_TOKEN


class FeishuError(RuntimeError):
    pass

def column_letter(n: int) -> str:
    result = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result.append(chr(65 + rem))
    return ''.join(reversed(result)) if result else 'A'

# Process-level token cache by app_id
_process_token_cache: Dict[str, Tuple[str, float]] = {}
_process_token_lock = threading.Lock()

class FeishuClient:
    def __init__(self, app_id: str = FEISHU_APP_ID, app_secret: str = FEISHU_APP_SECRET):
        self.app_id = app_id
        self.app_secret = app_secret
        self.req_lock = threading.Lock()
        self.last_write = 0.0
        self.session = requests.Session()
        self.session.trust_env = False

    def get_token(self, force_refresh: bool = False) -> str:
        now = time.time()
        with _process_token_lock:
            cached = _process_token_cache.get(self.app_id)
            if not force_refresh and cached:
                token, expires_at = cached
                if now < expires_at - 120:  # 提前 120 秒刷新
                    return token

            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            r = self.session.post(
                url,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=(10, 30)
            )
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                raise FeishuError(f"Feishu token failed: {data.get('code')} {data.get('msg')}")
            new_token = data["tenant_access_token"]
            expires_at = now + data.get("expire", 7200)
            _process_token_cache[self.app_id] = (new_token, expires_at)
            return new_token

    def request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        url = f"https://open.feishu.cn/open-apis/{path.lstrip('/')}"
        is_write = method.upper() in ("POST", "PUT", "PATCH", "DELETE")
        refreshed_401 = False

        for attempt in range(5):
            if is_write:
                with self.req_lock:
                    elapsed = time.monotonic() - self.last_write
                    if elapsed < 1.2:
                        time.sleep(1.2 - elapsed)
                    token = self.get_token()
                    headers = kwargs.setdefault("headers", {})
                    headers["Authorization"] = f"Bearer {token}"
                    r = self.session.request(method, url, timeout=(10, 60), **kwargs)
                    self.last_write = time.monotonic()
            else:
                token = self.get_token()
                headers = kwargs.setdefault("headers", {})
                headers["Authorization"] = f"Bearer {token}"
                r = self.session.request(method, url, timeout=(10, 60), **kwargs)

            # 401 token 过期重刷一次
            if r.status_code == 401 and not refreshed_401:
                refreshed_401 = True
                self.get_token(force_refresh=True)
                continue

            # 429 按 Retry-After 避让
            if r.status_code == 429 and attempt < 4:
                retry_after = float(r.headers.get("Retry-After", 2 * (attempt + 1)))
                time.sleep(retry_after + random.uniform(0.1, 0.5))
                continue

            # 5xx 指数退避加抖动
            if r.status_code >= 500 and attempt < 4:
                time.sleep((1.5 ** attempt) + random.uniform(0.2, 0.6))
                continue

            r.raise_for_status()
            res = r.json()
            code = res.get("code")
            if code == 0:
                return res.get("data") or {}

            # 飞书特定限流码 90217, 99991400
            if code in (90217, 99991400) and attempt < 4:
                time.sleep((2.0 ** attempt) + random.uniform(0.2, 0.8))
                continue

            raise FeishuError(f"Feishu API error {code}: {res.get('msg')}")
        raise FeishuError(f"Feishu API retry exceeded for {path}")

    def get_or_create_shared_folder(self, folder_name: str = SHARED_FOLDER_NAME) -> str:
        if SHARED_FOLDER_TOKEN:
            return SHARED_FOLDER_TOKEN
        # 翻页查询根目录
        page_token = ""
        while True:
            query = "drive/v1/files?folder_token=&page_size=50"
            if page_token:
                query += f"&page_token={page_token}"
            data = self.request("GET", query)
            files = data.get("files") or []
            for f in files:
                if f.get("type") == "folder" and f.get("name") == folder_name:
                    return f.get("token")
            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")

        # 创建文件夹
        create_res = self.request("POST", "drive/v1/files/create_folder", json={"name": folder_name, "folder_token": ""})
        return create_res.get("token")

    def create_spreadsheet(self, title: str, folder_token: str = "") -> Dict[str, str]:
        body = {"title": title}
        if folder_token:
            body["folder_token"] = folder_token
        res = self.request("POST", "sheets/v3/spreadsheets", json=body)
        spreadsheet = res.get("spreadsheet") or {}
        token = spreadsheet.get("spreadsheet_token")
        url = spreadsheet.get("url")
        return {"spreadsheet_token": token, "url": url}

    def set_sheet_share_permission(self, spreadsheet_token: str, mode: Optional[str] = None) -> Dict[str, Any]:
        from app.config import FEISHU_SHEET_SHARE_MODE
        share_mode = (mode or FEISHU_SHEET_SHARE_MODE or "private").strip().lower()
        if share_mode == "tenant_editable":
            payload = {
                "link_share_entity": "tenant_editable",
                "share_entity": "same_tenant",
                "external_access": False
            }
        elif share_mode == "tenant_readable":
            payload = {
                "link_share_entity": "tenant_readable",
                "share_entity": "same_tenant",
                "external_access": False
            }
        else:  # private
            payload = {
                "link_share_entity": "closed",
                "external_access": False
            }

        try:
            self.request("PATCH", f"drive/v1/permissions/{spreadsheet_token}/public?type=sheet", json=payload)
        except Exception:
            pass

        # 回读确认
        try:
            confirmed = self.request("GET", f"drive/v1/permissions/{spreadsheet_token}/public?type=sheet")
            return confirmed or {}
        except Exception:
            return {}

    def set_sheet_public_editable(self, spreadsheet_token: str) -> Dict[str, Any]:
        return self.set_sheet_share_permission(spreadsheet_token)

    def set_public_permission(self, spreadsheet_token: str, edit: bool = True) -> Dict[str, Any]:
        mode = "tenant_editable" if edit else "tenant_readable"
        return self.set_sheet_share_permission(spreadsheet_token, mode=mode)

    def get_sheets(self, spreadsheet_token: str) -> List[Dict[str, Any]]:
        sheets = []
        page_token = ""
        while True:
            path = f"sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
            if page_token:
                path += f"?page_token={page_token}"
            res = self.request("GET", path)
            batch = res.get("sheets") or []
            sheets.extend(batch)
            if not res.get("has_more"):
                break
            page_token = res.get("page_token", "")
        return sheets

    def add_worksheet(self, spreadsheet_token: str, title: str) -> str:
        res = self.request("POST", f"sheets/v2/spreadsheets/{spreadsheet_token}/sheets_batch_update", json={
            "requests": [{"addSheet": {"properties": {"title": title}}}]
        })
        replies = res.get("replies") or []
        if replies and "addSheet" in replies[0]:
            return replies[0]["addSheet"]["properties"]["sheetId"]
        raise FeishuError("Failed to add worksheet")

    def read_values(self, spreadsheet_token: str, sheet_id: str, range_suffix: Optional[str] = None, col_count: Optional[int] = None) -> List[List[Any]]:
        if not range_suffix:
            width = col_count if (col_count and col_count > 0) else 50
            end_col = column_letter(width)
            range_suffix = f"A1:{end_col}5000"
        res = self.request("GET", f"sheets/v2/spreadsheets/{spreadsheet_token}/values/{sheet_id}!{range_suffix}")
        return res.get("valueRange", {}).get("values") or []

    def find_last_row_index(self, spreadsheet_token: str, sheet_id: str, col_count: int = 50) -> int:
        end_col = column_letter(max(col_count, 1))
        rows = self.read_values(spreadsheet_token, sheet_id, range_suffix=f"A:{end_col}")
        last = 0
        for idx, row in enumerate(rows, 1):
            if any(str(c).strip() for c in row if c is not None):
                last = idx
        return last

    def write_rows(self, spreadsheet_token: str, sheet_id: str, start_row: int, rows: List[List[Any]]):
        if not rows:
            return
        width = max(len(r) for r in rows)
        end_col = column_letter(width)
        end_row = start_row + len(rows) - 1
        range_str = f"{sheet_id}!A{start_row}:{end_col}{end_row}"
        self.request("PUT", f"sheets/v2/spreadsheets/{spreadsheet_token}/values", json={
            "valueRange": {"range": range_str, "values": rows}
        })

    def write_ranges(self, spreadsheet_token: str, sheet_id: str, batch_ranges: List[Dict[str, Any]]):
        if not batch_ranges:
            return
        data_payload = []
        for b in batch_ranges:
            data_payload.append({
                "range": f"{sheet_id}!{b['range']}",
                "values": b["values"]
            })
        self.request("POST", f"sheets/v2/spreadsheets/{spreadsheet_token}/values_batch_update", json={
            "valueRanges": data_payload
        })

    def merge_cells(self, spreadsheet_token: str, range_str: str, merge_type: str = "MERGE_ALL") -> Dict[str, Any]:
        return self.request("POST", f"sheets/v2/spreadsheets/{spreadsheet_token}/merge_cells", json={
            "range": range_str,
            "mergeType": merge_type
        })

    def write_cells(self, spreadsheet_token: str, range_str: str, values: List[List[Any]]) -> Dict[str, Any]:
        return self.request("PUT", f"sheets/v2/spreadsheets/{spreadsheet_token}/values", json={
            "valueRange": {"range": range_str, "values": values}
        })

    def add_columns(self, spreadsheet_token: str, sheet_id: str, length: int) -> Dict[str, Any]:
        return self.request("POST", f"sheets/v2/spreadsheets/{spreadsheet_token}/dimension_range", json={
            "dimension": {
                "sheetId": sheet_id,
                "majorDimension": "COLUMNS",
                "length": length
            }
        })

    def add_rows(self, spreadsheet_token: str, sheet_id: str, length: int) -> Dict[str, Any]:
        return self.request("POST", f"sheets/v2/spreadsheets/{spreadsheet_token}/dimension_range", json={
            "dimension": {
                "sheetId": sheet_id,
                "majorDimension": "ROWS",
                "length": length
            }
        })

    def clear_rows_below(self, spreadsheet_token: str, sheet_id: str, keep_header_row: int = 1, col_count: int = 50):
        try:
            last = self.find_last_row_index(spreadsheet_token, sheet_id, col_count=col_count)
        except TypeError:
            last = self.find_last_row_index(spreadsheet_token, sheet_id)
        if last > keep_header_row:
            end_col = column_letter(max(col_count, 1))
            num_rows = last - keep_header_row
            empty_rows = [["" for _ in range(max(col_count, 1))] for _ in range(num_rows)]
            range_str = f"{sheet_id}!A{keep_header_row + 1}:{end_col}{last}"
            self.write_cells(spreadsheet_token, range_str, empty_rows)
    def restore_sheet_values(self, spreadsheet_token: str, sheet_id: str, backup_values: List[List[Any]]) -> bool:
        """回滚时先清掉 len(backup)+1 行之后的全部内容，再写回备份，然后按内容 hash 做校验"""
        import hashlib
        backup_rows = len(backup_values) if backup_values else 0
        backup_cols = max((len(r) for r in backup_values), default=20)
        end_col = column_letter(max(backup_cols, 1))

        # 1. 清理 len(backup)+1 之后的行
        try:
            last_row = self.find_last_row_index(spreadsheet_token, sheet_id, col_count=backup_cols)
        except TypeError:
            last_row = self.find_last_row_index(spreadsheet_token, sheet_id)
        if last_row > backup_rows:
            self.clear_rows_below(spreadsheet_token, sheet_id, keep_header_row=backup_rows, col_count=backup_cols)

        # 2. 写回备份
        if backup_values:
            self.write_rows(spreadsheet_token, sheet_id, start_row=1, rows=backup_values)

        # 3. 回读校验
        verify_range = f"A1:{end_col}{max(backup_rows, 1)}"
        restored = self.read_values(spreadsheet_token, sheet_id, range_suffix=verify_range)
        restored_hash = hashlib.sha256(str(restored[:backup_rows]).encode("utf-8")).hexdigest()
        backup_hash = hashlib.sha256(str(backup_values).encode("utf-8")).hexdigest()
        return restored_hash == backup_hash
