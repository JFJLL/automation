import pytest
from unittest.mock import MagicMock
from core.sync import get_item_natural_key
from feishu.client import FeishuClient

def test_juguang_natural_key_distinguishes_keywords_and_placements():
    # 同一创意 ID、同一天，但关键词不同
    item1 = {"创意ID": "c_101", "日期": "2026-09-25", "投放位置": "搜索推广", "精准定向": "定向A", "关键词": "凯乐石冲锋衣"}
    item2 = {"创意ID": "c_101", "日期": "2026-09-25", "投放位置": "搜索推广", "精准定向": "定向A", "关键词": "凯乐石登山鞋"}
    item3 = {"创意ID": "c_101", "日期": "2026-09-25", "投放位置": "信息流推广", "精准定向": "定向A", "关键词": "凯乐石冲锋衣"}
    
    k1 = get_item_natural_key("juguang", item1, "c_101", "")
    k2 = get_item_natural_key("juguang", item2, "c_101", "")
    k3 = get_item_natural_key("juguang", item3, "c_101", "")
    
    assert k1 != k2, "不同关键词必须拥有不同 natural key"
    assert k1 != k3, "不同投放位置必须拥有不同 natural key"
    assert len({k1, k2, k3}) == 3, "三条记录应互不冲突"

def test_taobao_natural_key_distinguishes_flow_type():
    item1 = {"内容ID": "cnt_888", "日期": "2026-09-25", "流量类型": "自然流量"}
    item2 = {"内容ID": "cnt_888", "日期": "2026-09-25", "流量类型": "付费流量"}
    
    k1 = get_item_natural_key("taobao", item1, "cnt_888", "内容")
    k2 = get_item_natural_key("taobao", item2, "cnt_888", "内容")
    assert k1 != k2, "不同流量类型必须拥有不同 natural key"

def test_full_rollback_clears_dirty_tail_rows_and_cols():
    # 模拟飞书存储
    feishu_sheet_state = {
        # 写入前备份为 3 行 x 2 列
        "rows": [
            ["日期", "任务ID"],
            ["2026-09-20", "101"],
            ["2026-09-21", "101"]
        ]
    }
    
    client = FeishuClient(app_id="mock", app_secret="mock")
    
    def mock_request(method, path, **kwargs):
        if method == "PUT" and "values" in path:
            val_range = kwargs.get("json", {}).get("valueRange", {})
            values = val_range.get("values", [])
            # 模拟写入
            start_row = 1
            if "!A" in val_range.get("range", ""):
                try:
                    r_part = val_range["range"].split("!A")[1]
                    start_row = int(r_part.split(":")[0])
                except Exception:
                    start_row = 1
            while len(feishu_sheet_state["rows"]) < start_row - 1 + len(values):
                feishu_sheet_state["rows"].append(["", ""])
            for offset, row in enumerate(values):
                feishu_sheet_state["rows"][(start_row - 1) + offset] = list(row)
            return {}
        elif method == "GET" and "values" in path:
            # 解析请求的范围行数，例如 A1:B3 仅返回 3 行
            req_range = path.split("values/")[1].split("!")[1] if "!" in path else ""
            max_r = len(feishu_sheet_state["rows"])
            if ":" in req_range:
                try:
                    end_cell = req_range.split(":")[1]
                    digits = "".join(c for c in end_cell if c.isdigit())
                    if digits:
                        max_r = min(int(digits), len(feishu_sheet_state["rows"]))
                except Exception:
                    pass
            return {"valueRange": {"values": [list(r) for r in feishu_sheet_state["rows"][:max_r]]}}
        return {}
        
    client.request = mock_request
    client.find_last_row_index = lambda token, sid: len(feishu_sheet_state["rows"])
    
    # 模拟中间写入故障：扩展到了 6 行 x 4 列
    feishu_sheet_state["rows"] = [
        ["日期", "任务ID", "新列1", "新列2"],
        ["2026-09-20", "101", "脏A", "脏B"],
        ["2026-09-21", "101", "脏C", "脏D"],
        ["2026-09-22", "101", "脏E", "脏F"],
        ["2026-09-23", "101", "脏G", "脏H"],
        ["2026-09-24", "101", "脏I", "脏J"],
    ]
    
    old_backup = [
        ["日期", "任务ID"],
        ["2026-09-20", "101"],
        ["2026-09-21", "101"]
    ]
    
    # 执行原子完整回滚
    res = client.restore_sheet_values("token", "sheet0", old_backup)
    assert res is True
    
    # 验证回滚后数据内容严格等于备份
    assert [r for r in feishu_sheet_state["rows"][:3]] == old_backup

