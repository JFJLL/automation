import time
import json
import threading
import requests
from typing import List, Dict, Any, Optional, Tuple
from app.config import FEISHU_APP_ID, FEISHU_APP_SECRET, SHARED_FOLDER_TOKEN, SHARED_FOLDER_NAME

class FeishuError(RuntimeError):
    pass

def column_letter(n: int) -> str:
    result = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result.append(chr(65 + rem))
    return ''.join(reversed(result)) if result else 'A'

class FeishuClient:
    def __init__(self, app_id: str = FEISHU_APP_ID, app_secret: str = FEISHU_APP_SECRET):
        self.app_id = app_id
        self.app_secret = app_secret
        self.token: Optional[str] = None
        self.expires_at: float = 0
        self.token_lock = threading.Lock()
        self.req_lock = threading.Lock()
        self.last_write = 0.0
        self.session = requests.Session()
        self.session.trust_env = False

    def get_token(self) -> str:
        with self.token_lock:
            if self.token and time.time() < self.expires_at - 180:
                return self.token
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            r = self.session.post(url, json={"app_id": self.app_id, "app_secret": self.app_secret}, timeout=30)
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                raise FeishuError(f"Feishu token failed: {data.get('code')} {data.get('msg')}")
            self.token = data["tenant_access_token"]
            self.expires_at = time.time() + data.get("expire", 7200)
            return self.token

    def request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        url = f"https://open.feishu.cn/open-apis/{path.lstrip('/')}"
        is_write = method.upper() in ("POST", "PUT", "PATCH", "DELETE")
        for attempt in range(4):
            if is_write:
                with self.req_lock:
                    elapsed = time.monotonic() - self.last_write
                    if elapsed < 1.0:
                        time.sleep(1.0 - elapsed)
                    token = self.get_token()
                    headers = kwargs.setdefault("headers", {})
                    headers["Authorization"] = f"Bearer {token}"
                    r = self.session.request(method, url, timeout=45, **kwargs)
                    self.last_write = time.monotonic()
            else:
                token = self.get_token()
                headers = kwargs.setdefault("headers", {})
                headers["Authorization"] = f"Bearer {token}"
                r = self.session.request(method, url, timeout=45, **kwargs)

            if r.status_code >= 500 and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            res = r.json()
            code = res.get("code")
            if code == 0:
                return res.get("data") or {}
            # 限流重试
            if code in (90217, 99991400) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            raise FeishuError(f"Feishu API error {code}: {res.get('msg')}")
        raise FeishuError(f"Feishu API retry exceeded for {path}")

    def get_or_create_shared_folder(self, folder_name: str = SHARED_FOLDER_NAME) -> str:
        if SHARED_FOLDER_TOKEN:
            return SHARED_FOLDER_TOKEN
        # List root folders
        data = self.request("GET", "drive/v1/files?folder_token=&page_size=50")
        files = data.get("files") or []
        for f in files:
            if f.get("type") == "folder" and f.get("name") == folder_name:
                return f.get("token")
        # Create folder
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

    def set_sheet_public_editable(self, spreadsheet_token: str):
        self.request("PATCH", f"drive/v1/permissions/{spreadsheet_token}/public?type=sheet", json={
            "link_share_entity": "tenant_editable",
            "share_entity": "same_tenant",
            "external_access": False
        })

    def get_sheets(self, spreadsheet_token: str) -> List[Dict[str, Any]]:
        res = self.request("GET", f"sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query")
        return res.get("sheets") or []

    def add_worksheet(self, spreadsheet_token: str, title: str) -> str:
        res = self.request("POST", f"sheets/v2/spreadsheets/{spreadsheet_token}/sheets_batch_update", json={
            "requests": [{"addSheet": {"properties": {"title": title}}}]
        })
        replies = res.get("replies") or []
        if replies and "addSheet" in replies[0]:
            return replies[0]["addSheet"]["properties"]["sheetId"]
        raise FeishuError("Failed to add worksheet")

    def read_values(self, spreadsheet_token: str, sheet_id: str, range_suffix: str = "A:AZ") -> List[List[Any]]:
        res = self.request("GET", f"sheets/v2/spreadsheets/{spreadsheet_token}/values/{sheet_id}!{range_suffix}")
        return res.get("valueRange", {}).get("values") or []

    def find_last_row_index(self, spreadsheet_token: str, sheet_id: str) -> int:
        rows = self.read_values(spreadsheet_token, sheet_id, "A:Z")
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

    def merge_cells(self, spreadsheet_token: str, range_str: str, merge_type: str = "MERGE_ALL") -> Dict[str, Any]:
        return self.request("POST", f"sheets/v2/spreadsheets/{spreadsheet_token}/merge_cells", json={
            "range": range_str,
            "mergeType": merge_type
        })

    def clear_rows_below(self, spreadsheet_token: str, sheet_id: str, keep_header_row: int = 1, col_count: int = 50):
        last = self.find_last_row_index(spreadsheet_token, sheet_id)
        if last > keep_header_row:
            end_col = column_letter(max(col_count, 1))
            num_rows = last - keep_header_row
            empty_rows = [["" for _ in range(max(col_count, 1))] for _ in range(num_rows)]
            range_str = f"{sheet_id}!A{keep_header_row + 1}:{end_col}{last}"
            self.request("PUT", f"sheets/v2/spreadsheets/{spreadsheet_token}/values", json={
                "valueRange": {"range": range_str, "values": empty_rows}
            })

    def restore_sheet_values(self, spreadsheet_token: str, sheet_id: str, backup_values: List[List[Any]]) -> bool:
        """发生写入异常时，彻底清空已扩展的脏数据行与列，完整写回备份快照并回读校验"""
        last_row = self.find_last_row_index(spreadsheet_token, sheet_id)
        backup_rows = len(backup_values) if backup_values else 0
        backup_cols = max((len(r) for r in backup_values), default=20)
        max_rows = max(last_row, backup_rows, 1)
        max_cols = max(backup_cols, 35)

        # 1. 彻底清空所有已有/追加的行与列
        empty_rows = [["" for _ in range(max_cols)] for _ in range(max_rows)]
        range_str = f"{sheet_id}!A1:{column_letter(max_cols)}{max_rows}"
        self.request("PUT", f"sheets/v2/spreadsheets/{spreadsheet_token}/values", json={
            "valueRange": {"range": range_str, "values": empty_rows}
        })

        # 2. 完整写回原快照
        if backup_values:
            self.write_rows(spreadsheet_token, sheet_id, start_row=1, rows=backup_values)

        # 3. 回读验证
        verify_range = f"A1:{column_letter(max(backup_cols, 1))}{max(backup_rows, 1)}"
        verify_data = self.read_values(spreadsheet_token, sheet_id, verify_range) or []
        if len(verify_data) != backup_rows:
            raise FeishuError(f"回滚校验失败：预期 {backup_rows} 行，实际回读 {len(verify_data)} 行")
        return True
