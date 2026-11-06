import io
import pandas as pd
from core.sync import (
    format_cell_value,
    format_id_value,
    is_id_column,
    coerce_row_data_types,
    map_item_to_row,
)
from core.ingest import parse_excel_sheets


def test_is_id_column_precision():
    assert is_id_column("任务ID") is True
    assert is_id_column("内容ID") is True
    assert is_id_column("创意ID") is True
    assert is_id_column("orderId") is True
    assert is_id_column("contentId") is True
    assert is_id_column("projectId") is True
    assert is_id_column("sellerId") is True
    assert is_id_column("店铺编码") is True
    assert is_id_column("流水号") is True

    assert is_id_column("bid") is False
    assert is_id_column("平均市场出价") is False
    assert is_id_column("阅读UV") is False
    assert is_id_column("点赞UV") is False
    assert is_id_column("下单GMV") is False
    assert is_id_column("日期") is False
    assert is_id_column("任务标题") is False
    assert is_id_column("平台") is False


def test_format_id_value_cleans_float_str():
    assert format_id_value("195082") == "195082"
    assert format_id_value("195082.0") == "195082"
    assert format_id_value(195082) == "195082"
    assert format_id_value(195082.0) == "195082"
    assert format_id_value("6a79a074000000003301b89e") == "6a79a074000000003301b89e"
    assert format_id_value(None) == ""


def test_format_cell_value_type_fidelity():
    # Integers
    assert format_cell_value(6482) == 6482
    assert isinstance(format_cell_value(6482), int)
    assert format_cell_value("6482") == 6482
    assert isinstance(format_cell_value("6482"), int)
    assert format_cell_value(0) == 0
    assert isinstance(format_cell_value(0), int)
    assert format_cell_value("0") == 0
    assert isinstance(format_cell_value("0"), int)

    # Floats / Decimals
    assert format_cell_value(35.9) == 35.9
    assert isinstance(format_cell_value(35.9), float)
    assert format_cell_value("35.9") == 35.9
    assert isinstance(format_cell_value("35.9"), float)

    # Float whole numbers from pandas float casting (e.g. 306.0)
    assert format_cell_value("306.0") == 306
    assert isinstance(format_cell_value("306.0"), int)
    assert format_cell_value(306.0) == 306
    assert isinstance(format_cell_value(306.0), int)

    # Non-numeric text
    assert format_cell_value("婴配-启萃-日常-7月-小红盟") == "婴配-启萃-日常-7月-小红盟"
    assert format_cell_value("小红书") == "小红书"
    assert format_cell_value("") == ""
    assert format_cell_value(None) == ""

    # Formulas preserved
    assert format_cell_value("=SUM(F2:F10)") == "=SUM(F2:F10)"

    # Rich text list preserved
    rich_text = [{"text": "https://example.com", "link": "https://example.com"}]
    assert format_cell_value(rich_text) == rich_text


def test_coerce_row_data_types_jzt_columns():
    headers = [
        "日期", "任务ID", "任务标题", "平台", "归因范围",
        "阅读UV", "点赞UV", "收藏UV", "评论UV", "分享UV",
        "互动UV", "访客UV", "搜索浏览UV", "商详浏览UV", "商品加购UV",
        "商品收藏UV", "下单UV", "主推商品下单UV", "下单GMV", "主推商品下单GMV",
        "成交UV", "主推商品成交uv"
    ]
    # Raw row with all strings (as read from legacy Feishu sheet)
    raw_row = [
        "2026-07-01", "195082.0", "婴配-启萃-日常-7月-小红盟", "小红书", "飞鹤（FIRMUS）",
        "6482", "855", "608", "51", "18",
        "1532", "12", "4", "12", "10",
        "0", "1", "0", "35.9", "0.0",
        "1", "0"
    ]

    coerced = coerce_row_data_types(raw_row, headers, id_col="任务ID", date_col="日期")

    assert isinstance(coerced[0], int)  # Excel date serial
    assert coerced[1] == "195082"  # Clean string ID without .0
    assert isinstance(coerced[1], str)
    assert coerced[2] == "婴配-启萃-日常-7月-小红盟"
    assert isinstance(coerced[5], int) and coerced[5] == 6482
    assert isinstance(coerced[6], int) and coerced[6] == 855
    assert isinstance(coerced[7], int) and coerced[7] == 608
    assert isinstance(coerced[11], int) and coerced[11] == 12
    assert isinstance(coerced[16], int) and coerced[16] == 1
    assert isinstance(coerced[18], float) and coerced[18] == 35.9
    assert isinstance(coerced[20], int) and coerced[20] == 1


def test_map_item_to_row_preserves_numbers():
    headers = ["日期", "任务ID", "阅读UV", "下单GMV"]
    item = {
        "日期": "2026-10-23",
        "任务ID": 195082,
        "阅读UV": "1250",
        "下单GMV": "99.85",
    }
    row = map_item_to_row(item, headers, id_col="任务ID", date_col="日期")
    assert isinstance(row[0], int)  # Serial date
    assert row[1] == "195082"  # ID is str
    assert row[2] == 1250  # Metric is int
    assert isinstance(row[2], int)
    assert row[3] == 99.85  # GMV is float
    assert isinstance(row[3], float)


def test_parse_excel_sheets_preserves_numeric_metrics():
    df = pd.DataFrame([
        {
            "日期": "2026-07-01",
            "任务ID": 195082,
            "任务标题": "婴配-启萃-日常-7月-小红盟",
            "阅读UV": 6482,
            "下单GMV": 35.9,
        }
    ])
    bio = io.BytesIO()
    df.to_excel(bio, index=False)
    bio.seek(0)

    sheets = parse_excel_sheets(bio.getvalue(), "test.xlsx")
    assert len(sheets) == 1
    row0 = sheets[0]["all_data_rows"][0]
    assert row0["任务ID"] == "195082"  # ID preserved as string
    assert row0["阅读UV"] == 6482  # Metric preserved as int
    assert isinstance(row0["阅读UV"], int)
    assert row0["下单GMV"] == 35.9  # GMV preserved as float
    assert isinstance(row0["下单GMV"], float)
