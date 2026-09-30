import sys
import pytest
from playwright.sync_api import sync_playwright

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
        page.click("a[href='/keyword']")
        page.wait_for_timeout(500)
        
        # 验证关键词洞察页面组件渲染
        assert "小红书聚光关键词深度洞察" in page.inner_text("main")
        assert "关键词库索引" in page.inner_text("main")
        
        # 再次确认无 iframe
        assert page.locator("iframe").count() == 0
        
        # 3. 验证导航至同步任务页面
        page.click("a[href='/tasks']")
        page.wait_for_timeout(500)
        assert "数据同步任务管理" in page.inner_text("main")
        
        # 验证没有未捕获的前端 JS 异常
        assert len(console_errors) == 0, f"Found console errors: {console_errors}"
        
        browser.close()

