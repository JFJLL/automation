import sys
import os

console_dir = "D:/download/pic-vec/automation/sync_console"
os.chdir(console_dir)
sys.path.insert(0, console_dir)

from fastapi.testclient import TestClient
from app.main import app

def run_tests():
    client = TestClient(app)
    
    # 1. 验证 HTML 页面无冗余组件且包含自定义 Modal、纯文字“加词”与无括号频率文案
    r_page = client.get("/keyword")
    assert r_page.status_code == 200
    html = r_page.text
    assert "appendWordsModal" in html
    assert "deleteConfirmModal" in html
    assert "directSheetModal" in html
    assert "statsRow" not in html
    assert "btnExport" not in html
    assert "导出表格" not in html
    assert "加词" in html
    assert ">加词</button>" in html, "Must have clean button label without emoji"
    assert "➕ 加词" not in html, "Emoji must be removed from button"
    assert "推荐，T-1数据就绪" not in html, "Parentheses and notes must be removed"
    assert "每天 12:30 执行" in html
    assert "confirm(" not in html
    print("[1] UI 规范、纯文字按钮与精简选项校验通过")

    # 2. 验证多词搜索接口
    r_search = client.post("/api/keyword/search", json={
        "keywords": "辛芷蕾同款凯乐石 凯乐石",
        "start_date": "2026-08-25",
        "end_date": "2026-09-23"
    })
    assert r_search.status_code == 200
    s_data = r_search.json()
    assert s_data["success"] is True
    assert set(s_data["keywords"]) == {"辛芷蕾同款凯乐石", "凯乐石"}
    assert len(s_data["dates"]) == 30
    xzl_total = sum(v["search_num"] for v in s_data["data"]["辛芷蕾同款凯乐石"].values())
    assert xzl_total == 66620
    print("[2] 多词搜索与官方指标核对通过")

    # 3. 验证任务列表与加词接口
    tasks = client.get("/api/keyword/tasks").json()
    if tasks:
        t_id = tasks[0]["id"]
        r_append = client.post(f"/api/keyword/tasks/{t_id}/append_keywords", json={
            "keywords": "测试新词",
            "sync_now": False
        })
        assert r_append.status_code == 200
        assert r_append.json()["success"] is True
        print(f"[3] 任务 #{t_id} 追加新词验证通过")

    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()

