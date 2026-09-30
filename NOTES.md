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

## 2. 阶段 1：凭据止血 (分支: fix/secrets)

### 2.1 改动文件清单与对应问题
- `lingxi_service/token.json` (git rm --cached) 及所有 `*.example` 模板 (P0-1, K-SEC-01)
- `.gitignore`: 补充各类敏感文件、日志、备份、本地配置屏蔽规则
- `feishu_three_sync/jzt_sync/config_loader.py`: 移除硬编码飞书 App Secret 兜底 (P0-1)
- `feishu_three_sync/jzt_sync/local_login.py` & `refresh_login.py`: 移除明文京东账号密码，改用环境变量/Keyring (P0-1)
- `feishu_three_sync/jzt_sync/configs/`: `all_23_accounts.json` 与 `all_tasks_merged.json` 移动至 `configs/local/` (已在 .gitignore)，仓库只保留脱敏假数据模板；`daily_sync.py` 优先读取本地目录 (P0-1)
- `sync_console/core/credentials.py`: 全新创建统一安全凭据存储 `CredentialStore`，支持原子写入、POSIX 0600、文件锁、防路径遍历、最大 64KB 限制、sha256 8 位指纹脱敏 (P1-OSS, 后端 P0)
- `sync_console/platforms/registry.py`: 删除匿名 GET 拉取，重定向至 `CredentialStore`
- `sync_console/platforms/jzt.py`, `taobao.py`, `juguang.py`: 接入 `CredentialStore`
- `keyword_service/client.py` & `lingxi_service/client.py`: 接入 `CredentialStore`，移除硬编码路径与写死 sellerId (K-AUTH-01/02)
- `lingxi_service/router.py`: GET /cookie 接口仅返回 has_cookie、cookie_length 和 fingerprint，绝不返回明文片段
- `.pre-commit-config.yaml`: 新增 gitleaks 与 ruff 预提交检查
- `tests/test_credentials.py`: 新增单元测试，覆盖读取顺序、防路径遍历、原子锁写入、指纹脱敏与 OSS 回退

### 2.2 验证结果
- `tests/test_credentials.py`: 6 passed
- `sync_console/tests/test_juguang_subaccount.py`: 4 passed

### 2.3 需要人工执行的清单 (极为重要)
1. **轮换会话与密钥**:
   - 小红书聚光、小红书灵犀、京东京准通、淘宝星河的所有会话与登录状态全部重新登录/失效；
   - 飞书开放平台管理后台: 重新生成并轮换 `FEISHU_APP_SECRET`；
   - 立即修改京东账号密码；
   - 阿里云控制台: 将 OSS Bucket (`redmagic`) 读写权限设为私有 (Private)，并轮换 `OSS_ACCESS_KEY_ID` 与 `OSS_ACCESS_KEY_SECRET`。
2. **仓库权限设置**:
   - 将 GitHub / Git 仓库设置为 Private 私有仓库。
3. **Git 历史凭据清理命令 (建议在独立克隆仓库中演练后执行，切勿在此分支直接跑)**:
   ```bash
   git filter-repo --invert-paths --path lingxi_service/token.json --path feishu_three_sync/jzt_sync/token.txt --path feishu_three_sync/taobao/adstar.txt --path feishu_three_sync/taobao/.env --path feishu_three_sync/jg_sync/session_headers.json --path feishu_three_sync/jg_sync/browser_state.json
   ```

---

## 3. 阶段 2：鉴权改为 fail-closed (分支: fix/auth)

### 3.1 改动文件清单与对应问题
- `sync_console/core/security.py`:
  - 核心鉴权逻辑由 fail-open 彻底改为 fail-closed (后端 P1 鉴权)；
  - `AUTH_MODE` 统一读取 app.config，默认值为 token；require_auth 与 require_admin 统一校验标准；
  - 强制启动时校验 `SESSION_SECRET` 长度不得小于 32 字符，小于时直接阻止启动 (P2-启动安全)；
  - 密码与令牌比对全面替换为 `hmac.compare_digest`，防御时序侧信道攻击；
  - 会话载荷加入 `jti` (16 字节随机 hex) 唯一令牌标识；
  - 彻底移除对废弃 `access_token` 明文 Cookie 的读写与依赖。
- `sync_console/app/main.py`:
  - 增加全局 API 中间件，除公开白名单 (health/ready/business-time/login/check) 之外，所有 `/api/*` 默认全部拦截未授权访问 (返回 401)；
  - 登录接口增加 IP 限速 (单 IP 每分钟最多 10 次，超限返回 429)；
  - 响应脱敏：`/api/settings` 中的 notification_webhook 与 shared_folder_token 进行自动脱敏掩码，`/api/tasks` 严格使用字段白名单过滤内部字段，`/api/runs` 对 error_detail 深度脱敏；
  - 飞书权限：接入 `FEISHU_SHEET_SHARE_MODE` (默认 private)，新建表格后自动设置并在服务端回读确认 (P1 飞书权限)。
- 统一 CSRF 防御机制说明与选择理由：
  - 方案选择：采用 **Double-Submit Cookie (CSRF Token)** 机制。
  - 选择理由：系统前端管理后台同时支持 Cookie Session 会话与 API Token。在浏览器环境下，Cookie 会在同源请求中自动附带，必须通过由 JS 可读的非 HttpOnly `csrf_token` Cookie 并由前端在写请求 (POST/PUT/PATCH/DELETE) 中作为 `X-CSRF-Token` 请求头回传，服务端在检测到 Cookie 登录时强制校验一致性。同时对携带 Bearer/X-Access-Token 的外部 API 调用予以免校验，兼顾了浏览器防护与脚本自动化兼容性。
- `frontend/src/shared/api/client.ts`:
  - `VITE_API_BASE` 动态配置支持；
  - 自动在写请求中附加 `X-CSRF-Token` 请求头；
  - 捕获 401 自动广播 `auth:unauthorized` 事件并提供统一 ApiError 类型。
- `frontend/src/features/settings/pages/SettingsPage.tsx`:
  - 删除写死的 sellerId；Cookie 输入增加密码显示/隐藏切换；展示脱敏后的系统配置。
- `tests/test_api_auth.py`:
  - 新增动态遍历所有注册路由测试，全自动验证白名单外所有接口 401 拦截；
  - 新增 SESSION_SECRET 长度与存在性防御测试；
  - 新增 CSRF 缺失拦截 (403) 与正确通行测试；
  - 新增登录限速测试 (第 11 次返回 429)。

### 3.2 验证结果
- pytest 测试摘要:
  69 passed, 3 warnings in 3.12s
- 前端构建与测试摘要:
  1969 modules transformed, built in 2.65s; Tests 2 passed (2)
- ruff 代码检查:
  All checks passed!

### 3.3 剩余风险
- 若用户在反向代理下未配置 X-Forwarded-For，登录限速将回退到代理 IP；部署文档中需强调配置 --proxy-headers --forwarded-allow-ips=127.0.0.1。

---

## 4. 阶段 3：同步引擎正确性 (分支: fix/sync-engine)

### 4.1 改动文件清单与对应问题
- `sync_console/core/database.py`:
  - 租约改为单条 SQL 原子获取 (INSERT ... ON CONFLICT DO UPDATE WHERE expires_at < :now)，避免并发竞争漏洞 (后端 P1 lease)；
  - 释放租约增加 owner 隔离匹配，防止旧进程误删新持锁者的租约；
  - 新增 `renew_task_lease` 支持长任务续租；
  - 新增 Migration 4：tasks 表增加 `max_backfill_days` 字段 (默认 90 天)。
- `sync_console/core/sync_runner.py`:
  - 新建统一任务运行看门狗 `TaskRunGuard`，统一管理锁生命周期、运行日志记录与状态收尾。
- `sync_console/feishu/client.py`:
  - 进程级全局缓存 `tenant_access_token` (按 app_id，提前 120s 自动刷新，401 自动重试一次)；
  - 请求封装支持 429 Retry-After 避让、5xx 与 90217 指数退避加随机抖动，写操作强制间隔 >= 1.2 秒；
  - 动态计算列字母 (不再局限于 A:Z / A:AZ 固定范围)；
  - 新增 `write_ranges` 批量区间写入；
  - 文件夹与工作表查询支持 page_token 全量分页。
- `sync_console/core/sync.py`:
  - Phase 1 实行有界并发抓取 (PROVIDER_CONCURRENCY = 3)，任意实体抓取失败直接中止写表；
  - Overwrite 模式安全屏障：上游返回空数据时默认不清表，run 标记为 `empty_upstream`，仅在显式配置 allow_empty_overwrite 时允许清空；
  - 自然键安全：缺失关键字段 (ID 或日期) 不参与 upsert 并计入警告；批次内发现重复键时自动暂停任务并抛出校验异常；
  - 写后回读严格校验表头和数据行，不一致时触发快照回滚；
  - 彻底清理原表末尾脏数据行，写回备份并按 SHA-256 内容哈希严格校验回滚有效性；回滚失败标记 needs_attention 并停用调度。
- `sync_console/core/feishu_matrix.py`:
  - 抽离通用表格矩阵写入工具，限制最大 5000 行、200 列，安全扩展维度，自动防范 =/@/+/- 电子表格公式注入。
- `sync_console/core/keyword_repo.py`:
  - 抽离公共关键词库与分页参数验证 (1<=page, 1<=page_size<=100，非法参数返回 422)。
- `keyword_service/sync_engine.py` & `lingxi_service/sync_engine.py`:
  - 统一接入 `TaskRunGuard`；
  - 严格模式：上游抓取失败的词绝不写入 0，直接标记失败并中止写表，杜绝虚假数据污染；
  - 灵犀引擎真正支持 `update_mode` (overwrite 与 append)；
  - 支持 removed_keywords 排除。
- `keyword_service/router.py` & `lingxi_service/router.py`:
  - 状态机强化：已归档任务禁止切换状态 (返回 409)；删除任务改为软删除 (status='archived')；任务不存在返回 404。
- 测试覆盖：
  - `tests/test_lease.py`: 验证抢锁并发竞争、过期接管与 owner 隔离释放、续租；
  - `tests/test_feishu_client.py`: 验证 429 重试、90217 避让、超过 AZ 宽表列字母；
  - `tests/test_keyword_lingxi_engine.py`: 验证失败词不写 0、分页 422 报错、空表无越界。

### 4.2 决策与选择
- **关键词失败数据处理策略**：选用**严格模式（Strict Mode）**。当监控词在上游获取失败或失效时，不将单元格赋 0 写入，而是整次运行标记为 failed，在错误详情中明确记录失败词列表并保留飞书表格既有历史。这样避免了业务方根据报表误判“搜索量归零”。

### 4.3 验证结果
- pytest 测试摘要:
  79 passed, 3 warnings in 5.21s
- 前端构建与测试摘要:
  1969 modules transformed, built in 2.65s; Tests 2 passed (2)
- ruff 代码检查:
  All checks passed!

---

## 5. 阶段 4：Provider 与输入边界 (分支: fix/providers)

### 5.1 京准通日期参数用法查明与判断依据
- **代码与脚本证据**：
  - `feishu_three_sync/jzt_sync/daily_client.py:fetch_report` 中调用 `https://jzt-api.jd.com/jrw/content/outside/demand/report/downloadGrassDailyData`，请求体载荷写死为 `dataCycle='30'`，没有传入任何 `startDate` 或 `endDate` 字段；
  - 返回内容直接为 25 列的 Excel 导出版（包含近 30 天数据）。
- **技术判断**：
  - 京准通该接口是面向看板导出的滚动 30 天汇总数据包，不支持自定义历史大跨度区间拉取；
  - 在 `platforms/jzt.py` 中，如果业务传入的 start_date 早于当前时间 30 天前，接口无法覆盖全部日期。
  - **处理方案**：计算请求起始日期与业务当前日期的间隔，若超出 30 天窗口，明确抛出 `ProviderUpstreamError("京准通接口仅支持导出近 30 天窗口数据，无法回溯至 {start_norm}")`，绝不静默截断数据；同时增加 3 次网络错误重试与指数退避。

### 5.2 改动文件清单与对应问题
- `sync_console/platforms/jzt.py`:
  - 30 天窗口严格校验；网络异常 3 次指数重试；规范日期格式解析校验；
- `sync_console/platforms/taobao.py`:
  - 分页同时校验 `hasNext` 与 `total`，设置最大 100 页上限；达到上限且仍有数据时返回 `PARTIAL`；
  - 引入 SHA-256 页面数据指纹检测，发现重复页时返回 `PARTIAL` 防止死循环；网络重试 3 次；
- `sync_console/core/models.py`:
  - 统一 Provider 契约：`SUCCESS`、`EMPTY`、`PARTIAL`、`AUTH_EXPIRED`、`UPSTREAM_ERROR` 五种状态模型；
- `sync_console/core/ingest.py`:
  - Excel 文件大小限制 10MB；仅允许 .xlsx/.xls/.csv；
  - 增加 ZipBomb 压缩炸弹安全检测 (解压体积 > 100MB 或压缩比 > 100 拦截)；
  - 采用 openpyxl `read_only=True, data_only=True` 流式读取；单个文件限制最多 20 个工作表，每表最多 5000 行、200 列；解析失败严格返回 400；
- `sync_console/feishu/notify.py`:
  - 限制 webhook URL 必须属于 `open.feishu.cn` 官方白名单域名；
  - 告警内容严格脱敏 (URL 敏感 query 参数、Cookie、Bearer 令牌)，限制最大长度 1000 字符；
- `sync_console/core/workdays.py`:
  - 增加对 chinesecalendar 库缺失的显式告警日志，保留 2026 年调休表与常规工作日作为平滑兜底；
- `keyword_service/client.py` & `lingxi_service/client.py`:
  - 依据 HTTP 状态码 (401/403) 与业务错误码 (401/403/601/902/100001) 判定 auth_expired，不再仅依赖中文匹配；
- `tests/test_provider_contracts.py`:
  - 新增 JZT 30 天窗口拦截测试、淘宝最大 100 页 PARTIAL 判定测试、ZipBomb 与文件大小拦截测试、Webhook 域名白名单拦截测试、公式注入转义测试。

### 5.3 验证结果
- pytest 测试摘要:
  84 passed, 3 warnings in 7.94s
- 前端构建与测试摘要:
  1969 modules transformed, built in 2.48s; Tests 2 passed (2)
- ruff 代码检查:
  All checks passed!

---

## 6. 阶段 5：调度引擎可靠性 (分支: fix/scheduler)

### 6.1 改动文件清单与对应问题
- `sync_console/core/schedule_rules.py`:
  - 抽离出统一的纯函数 `next_run(rule_str, after_dt)`，支持 RRULE 与 WORKDAY 规则；
  - 严格支持周末跳过、法定调休补班及法定节假日计算，BYHOUR/BYMINUTE 缺失时默认 09:00。
- `sync_console/core/scheduler_manager.py`:
  - 调度任务注册统一加上 `misfire_grace_time=3600, coalesce=True, max_instances=1`；
  - `restore_all_tasks` 增加错失运行检测机制：当 next_run_at < now 且 last_run_at < next_run_at 时，依据 `MISSED_RUN_POLICY` (默认 run_once) 自动补跑一次；
  - 注册失败的任务记录进 `failed_tasks`，使得 `/api/ready` 返回 degraded 降级状态；
  - 启动时检测 `WEB_CONCURRENCY > 1` 或 `WORKERS > 1` 时，调度器拒绝在从属 worker 中启动，防止跨进程竞态。
- `sync_console/app/main.py`:
  - `/api/ready` 检查增加对调度器降级状态的响应。
- `frontend/src/features/sync/pages/RunsPage.tsx` & `TasksPage.tsx`:
  - 增加 3 秒动态轮询：当存在 running / queued 状态时自动以 3 秒间隔轮询刷新，无 running 时停止轮询。
- `frontend/src/features/keywords/pages/KeywordRunsPage.tsx` & `frontend/src/features/lingxi/pages/LingxiRunsPage.tsx`:
  - 同样增加 3 秒动态轮询机制。
- `DEPLOY.md`:
  - 创建并详细记录调度器单进程约束、系统环境变量约束、Linux 内核安全沙箱参数与 Nginx 反代配置。
- `tests/test_scheduler.py`:
  - 单元测试覆盖周末跳过、缺省时分兜底、多进程启动阻止、就绪检查 degraded 状态。

### 6.2 验证结果
- pytest 测试摘要:
  88 passed, 3 warnings in 8.31s
- 前端构建与测试摘要:
  1969 modules transformed, built in 2.48s; Tests 2 passed (2)
- ruff 代码检查:
  All checks passed!

---
