import pytest

pytest.importorskip("playwright", reason="playwright is not installed")
from playwright.sync_api import sync_playwright


@pytest.mark.e2e
def test_react_spa_no_iframe_e2e():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # 1. 访问首页 (React SPA)
        page.goto("http://127.0.0.1:8092/", wait_until="domcontentloaded")

        # 核心架构断言 (Section 四十九)：页面中绝对没有 iframe 架构！
        iframe_count = page.locator("iframe").count()
        assert iframe_count == 0, f"Expected 0 iframes, but found {iframe_count}"
        assert '<iframe id="keywordFrame"' not in page.content()
        assert 'keywordFrame' not in page.content()

        # 2. 验证导航至关键词洞察页面
        page.click("button:has-text('关键词洞察')")
        page.wait_for_timeout(500)

        # 验证关键词洞察页面组件渲染
        assert "关键词洞察" in page.inner_text(".container")
        assert "关键词库" in page.inner_text(".container")

        # 再次确认无 iframe
        assert page.locator("iframe").count() == 0

        # 3. 验证导航回数据同步中心并查看任务页面
        page.click("button:has-text('数据同步中心')")
        page.wait_for_timeout(500)
        page.click("a[href='/tasks']")
        page.wait_for_timeout(500)
        assert "现有定时同步任务" in page.inner_text(".container")

        # 验证没有未捕获的前端 JS 异常
        assert len(console_errors) == 0, f"Found console errors: {console_errors}"

        browser.close()

