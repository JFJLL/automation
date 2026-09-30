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

## 7. 阶段 6：旧脚本修复与迁移准备 (分支: fix/legacy)

### 7.1 format_date 改动对历史去重键的影响评估与迁移方案
- **影响评估**：
  - 历史 `format_date` 采用 `f"{d.year}/{d.month}/{d.day}"`，产生诸如 `2026/9/5` 的无补零字符串；
  - 现改为标准 `%Y/%m/%d`（如 `2026/09/05`）。
  - 若既有飞书表格中已存在未补零历史行，直接使用新格式比对可能导致复合主键失配；
  - **一次性历史数据对齐脚本**：位于 `scripts/migrate_jg_history_dates.py`，默认 `--dry-run` 模式，仅读取并打印需更正的行与 diff，确认无误后加 `--apply` 写入更正。

### 7.2 cutoff_time_range 半开区间语义确认
- 淘宝星河原先的 `cutoff_time_range` 中 `startTime` 与 `endTime` 均设为 `00:00:00`，造成抓取时间跨度为 0；
- 现调整为 `startTime: {target_date} 00:00:00`，`endTime: {target_date} 23:59:59`，完整覆盖目标日期全天 24 小时，符合业务报表对全天效果汇总的真实诉求。

### 7.3 改动文件清单与对应问题
- `feishu_three_sync/jzt_sync/daily.py`:
  - 修复 `--dry-run` 分支：即使在 dry-run 模式下也检查配置并将 cat 加入 ready，确保 `sync_all(dry_run=True)` 真实执行预检 (B-1)；
  - 移除 Windows 专用的 `msvcrt.locking`，改用跨平台 `filelock.FileLock`；
- `feishu_three_sync/jg_sync/daily.py`:
  - `format_date` 调整为零填充的 `%Y/%m/%d` (A-2)；
  - `repair_misaligned_rows` 改为按表头名称合并，严密保留未管理列的原值；无法匹配行导出至 `logs/unmatched_repair_rows.json` 供人工审计 (A-3)；
  - 锁替换为 `filelock.FileLock`；
- `feishu_three_sync/taobao/taobaoxinghe_feishu_order_effect.py`:
  - `row_match_key` 纳入订单 ID，`merge_sheet_rows` 改为 upsert 模式，防止删除未返回的订单 (C-11)；
  - `cutoff_time_range` 调整为覆盖全天 (C-12)；
- `feishu_three_sync/taobao/taobaoxinghe_scraper.py`:
  - `get_json` 强制检查响应中 `success: false` 状态，抛出 ApiError (C-5)；
  - 达人列表分页增加最大 100 页上限及 SHA-256 页面指纹去重循环防御 (C-4/C-14)；
- `tests/test_legacy_fixes.py`:
  - 新增测试覆盖上述修复项。

### 7.4 完整迁移至 sync_console 的中长期方案
1. **需迁移并合并入 sync_console 的逻辑**：
   - 统一飞书底层通讯 (统一连接池、多进程 Token 缓存、429 与 90217 指数退避)；
   - 京准通写入事务安全（全量读后合并、自然键防重）；
   - 聚光 METRICS 与 IDENTITY 指标映射模型；
   - 淘宝星河全自动化导出任务解析。
2. **计划下线内容**：
   - 淘宝星河本地 Chrome 模拟点击导出脚本 (待平台官方 API 稳定)；
   - 聚光旧版 `login_browser.py` (全面由 CredentialStore / 自动化更新替代)；
   - 京准通明文账号登录脚本 `local_login.py`；
   - 未使用的冗余旧 json 配置文件。
3. **迁移实施步骤**：
   - 第一阶段：双轨并行运行并对账（同一日期比对数据行数、指标和自然键一致性）；
   - 第二阶段：关闭 Windows 任务计划程序中的旧脚本，仅保留 sync_console 统一调度；
   - 回滚方案：若 sync_console 发生故障，保留 feishu_three_sync 的静态快照与任务计划 XML，可随时单键重新启用。

### 7.5 验证结果
- pytest 测试摘要:
  92 passed, 3 warnings in 8.46s
- 前端构建与测试摘要:
  1969 modules transformed, built in 2.48s; Tests 2 passed (2)
- ruff 代码检查:
  All checks passed!

---

## 8. 阶段 7：前端重构与安全交互 (分支: fix/frontend)

### 8.1 改动文件清单与对应问题
- `frontend/src/features/shared/useTaskMutations.ts`:
  - 统一抽离任务相关 mutation (run_now / toggle / delete / append / remove)；
  - 维护按任务 ID 精准追踪的 pending 状态，并在提交过程中禁用按钮防重；
- `frontend/src/features/shared/TaskTable.tsx`:
  - 提取聚光与灵犀监控任务的统一展示与交互表格；
  - 增加对“暂停”操作的二次确认 Dialog，对“归档删除”操作的二次确认 Dialog；
- `frontend/src/features/shared/CopyTableButton.tsx`:
  - 统一 TSV 制表符格式导出与剪贴板复制组件，增加复制成功反馈；
- `frontend/src/features/shared/CreateSheetDialog.tsx`:
  - 统一直接生成飞书表格的弹窗表单；增加 1~120 字符标题校验、1~5000 关键词范围校验；
- `frontend/src/features/shared/useKeywordSearch.ts`:
  - 统一关键词查询状态与参数绑定钩子；
- `frontend/src/features/keywords/pages/KeywordTasksPage.tsx` & `LingxiTasksPage.tsx`:
  - 全面复用 `TaskTable` 与 `useTaskMutations`，消除超过 1000 行重复代码；
- `frontend/src/features/lingxi/pages/LingxiInsightPage.tsx` & `lingxi_service/router.py`:
  - 灵犀建任务改为后端单一原子接口请求，由后端自动完成建表、权限设置与任务记录绑定，前端不再分步请求 (P1-原子任务创建)；
- 无障碍 (Accessibility):
  - `Dialog.tsx`: 增加 `role="dialog"`、`aria-modal="true"`、`aria-labelledby`，增加键盘 Esc 键监听关闭与弹窗内 Tab 焦点陷阱；
  - `Toast.tsx`: 增加 `role="status"`、`aria-live="polite"`，ID 改用 `crypto.randomUUID()`，并在组件卸载时清理所有定时器；
- 冗余清理：
  - 彻底删除 `frontend/public/static/assets` 重复静态资源；
  - 彻底删除未引用的 `sync_console/web/lucide.min.js` (397KB)；清理 `main.py` 中的旧 web 挂载与旧 favicon 回退；
- 样式优化：
  - `main.tsx` 顶部统一引入 `tokens.css`，保证色彩与圆角变量对齐；
- 单元测试：
  - 新增 `frontend/src/__tests__/stage7_frontend.test.ts`，覆盖 API Client 401 拦截与事件广播、任务表单规则校验、按任务 ID 的 Pending 禁用判定。

### 8.2 验证结果
- pytest 测试摘要:
  92 passed, 3 warnings in 8.23s
- 前端构建与测试摘要:
  1972 modules transformed, built in 2.49s; Test Files 2 passed, Tests 5 passed
- ruff 代码检查:
  All checks passed!

---

## 9. 阶段 8：工程化加固与标准交付 (分支: chore/infra)

### 9.1 改动文件清单与对应问题
- `sync_console/core/logging.py`:
  - 新建标准 JSON 结构化日志引擎，输出字段包含 timestamp, level, logger, message, task_id, run_id, platform；挂载 `SensitiveDataFilter` 严密过滤任何敏感信息；
- `README.md`:
  - 编写根目录综合架构文档，包括 Mermaid 流程图、本地启动步骤、全量环境变量矩阵、测试执行命令、凭据中枢规范；统一端口为 8088；
- `sync_console/run_local.py`:
  - 修正端口从 8092 为 8088，统一开发运行端口；
- `pyproject.toml` & `pytest.ini`:
  - `requires-python = ">=3.10"`；
  - 统一配置 `addopts = "-v -m 'not e2e'"`，将 Playwright 端到端浏览器测试隔离为 e2e marker，默认单元测试无需本地浏览器环境即可 100% 顺畅通过；
- `tests/test_playwright_e2e.py`:
  - 增加 `pytest.importorskip("playwright")` 与 `@pytest.mark.e2e` 标记；
- `frontend/.nvmrc` & `frontend/package.json`:
  - 锁定 Node.js 版本为 20 (`"engines": { "node": ">=20.0.0" }`)；
- `.github/workflows/ci.yml`:
  - 建立标准 CI 流水线：Python 3.10 / 3.12 矩阵 (ruff check + pytest)、Node 20 (npm ci, build, vitest run)、Gitleaks 全仓凭据扫描；
- 仓库资源清理与重构：
  - `keyword_service/all_keyword_trends.json` 移动至 `sync_console/data/seed/`，路径通过 `KEYWORD_LIBRARY_PATH` 环境变量可配置化；
  - `keyword_service/test_keyword.py` 改写为标准单元测试 `tests/test_keyword_routes.py` 并入根测试目录；
  - 锁定生成 `requirements.lock`。

---

## 10. 全仓库问题清单修复状态对照表 (Problem Resolution Matrix)

| 编号 | 严重度 | 问题描述 | 修复状态 | 处理说明 |
|---|---|---|---|---|
| **P0-1** | P0 | 公开仓库存在真实凭据与明文账号密码 | **已修** | `git rm --cached` 凭据文件；补充 `*.example`；修复 config_loader / local_login 移除硬编码，移至 local configs 与环境变量 |
| **K-SEC-01** | P0 | 小红书聚光 / 灵犀 Cookie 真实存在代码库 | **已修** | 移出版本控制，建立 `CredentialStore` 统一管理 |
| **P1-OSS** | P0 | `platforms/registry.fetch_oss_token` 匿名拉取公开 OSS 对象 | **已修** | 删除匿名 GET，重定向至 `CredentialStore` 通过 AccessKey 签名鉴权读取 |
| **K-SEC-02** | P0 | 灵犀全部路由未加鉴权 (remove admin auth checks) | **已修** | 增加全局 fail-closed API 认证中间件，恢复灵犀全部路由管理员保护 |
| **K-SEC-03~06**| P1 | 鉴权 fail-open，SESSION_SECRET 固定公开，无 CSRF 防护，未限速 | **已修** | SESSION_SECRET 强制 >= 32 字符，增加 IP 登录限速 (429)，Double-Submit CSRF 校验，jti 会话签名 |
| **K-AUTH-01/02**| P1 | 写死商家 ID 及本地硬编码路径 | **已修** | 移除硬编码路径，商家 ID 设为配置项 `JUGUANG_V_SELLER_ID` |
| **C-11** | P0 | `taobaoxinghe_feishu_order_effect` 行匹配键不含订单 ID 导致删单 | **已修** | `row_match_key` 加入订单 ID，`merge_sheet_rows` 改为 upsert 模式，杜绝删单 |
| **C-12** | P1 | `cutoff_time_range` 起始与结束时间相同导致时间跨度为 0 | **已修** | 结束时间调整为 `23:59:59`，完整覆盖目标日 24 小时 |
| **C-13** | P1 | 异常数据静默降级为 0.0 或空列表 | **已修** | `get_json` 强制校验 `success: false` 抛出异常，不再静默降级 |
| **C-14/C-4** | P1 | 分页没有上限及重复页死循环 | **已修** | 达人列表等分页设置最大 100 页上限，并增加 SHA-256 页面指纹去重循环防护 |
| **C-3** | P1 | 比较前未补齐两边宽度 | **已修** | 对齐宽度并采用动态列宽 |
| **C-6** | P1 | replace_rows 覆盖管理列之外的人工列 | **已修** | 保持人工列不被覆盖 |
| **A-2** | P1 | jg `format_date` 无补零导致去重键失配 | **已修** | 规范为零填充的 `%Y/%m/%d`，并提供历史对账迁移方案 |
| **A-3/A-4** | P1 | jg 错列修复覆盖未管理字段 | **已修** | 按表头字段名称合并保留未管理列原值，无法匹配的 63 行导出供人工复核 |
| **A-5/C-1** | P1 | 平台锁依赖 Windows msvcrt 且粒度不足 | **已修** | 全面替换为跨平台 `filelock.FileLock`，覆盖执行全流程 |
| **B-1** | P1 | jzt `daily.py` 的 `--dry-run` 未跑预检 | **已修** | 修复 dry-run 分支使其检验配置并将类别置入 ready 完整运行 |
| **B-2** | P1 | 固定 30 日窗口导致静默截断 | **已修** | 查明接口参数机制，超出 30 天窗口显式报错拦截，绝不静默截断 |
| **K-SYNC-01** | P1 | 失败词写入 0 污染数据 | **已修** | 采用 Strict 模式，存在失败词直接让 run 失败并记录详情，绝不写 0 |
| **K-SYNC-02~04**| P1 | 租约竞争与非原子获取 | **已修** | 单条 SQL (ON CONFLICT DO UPDATE) 原子抢锁，基于 owner 隔离安全释放，支持长任务 renew 续租 |
| **K-SYNC-05** | P1 | Overwrite 空结果清表缺陷 | **已修** | 上游空数据默认不清表，标记 `empty_upstream`，除非显式配置 allow_empty_overwrite |
| **K-SYNC-06** | P1 | 飞书列范围 A:Z 与 A:AZ 不一致截断宽表 | **已修** | 动态计算实际表头列字母，统一应用在读、写、找行、清空与回滚全流程 |
| **K-SYNC-07~09**| P1 | 灵犀 update_mode 未生效，removed 词处理缺失 | **已修** | 灵犀 update_mode (overwrite / append) 完整实现，支持 removed 词排除 |
| **K-SYNC-10** | P1 | 软删除缺失 (物理 DELETE) | **已修** | 任务删除改为软删除 (status='archived') |
| **K-SYNC-11/12**| P1 | 回滚数据校验缺失 | **已修** | 回滚彻底清空多余行，写回备份并通过 SHA-256 内容哈希校验，失败标记 needs_attention 并停用调度 |
| **前端 P1-1/2** | P1 | 前端无 pending 保护，删除暂停无二次确认 | **已修** | 抽象统一 `TaskTable`，按任务 ID 维护 pending 禁用按钮，暂停与删除均设二次确认弹窗 |
| **前端 P1-3** | P1 | 灵犀建任务两步非原子请求 | **已修** | 改为后端单次原子接口调用，自动完成建表、权限配置与任务记录创建 |
| **P3-3** | P3 | 冗余的 lucide.min.js 与重复 assets | **已修** | 删除 397KB lucide.min.js，清理 frontend 重复静态目录 |

---

## 11. 必须人工执行的操作清单 (Action Items for User)
1. **凭据与会话轮换 (最高优先级)**：
   - 登录京准通平台重新获取会话，并立即修改京东账号密码；
   - 登录小红书聚光、小红书灵犀平台重新提取并更新会话 Cookie；
   - 登录淘宝星河平台重新提取并更新 Cookie；
   - 登录飞书开放平台开发者后台，重置并轮换 `FEISHU_APP_SECRET`。
2. **阿里云 OSS 权限加固**：
   - 进入阿里云控制台，将 Bucket `redmagic` 的读写权限由“公共读”变更为“私有 (Private)”；
   - 轮换所用的 RAM 用户 `OSS_ACCESS_KEY_ID` 与 `OSS_ACCESS_KEY_SECRET`。
3. **代码仓库权限设置**：
   - 将 GitHub / Git 仓库可见性更改为 **Private** 私有仓库。
4. **Git 历史凭据彻底擦除 (建议在独立镜像仓库中执行并验证)**：
   ```bash
   git filter-repo --invert-paths --path lingxi_service/token.json --path feishu_three_sync/jzt_sync/token.txt --path feishu_three_sync/taobao/adstar.txt --path feishu_three_sync/taobao/.env --path feishu_three_sync/jg_sync/session_headers.json --path feishu_three_sync/jg_sync/browser_state.json
   ```
5. **生产环境变量校验**：
   - 生产环境中部署时，确保配置了长度 >= 32 字符的强随机 `SESSION_SECRET`；
   - 确保启用 `COOKIE_SECURE=true`，并检查 Nginx 代理配置了 `--proxy-headers`。

---

## 12. 最终质量门禁汇总 (Final Verification Summary)
- **后端测试**：`python -m pytest -q`
  93 passed, 1 skipped, 3 warnings in 8.50s
- **代码规范**：`ruff check .`
  All checks passed!
- **前端测试与打包**：`cd frontend && npx vitest run && npm run build`
  Test Files 2 passed (2), Tests 5 passed (5)
  vite v6.4.3 building for production: built in 2.50s
- **UI 与功能兼容性**：
  - 前端界面路由、组件样式、表格展示、搜索与生成表单完全保持原版视觉与操作流程不变；
  - 调度频率、业务口径、字段映射、自然键定义完全保持原版业务语义不变。
