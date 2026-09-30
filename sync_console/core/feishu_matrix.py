import hashlib
from typing import Any, List

from feishu.client import FeishuClient, FeishuError, column_letter

MAX_MATRIX_ROWS = 5000
MAX_MATRIX_COLS = 200

def sanitize_formula_injection(val: Any) -> Any:
    if isinstance(val, str) and val and val[0] in ('=', '+', '-', '@'):
        return f"'{val}"
    return val

def write_matrix_to_sheet(
    feishu: FeishuClient,
    ss_token: str,
    sheet_id: str,
    matrix: List[List[Any]],
    col_chunk_size: int = 50
) -> None:
    if not matrix:
        return

    total_rows = len(matrix)
    if total_rows > MAX_MATRIX_ROWS:
        raise FeishuError(f"行数 {total_rows} 超过最大允许上限 {MAX_MATRIX_ROWS}")

    total_cols = max(len(r) for r in matrix) if matrix else 0
    if total_cols > MAX_MATRIX_COLS:
        raise FeishuError(f"列数 {total_cols} 超过最大允许上限 {MAX_MATRIX_COLS}")

    # Formula injection protection
    sanitized_matrix = [
        [sanitize_formula_injection(cell) for cell in row]
        for row in matrix
    ]

    sheets = feishu.get_sheets(ss_token)
    if not sheets:
        raise FeishuError(f"Spreadsheet {ss_token} has no sheets.")

    curr_sheet = next((s for s in sheets if s.get("sheet_id") == sheet_id), sheets[0])
    grid_props = curr_sheet.get("grid_properties", {})
    curr_cols = grid_props.get("column_count", 20)
    curr_rows = grid_props.get("row_count", 200)

    # 扩展列数
    if total_cols > curr_cols:
        add_cols = total_cols - curr_cols + 20
        feishu.request("POST", f"sheets/v2/spreadsheets/{ss_token}/dimension_range", json={
            "dimension": {
                "sheetId": sheet_id,
                "majorDimension": "COLUMNS",
                "length": add_cols
            }
        })

    # 扩展行数
    if total_rows > curr_rows:
        add_rows = total_rows - curr_rows + 50
        feishu.request("POST", f"sheets/v2/spreadsheets/{ss_token}/dimension_range", json={
            "dimension": {
                "sheetId": sheet_id,
                "majorDimension": "ROWS",
                "length": add_rows
            }
        })

    # 分块写入
    for c_start in range(1, total_cols + 1, col_chunk_size):
        c_end = min(c_start + col_chunk_size - 1, total_cols)
        start_letter = column_letter(c_start)
        end_letter = column_letter(c_end)
        range_str = f"{sheet_id}!{start_letter}1:{end_letter}{total_rows}"

        chunk_rows = []
        for r in sanitized_matrix:
            sub = r[c_start - 1 : c_end]
            if len(sub) < (c_end - c_start + 1):
                sub = sub + [""] * ((c_end - c_start + 1) - len(sub))
            chunk_rows.append(sub)

        feishu.request("PUT", f"sheets/v2/spreadsheets/{ss_token}/values", json={
            "valueRange": {"range": range_str, "values": chunk_rows}
        })

def backup_sheet_values(feishu: FeishuClient, ss_token: str, sheet_id: str, col_count: int = 50) -> List[List[Any]]:
    return feishu.read_values(ss_token, sheet_id, col_count=col_count)

def rollback_sheet_values(
    feishu: FeishuClient,
    ss_token: str,
    sheet_id: str,
    backup: List[List[Any]],
    col_count: int = 50
) -> bool:
    try:
        # 1. 清空备份行数之后的所有多余数据
        backup_len = len(backup)
        feishu.clear_rows_below(ss_token, sheet_id, keep_header_row=backup_len, col_count=col_count)
        # 2. 写回备份数据
        if backup:
            feishu.write_rows(ss_token, sheet_id, start_row=1, rows=backup)
        # 3. 校验回滚一致性
        restored = feishu.read_values(ss_token, sheet_id, col_count=col_count)
        restored_hash = hashlib.sha256(str(restored).encode("utf-8")).hexdigest()
        backup_hash = hashlib.sha256(str(backup).encode("utf-8")).hexdigest()
        return restored_hash == backup_hash
    except Exception:
        return False
