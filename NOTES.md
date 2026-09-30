# JFJLL/automation 修复过程记录与审计日志 (NOTES.md)

## 0. 完整阅读记录
- 已完整阅读：feishu_three_sync/taobao/refresh_adstar_cookie.py 1229 行
- 已完整阅读：feishu_three_sync/taobao/taobaoxinghe_feishu_order_effect.py 1189 行
- 已完整阅读：feishu_three_sync/taobao/taobaoxinghe_scraper.py 1064 行
- 已完整阅读：sync_console/main.py 433 行
- 已完整阅读：sync_console/core/database.py 235 行
- 已完整阅读：sync_console/core/security.py 213 行
- 已完整阅读：sync_console/core/sync_runner.py (待阶段3重构创建)
- 已完整阅读：keyword_service/router.py 335 行
- 已完整阅读：lingxi_service/router.py 373 行
- 已完整阅读：sync_console/feishu/client.py 289 行

## 1. 阶段 0：基线测试与补审报告 (分支: chore/baseline)

### 1.1 基线测试结果
- **pytest**:
  - 运行命令: python -m pytest -q --ignore=tests/test_playwright_e2e.py
  - 结果: 57 passed, 2 failed, 3 warnings in 9.52s.
  - 失败项 1: 	ests/test_api_auth.py::test_cookie_preview_never_exposed (断言 200 == 401，原因是 /api/keyword/cookie 未设鉴权)。
  - 失败项 2: 	ests/test_api_auth.py::test_admin_route_protection (断言 200 == 401，原因是 /api/keyword/tasks 未设鉴权)。
  - 外部依赖: 	ests/test_playwright_e2e.py 依赖本地 playwright 浏览器环境，默认未安装报错，阶段 8 统一加 mark 排除。
- **前端 npm run build**:
  - 构建产物: 1969 modules transformed, dist 生成正常 (index.html, css, js)。
- **前端 vitest run**:
  - 结果: 1 passed (2 tests), 669ms。

### 1.2 三大文件补审与关键缺陷核实

#### A. eishu_three_sync/taobao/refresh_adstar_cookie.py (1229 行)
- **职责**: 启动本地 Chrome (远程调试端口)，通过 CDP (Chrome DevTools Protocol) 自动完成淘宝星河/Adstar 登录及 Cookie 刷新提取。
- **关键函数清单与审查说明**:
  - ind_browser (78-112): 遍历系统注册表与典型路径查找 Chrome 可执行文件。
  - pick_free_port (115-118): 绑定 0 端口获取可用本地端口。
  - wait_for_devtools (126-138): HTTP 轮询 /json/version 等待调试服务就绪。
  - WebSocket (176-285): 自行实现最小 RFC 6455 客户端。问题 (C-16): 缺少心跳 ping 处理，异常关闭直接抛 CookieRefreshError。
  - CdpSession (288-310): 封装 CDP call 命令与 JSON RPC。
  - choose_page_target (321-329): 选择目标页面。问题 (C-15): 若 preferred_host 未命中，直接降级返回 pages[0]，可能误连无关页面。
  - clear_login_state (401-429): 清理 cookies 与 storage。
  - ill_login_form_dom / ill_login_form (504-809): 注入 JS 或模拟键鼠输入用户名密码。
  - 
un_post_login_steps (980-1038): 登录后进入首页并点击员工登录/快速进入。
  - wait_for_login_cookies (1041-1086): 轮询提取符合条件的 cookie。
  - write_cookie_file (1089-1097): 格式化输出为 cookie.txt。
  - main (1138-1221): 流程编排。finally 块执行浏览器进程 terminate/kill。

#### B. eishu_three_sync/taobao/taobaoxinghe_feishu_order_effect.py (1189 行)
- **职责**: 导出淘宝星河效果订单明细，并更新/同步至飞书多维表格或电子表格。
- **核实项**:
  - **C-11 核实**: 
ow_match_key() (192-198行) 仅返回 (结算主体, 日期, 计划名称, 单元名称)，完全不含订单 ID。在 merge_sheet_rows() 中，对于同主体同日期的记录，只要有新返回行，未返回的历史订单行会被直接丢弃。**确认为高危数据丢失缺陷**。
  - **C-12 核实**: cutoff_time_range() (92-98行) 返回 startTime: f'{target_date} 00:00:00' 与 ndTime: f'{target_date} 00:00:00' 完全一致。时间跨度为 0。**确认为时间筛选缺陷**。
  - **C-6 核实**: 
eplace_rows() (527-553行) 构造 range A1:EndCol，若表格右侧存在人工列，全量填充覆盖时如果行数减少或排序重排，会导致人工列与数据错位。**确认为行覆盖缺陷**。
  - 函数清单: 
ormalize_datetime, yesterday_date, cutoff_time_range, order_start_time, order_end_date, ormat_date, parse_date_value, display_date, pi_date, safe_filename, default_output_path, json_output_path, chunked, 
ormalize_row_value, 
ow_identity, 
ow_match_key, 
ow_is_blank, sort_rows_for_sheet, 
ow_date_summary, merge_sheet_rows, display_order_id_from_order, internal_order_id_from_order, order_id_corrections_from_orders, pply_order_id_corrections, pi_response_summary, column_letter, load_env_file, nv_first, parse_feishu_sheet_url, eishu_tenant_access_token, 
esolve_wiki_sheet, 
esolve_first_sheet_id, FeishuSheetsClient (read, replace, upsert, append), FeishuBitableClient, FeishuOrderEffectExporter (search_orders, filter_orders, build_detail_ext, get_effect_detail_rows, export), write_outputs, mpty_result, 
esolve_auto_range, parse_args, main。

#### C. eishu_three_sync/taobao/taobaoxinghe_scraper.py (1064 行)
- **职责**: 抓取淘宝星河达人种草、项目、订单明细与效果归因数据。
- **核实项**:
  - **C-13 核实**: 	o_number() (150-157行) 遇到 ValueError 静默降级为 0.0；list_from_model() (138-147行) 异常数据返回 ([], model)；get_json() (303-314行) 仅判断 HTTP 状态码，未检查响应中 success: false 业务错误，异常时退化为错误 JSON 而不报错。**确认为静默降级缺陷**。
  - **C-14 核实**: get_creator_list() (541-570行) while True 循环中无最大页数限制，且无重复页判定，网络不稳定或上游异常时可能死循环。**确认为分页无上限缺陷**。
  - 函数清单: ApiError, clean_cookie_text, cookie_text_from_json_payload, cookie_text_from_payload, parse_cookie_string, candidate_cookie_paths, load_cookies, irst_value, list_from_model, 	o_number, json_cell, xcel_row, xtract_query_id, infer_input, ormat_money, ormat_bool_cn, date_range_with_days, compact_json, pick_service_provider, content_budget, alue_if_present, TaobaoXingheScraperV5 (__init__, log, _find_tb_token, get_json, get_order_detail, get_event_info_detail, get_order_products, build_effect_ext, get_effect_summary, get_effect_details, get_creator_list, get_creator_task_detail, get_order_list, get_project_list, scrape_order, scrape_project, scrape_project_search), xport_three_tab_excel, parse_args, default_output_path, default_json_output_path, main。

### 1.3 凭据扫描发现 (文件、类型、首次提交)
- lingxi_service/token.json: 真实 Cookie 凭据, 首次提交: c592c30
- eishu_three_sync/jzt_sync/local_login.py: Secret Keyword (京东账号密码明文), 首次提交: 0cca0c0
- eishu_three_sync/manifest.sha256.json: 打包清单中记录包含 token.txt / adstar.txt / .env 等, 首次提交: 0cca0c0
- sync_console/tokens/adstar.txt, sync_console/tokens/jzt_token.txt: 运行时本地令牌文件 (未追踪或仅本地测试), 首次提交: 未追踪
- eishu_three_sync/taobao/adstar.txt: 本地令牌文件, 首次提交: 未追踪
- eishu_three_sync/jzt_sync/token.txt: 本地令牌文件, 首次提交: 未追踪
- eishu_three_sync/taobao/.env: 本地环境变量明文, 首次提交: 未追踪

---
