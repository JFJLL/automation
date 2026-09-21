import unittest
import io
import openpyxl
from datetime import datetime
from platforms.registry import calculate_match_scores, detect_best_platform, find_id_column, find_date_column
from core.ingest import parse_excel_sheets, analyze_sheet_for_platform
from core.scheduler import parse_next_run
from core.sync import map_item_to_row
from feishu.client import FeishuClient

class TestSyncConsole(unittest.TestCase):

    def test_platform_matching(self):
        # 1. 测试京准通表头命中
        jzt_headers = ["日期", "任务ID", "任务标题", "平台", "成交GMV", "下单UV"]
        best_code, best_info = detect_best_platform(jzt_headers)
        self.assertEqual(best_code, "jzt")
        self.assertEqual(find_id_column("jzt", jzt_headers), "任务ID")
        self.assertEqual(find_date_column("jzt", jzt_headers), "日期")

        # 2. 测试淘宝星河表头命中
        taobao_headers = ["日期", "内容ID", "流量类型", "归因口径", "商家GMV", "进店UV"]
        best_code, best_info = detect_best_platform(taobao_headers)
        self.assertEqual(best_code, "taobao")
        self.assertEqual(find_id_column("taobao", taobao_headers), "内容ID")

        # 3. 测试聚光表头命中
        jg_headers = ["时间", "创意ID", "笔记ID", "消费", "展现量", "点击率", "精准定向"]
        best_code, best_info = detect_best_platform(jg_headers)
        self.assertEqual(best_code, "juguang")
        self.assertEqual(find_id_column("juguang", jg_headers), "创意ID")

    def test_excel_ingest_pipeline(self):
        # 构造内存中的测试 Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "达人日常数据"
        ws.append(["日期", "任务ID", "任务标题", "平台", "成交GMV"])
        ws.append(["2026-09-15", "198973", "测试任务A", "小红盟", "5200.5"])
        ws.append(["2026-09-16", "198973", "测试任务A", "小红盟", "6100.0"])
        
        bio = io.BytesIO()
        wb.save(bio)
        bytes_data = bio.getvalue()

        # 解析
        sheets = parse_excel_sheets(bytes_data, "test.xlsx")
        self.assertEqual(len(sheets), 1)
        self.assertEqual(sheets[0]["sheet_title"], "达人日常数据")
        self.assertEqual(sheets[0]["detected_platform"], "jzt")

        # 诊断分析 (用户选择了京准通)
        analysis = analyze_sheet_for_platform(sheets[0], "jzt")
        self.assertFalse(analysis["needs_confirm"])
        self.assertIn("198973", analysis["detected_entity_ids"])
        self.assertEqual(analysis["id_column"], "任务ID")

        # 若用户选错为淘宝星河，应触发二次确认提醒
        mismatch_analysis = analyze_sheet_for_platform(sheets[0], "taobao")
        self.assertTrue(mismatch_analysis["needs_confirm"])
        self.assertIn("京准通", mismatch_analysis["confirm_message"])

    def test_rrule_scheduler_calculation(self):
        # 每天 09:00
        dt = parse_next_run("RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0")
        self.assertEqual(dt.hour, 9)
        self.assertEqual(dt.minute, 0)

        # 错峰工作日 13:30
        dt_workday = parse_next_run("RRULE:FREQ=WEEKLY;BYHOUR=13;BYMINUTE=30;BYDAY=MO,TU,WE,TH,FR")
        self.assertEqual(dt_workday.hour, 13)
        self.assertEqual(dt_workday.minute, 30)

    def test_row_mapping(self):
        item = {"日期": "2026-09-18", "任务ID": "198973", "成交GMV": 99.8, "额外指标": "ok"}
        headers = ["日期", "任务ID", "成交GMV", "未映射指标"]
        row = map_item_to_row(item, headers, "任务ID", "日期")
        self.assertEqual(row, ["2026-09-18", "198973", "99.8", ""])

if __name__ == "__main__":
    unittest.main()
