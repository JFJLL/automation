import csv
import io
import zipfile
from typing import Any, Dict, List

import openpyxl
from fastapi import HTTPException
from platforms.registry import PLATFORMS, calculate_match_scores, detect_best_platform, find_date_column, find_id_column

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
MAX_UNCOMPRESSED_SIZE = 100 * 1024 * 1024  # 100MB
MAX_COMPRESSION_RATIO = 100
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
MAX_SHEETS = 20
MAX_ROWS_PER_SHEET = 5000
MAX_COLS_PER_SHEET = 200

def normalize_date_str(val: Any) -> str:
    s = str(val).strip().replace("/", "-").split(" ")[0]
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 8:
        candidate = f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    else:
        candidate = s
    try:
        from datetime import datetime as dt
        parsed = dt.strptime(candidate, "%Y-%m-%d").date()
        return parsed.isoformat()
    except Exception:
        return s

def check_zip_bomb(file_bytes: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            total_uncompressed = 0
            for info in z.infolist():
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_UNCOMPRESSED_SIZE:
                    raise HTTPException(status_code=400, detail="解压后数据量过大，已被安全防护拦截")
            compressed_size = len(file_bytes)
            if compressed_size > 0 and (total_uncompressed / compressed_size) > MAX_COMPRESSION_RATIO:
                raise HTTPException(status_code=400, detail="检测到异常高压缩比文件，已被安全防护拦截")
    except zipfile.BadZipFile:
        pass

def parse_excel_sheets(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过 10MB 限制")

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件扩展名: {ext}，仅支持 xlsx/xls/csv")

    if ext == ".xlsx":
        check_zip_bomb(file_bytes)

    sheets_info = []

    try:
        if ext == ".csv":
            text = file_bytes.decode("utf-8-sig", errors="replace")
            reader = list(csv.reader(io.StringIO(text)))
            if not reader:
                raise HTTPException(status_code=400, detail="CSV 文件内容为空")
            header = [str(c).strip() for c in reader[0][:MAX_COLS_PER_SHEET]]
            sample_rows = []
            for r in reader[1:31]:
                row_dict = {col: str(val).strip() for col, val in zip(header, r[:len(header)]) if col}
                if any(row_dict.values()):
                    sample_rows.append(row_dict)
            scores = calculate_match_scores(header)
            best_code, _ = detect_best_platform(header)
            sheets_info.append({
                "sheet_title": filename.rsplit(".", 1)[0],
                "header_row_index": 0,
                "headers": header,
                "sample_rows": sample_rows,
                "detected_platform": best_code,
                "match_scores": scores
            })
            return sheets_info

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        sheet_names = wb.sheetnames[:MAX_SHEETS]

        for title in sheet_names:
            ws = wb[title]
            rows_iter = []
            for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
                if r_idx >= MAX_ROWS_PER_SHEET:
                    break
                rows_iter.append(row[:MAX_COLS_PER_SHEET])

            if not rows_iter:
                continue

            header_row_idx = 0
            header_vals = []
            for idx, row in enumerate(rows_iter[:10]):
                clean_r = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if len(clean_r) >= 2:
                    header_row_idx = idx
                    header_vals = [str(c).strip() if c is not None else "" for c in row]
                    while header_vals and not header_vals[-1]:
                        header_vals.pop()
                    break
            if not header_vals:
                continue

            sample_rows = []
            for r in rows_iter[header_row_idx + 1: header_row_idx + 31]:
                row_dict = {}
                for col_name, val in zip(header_vals, r):
                    if col_name:
                        row_dict[col_name] = "" if val is None else str(val).strip()
                if any(row_dict.values()):
                    sample_rows.append(row_dict)

            scores = calculate_match_scores(header_vals)
            best_code, _ = detect_best_platform(header_vals)

            sheets_info.append({
                "sheet_title": title,
                "header_row_index": header_row_idx,
                "headers": header_vals,
                "sample_rows": sample_rows,
                "detected_platform": best_code,
                "match_scores": scores
            })
        wb.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件解析失败: {str(e)}")

    if not sheets_info:
        raise HTTPException(status_code=400, detail="未能从文件中读取到有效工作表或表头")

    return sheets_info

def analyze_sheet_for_platform(sheet_info: Dict[str, Any], selected_platform: str) -> Dict[str, Any]:
    headers = sheet_info["headers"]
    sample_rows = sheet_info["sample_rows"]
    scores = sheet_info["match_scores"]

    selected_score = scores.get(selected_platform, {})
    detected_platform = sheet_info["detected_platform"]
    detected_score = scores.get(detected_platform, {})

    needs_confirm = False
    confirm_message = ""
    if detected_platform != selected_platform:
        sel_has_id = selected_score.get("has_id_column", False)
        det_has_id = detected_score.get("has_id_column", False)
        sel_score = selected_score.get("score", 0)
        det_score = detected_score.get("score", 0)
        if (not sel_has_id and det_has_id) or (det_score > sel_score + 5):
            needs_confirm = True
            sel_name = PLATFORMS.get(selected_platform, {}).get("name", selected_platform)
            det_name = PLATFORMS.get(detected_platform, {}).get("name", detected_platform)
            confirm_message = (
                f"您选择了【{sel_name}】（匹配率 {selected_score.get('score', 0)}%），"
                f"但表头特征更符合【{det_name}】（匹配率 {detected_score.get('score', 0)}%）。\n"
                f"若您确认该表格确实来自【{sel_name}】，可点击继续；也可以切换为【{det_name}】。"
            )

    id_col = find_id_column(selected_platform, headers)
    date_col = find_date_column(selected_platform, headers)

    entity_ids = []
    seen = set()
    dates = []
    for r in sample_rows:
        val = str(r.get(id_col, "")).strip()
        if val and val not in seen and val != id_col:
            seen.add(val)
            entity_ids.append(val)
        d_val = normalize_date_str(r.get(date_col, ""))
        if len(d_val) == 10 and d_val[4] == "-" and d_val[7] == "-":
            dates.append(d_val)

    dimension = "默认"
    if selected_platform == "taobao":
        dimension = "内容" if "内容ID" in headers else "任务"
    elif selected_platform == "juguang":
        if "精准定向" in headers:
            dimension = "target"
        elif "关键词" in headers:
            dimension = "keyword"
        elif "投放位置" in headers and "创意ID" not in headers:
            dimension = "account"
        else:
            dimension = "creativity"

    platform_vocab = set(PLATFORMS.get(selected_platform, {}).get("vocab", []))
    column_mapping = []
    for h in headers:
        is_key = (h == id_col or h == date_col)
        mapped = (h in platform_vocab)
        column_mapping.append({
            "column_name": h,
            "is_key": is_key,
            "mapped": mapped,
            "status": "ok" if mapped else "unmapped_metric"
        })

    return {
        "sheet_title": sheet_info["sheet_title"],
        "headers": headers,
        "id_column": id_col,
        "sample_id_values": entity_ids[:5],
        "date_column": date_col,
        "detected_entity_ids": entity_ids,
        "min_sample_date": min(dates) if dates else None,
        "max_sample_date": max(dates) if dates else None,
        "dimension": dimension,
        "column_mapping": column_mapping,
        "needs_confirm": needs_confirm,
        "confirm_message": confirm_message,
        "selected_platform": selected_platform,
        "detected_platform": detected_platform
    }
