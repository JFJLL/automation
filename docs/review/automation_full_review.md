# JFJLL/automation 全仓库代码审查报告（master，2026-09-30）

## 审查范围说明
- 已逐文件完整读完：sync_console 后端全部 31 个文件、keyword_service / lingxi_service 全部源码、tests/ 和 sync_console/tests/ 下全部 19 个测试、frontend 全部源码和配置、feishu_three_sync 里除下面 3 个以外的所有脚本/配置/PowerShell。
- 未能完整读完（读取工具在文件中段就截断了，已经尝试过 raw / Contents API / blob API / jsDelivr / githack 各种方式）：`feishu_three_sync/taobao/refresh_adstar_cookie.py`、`taobaoxinghe_feishu_order_effect.py`、`taobaoxinghe_scraper.py`。这 3 个文件前半部分的发现已经收进附录 D，后半部分已写进本地 Agent 提示词，要求本地逐函数补审。
- 没读的：package-lock.json、lucide.min.js（397KB 第三方库）、all_keyword_trends.json（数据文件，只看了结构）。两个大 CSS 只做了浏览。
- 报告里不包含任何凭据原值。

## 全局结论（按优先级）

**P0（今天就要处理）**
1. 公开仓库里有真实凭据：`lingxi_service/token.json`（小红书多子站 Cookie）；manifest 显示 `.env`、`token.txt`、`adstar.txt`、`session_headers.json`、`browser_state.json` 都被打过包；`jzt_sync/config_loader.py` 里有飞书 App Secret 的硬编码兜底；`jzt_sync/local_login.py` 里有明文京东账号密码；`all_tasks_merged.json` 里有飞书表 token。
2. `platforms/registry.fetch_oss_token` 用匿名 GET 从公共读的 OSS 拉 Cookie，而 bucket 名和对象路径都写死在公开代码里。
3. 灵犀 `/api/lingxi/*` 全部路由都没有鉴权（最近一次提交 "remove admin auth checks" 直接把鉴权删了）：搜索、Cookie 读写、OSS 同步、建表、任务 CRUD、run_now 都能匿名调用，GET cookie 还会返回首尾片段。

**P1（这周）**
4. 鉴权整体是 fail-open 的：`/api/tasks`、`/api/runs`、`/api/keyword/tasks|runs`、子账号接口都没加鉴权；`require_auth` 默认 internal 等于直接放行；SESSION_SECRET 有公开的固定兜底值；兼容 cookie 里存的是明文口令；登录没有限速，也没有 CSRF 防护；反向代理下 Secure 属性判断会出错。
5. 新建的飞书表一律被设成 tenant_editable。
6. 同步引擎：lease 固定 900s 且不续租，释放时不校验 owner（可能误删后面任务的锁），异常路径还会泄漏；overwrite 模式遇到上游返回空会直接清表；写后校验只检查"至少一行"；回滚清不掉追加的行；A:Z 和 A:AZ 两处列范围不一致，宽表会错位；append 模式逐行写；自然键缺字段时会把多行折叠成一行。
7. 平台 provider：京准通固定 dataCycle=30，没有传日期参数，超过 30 天的窗口会被静默截断；淘宝的备用分支缺少 `import os`，一走就 NameError，分页最多 100 页而且截断时不报错；各平台都把空页、不完整响应当成成功。
8. 灵犀：失败的关键词按 0 写进飞书，run 却标成 success；update_mode 被忽略，一律按 append 处理；page_size=0 会除零；删除操作是物理删除。
9. 调度：用的是一次性 date trigger，停机期间错过的任务不会补跑；BackgroundScheduler 在多 worker 下会重复执行。
10. 旧脚本：淘宝旧导出的 `merge_sheet_rows` 匹配键里没有订单 ID，接口只返回部分订单时会静默删掉其他订单；`cutoff_time_range` 的 start 和 end 相等；聚光错列修复会把跳转链接、单元、计划等字段清空；jg 和 jzt 都依赖 msvcrt，只能在 Windows 上跑；jzt 的 `--dry-run` 永远跑 0 个任务；计划任务依赖交互式桌面登录，失败也没有告警。
11. 上传 Excel 没有任何大小或资源限制；写进表格的值没有防公式注入。
12. 前端：没有统一的 401 处理；Settings 页面直接展示 folder token 和 webhook；灵犀是先建表再建任务，失败会留下孤儿表；操作按钮没有防重复提交；表单基本没有校验。

**P2/P3**：时区混用、Feishu 分页只拉一页、token 缓存和 429 重试缺失、状态机允许 archived→active、依赖版本没锁、sys.path hack、workdays 兜底只覆盖 2026 年、KeywordTasksPage 和 LingxiTasksPage 逐段复制、两个大 CSS 互相覆盖、lucide.min.js 冗余、Playwright 测试依赖本机 Edge 和外部进程、测试可能污染真实数据库、断言偏弱。

详细证据（文件、函数、代码片段、修复方案）见下面 4 个附录。

---

# 附录 A：sync_console 后端
# JFJLL/automation `master` 分支 `sync_console` 后端代码审查

审查对象是公开仓库 `JFJLL/automation` 的 `master` 分支；原始源码链接均指向对应文件。除特别说明外，以下结论是静态审查结论，未向真实飞书、OSS 或广告平台写数据。

## 总结

当前实现不宜直接暴露到生产网络。最紧急的风险是：仓库中提交了会话凭据；任务/运行列表匿名可读；鉴权存在公开可猜的 session secret 兜底和 `AUTH_MODE` 不一致；新表被设成租户范围可编辑；同步 lease 会过期且释放不校验 owner；飞书写入回读/回滚校验不足；Excel、OSS 输入无资源边界；调度停机期间会漏跑；京准通日期参数未传递、淘宝回退分支有 `NameError` 且分页可能静默截断。

严重度：P0=立即止血；P1=高概率造成越权、泄露、丢数或漏跑；P2=重要正确性/可用性/防御纵深；P3=维护性或低风险问题。

## 发现

### P0. 仓库中提交真实会话凭据

* **位置**：`lingxi_service/token.json`（对象级配置）；关联 `.gitignore`。
* **证据**：完整文件是包含 `cookie` 及多个会话/访问令牌类字段的 JSON。报告不重复任何原值。[token.json](https://raw.githubusercontent.com/JFJLL/automation/master/lingxi_service/token.json)；[.gitignore](https://raw.githubusercontent.com/JFJLL/automation/master/.gitignore) 只忽略 `keyword_service/token.json`，没有忽略该路径。
* **影响**：公开仓库读者可尝试复用第三方会话，造成广告账户数据访问或代操作；Git 历史也可能保留旧值。
* **修复**：立即在第三方平台撤销/轮换全部已提交凭据；从 Git 历史清除；使用 secret manager 或受限文件注入；补全忽略规则并启用 secret scanning/push protection。原值不得写入报告或日志。

### P1. 敏感读接口无鉴权

* **位置**：`app/main.py::list_tasks`（约 315 行）、`list_runs`（约 350 行），以及 `get_platforms`、`get_juguang_subaccounts`、`readiness_check` 等 GET。
* **证据**：
  ```python
  @app.get("/api/tasks")
  def list_tasks():
  @app.get("/api/runs")
  def list_runs(...):
  ```
  两路由没有 `Depends(require_auth/require_admin)`；`list_tasks` 直接 `SELECT * FROM tasks`，返回 `folder_token`、`spreadsheet_token`、URL、RRULE；runs 返回 `error_detail`。[main.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/app/main.py)
* **影响**：匿名枚举任务、飞书对象标识、平台/子账号及错误信息。
* **修复**：任务/运行/子账号等默认鉴权；健康检查单独最小化；使用响应 DTO 白名单，禁止 `SELECT *` 直接序列化；错误详情仅管理员可读并脱敏。

### P1. session secret 有公开硬编码兜底，认证模式默认值不一致

* **位置**：`core/security.py` 模块初始化、`require_admin`、`require_auth`；`app/config.py`。
* **证据**：
  ```python
  SESSION_SECRET = os.getenv("SESSION_SECRET", ACCESS_TOKEN or "<公开固定字符串>").encode("utf-8")
  ```
  ```python
  # require_admin 默认 token；require_auth 默认 internal
  auth_mode = os.getenv("AUTH_MODE", "token").strip().lower()
  auth_mode = os.getenv("AUTH_MODE", "internal").strip().lower()
  ```
  且 `require_admin` 在 `internal` 时直接放行。[security.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/security.py)；[config.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/app/config.py)。
* **影响**：未配置 secret 时可伪造管理员签名；`AUTH_MODE=internal` 会使主文件所有 admin 路由直接开放；不同 endpoint 行为不一致。
* **修复**：生产启动强制随机高熵 `SESSION_SECRET`，缺失/弱值拒绝启动；统一 fail-closed 的认证模式；内部模式仅允许受控网络/代理；集中解析配置并拒绝模板值。

### P1. Cookie 会话缺 CSRF 防护，反代下 `Secure` 可能错误

* **位置**：`app/main.py::login`；`core/security.py`；systemd 配置。
* **证据**：
  ```python
  is_secure = request.url.scheme == "https"
  response.set_cookie(..., httponly=True, samesite="lax", secure=is_secure)
  ```
  写操作依赖 cookie，但没有 CSRF token。systemd 的 Uvicorn 命令没有 `--proxy-headers`，尽管部署文档的 Nginx 会转发 `X-Forwarded-Proto`。[main.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/app/main.py)；[sync_console.service](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/sync_console.service)。
* **影响**：Lax 不是完整 CSRF 防护；TLS 在代理终止时应用可能认为 HTTP，session cookie 不带 Secure。
* **修复**：写接口加 CSRF token 或完全改为 Authorization header；生产强制 Secure；明确可信代理和 `--proxy-headers`；8088 只允许本机。

### P1. 新表默认租户范围可编辑

* **位置**：`app/main.py::create_task`；`feishu/client.py::set_sheet_public_editable`。
* **证据**：
  ```python
  feishu.set_sheet_public_editable(ss_token)
  ```
  该函数发送 `link_share_entity: "tenant_editable"`、`share_entity: "same_tenant"`。[main.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/app/main.py)；[client.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/feishu/client.py)。
* **影响**：同租户用户可改表头/历史数据/自然键，破坏同步结果和回滚基线。
* **修复**：默认私有；仅授权指定用户/群组，最低权限读/写；人工输入和同步输出分表；创建后回读权限确认。

### P1. lease 可过期并误删后继 lease

* **位置**：`core/database.py::acquire_task_lease/release_task_lease`；`core/sync.py::execute_task_sync`。
* **证据**：
  ```python
  acquire_task_lease(..., lease_seconds=900)
  ```
  没有续租；释放为 `DELETE FROM task_leases WHERE task_key = ?`，不校验 owner；`execute_task_sync` 没有覆盖全函数的 finally。[database.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/database.py)；[sync.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/sync.py)。
* **影响**：长任务超过 900 秒后可并发；旧执行者结束时能删除新执行者 lease，第三个执行者再次进入；异常早于阶段 try 或 DB 失败也可能泄漏 lease。
* **修复**：随机 owner/fencing token，释放加 `WHERE task_key AND owner`；定期续租并在失锁时停止写入；原子条件 UPSERT；acquire 后用覆盖全路径的 finally。

### P1. 飞书写入/回滚不是原子事务，校验只看行数/非空

* **位置**：`core/sync.py::execute_task_sync`；`feishu/client.py::restore_sheet_values/find_last_row_index`。
* **证据**：写后只检查 `len(verify_rows) < 1`；回滚只检查 `len(verify_data) != backup_rows`；`find_last_row_index` 只读 `A:Z`，同步/回滚最多读 `A:AZ`。[sync.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/sync.py)；[client.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/feishu/client.py)。
* **影响**：短写、错误表头、错误内容会被判成功；AA 之后有数据的行可能找不到，追加覆盖错误位置，回滚清不掉脏行；回滚失败后仅记录状态。
* **修复**：批量/原子写；验证表头、列数、行数、自然键集合和关键值 hash；统一动态列范围；完整快照回滚并验证内容；回滚失败暂停任务进入人工修复状态。

### P1. overwrite 的空结果会清空旧表

* **位置**：`core/sync.py::execute_task_sync` overwrite 分支。
* **证据**：
  ```python
  if not new_rows and not existing_values:
      pass
  else:
      feishu.clear_rows_below(...)
      if new_rows: feishu.write_rows(...)
  ```
  provider 的 EMPTY 没有被阻断。[sync.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/sync.py)
* **影响**：临时空响应、日期无数据或误判认证成功均会清掉历史。
* **修复**：空结果默认 fail-closed，保留旧表并标记 empty_upstream；只有明确确认才允许清空。

### P1. OSS token 匿名 GET、无大小约束，子账号键/本地路径未约束

* **位置**：`platforms/registry.py::fetch_oss_token`；`platforms/juguang.py::get_juguang_subaccount_headers`。
* **证据**：
  ```python
  url = f"{base_url.rstrip('/')}/{object_key.lstrip('/')}"
  r = requests.get(url, timeout=15)
  return r.text.strip()
  ```
  子账号 ID 直接拼 URL 对象键及 `BASE_DIR / "tokens" / f"{sub_account_id}.txt"`。[registry.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/platforms/registry.py)；[juguang.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/platforms/juguang.py)。
* **影响**：公共 OSS 可直接公开 Cookie；重定向/大响应未限制；`../`、路径分隔符可读非预期对象或本地文件，再作为 Cookie 发送上游。
* **修复**：bucket 私有、最小权限 SDK/短期签名 URL；endpoint allowlist、禁止非预期重定向、大小/type/schema 校验；ID 白名单及长度验证；`resolve()` 后确认位于 tokens 根目录。

### P1. Excel 上传无资源边界

* **位置**：`app/main.py::upload_excel`；`core/ingest.py::parse_excel_sheets`。
* **证据**：
  ```python
  content = await file.read()
  rows_iter = list(ws.iter_rows(values_only=True))
  ```
  没有大小、扩展名/MIME、ZIP 压缩比、sheet/行/列/单元格限制。[main.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/app/main.py)；[ingest.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/ingest.py)
* **影响**：大文件/压缩炸弹/大量空行耗尽内存和 CPU，单 worker 易被拖垮；解析异常变成 500。
* **修复**：代理和应用双重大小上限；只收必要格式，校验 ZIP 结构/压缩比；read-only 流式解析并限制采样；异常返回 400，限制上传速率和并发。

### P1. 京准通没有把日期范围传给上游

* **位置**：`platforms/jzt.py::fetch_jzt_data`。
* **证据**：函数接收 `start_date/end_date`，但 payload 固定 `dataCycle="30"`、`pageIndex="1"`，未出现 start/end 字段。[jzt.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/platforms/jzt.py)
* **影响**：超过 30 天的 overwrite/校准窗口被截断，截断结果仍当成功。
* **修复**：核实并传递 API 日期参数；若上游仅支持 30 天则分段请求、合并去重，或拒绝超窗；回传实际覆盖日期并校验。

### P1. 淘宝备用 Cookie 分支有 NameError，分页上限静默截断

* **位置**：`platforms/taobao.py::get_taobao_cookies/fetch_taobao_data`。
* **证据**：文件没有 `import os`，却执行 `os.getenv(...)`；分页是 `for page in range(1, 101)`，达到上限后无 partial 检查。[taobao.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/platforms/taobao.py)
* **影响**：OSS 失败时本地回退抛 NameError；大结果集可能只写前 10000 行，`expected_pages` 还等于已抓页数，伪装完整。
* **修复**：补导入并测试回退；以 total/hasNext 检查完整性，达到上限返回 partial/失败；加 429/5xx 退避重试和 schema 校验。

### P1. provider 空页/不完整响应被当成功

* **位置**：`juguang.py::fetch_juguang_data`、`taobao.py::fetch_taobao_data`、`jzt.py::fetch_jzt_data`。
* **证据**：聚光遇到 `not batch` 直接 break；淘宝以 `len(items) < 100 or not model.get("hasNext")` 结束；各实现都没有统一核对 total、实际日期覆盖和 schema。[juguang.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/platforms/juguang.py)；[taobao.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/platforms/taobao.py)；[jzt.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/platforms/jzt.py)
* **影响**：中途空页、字段变更、错误 JSON 可能产生 SUCCESS/EMPTY，进而清表或写入不完整数据。
* **修复**：统一 provider 契约，强制响应 schema、分页终止、实际日期/行数核验；中途空页或元数据缺失返回 PARTIAL/UPSTREAM_ERROR；失败结果禁止进入 overwrite。

### P1. date trigger 停机期间漏跑，无 misfire 补跑

* **位置**：`core/scheduler_manager.py::schedule_*_task`、`restore_all_tasks`、`_run_*_task_job`。
* **证据**：
  ```python
  self.scheduler.add_job(..., trigger="date", run_date=next_dt, ...)
  ```
  重启时重新以当前时间求下一次，没有 misfire_grace、持久化 job store 或补跑策略。[scheduler_manager.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/scheduler_manager.py)
* **影响**：停机窗口直接跳过数据窗口；DB 已写 next_run_at 而注册 job 失败时状态也可能失真。
* **修复**：启动扫描 next/last 状态并补跑；配置 misfire/coalesce/max_instances；使用持久化调度状态，并记录注册失败。

### P1. Feishu 分页和列范围不完整

* **位置**：`feishu/client.py::get_or_create_shared_folder/get_sheets/read_values/find_last_row_index`。
* **证据**：目录调用 `page_size=50` 只读一页；`read_values` A:AZ，而 last-row 只 A:Z；`write_rows` 却能动态写超过 AZ。[client.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/feishu/client.py)
* **影响**：找不到第一页后的目录会重复创建；宽表 AA+ 数据读取、追加、回滚不一致。
* **修复**：按 page_token/has_more 翻页；按 header 动态生成范围并统一最大列策略；超出支持宽度在建任务前拒绝。

### P2. 登录可暴力猜测，且把原始管理员口令写入 Cookie

* **位置**：`app/main.py::login`。
* **证据**：无限速的 `pwd != ACCESS_TOKEN` 比较，成功后 `set_cookie(key="access_token", value=ACCESS_TOKEN, ...)`。[main.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/app/main.py)
* **影响**：在线猜测静态口令；兼容 cookie 扩大口令暴露面。
* **修复**：移除原始口令 cookie，只使用随机 session；IP/账户限速、审计、恒时比较，最好接 SSO/MFA。

### P2. 部署脚本端口不一致且缺少 systemd 硬化

* **位置**：`run_local.ps1`、`run_local.py`、`start.sh`、`sync_console.service`、`DEPLOY.md`。
* **证据**：PS 用 8088，Python 本地脚本用 8092，生产用 8088；systemd 没有 `NoNewPrivileges/PrivateTmp/ProtectSystem/ReadWritePaths`。[run_local.ps1](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/run_local.ps1)；[run_local.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/run_local.py)；[start.sh](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/start.sh)；[sync_console.service](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/sync_console.service)；[DEPLOY.md](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/DEPLOY.md)
* **影响**：本地验证与生产不一致；缺 data/backups 时 chmod 可能失败；应用账号拥有项目树较宽写权限。
* **修复**：统一端口配置；脚本显式创建目录；systemd 最小写目录与硬化选项；反代只接本机上游。

### P2. 通知 webhook 外发内部错误，缺脱敏和白名单

* **位置**：`feishu/notify.py::send_webhook_message/notify_failure`。
* **证据**：`requests.post(webhook_url, json=..., timeout=10)`，消息直接拼任务名、平台和异常字符串。[notify.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/feishu/notify.py)
* **影响**：配置错误时向第三方外发内部标识/上游错误；异常可能含 URL 或响应片段。
* **修复**：限制 webhook 域名和配置权限；过滤 Cookie/Authorization/token/query，发送错误码而非原文并限长；完整错误放受限日志。

### P2. 业务时区与系统日期混用、无效时区静默回退

* **位置**：`business_time.py::get_business_tz/latest_*`、`sync.py::execute_task_sync`、`scheduler_manager.py`。
* **证据**：同步回退使用 `date.today()`，截止日使用业务时区；business_time 对无效时区回退上海，而 scheduler 的 `gettz(TIMEZONE)` 可能不可用。[business_time.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/business_time.py)；[sync.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/sync.py)；[scheduler_manager.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/scheduler_manager.py)
* **影响**：跨午夜时漏取/多取；模块对错误配置行为不同。
* **修复**：统一经校验的 ZoneInfo；无效配置启动即失败；明确 aware/naive 转换。

### P2. 自然键缺字段会折叠多行

* **位置**：`core/sync.py::get_item_natural_key` 及 append 分支。
* **证据**：`primary_entity_id = entity_ids[0] if entity_ids else ""`；缺任务/内容/创意 ID 或日期时多个 item 会得到相同复合键，已有重复键由 `existing_key_map[key] = idx` 覆盖。[sync.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/sync.py)
* **影响**：最后一条覆盖前条，历史重复行仍存在。
* **修复**：缺关键字段拒绝/隔离，不用首实体代替；验证 provider 键唯一性；发现旧重复键即暂停任务并显式迁移。

### P2. 状态机和外部副作用不安全

* **位置**：`app/main.py::toggle_task_status/archive_task/create_task`。
* **证据**：`new_status = "paused" if r["status"] == "active" else "active"` 会把 archived 变 active；archive 不检查不存在 ID；create_task 先建/写飞书表、设权限，后 DB INSERT，失败无补偿。[main.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/app/main.py)
* **影响**：归档任务可重新调度；不存在任务也返回成功；DB 失败留下孤儿表和开放权限。
* **修复**：只允许 active↔paused，归档需显式恢复流程；不存在返回 404；使用 provisioning 状态、幂等 key、资源补偿删除/撤销权限。

### P2. Feishu token 缓存/重试与单行写入性能不足

* **位置**：`feishu/client.py::get_token/request/write_rows`。
* **证据**：token/expires_at 属于每个 client；主路由频繁 new client。重试只覆盖部分 5xx 和业务码，未处理 HTTP 429/Retry-After；append/upsert 对每行调用 `write_rows`。[client.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/feishu/client.py)
* **影响**：重复 token 请求、限流时失败；大表同步非常慢，窗口内 lease 更易过期。
* **修复**：进程级按 app 共享缓存，401 只刷新一次；统一 429/5xx/网络退避；批量更新并设置总时限。

### P2. 输入 schema、公式注入和 provider 异常边界不足

* **位置**：`main.py::PreviewRequest/SheetConfig/CreateTaskRequest/fetch_preview`、`ingest.py`、`sync.py::format_cell_value`、`juguang.py`。
* **证据**：preview/upload 的 platform/dimension/list 没有严格 Enum、长度/数量约束；`normalize_date_str` 仅按 8 位数字拼接不验证日期；映射将原始字符串直接写表；聚光对 `json.loads(dataValueJson)`、`int(totalPage)` 未统一包装。[main.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/app/main.py)；[ingest.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/ingest.py)；[sync.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/sync.py)；[juguang.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/platforms/juguang.py)
* **影响**：绕过 SPA 可提交大 payload/未知平台；坏日期参与字符串比较；以 `=`, `+`, `-`, `@` 开头的值可能成为电子表格公式；上游字段变更导致 500。
* **修复**：服务端 Enum、最大长度/数量/列宽/sheet 数；真实日期解析；不可信文本公式转义；provider 响应 schema 和统一 ProviderUpstreamError。

### P3. 连接、迁移、依赖与导入维护问题

* **位置**：`app/db.py::init_db`、`core/database.py`、`scheduler_manager.py`、依赖文件、包初始化。
* **证据/影响**：`init_db` 打开连接后没有 `with/close`；调度恢复异常仅 `print` 后继续，任务可长期不运行；requirements/pyproject 都是 `>=` 且 pandas/dateutil 最低版本漂移；`sync_console/__init__.py` 和 main 全局改 `sys.path`，另有重复/未使用 import。[db.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/app/db.py)；[database.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/database.py)；[pyproject.toml](https://raw.githubusercontent.com/JFJLL/automation/master/pyproject.toml)；[requirements.txt](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/requirements.txt)。
* **修复**：所有连接 finally 关闭；恢复失败纳入 ready/degraded；锁定依赖和 hash；统一包导入，移除 sys.path 修改及死代码。

### P3. 工作日 fallback 只覆盖 2026

* **位置**：`core/workdays.py::is_china_workday`。
* **证据**：calendar 不可用时只有 `FALLBACK_2026_WORKDAYS/HOLIDAYS`，其他年份退化为周一至周五。[workdays.py](https://raw.githubusercontent.com/JFJLL/automation/master/sync_console/core/workdays.py)
* **影响**：未来节假日/调休错排。
* **修复**：版本化逐年节假日数据；缺依赖时启动失败或明确告警；为春节、国庆、周末补班写年度测试。

## 已知线索核实情况

1. `lingxi_service/token.json` 确实是含会话凭据字段的完整 JSON；原值未写入本文。
2. `registry.fetch_oss_token` 确实匿名 `requests.get` 公共 URL 并返回正文；其对象键被各 provider 用来取 Cookie/会话。
3. `/api/tasks`、`/api/runs` 确实无依赖鉴权，且返回字段过宽。
4. `SESSION_SECRET` 确实以 ACCESS_TOKEN 或公开固定字符串兜底；`require_admin` 与 `require_auth` 默认 AUTH_MODE 不同。
5. `create_task` 确实调用 `set_sheet_public_editable`，底层是 `tenant_editable`/`same_tenant`。
6. sync lease 确实固定 900 秒、无续租，释放不检查 owner；append 逐行写；回滚校验只看行数且 A:Z/A:AZ 范围不一致；写后校验只要求至少一行。
7. scheduler 确实使用一次性 `date` trigger，没有 misfire 补跑配置。

## 已读文件清单

以下每项均已完整读取；`app/__init__.py` 原始 raw 抓取失败，改用 GitHub Contents API 核实为 `size: 0`、空内容，因此标为完整读完。

| 文件 | 完整读完 |
|---|---|
| `sync_console/.env.example` | 是 |
| `sync_console/DEPLOY.md` | 是 |
| `sync_console/__init__.py` | 是 |
| `sync_console/requirements.txt` | 是 |
| `sync_console/run_local.ps1` | 是 |
| `sync_console/run_local.py` | 是 |
| `sync_console/start.sh` | 是 |
| `sync_console/sync_console.service` | 是 |
| `sync_console/app/__init__.py` | 是（0 字节） |
| `sync_console/app/config.py` | 是 |
| `sync_console/app/db.py` | 是 |
| `sync_console/app/main.py` | 是 |
| `sync_console/core/business_time.py` | 是 |
| `sync_console/core/database.py` | 是 |
| `sync_console/core/errors.py` | 是 |
| `sync_console/core/ingest.py` | 是 |
| `sync_console/core/models.py` | 是 |
| `sync_console/core/scheduler.py` | 是 |
| `sync_console/core/scheduler_manager.py` | 是 |
| `sync_console/core/security.py` | 是 |
| `sync_console/core/sync.py` | 是 |
| `sync_console/core/workdays.py` | 是 |
| `sync_console/feishu/client.py` | 是 |
| `sync_console/feishu/notify.py` | 是 |
| `sync_console/platforms/juguang.py` | 是 |
| `sync_console/platforms/jzt.py` | 是 |
| `sync_console/platforms/registry.py` | 是 |
| `sync_console/platforms/taobao.py` | 是 |
| `pyproject.toml` | 是 |
| `pytest.ini` | 是 |
| `.gitignore` | 是 |

另行读取、仅用于核实线索的 `lingxi_service/token.json` 也已完整读取；凭据原值未进入报告。

## 建议修复顺序

1. 立即撤销/轮换仓库历史中的第三方会话凭据并清理 Git 历史。
2. 给所有任务/运行/子账号及所有写接口统一 fail-closed 鉴权；移除固定 session secret 和原始口令 cookie。
3. 取消租户公开可编辑，关闭匿名 OSS token，修复对象键/本地路径校验。
4. 为同步 lease 增加 owner fencing/续租/finally；空结果不清表；扩展写后校验和可验证回滚。
5. 修复 provider 日期、分页和响应完整性，统一重试/认证失效状态。
6. 给上传和请求加大小、数量、格式、字段及公式注入防护。
7. 增加调度 misfire 补跑、持久化/恢复审计、数据库连接与部署硬化。

## 真实限制

* 未调用真实外部平台，也未执行生产写入；Feishu 精确分页字段、range 语法及权限语义应在测试租户按当前 API 文档回归。
* `app/main.py` 还导入 `keyword_service`、`lingxi_service` 路由；这些不在用户给定逐文件清单内，未声称已完成它们的全量审查。
* 没有把任何 Cookie、Token 或 Secret 的原值写入本报告。

---
# 附录 B：keyword_service / lingxi_service / 测试
# JFJLL/automation（master）keyword_service、lingxi_service 与测试代码审查

审查基线：`master` 当前头为 [f72fd8b](https://github.com/JFJLL/automation/commit/f72fd8b8b0ce775528fc15333bed1ee48d7bb2d4)（fix(main)，2026-09-30）。已知的 `fix(lingxi): ... remove admin auth checks` 是较早的 [d2399ec](https://github.com/JFJLL/automation/commit/d2399ec1b1890a2e03e6ce8a39cfba40ca51c887)，但其修改仍在当前 master 中；后续合并提交为 [0a0116f](https://github.com/JFJLL/automation/commit/0a0116ff2c20d130ffbf2831dd9bdd323f72f50c)。以下行号为 master 文件的约行号（以 GitHub 文件当前版本为准）。

## 结论摘要

1. **P0：仓库公开提交了 `lingxi_service/token.json`，其中存在真实 Cookie。** 我只确认文件存在及其内容结构，没有在本报告写出任何原值；必须立即撤销/轮换该 Cookie，并清理 Git 历史。
2. **P0/P1：Lingxi API 完全没有依赖 `require_auth`/`require_admin`。** 搜索、Cookie 读取/写入/OSS 同步、飞书建表、任务 CRUD、立即运行、暂停/删除、runs 查询均可被未登录请求访问。
3. **P1：keyword 的 `/api/keyword/tasks` 和 `/api/keyword/runs` 也无鉴权**，泄漏任务、表格 URL、运行状态；keyword search 使用 `require_auth`，但 `require_auth` 在没有 `AUTH_MODE` 时默认是 `internal`，默认配置会绕过认证。
4. **P1：Lingxi 失败词会按 0 写入飞书，但 run 仍标记 success。** `direct_create_feishu_sheet` 与 `run_lingxi_task` 没有 strict/失败中止语义，可能把上游失败误写成真实的 0。
5. **P1：两套飞书写入都是多次 PUT/写单元格，没有引擎级备份、清理或回滚。** 中途失败会留下部分新数据；数据库 run 只会变 failed，不能把外部表恢复。
6. **P1：lease 释放不校验 owner，且旧 lease 过期后可能和新运行并发；旧运行 finally 可删除新运行的 lease。** 当前测试没有覆盖过期竞态。
7. **P1：Lingxi 的分页参数没有边界校验（尤其 `page_size=0` 会除零），delete 物理删除审计记录；create 的 `update_mode` 参数实际上被忽略/强制 append。**
8. **P1/P2：Cookie 明文落盘，写入非原子、未设置文件权限、会复制到第二个 session_headers 文件；Lingxi GET Cookie 还返回首尾片段。** 代码没有显式打印 Cookie，但这不能抵消公开 token 和落盘风险。
9. **P2：Lingxi client 有无法移植且疑似错误的硬编码 Windows 路径；关键 API 调用没有重试/限流/严格 auth_expired 检测。** Keyword 也没有普通网络重试。
10. **测试整体更像冒烟/契约样例而非安全与写入一致性测试：** Playwright 依赖外部已运行的 `127.0.0.1:8092` 和本机 `msedge`；Lingxi 测试会操作真实全局数据库/调度器；两个测试目录有重复路由覆盖；pytest 配置没有隔离、超时或跳过标记。

---

## 一、P0/P1 安全与凭据问题

### K-SEC-01（P0）公开仓库中的 Lingxi Cookie 必须视为已泄露
- **文件/位置**：`lingxi_service/token.json`（文件级；该文件不是用户要求逐函数审查的 Python 文件，但属于重点 Cookie 检查对象）。
- **证据**：[GitHub Contents API](https://api.github.com/repos/JFJLL/automation/contents/lingxi_service/token.json?ref=master) 返回该文件存在、大小 1586 字节，并包含 `cookie` 字段的 base64 内容；未解码/复述其值。
- **影响**：任何能读公开仓库的人都可以拿到小红书灵犀会话，进而调用接口；同时当前 Lingxi 路由没有鉴权，风险叠加。
- **修复**：立即在小红书侧退出/撤销并重新生成 Cookie；从工作树和全部 Git 历史删除，启用 secret scanning/pre-commit；生产凭据改用 Secret Manager/环境变量或受限文件；启动时拒绝仓库内 token 文件；对历史泄露做审计。

### K-SEC-02（P0）Lingxi 全部 API 路由移除了管理员鉴权
- **文件/函数**：`lingxi_service/router.py`，`search_lingxi_keywords`、`get_lingxi_cookie`、`update_lingxi_cookie`、`sync_lingxi_cookie_oss`、`direct_create_sheet`、`list_lingxi_tasks`、`create_task_endpoint`、`append_keywords_endpoint`、`remove_keywords_endpoint`、`run_task_now_endpoint`、`toggle_task_endpoint`、`delete_task_endpoint`、`list_lingxi_runs`（约第 45–220 行）。
- **证据片段**：
  ```python
  private_router = APIRouter(prefix="/api/lingxi")
  @private_router.post("/search")
  def search_lingxi_keywords(req: LingxiSearchRequest):
  ...
  @private_router.post("/cookie")
  def update_lingxi_cookie(req: CookieUpdateRequest):
  ...
  @private_router.post("/feishu/direct_create")
  def direct_create_sheet(req: LingxiDirectSheetRequest):
  ```
  路由函数签名没有 `Depends(require_auth)` 或 `Depends(require_admin)`；文件虽导入 `require_admin`、`require_auth`，却未使用。相关删除鉴权的提交说明见 [d2399ec](https://github.com/JFJLL/automation/commit/d2399ec1b1890a2e03e6ce8a39cfba40ca51c887)。
- **影响**：匿名用户可查询上游数据、读取 Cookie 片段、覆盖 Cookie、触发 OSS 同步、创建公开可编辑飞书表、运行/删除任务。
- **修复**：所有 `/api/lingxi/*` 默认使用 `require_auth`；Cookie、同步、建表、任务写操作使用 `require_admin`；对 `GET /tasks`、`GET /runs` 至少使用登录态；增加路由级 deny-by-default 测试。不要通过删除依赖来“修复前端登录问题”。

### K-SEC-03（P1）Lingxi Cookie 预览本身泄漏敏感 Cookie 片段
- **文件/函数**：`lingxi_service/router.py:get_lingxi_cookie`（约第 78–86 行）。
- **证据片段**：
  ```python
  cookie_val = token.get("cookie", "")
  masked = f"{cookie_val[:10]}...{cookie_val[-10:]}" if len(cookie_val) > 20 else cookie_val
  return {"has_cookie": bool(cookie_val), "masked_cookie": masked, ...}
  ```
- **影响**：在当前无鉴权前提下，匿名请求直接获得 Cookie 首尾；即使恢复鉴权，首尾片段也不必要。
- **修复**：接口只返回 `has_cookie`、长度、更新时间；前端不需要片段。若确实要预览，只对管理员返回固定 `***`，并避免把 Cookie 回显到日志/错误信息。

### K-SEC-04（P1）Keyword 任务和运行记录列表匿名可读
- **文件/函数**：`keyword_service/router.py:list_keyword_tasks`、`list_keyword_runs`（约第 220–300 行）。
- **证据片段**：
  ```python
  @private_router.get("/tasks")
  def list_keyword_tasks():
      ... SELECT * FROM keyword_tasks ...
  @private_router.get("/runs")
  def list_keyword_runs(...):
      ... SELECT * FROM keyword_runs ...
  ```
  两者均无 `dependencies=[Depends(require_auth)]`；相对地 `search_keywords` 有 `_=Depends(require_auth)`，写任务路由多数有 `require_admin`。
- **影响**：匿名可获得关键词、内部飞书 token/URL、任务名、失败详情与运行状态。
- **修复**：统一给列表与详情接口加认证；按用户/租户隔离任务；不要 `SELECT *` 直接输出内部字段，明确允许字段。

### K-SEC-05（P1）`require_auth` 的默认值是绕过认证，配置缺失即开放
- **文件/函数**：`sync_console/core/security.py:require_auth`（约第 68–73 行）。
- **证据片段**：
  ```python
  def require_auth(request: Request) -> bool:
      auth_mode = os.getenv("AUTH_MODE", "internal").strip().lower()
      if auth_mode == "internal":
          return True
      return require_admin(request)
  ```
- **影响**：keyword search 虽然写了 `Depends(require_auth)`，但生产漏设 `AUTH_MODE` 时默认开放。测试 `conftest.py` 强行设为 `token`，掩盖了默认部署行为。
- **修复**：生产默认 deny（例如默认 `token`）；`internal` 必须显式配置且只允许受信任内部网络/反向代理；启动时校验 `AUTH_MODE` 与密钥，不满足则拒绝启动。

### K-SEC-06（P1）Session secret 可回退到弱/可预测默认值；原始 Access Token 兼容入口扩大泄漏面
- **文件/函数**：`sync_console/core/security.py` 顶层 `SESSION_SECRET`、`is_admin_authenticated`（约第 10、40–66 行）。
- **证据片段**：
  ```python
  SESSION_SECRET = os.getenv("SESSION_SECRET", ACCESS_TOKEN or "sync-console-secret-key").encode("utf-8")
  ...
  if ACCESS_TOKEN and header_token == ACCESS_TOKEN: return True
  ...
  if ACCESS_TOKEN and bearer_val == ACCESS_TOKEN: return True
  ```
- **影响**：缺少配置时使用固定默认签名密钥；`X-Access-Token`/Bearer 直接接受长期明文 token，容易被代理、日志或客户端泄露。
- **修复**：`SESSION_SECRET` 必须是高熵 Secret Manager 值，缺失即启动失败；只接受短期签名 session，保留 raw token 兼容时应有明确弃用期限、审计和限流。

---

## 二、Cookie、上游调用与参数正确性

### K-AUTH-01（P1）Cookie 写入非原子且没有文件权限加固，更新了两份明文文件
- **文件/函数**：`keyword_service/router.py:update_keyword_cookie`（约第 170–198 行）；`keyword_service/client.py:sync_token_from_oss`（约第 18–96 行）；`lingxi_service/router.py:update_lingxi_cookie`（约第 88–102 行）；`lingxi_service/client.py:sync_token_from_oss`（约第 10–43 行）。
- **证据片段**：
  ```python
  DEFAULT_TOKEN_FILE.write_text(json.dumps(token_data, ...), encoding="utf-8")
  ...
  session_file.write_text(json.dumps(token_data, ...), encoding="utf-8")
  ```
  Lingxi 同样直接 `token_path.write_text(...)`；没有临时文件 + `os.replace`、`chmod 0600`、目录权限或并发锁。
- **影响**：进程崩溃可留下截断 JSON；并发更新可互相覆盖；服务器本地其他用户可能读取 Cookie；Keyword 还将凭据复制到 `sync_console/tokens/session_headers.json`。
- **修复**：不把 Cookie 持久化到仓库目录；改 Secret Manager。若必须落盘，目录/文件 `0700/0600`，校验 schema，写临时文件后 fsync + `os.replace`，使用进程/文件锁，必要时版本化并拒绝旧覆盖。

### K-AUTH-02（P2）Lingxi 硬编码 Windows 路径不可移植且写法疑似错误
- **文件/函数**：`lingxi_service/client.py:load_token`（约第 51–69 行）。
- **证据片段**：
  ```python
  local_txt = Path(r"D:downloadpic-vecoss-uploadcookieslingxi_cookie.txt")
  ```
- **影响**：缺少 `D:\` 分隔符；在 Windows 是 drive-relative 路径，在 Linux 通常被当作相对路径。部署可能意外读取工作目录中的同名路径，或完全找不到预期 Cookie。
- **修复**：删除机器私有 fallback；路径由配置注入并用 `Path` 拼接；优先 Secret Manager，读取前校验 realpath 在允许目录内。

### K-AUTH-03（P2）OSS 同步的 `force` 参数没有实际语义，且会静默覆盖人工更新
- **文件/函数**：两套 `sync_token_from_oss(force=False)`（keyword client 约第 18 行、lingxi client 约第 10 行）。
- **证据片段**：函数接受 `force`，但函数体没有使用它；成功时直接 `write_text` 覆盖本地 token。Scheduler 每次任务前又调用同步。
- **影响**：调度器可能覆盖刚由管理员写入的 Cookie；调用方以为 `force=True` 有刷新/锁定语义但实际没有；没有版本、更新时间或来源冲突保护。
- **修复**：明确 `force`（强制拉取/不覆盖本地）语义；同步前后加版本/ETag/租约；成功写入必须原子化；不要在每次 job 前无条件覆盖凭据。

### K-CLIENT-01（P1）Lingxi 没有稳定的 auth_expired 检测与重试
- **文件/函数**：`lingxi_service/client.py:_fetch_single_word`、`fetch_lingxi_keywords`（约第 79–160 行）。
- **证据片段**：
  ```python
  if resp.status_code != 200:
      return {"status": "upstream_error", "message": f"HTTP {resp.status_code}", ...}
  ...
  if data.get("code") != 0 or not data.get("success"):
      if "登录" in msg or "login" in msg.lower() or "auth" in msg.lower():
          return {"status": "auth_expired", ...}
  ```
  HTTP 401/403 被归为 `upstream_error`；没有根据 `auth_expired` 刷新 OSS 并重试，也没有退避重试。
- **影响**：Cookie 失效时调用方看不到一致的认证错误；短暂 429/5xx/连接错误直接失败；多关键词并发可能同时击穿上游。
- **修复**：统一响应分类（HTTP 401/403、明确业务 code、登录关键字）；认证失败只刷新一次并只重试失败词；对连接/408/429/5xx 使用有限指数退避+jitter；记录不含 Cookie 的 provider 状态。

### K-CLIENT-02（P1）Lingxi client 的并发数不受控，且没有限流
- **文件/函数**：`lingxi_service/client.py:fetch_lingxi_keywords`（约第 145–181 行）。
- **证据片段**：
  ```python
  with ThreadPoolExecutor(max_workers=max_workers) as executor:
      future_to_kw = {executor.submit(_fetch_single_word, kw, token): kw for kw in keywords}
  ```
  `max_workers` 是调用方可传的任意值，无上限；只有 router 对关键词数做了 100 限制，直接调用 client 不受限。
- **影响**：内部调用或未来新路由传入大量关键词时可创建过多线程、触发上游限流或造成本地资源耗尽。
- **修复**：在 client 层 clamp `1..N`，关键词总数也在 service 层统一限制；加 semaphore/token bucket；对重复词在 client 层去重并保持输入顺序。

### K-CLIENT-03（P2）Keyword 普通网络失败没有重试，`max_workers` 边界未校验
- **文件/函数**：`keyword_service/client.py:_fetch_single_word`、`fetch_keywords_insight`（约第 120–365 行）。
- **证据片段**：
  ```python
  except requests.Timeout: ...
  except Exception as e: return ...
  ...
  with ThreadPoolExecutor(max_workers=min(max_workers, len(targets))) as executor:
  ```
  只有认证失败会 OSS 刷新并重试一次；`max_workers=0`/负数会在 executor 构造处失败。
- **影响**：瞬时连接失败直接失败；内部调用传入无效并发数得到 500；不能区分可重试与不可重试错误。
- **修复**：参数校验；对有限网络错误加退避；只对幂等 POST 且请求可安全重放时重试；上游 429 使用 Retry-After。

### K-CLIENT-04（P2）Keyword 的 `v_seller_id` 有硬编码 fallback，未强制凭据一致性
- **文件/函数**：`keyword_service/client.py:_fetch_single_word`（约第 121–139 行）、`router.py:CookieUpdateRequest`、`get_current_cookie`（约第 45、166–178 行）。
- **证据片段**：
  ```python
  v_seller_id = token.get("v_seller_id") or token.get("v-seller-id", "628b3a5056228a000189c0e4")
  ...
  v_seller_id: Optional[str] = "628b3a5056228a000189c0e4"
  ```
- **影响**：缺字段或拼写错误时请求落到固定账号；Cookie 与 query/header 中的卖家 ID 可能不匹配，造成错误账户查询或认证失败。该默认值也出现在 referer。
- **修复**：vSellerId 必须来自受校验配置，不存在就拒绝请求；校验 Cookie 所属账号（能验证时）；删除业务账号硬编码，按子账号/租户显式选择。

### K-CLIENT-05（P2）Keyword 响应日期/重复日期/缺失日期处理可能把异常变成 0
- **文件/函数**：`keyword_service/client.py:_fetch_single_word`（约第 189–224 行）与 `fetch_keywords_insight`（约第 300–330 行）。
- **证据片段**：
  ```python
  daily_data[str(day)[:10]] = {...}  # 同一天后到的数据覆盖先到的数据
  ...
  if d in item.data: ...
  else: kw_map[d] = {"search_num": 0, ...}
  ```
- **影响**：重复日期未检测；上游漏报的成功日期被当成 0，无法区分“真实 0”和“数据不完整”。失败词虽保留为 `None`，但成功响应内部缺日仍会被填 0。
- **修复**：严格校验日期格式与请求区间，重复日期按契约报错或明确聚合；缺失日期返回 `missing_dates`/null，不自动填 0，只有 provider 明确无数据时才填 0。

### K-CLIENT-06（P2）`load_token` 对存在但坏掉的 token.json 不回退 OSS
- **文件/函数**：`keyword_service/client.py:load_token`（约第 98–117 行）。
- **证据片段**：
  ```python
  with open(path, "r", encoding="utf-8") as f:
      data = json.load(f)
  return data
  ```
  仅在文件不存在时尝试 OSS；存在但 JSON 损坏/字段缺失会直接抛出或继续发送空 Cookie。
- **修复**：schema 校验失败时记录非敏感错误并走受控 OSS fallback；校验 cookie、v_seller_id、origin 等必要字段；不能把任意 JSON 当凭据。

---

## 三、同步引擎、飞书写入与 run/lease 一致性

### K-SYNC-01（P1）Lingxi 失败关键词被写成 0，且 run 仍成功
- **文件/函数**：`lingxi_service/sync_engine.py:build_lingxi_date_matrix`、`direct_create_feishu_sheet`、`run_lingxi_task`（约第 20–63、75–115、184–275 行）。
- **证据片段**：
  ```python
  # build_lingxi_date_matrix
  new_kw_item = new_data.get(kw, {})
  ...
  if d == new_date and kw in new_data:
      cnt = new_kw_item.get("user_cnt", 0)
  ...
  fetch_res = fetch_lingxi_keywords(keywords)
  ...
  write_matrix_to_sheet(feishu, ss_token, sheet_id, matrix)
  ...
  UPDATE lingxi_runs SET ... status = 'success', ...
  ```
  `fetch_lingxi_keywords` 对失败词仍放入 `results` 且 `user_cnt=0`；引擎没有检查 `failed_keywords`，直接写表并成功收尾。
- **影响**：上游 401/500/timeout 会被呈现为覆盖人数为 0，且任务状态成功，后续无法可靠区分。
- **修复**：引擎引入 `strict=True` 默认：任一失败则在写表前失败并写 failed run；非严格模式写 null/标记列而不是 0；成功 run 的 `failed_keywords` 必须为空。

### K-SYNC-02（P1）两套写表都不是原子操作，中途异常会留下部分数据
- **文件/函数**：`keyword_service/sync_engine.py:write_matrix_to_sheet`（约第 36–83 行）；`lingxi_service/sync_engine.py:write_matrix_to_sheet`（约第 68–108 行）；调用方 `run_keyword_task`/`run_lingxi_task`。
- **证据片段**：
  ```python
  for c_start in range(...):
      ...
      feishu.request("PUT", ..., json={...})
  ```
  Lingxi 版本同样按 chunk 调 `feishu.write_cells`。单个 chunk 失败时此前 chunk 已经持久化；引擎没有调用 `restore_sheet_values` 或备份恢复。
- **影响**：飞书表出现半张新表；数据库 run failed 不能回滚外部副作用；重跑可能基于半写入历史继续扩散。
- **修复**：写前读取并持久化受控备份；使用飞书批量/事务 API（若无事务则 staging sheet + 校验后切换）；每个 chunk 记录 checkpoint；异常时恢复备份并写 `rollback_status`；恢复失败必须告警。

### K-SYNC-03（P1）维度扩展失败仅打印后继续写，且无行列硬上限
- **文件/函数**：两套 `write_matrix_to_sheet`、Keyword `merge_date_headers`（约第 40–112 行）。
- **证据片段**：
  ```python
  try: feishu.request(... dimension_range ...)
  except Exception as e: print(f"[Feishu] Dimension expand ... {e}")
  ```
  扩展失败没有中止；`total_rows/total_cols` 由输入直接决定，也没有 API 限额检查。
- **影响**：后续 PUT 很可能失败或只写入部分；keyword 请求允许最多 5000 词×90 天，可能生成约 5002 行×361 列的大矩阵；没有明确拒绝超限。
- **修复**：扩展失败立即抛出 `FeishuWriteError`；写前检查飞书工作表行列上限和 payload 大小，分批并设置服务级配额；不要用 `print` 替代结构化告警。

### K-SYNC-04（P1）Lease 只有 key，没有 owner 校验，过期竞态可破坏互斥
- **文件/函数**：`sync_console/core/database.py:acquire_task_lease`、`release_task_lease`（约第 210–263 行）；两套 `run_*_task` finally（Keyword 约第 420 行，Lingxi 约第 275 行）。
- **证据片段**：
  ```python
  def release_task_lease(conn, task_key):
      ... conn.execute("DELETE FROM task_leases WHERE task_key = ?", (task_key,))
  ```
  release 不带 owner/token；旧 worker 超过 600/900 秒后，新 worker 可覆盖 lease，旧 worker finally 会无条件删除新 worker 的 lease。
- **影响**：同一任务可能同时写飞书；后续调度/手动运行也可能绕过防重。
- **修复**：lease 返回随机 fencing token，`release ... WHERE task_key=? AND token=?`；所有写入带 fencing token 或外部锁；续租心跳；过期后旧 worker 必须在写前再次校验所有权。增加多连接、睡眠过期、旧 owner release 的测试。

### K-SYNC-05（P1）Lingxi `update_mode` 参数被忽略并强制 `append`
- **文件/函数**：`lingxi_service/router.py:CreateLingxiTaskRequest/create_task_endpoint`；`lingxi_service/sync_engine.py:create_lingxi_task/run_lingxi_task`（约第 28–42、130–181、184–210 行）。
- **证据片段**：
  ```python
  update_mode: str = Field("append")
  ...
  INSERT INTO lingxi_tasks (... update_mode, ...) VALUES (..., 'append', ...)
  ```
  `create_task_endpoint` 把请求的 `update_mode` 传入函数，但 `create_lingxi_task` SQL 固定写 `'append'`；`run_lingxi_task` 读取 `update_mode` 后没有分支使用。
- **影响**：调用方选择 overwrite 得到的仍是 append；历史列无限增长，接口契约与实际行为不一致。
- **修复**：只允许明确枚举；数据库写入真实值；`run` 对 overwrite/append 分别实现并测试；若产品只支持 append，就删除参数并在 API 明确返回。

### K-SYNC-06（P1）Lingxi 使用服务器本地时间，不使用业务时区/可用日期策略
- **文件/函数**：`lingxi_service/sync_engine.py:direct_create_feishu_sheet`、`run_lingxi_task`（约第 78、213 行）。
- **证据片段**：
  ```python
  today_str = datetime.now().strftime("%Y-%m-%d")
  ```
  Keyword 则使用 `latest_keyword_available_date()` 与 `validate_keyword_date_range`。
- **影响**：服务器 UTC 或夏令时环境在北京时间跨日附近会把数据写入错误日期；与调度器的 `TIMEZONE` 不一致。
- **修复**：统一 `now_business_tz()`；如果灵犀数据实际是“可用日”而非自然日，定义并测试 cutoff；时间统一保存带时区 ISO 8601。

### K-SYNC-07（P1）Lingxi 分页、删除与 runs API 缺乏安全边界
- **文件/函数**：`lingxi_service/router.py:list_lingxi_runs`、`delete_task_endpoint`（约第 201–220、183–198 行）。
- **证据片段**：
  ```python
  total_pages = max(1, (total + page_size - 1) // page_size)
  ... LIMIT ? OFFSET ?
  ```
  `page_size=0` 会在除法处触发 500；负数可能得到负 OFFSET/LIMIT 的 SQLite 特殊行为。delete 直接 `DELETE FROM lingxi_tasks` 且不检查 rowcount。
- **影响**：分页可被异常参数打崩；物理删除会按外键级联删除 runs（审计丢失）；删除不存在任务也返回成功。
- **修复**：Pydantic `ge=1, le=100`，page `ge=1`；非法参数 422；采用 archived 状态保留审计；删除检查 rowcount 并返回 404；列表按租户过滤。

### K-SYNC-08（P2）Lingxi removed_keywords 没有参与同步语义
- **文件/函数**：`lingxi_service/sync_engine.py:run_lingxi_task`、`remove_keywords_from_lingxi_task`（约第 223–231、293–312 行）。
- **证据片段**：
  ```python
  all_target_keywords = list(dict.fromkeys(list(old_history.keys()) + keywords))
  ```
  运行时没有读取 `removed_keywords_json`，也没有像 Keyword 那样对移除词保持空白/停止更新。
- **影响**：移除词仍保留历史行并对新日期填 0；重新添加时 removed 集合也没有清除逻辑。用户看见的“移除”与数据语义不一致。
- **修复**：明确产品策略：移除词保留历史但新日为 null，或彻底删除；读取 removed 集合并按日期处理；追加时从 removed 集合移除；补回归测试。

### K-SYNC-09（P2）日期解析过于宽松，可能把非日期表头当日期
- **文件/函数**：`lingxi_service/sync_engine.py:parse_existing_lingxi_sheet`（约第 20–54 行）。
- **证据片段**：
  ```python
  val = str(row0[idx]).strip() if row0[idx] is not None else ""
  if val:
      existing_dates.append(val)
      date_col_map[val] = idx
  ```
  没有 `YYYY-MM-DD` 校验，重复 header 只保留最后一列；keyword 版本至少检查长度和第 5/8 字符。
- **修复**：用严格 `date.fromisoformat`，拒绝重复日期和异常列；返回解析诊断，不要静默吞掉表格损坏。

### K-SYNC-10（P2）空 sheet 造成 IndexError；Feishu 公开编辑扩大数据暴露
- **文件/函数**：两套 `write_matrix_to_sheet` 的 `sheets[0]` fallback；`keyword_service/sync_engine.py:direct_create_feishu_sheet/create_keyword_task`；`lingxi_service/sync_engine.py:direct_create_feishu_sheet`。
- **证据片段**：
  ```python
  curr_sheet = next((s for s in sheets if s["sheet_id"] == sheet_id), sheets[0])
  ```
  以及 `feishu.set_sheet_public_editable(ss_token)`、`feishu.set_public_permission(ss_token, edit=True)`。
- **影响**：上游返回空 sheet 列表时直接 500；创建成功后把关键词和指标设置为公开可编辑，尤其 Lingxi direct endpoint 当前匿名可触发。
- **修复**：显式检查空列表并抛出可诊断错误；默认私有，仅授予指定用户/群组；公开编辑必须是明确、审计过的产品选项并需要管理员确认。

### K-SYNC-11（P2）run 记录语义不一致，直接建表缺少失败记录
- **文件/函数**：Keyword `direct_create_feishu_sheet/create_keyword_task/run_keyword_task`；Lingxi `direct_create_feishu_sheet/create_lingxi_task/run_lingxi_task`。
- **证据片段**：Keyword direct 在写入全部完成后才 `INSERT keyword_runs ... 'success'`；Lingxi direct 没有插入 `lingxi_runs`；两套 create 在飞书创建/写入失败时不会留下失败 run；只有 scheduled/manual run 在开始时插入 running。
- **影响**：运维看不到 direct 失败；两服务的 runs API 无法比较；外部表已创建但 DB 任务未创建时形成孤儿表。
- **修复**：建立统一 run 生命周期：开始即写 running，任何失败写 failed/error_detail/rollback_status，成功才 success；direct 也有 run_id；外部资源创建失败/DB 写失败要有补偿或标记 orphan。

### K-SYNC-12（P2）数据库连接生命周期和任务状态校验不一致
- **文件/函数**：`lingxi_service/db.py:init_db`、`get_db`；Lingxi router 多个列表/任务函数；两套 `run_*_task`。
- **证据片段**：
  ```python
  def init_db():
      conn = get_db()
      run_migrations(conn, module="lingxi")
  ```
  Lingxi router 的 `conn = get_db()` 没有统一 `with`/close；`run_lingxi_task`/`run_keyword_task` 查到任务后没有拒绝 paused/archived 状态。
- **修复**：所有连接使用 context manager；`init_db` 完成后关闭；运行前原子校验 `status='active'`；增加连接泄漏与 paused 手动运行测试。

---

## 四、逐文件/逐函数审查记录

以下不是“只列文件名”：每个目标文件已完整读到末尾；对大数据文件按任务要求仅读取开头结构；对 token 文件只确认存在，不输出凭据。

### `keyword_service`

- [`README.md`](https://github.com/JFJLL/automation/blob/master/keyword_service/README.md)：完整。说明四指标、90 天/任务调度、飞书公开编辑和 `token.json` 位置；安全上把本地 token 覆盖描述成正常运维路径，没有权限/轮换说明。函数：无。
- [`__init__.py`](https://github.com/JFJLL/automation/blob/master/keyword_service/__init__.py)：完整（空文件）。函数：无。
- [`client.py`](https://github.com/JFJLL/automation/blob/master/keyword_service/client.py)：完整。函数 `sync_token_from_oss`（候选 key、解析、明文持久化、force 未用，见 K-AUTH-01/03）；`load_token`（本地/fallback/坏 JSON问题，K-CLIENT-06）；`_fetch_single_word`（请求 payload、header、401/902、JSON/日期/数字解析，K-CLIENT-04/05）；`fetch_keywords_insight`（去重、并发、认证重试、strict、部分结果，K-CLIENT-03/05）；`fetch_keyword_insight`（单词包装，依赖 strict）。
- [`db.py`](https://github.com/JFJLL/automation/blob/master/keyword_service/db.py)：完整。`get_db` 只是转发；`init_db` 调 migration 但不 close（K-SYNC-12）。
- [`router.py`](https://github.com/JFJLL/automation/blob/master/keyword_service/router.py)：完整。`keyword_library` 缓存整个 JSON 并按包含关系分类；缓存无失效/文件变更检测。`search_keywords` 有 `require_auth` 但默认 AUTH_MODE 风险；Cookie GET/POST（管理员依赖但明文落盘）；direct/create/run/append/remove/toggle/delete（多数管理员依赖）；`list_keyword_tasks`/`list_keyword_runs` 无鉴权；login 用 `ACCESS_TOKEN` + session cookie。详见 K-SEC-04、K-AUTH-01、K-CLIENT-04、K-SYNC-11。
- [`scheduler.py`](https://github.com/JFJLL/automation/blob/master/keyword_service/scheduler.py)：完整。`parse_next_run/reschedule_keyword_task/remove_keyword_job/init_keyword_scheduler` 都是 SchedulerManager 薄包装；没有额外认证/并发逻辑，真正调度在 `scheduler_manager.py`。
- [`sync_engine.py`](https://github.com/JFJLL/automation/blob/master/keyword_service/sync_engine.py)：完整。`build_sheet_matrix`、`write_matrix_to_sheet`、`merge_date_headers`、`parse_existing_sheet_history`、`direct_create_feishu_sheet`、`create_keyword_task`、`run_keyword_task`、`append_keywords_to_task`、`remove_keywords_from_task`。strict fetch 是正确的安全方向，但外部写入仍非原子；lease/失败记录/日期增量问题见 K-SYNC-02/03/04/11。
- [`test_keyword.py`](https://github.com/JFJLL/automation/blob/master/keyword_service/test_keyword.py)：完整。唯一的 `test_keyword_routes_and_search_mocked` mock 了搜索，只验证页面、搜索一条数值、词库存在；临时 DB 没有注入 app/core 实际 DB，且 login 状态未断言。没有未登录列表、Cookie 写入、task run、失败回滚覆盖。
- `all_keyword_trends.json`：按要求只读开头，确认顶层为“关键词 -> 日期 -> 字符串数值”的对象，例如首个键含连续日期；未声称完整读取 115KB。
- `token.json`：通过 Contents API 查询未找到（404）；未输出任何凭据。

### `lingxi_service`

- [`__init__.py`](https://github.com/JFJLL/automation/blob/master/lingxi_service/__init__.py)：完整，为中文模块 docstring，无函数。
- [`client.py`](https://github.com/JFJLL/automation/blob/master/lingxi_service/client.py)：完整。`sync_token_from_oss`、`load_token`、`_fetch_single_word`、`fetch_lingxi_keywords`；详见 K-AUTH-02/03、K-CLIENT-01/02。接口 payload 为 `encode/searchKey/extra.router=keyword_rec`，但测试没有契约断言。
- [`db.py`](https://github.com/JFJLL/automation/blob/master/lingxi_service/db.py)：完整。`get_db/init_db` 与 Keyword 对称，init 不 close。
- [`router.py`](https://github.com/JFJLL/automation/blob/master/lingxi_service/router.py)：完整。全部函数均无 auth dependency（K-SEC-02）；Cookie GET 返回 mask；任务 list 没有 archived 过滤；create 不验证 RRULE/模式；toggle/delete 无 rowcount；runs page 参数未约束。
- [`sync_engine.py`](https://github.com/JFJLL/automation/blob/master/lingxi_service/sync_engine.py)：完整。`parse_existing_lingxi_sheet`、`build_lingxi_date_matrix`、`write_matrix_to_sheet`、`direct_create_feishu_sheet`、`create_lingxi_task`、`run_lingxi_task`、`append_keywords_to_lingxi_task`、`remove_keywords_from_lingxi_task`。失败词 0 写入、append 强制、日期/removed/部分写入/lease 问题见 K-SYNC-01–09。
- `token.json`：已确认存在（Contents API 返回文件元数据和 `cookie` 字段）；按要求未读取/输出 Cookie 原值。

### `tests/`

- [`conftest.py`](https://github.com/JFJLL/automation/blob/master/tests/conftest.py)：完整。设置临时 sync/keyword DB、AUTH_MODE/token/session secret/timezone，并初始化迁移；`guard_production_database` 仅比较生产文件大小，不比较 mtime/内容且未包含 Lingxi DB（见 T-01）。
- [`test_api_auth.py`](https://github.com/JFJLL/automation/blob/master/tests/test_api_auth.py)：完整。`test_health_and_ready_endpoints`、`test_login_flow_session_cookie_no_token_leak`、`test_cookie_preview_never_exposed`、`test_admin_route_protection`。Keyword cookie 断言安全，但只测 Keyword；没有 Lingxi 路由匿名拒绝测试。
- [`test_business_time.py`](https://github.com/JFJLL/automation/blob/master/tests/test_business_time.py)：完整。覆盖 12:00 前后 T-2/T-1、90/91 天、起止/未来日期和 sync cutoff；这是 Keyword 日期较强的单元测试，但没有把实际 client payload 与日期断言连起来。
- [`test_database.py`](https://github.com/JFJLL/automation/blob/master/tests/test_database.py)：完整。测试 pragma、迁移幂等和同连接 lease 顺序；没有多连接、过期夺锁、owner fencing、异常释放覆盖。
- [`test_e2e_flow.py`](https://github.com/JFJLL/automation/blob/master/tests/test_e2e_flow.py)：完整。mock Feishu/provider，覆盖主同步与 Keyword search/create/run/list；没有真实外部网络，但断言主要是 HTTP/status/一项数据，不检查表格矩阵、失败回滚或 lease。
- [`test_keyword_client.py`](https://github.com/JFJLL/automation/blob/master/tests/test_keyword_client.py)：完整。覆盖成功/空/401/902/500/timeout/坏 JSON、partial/strict/auth retry；未检查 POST URL query、headers、payload columns/date、重复日期、缺日期、普通连接错误重试、并发边界。
- [`test_keyword_sync_engine.py`](https://github.com/JFJLL/automation/blob/master/tests/test_keyword_sync_engine.py)：完整。覆盖日期 key 对齐、移除词对齐、fetch 失败不建孤儿表；没有实际 `run_keyword_task` 飞书部分写失败回滚、run 字段、lease 竞态、append endpoint。
- [`test_lingxi_service.py`](https://github.com/JFJLL/automation/blob/master/tests/test_lingxi_service.py)：完整。`test_lingxi_matrix_builder`、`test_lingxi_task_crud`、`test_lingxi_api_routes`；模块级 `TestClient(app)`，调用 `init_db/create_lingxi_task`，会使用全局 Lingxi DB/调度器；没有 mock fetch/Feishu，也没有未登录保护、Cookie、失败 0、timezone、分页/overwrite 测试。
- [`test_natural_key_and_rollback.py`](https://github.com/JFJLL/automation/blob/master/tests/test_natural_key_and_rollback.py)：完整。主同步 natural key 和 Feishu `restore_sheet_values` 单测；**它测试的是 core.sync/Feishu 客户端，当前 Keyword/Lingxi 引擎没有调用该恢复逻辑**，因此不能证明两套 keyword 引擎具备回滚。
- [`test_playwright_e2e.py`](https://github.com/JFJLL/automation/blob/master/tests/test_playwright_e2e.py)：完整（raw 内容被截断时通过 [Contents API](https://api.github.com/repos/JFJLL/automation/contents/tests/test_playwright_e2e.py?ref=master) 读取）。`test_react_spa_no_iframe_e2e` 启动 `p.chromium.launch(channel="msedge")`，访问 `http://127.0.0.1:8092/`，点击按钮并每次只等 500ms；无服务 fixture、无 skip/marker、无 auth 数据。
- [`test_provider_contracts.py`](https://github.com/JFJLL/automation/blob/master/tests/test_provider_contracts.py)：完整。JZT/Juguang/Taobao provider mock HTTP；与 Keyword/Lingxi 只有外围参考关系。分页失败仅覆盖 Juguang，未覆盖 Lingxi。
- [`test_sync_write_safety.py`](https://github.com/JFJLL/automation/blob/master/tests/test_sync_write_safety.py)：完整。主 `core.sync` append 幂等和 phase-1 fetch failure；不是 Keyword/Lingxi 写入安全测试，不能覆盖它们 chunk 部分失败。
- [`test_web_ui.py`](https://github.com/JFJLL/automation/blob/master/tests/test_web_ui.py)：完整。验证 SPA 多路由返回 `div#root`、无 iframe、favicon；不验证认证或 API 行为。

### `sync_console/tests/`

- [`test_api.py`](https://github.com/JFJLL/automation/blob/master/sync_console/tests/test_api.py)：完整。`TestApiEndpoints.test_auth_flow`、`test_upload_and_preview_flow`、`test_task_management_routes`；与根 `test_api_auth.py`/`test_web_ui.py` 路由认证存在重叠。setUp 只构造 X-Access-Token，各测试没有统一 login，依赖 raw token 兼容分支。
- [`test_flow.py`](https://github.com/JFJLL/automation/blob/master/sync_console/tests/test_flow.py)：完整。平台识别、Excel ingest、RRULE、行映射；不覆盖 keyword/lingxi。
- [`test_juguang_subaccount.py`](https://github.com/JFJLL/automation/blob/master/sync_console/tests/test_juguang_subaccount.py)：完整。全部 OSS/HTTP mock，覆盖子账号列表/headers/一页抓取/不存在账号；不覆盖 Keyword 的硬编码 vSeller fallback。
- [`test_keyword_cookie.py`](https://github.com/JFJLL/automation/blob/master/sync_console/tests/test_keyword_cookie.py)：完整。登录、Cookie GET/空 Cookie 拒绝、mock search；不验证 POST 成功后的文件内容/权限/原子性，不验证未登录 GET tasks/runs。
- [`test_keyword_startup.py`](https://github.com/JFJLL/automation/blob/master/sync_console/tests/test_keyword_startup.py)：完整。尝试 patch `app.db.DB_PATH`/`keyword_service.db.DB_PATH`，建立 Keyword task 并检查 scheduler/job；但 `core.database` 已导入的路径常量不一定随这些 patch 改变，且没有恢复全局 singleton/数据库隔离的可靠保证；还以未登录方式访问公开 task 列表，反而掩盖鉴权缺口。
- [`test_ui_routing_cache.py`](https://github.com/JFJLL/automation/blob/master/sync_console/tests/test_ui_routing_cache.py)：完整。仅检查若干页面 200，与根 `test_web_ui.py` 路由覆盖重复且断言更弱。

### 上下文文件

- [`sync_console/core/scheduler_manager.py`](https://github.com/JFJLL/automation/blob/master/sync_console/core/scheduler_manager.py)：完整。Keyword/Lingxi 使用相同的 date-trigger/恢复逻辑；每次 job 前 OSS 同步，finally 重新 schedule；没有检查任务是否仍 active 后再 schedule 的竞态处理，也没有 lease fencing。`parse_kw_next_run` 不支持 workday 特殊逻辑（主同步的 `parse_sync_next_run` 才支持）。
- [`sync_console/core/security.py`](https://github.com/JFJLL/automation/blob/master/sync_console/core/security.py)：完整。见 K-SEC-05/06。
- [`sync_console/core/database.py`](https://github.com/JFJLL/automation/blob/master/sync_console/core/database.py)：完整。三套 DB/migration 对称，`acquire_task_lease/release_task_lease` 见 K-SYNC-04；Keyword/Lingxi 的 schema 没有数据库级唯一的业务 natural key 或 run 状态约束。

---

## 五、测试质量、缺失覆盖与 pytest 配置

### T-01（P1）全局测试隔离不完整，可能污染真实 Lingxi 数据库
- **文件/函数**：`tests/conftest.py:guard_production_database`；`tests/test_lingxi_service.py`。
- **证据片段**：guard 的 `prod_dbs` 只有 sync、keyword 两个 sync_console DB 和旧 Keyword DB，没有 `sync_console/data/lingxi_data.db`；Lingxi 测试直接 `init_db()`、`create_lingxi_task(...)`。
- **修复**：在 conftest 最早设置 `LINGXI_DB_PATH` 临时路径；所有测试通过 fixture 获取 DB；guard 比较内容/hash/行数而不是只比较文件大小；调度器用 fixture 或 monkeypatch，测试后必清空并 shutdown。

### T-02（P1）Playwright 测试依赖外部进程和本机 MS Edge，默认 pytest 不可复现
- **文件/函数**：`tests/test_playwright_e2e.py:test_react_spa_no_iframe_e2e`。
- **证据**：直接 `launch(channel="msedge")` 和 `page.goto("http://127.0.0.1:8092/")`，仓库测试没有启动服务 fixture；只 `wait_for_timeout(500)`。
- **修复**：使用 Playwright 自带 Chromium 或显式 CI 安装；fixture 启动/停止 app；用 locator 等待业务状态；加 `@pytest.mark.e2e`，默认单元测试跳过，CI profile 显式运行；失败保存 trace/screenshot。

### T-03（P1）没有测试 Lingxi 认证缺口，且现有测试依赖“匿名可访问”
- **文件/函数**：`tests/test_lingxi_service.py:test_lingxi_api_routes`、`sync_console/tests/test_keyword_startup.py`。
- **证据**：`client.get("/api/lingxi/tasks")`、`client.get("/api/lingxi/runs")` 没有登录仍断言 200；startup test 也匿名访问 Keyword tasks。没有 `assert status_code == 401` 的 Lingxi 参数化测试。
- **修复**：增加矩阵：匿名/普通登录/admin/过期 session 对 search、cookie、OSS、direct、task、runs；所有写接口未登录必须 401；测试默认 token 模式，另有显式 internal 模式测试。

### T-04（P1）没有两套引擎的部分写入、失败词、回滚和 run 一致性测试
- **文件/函数**：`tests/test_keyword_sync_engine.py`、`tests/test_lingxi_service.py`、`tests/test_natural_key_and_rollback.py`、`tests/test_sync_write_safety.py`。
- **证据**：`test_natural_key_and_rollback` 直接测 `FeishuClient.restore_sheet_values`；`test_sync_write_safety` 只测 `core.sync.execute_task_sync`；Keyword sync engine 只测解析/建任务失败，Lingxi 只测矩阵/CRUD。
- **修复**：对 Keyword/Lingxi 各加：第 N 个 chunk 抛错、扩维失败、read 失败、DB 更新失败；断言飞书最终恢复、run failed、rollback_status、task last_error；Lingxi failed keyword 不得写 0；direct 失败必须有 run。

### T-05（P2）Client 测试断言过弱，不能发现请求契约回归
- **文件/函数**：`tests/test_keyword_client.py` 全部函数；Lingxi 没有等价 client 测试。
- **证据**：Keyword tests mock `requests.post`，主要只根据返回 JSON 断言状态/一项字段，没有 `mock.call_args` 断言 URL `vSellerId`、headers Cookie/Origin、payload `startDate/endDate/timeUnit/columns/filters`；Lingxi search payload、Cookie header、HTTP 401/429/902 均未测。
- **修复**：增加请求契约 fixture；断言所有关键字段且 Cookie 只用哨兵值不输出；按 HTTP/业务 code 覆盖 auth/429/5xx/坏 JSON/错误数据类型；验证调用次数与重试上限。

### T-06（P2）重复测试目录没有明确职责，pytest 配置没有质量门槛
- **文件**：`pytest.ini`、`pyproject.toml`、根 `tests/test_web_ui.py`、`sync_console/tests/test_ui_routing_cache.py`、`test_api_auth.py`、`sync_console/tests/test_api.py`。
- **证据**：`pytest.ini` 与 `pyproject.toml` 同时声明 `pythonpath`、`testpaths`、收集规则；pytest.ini 另加 `-v`，没有 markers/timeout；两个 UI 测试都验证路由 200，两个 API 测试都验证 auth/settings。
- **修复**：保留单一 pytest 配置；定义 `unit/integration/e2e` markers、默认 timeout 和覆盖率门槛；合并重复路由测试；明确 root app 与 standalone app 的边界；CI 分开执行真实浏览器/外部 provider 套件。

### T-07（P2）生产库污染保护只看文件大小
- **文件/函数**：`tests/conftest.py:guard_production_database`。
- **证据**：记录 `(st_mtime, st_size)`，结束时只比较 `curr_size == init_size`；同尺寸 UPDATE/DELETE、WAL sidecar、已有文件内容变化均可能漏检。
- **修复**：测试前后导出表行/hash，或确保所有连接都指向临时 DB；把 WAL/SHM 和 Lingxi DB 纳入保护；不要依赖“文件大小不变”作为零污染证明。

### T-08（P2）关键输入边界未测
- **缺失项**：Keyword 搜索空列表/5000+词、`max_workers<=0`、超过 90 天/future/重复日期；Lingxi `page=0/page_size=0/负数`、100+词、空/重复词、非法 RRULE、空 sheet、重复日期、失败 fetch；两套 Cookie 超长/Unicode/并发更新/文件坏 JSON。
- **修复**：把 Pydantic 约束和 engine 约束各自测试；对外 API 断言 400/401/409/422/500 的稳定错误结构，避免只测“不是 404”。

---

## 六、两套服务重复代码及可抽取公共部分

重复不是仅“文件名相似”，而是下列函数级别的职责重复且目前行为已分叉：

1. **凭据读取/OSS 同步/落盘**：`keyword_service.client.sync_token_from_oss/load_token` 与 `lingxi_service.client.sync_token_from_oss/load_token`。可抽出 `core.credentials.TokenStore`：候选源、schema 校验、原子写、0600、锁、轮换、来源审计；provider 只提供 parser/默认 headers。
2. **并发关键词批处理**：`keyword_service.client.fetch_keywords_insight` 内 `run_batch` 与 `lingxi_service.client.fetch_lingxi_keywords` 的 `ThreadPoolExecutor/as_completed`。可抽出 `core.providers.parallel_fetch`：去重、输入顺序、最大线程、限流、异常收集、一次认证刷新、重试策略。
3. **任务 lease**：两套 `run_keyword_task/run_lingxi_task` 都是查任务→`acquire_task_lease`→插入 running run→外部读取/写入→更新 success/failed→finally release。可抽出 `core.sync_runner.TaskRunGuard`，要求 fencing token、owner 校验、续租、统一 run 状态。
4. **飞书矩阵写入/扩维/chunk**：`keyword_service.sync_engine.write_matrix_to_sheet` 与 `lingxi_service.sync_engine.write_matrix_to_sheet`。可抽出 `core.feishu_matrix.write_matrix`：行列校验、上限、扩维失败即停、staging/backup、chunk checkpoint、回滚；服务仅负责 matrix builder。
5. **飞书建表/direct flow**：两套 `direct_create_feishu_sheet` 都是 fetch→build matrix→create spreadsheet→get first sheet→write→设置公开权限→返回 metadata。可抽出公共 orchestration，并以 provider-specific `build_matrix` 与权限策略注入；同时统一 run 记录。
6. **任务关键词增删**：`keyword_service.sync_engine.append_keywords_to_task/remove_keywords_from_task` 与 Lingxi 同名函数。可抽出 JSON keyword set repository，统一 strip、去重、removed 集合互斥、事务和 rowcount。
7. **任务路由 CRUD/运行列表**：两个 router 都有 `/tasks`、append/remove/run_now/toggle/delete、`/runs`；可抽出带 schema/分页/鉴权的通用路由 helper，但必须保留 provider-specific DB 表和权限策略。
8. **DB wrapper/migrations**：两份 `db.py` 几乎相同；可抽出 `get_service_db(module)`，统一 close/context、迁移、路径和测试 fixture。

抽取时不要把当前问题“统一复制”：先把认证、TokenStore、lease、写入事务和错误模型修好，再复用；否则会把漏洞同步到两套服务。

---

## 七、建议的修复顺序

1. 立即撤销并轮换公开 Lingxi Cookie；删除 token 文件/历史；检查同一 Cookie 是否用于其他环境。
2. 恢复 Lingxi 全路由认证，给 Keyword tasks/runs 加认证；将 auth 默认改为 deny；加入匿名回归测试。
3. 暂停自动公开编辑飞书表；先修 direct/task 的 strict 失败语义，禁止 failed keyword 写 0。
4. 实现 TokenStore 原子安全落盘/Secret Manager，删除 Windows fallback 和硬编码 vSeller 默认值。
5. 实现 fencing lease + owner-safe release；增加过期并发测试。
6. 引擎层实现飞书 staging/备份/回滚、维度失败即停和行列限额；统一 run 记录。
7. 修正 Lingxi append/overwrite、removed/date/timezone、分页边界和物理删除审计问题。
8. 统一两套公共代码并增加真实请求契约（只用假 Cookie）；将 Playwright/外部服务测试拆到显式 integration/e2e CI。


---
# 附录 C：前端
# JFJLL/automation frontend 逐文件代码审查

- **范围**：`master` 分支（审查时按仓库给出的 frontend tree SHA `193ad3131f11babb173065817c673ff7265f2c2d` 对照；源码链接使用 master 路径）。
- **方法**：逐个读取列出的 TS/TSX、入口与配置文件；对 `keyword.css`（约 45 KB）和 `original.css`（约 30 KB）做整体结构及重复/冲突检查。没有读取 `package-lock.json`（按要求），没有读取 397 KB 的 `sync_console/web/lucide.min.js`（按要求）。
- **严重度**：P0=立即阻断/可直接导致重大安全或数据事故；P1=高风险，应尽快修复；P2=中风险/质量与可用性问题；P3=低风险/维护性问题。

## 结论摘要

代码整体是可读的 React + React Query 页面集合，但仍像从两个旧版控制台迁移、复制而来的工作台：API 层没有统一的运行时类型和认证失败处理；设置页把服务端返回的 token/webhook 状态数据带入浏览器并直接展示 token；关键任务创建/追加操作缺少客户端校验和重复提交保护；关键词和灵犀任务页几乎逐字复制；大量页面以 `any` 承接外部 API；测试只断言常量，不测试实际渲染、请求、错误或表单。建议先处理 P1（API/敏感配置/任务一致性），再做抽象和样式清理。

## 高优先级问题

### P1-1：API client 没有明确 base URL，也没有 401/会话失效处理；Cookie 鉴权的写操作没有可见的 CSRF 防护

- **文件/位置**：[`src/shared/api/client.ts`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/api/client.ts) `fetchJson`，约 11–39 行；[`vite.config.ts`](https://github.com/JFJLL/automation/blob/master/frontend/vite.config.ts) `server.proxy`，约 12–18 行。
- **证据**：所有请求都直接使用相对路径（如 `fetchJson('/api/tasks')`），client 固定 `credentials: 'same-origin'`；client 对所有非 2xx 统一抛 `ApiError`，但没有对 401 跳转登录/清理会话/广播认证失效。生产代理只写在 Vite dev server：`target: 'http://127.0.0.1:8088'`，没有 `VITE_API_BASE_URL` 或部署时的 API 配置。POST/DELETE 也只是依赖浏览器自动带同源 Cookie，没有 CSRF token/header。
- **风险**：静态前端若与 API 不在同一 origin，生产请求会打到错误主机；Cookie 过期时所有页面只进入 query/mutation error，用户看不到登录失效原因。若后端使用 Cookie 会话且没有 SameSite/CSRF 双重校验，跨站表单可能触发创建、删除、改 Cookie 等写操作。
- **修复**：封装 `API_BASE_URL`（生产从环境变量注入，开发代理作为默认值），统一处理 `401`（清理缓存并跳转登录/显示会话失效），写操作携带服务端下发的 CSRF token，并在后端校验 Origin/CSRF；区分网络错误、超时、业务错误并保留 request id。不要仅靠前端判断权限。

### P1-2：Settings 把共享文件夹 token 直接渲染，且把 notification_webhook 一并拉到浏览器；Cookie 是普通明文输入

- **文件/位置**：[`src/features/settings/pages/SettingsPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/settings/pages/SettingsPage.tsx) `settings` query 与共享云盘卡片，约 10–28、71–94 行；Cookie 表单约 113–158 行。
- **证据**：query 类型包含 `shared_folder_token`、`notification_webhook`，随后 JSX 直接输出 `{settings?.shared_folder_token || ...}`；Cookie 使用 `<input>` 而不是 password 控件，状态请求虽只返回 `configured/v_seller_id/cookie_length`，更新请求仍把 `cookieInput` 明文放入 JSON。
- **风险**：token、webhook 等凭据进入 React state、浏览器开发者工具、React DevTools、网络响应和潜在截图/日志；共享 token 在页面上直接暴露给所有能打开该路由的用户。当前 UI 没有权限判断，路由还把 `/admin` 重定向到 `/settings`，不能把“需要管理员”注释当作授权。
- **修复**：后端按字段最小化返回：页面只拿脱敏后的 `configured/last4/updated_at`；token 与 webhook 永不返回前端，创建/使用操作由后端完成。若必须输入 Cookie，使用 `type=password`、禁用复制/自动填充（视安全策略）、服务端加密保存并限制日志；Settings 路由必须配合后端 RBAC。删除写死的默认 `sellerIdInput = '628b3a5056228a000189c0e4'`，改为空值并由后端提供脱敏值或显式配置。

### P1-3：灵犀任务创建是“先建表、再建任务”的不可回滚两步操作

- **文件/位置**：[`src/features/lingxi/pages/LingxiInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/pages/LingxiInsightPage.tsx) `createTaskMutation.mutationFn`，约 53–79 行。
- **证据**：先 POST `/api/lingxi/feishu/direct_create`，取 `sheetRes.data.spreadsheet_token/url`，再 POST `/api/lingxi/tasks`；第二步失败时没有删除第一步生成的表，也没有保存 orphan token 或允许恢复绑定的流程。
- **风险**：网络重试、用户重复点击、后端部分失败会留下无法管理的飞书表；用户看到“创建失败”后重试，可能形成多个底表。表格创建成功但任务失败时还可能产生权限/数据残留。
- **修复**：优先提供后端一个原子 `create_task_with_sheet` 事务/补偿接口；至少给 mutation 一个 idempotency key，失败时由后端执行补偿删除或登记 orphan，前端展示明确的“表格已创建、任务绑定失败”状态。成功后同时失效 `lingxiTasks` 和 `lingxiRuns`（目前只失效任务）。

### P1-4：敏感操作和任务操作可重复提交，页面没有按 mutation 状态禁用按钮

- **文件/位置**：[`src/features/sync/pages/TasksPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/pages/TasksPage.tsx) 任务行操作，约 50–116 行；[`src/features/keywords/pages/KeywordTasksPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordTasksPage.tsx) 与 [`src/features/lingxi/pages/LingxiTasksPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/pages/LingxiTasksPage.tsx) 同类操作；创建/查询按钮在各 Insight 页。
- **证据**：`runNowMutation.mutate(t.id)`、`toggleMutation.mutate(t.id)`、`deleteMutation.mutate(...)` 直接挂在按钮回调上，未按 task id 检查 `isPending`，也没有 mutation scope/idempotency。加词默认发送 `{ sync_now: true }`，用户双击可能触发两次同步。
- **风险**：重复 run、重复追加、重复建表/建任务，尤其是异步同步和飞书写入可能造成重复数据或并发覆盖。
- **修复**：为每个动作提供按 task id 的 pending 集合，按钮使用 `disabled`；服务端所有写接口支持幂等键/去重；mutation 只在成功后失效相关 query，处理中明确提示。

### P1-5：任务与关键词表单没有真正的客户端验证，失败关键词只是警告而非阻止

- **文件/位置**：[`src/features/keywords/pages/KeywordInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordInsightPage.tsx) 搜索、直接建表和 `createTaskMutation`，约 165–260 行及表单 JSX；[`CreateKeywordTaskDialog.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/CreateKeywordTaskDialog.tsx) 约 26–94 行；[`CreateLingxiTaskDialog.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/components/CreateLingxiTaskDialog.tsx) 约 20–75 行；[`DirectSheetDialog.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/DirectSheetDialog.tsx) 约 20–82 行。
- **证据**：对话框只显示 `hasFailedKeywords` 提示，确认按钮仍调用 `onSubmit`；任务名、表格标题、RRULE 没有 `required`/长度/语法校验；`selectedWords` 可为空或无限增长。追加/减词对话框中，空输入会得到 `[]`，仍可 `appendMutation.mutate`/`removeMutation.mutate`。Search 的 `onSubmit` 只判断 `selectedWords.length > 0`，没有关键词数量、单词长度或总请求大小上限。
- **风险**：生成空表、创建无效调度任务、超大请求拖垮 API；失败词可能按用户提示“先清理”但实际仍能创建，形成脏数据。前端校验不能替代后端，但必须给出即时反馈。
- **修复**：共享 schema（例如 zod 或手写纯函数）校验：1–N 个关键词、去空白/去重、单词长度和总数上限；任务名/title 长度与字符限制；RRULE 解析并限制频率/时区/时间；日期非空、`start <= end`、不超过 90 天且不超过服务端业务上限；失败词存在时禁用确认或改为显式“仍然创建”二次确认。所有规则后端重复校验。

## React Query、并发和数据一致性

### P2-1：所有列表只手动刷新，没有运行中轮询；错误状态被静默当成空列表

- **文件/位置**：[`src/app/queryClient.ts`](https://github.com/JFJLL/automation/blob/master/frontend/src/app/queryClient.ts)；[`TasksPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/pages/TasksPage.tsx)、[`RunsPage.tsx`](https://github.com/JFJLL/automation/master/frontend/src/features/sync/pages/RunsPage.tsx)、关键词/灵犀同名页面；[`src/app/AppShell.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/app/AppShell.tsx) 三个徽标 query。
- **证据**：全局只有 `staleTime: 30 * 1000`、`refetchOnWindowFocus: false`、`retry: 1`，没有 `refetchInterval`。页面只读取 `isLoading` 和 `data = []`；没有 `isError/error` 分支。运行任务期间用户需要手动点刷新，接口失败也可能显示“暂无任务/暂无记录”。
- **修复**：运行记录/任务列表根据服务端状态采用 3–10 秒轮询，在 `running` 不存在时停止；只对幂等 GET 重试，401 不重试；区分加载、空、错误三态并提供重试按钮。徽标 query 可以按当前 section `enabled`，避免每个路由同时请求三个列表。

### P2-2：请求结果没有按输入版本绑定，旧搜索结果会在新输入/新请求期间继续展示

- **文件/位置**：[`KeywordInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordInsightPage.tsx) `queryResult = searchMutation.data` 与结果卡片，约 350 行、渲染约 600 行；[`LingxiInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/pages/LingxiInsightPage.tsx) 同样使用 `searchMutation.data?.data`。
- **证据**：选词、日期变化不会清空 mutation data；输入新条件后，旧 `searchMutation.data` 仍用于表格、复制、建表按钮。若用户在 pending 时修改选择，结果卡片的文案使用新 `selectedWords`，数据对象仍是旧请求。
- **修复**：将查询条件放进 `useQuery` key（如 `['keywordSearch', normalizedWords, start, end]`）或维护 request id/提交快照；pending 时隐藏/标注旧结果；建表必须使用结果快照而不是当前可变 state；用 AbortSignal/后端 request id 处理竞态。

### P2-3：API 响应基本全部用 `any`，外部数据字段未做运行时校验

- **文件/位置**：AppShell 的 `useQuery<any[]>`；Tasks 页 `any[]`、mutation `res:any/err:any`；结果表 `Record<string, Record<string, any>|null>`；ImportPage 的 `File`、sheet、preview rows；Settings 的响应只写静态 TS 类型但仍直接信任 JSON；Lingxi 推荐词 `Object.values(...).forEach((r:any)=>...)`。
- **证据**：例如 [`src/features/sync/pages/ImportPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/pages/ImportPage.tsx) 多处 `useState<any[]>` / `previewMutation.data?.rows`，[`KeywordResultTable.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/KeywordResultTable.tsx) 将 `data` 数字字段直接 `Number(...)`；fetchJson 返回的 JSON 没有 schema parse。
- **风险**：后端字段缺失或类型改变时，渲染可能抛异常（例如 `recommendedKeywords` 中 `rw.keyword` 缺失后传入 `handleAddWord().trim()`）；错误信息/日期/数字的异常值也会悄悄显示。
- **修复**：为每个 endpoint 定义 `Task/Run/SearchResult/Sheet/Settings` 类型，使用 zod/valibot 或等价解析；`fetchJson<T>` 只解决编译期类型，不是运行时验证。错误统一为 `unknown` 后用 type guard 读取 message。

### P2-4：日期和 RRULE 规则多套实现且格式不一致

- **文件/位置**：[`KeywordInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordInsightPage.tsx) `validateAndSetDateRange`、`handlePresetDays`，约 285–350 行；[`src/shared/utils/formatRrule.ts`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/utils/formatRrule.ts)；[`ImportPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/pages/ImportPage.tsx) 初始 RRULE，约 24 行；各创建对话框。
- **证据**：ImportPage 默认值为 `RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0`，关键词/灵犀页面传 `FREQ=DAILY;...`（无前缀）；`formatRruleText` 可以去掉前缀，但没有实际 RRULE 解析/校验。日期代码用 `new Date('YYYY-MM-DD')`、本地 `setDate` 与 `toISOString()` 混用；`maxEndDate` 在业务时间 query 尚未返回时硬编码为 `'2026-09-29'`，而 `is_after_noon` 没有参与校验，只在 UI 写死提示。
- **风险**：不同浏览器/时区可能出现边界日期偏移；业务日期变化时初始请求可能指向硬编码未来日期；后端若只接受一种 RRULE 规范，任务创建会失败或被错误解释。
- **修复**：统一一个 `DateRange`/RRULE 模块，以本地日历日期（不要无意中转 UTC）计算；业务时间接口加载前禁用搜索和任务创建；以结构化 `rrule` builder 生成值，服务端返回规范化值，显示层只负责格式化。测试 T-2/T-1、夏令时、90 天边界和无前缀/有前缀输入。

## 安全、XSS、可访问性

### P2-5：当前没有发现 `dangerouslySetInnerHTML`，React 文本插值本身会转义；但外链与错误内容仍应做协议/属性约束

- **文件/位置**：结果表、Runs/Tasks 页、PreviewPanel、Settings 页各处把服务端字符串作为 `{value}` 输出；例如 [`KeywordResultTable.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/KeywordResultTable.tsx) 行约 56–130。
- **证据**：审查的 TSX 中未见 `dangerouslySetInnerHTML` 或 `innerHTML`；错误详情、关键词、sheet 单元格都通过 React child 渲染，默认不会执行 HTML。`DirectSheetDialog`、Tasks/Runs 页会把后端 URL 放到 `<a href>`（对 URL 只做了 `startsWith('https://')` 的有限检查，关键词页内联链接还没有统一的 URL helper）。
- **风险/修复**：当前主要 XSS 路径已被 React 转义保护，但仍应在后端和前端 URL helper 中只允许 `https:`，拒绝 `javascript:`/控制字符，并对新窗口链接加 `rel="noopener noreferrer"`。不要为“修复样式”引入 HTML 拼接；错误详情应限制长度并避免把敏感响应原样 toast。

### P2-6：Dialog、Toast、可点击卡片和自定义选择控件的无障碍语义不足

- **文件/位置**：[`src/shared/components/Dialog.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/components/Dialog.tsx) 全组件；[`Toast.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/components/Toast.tsx) `ToastProvider`；[`PlatformSelector.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/components/PlatformSelector.tsx)、[`SheetSelector.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/components/SheetSelector.tsx)、[`KeywordLibrary.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/KeywordLibrary.tsx)。
- **证据**：Dialog 只是固定层 + backdrop click，没有 `role="dialog"/aria-modal`、标题关联、Escape 关闭、焦点移入/恢复或 focus trap。Toast 无 `aria-live`/role=status；许多选择项用 `<div onClick>`（平台卡片、工作表、关键词 chip），键盘用户不能操作。Pagination 按钮只改 cursor/opacity，没有实际 `disabled` 属性；`onClick={() => onPageChange(page - 1)}` 在第一页仍会触发。
- **修复**：Dialog 使用原生 `<dialog>` 或完整 WAI-ARIA dialog；给所有操作元素用 button/input，补键盘 Enter/Space、焦点样式、aria-pressed/checked/label。Toast 使用 `role=status/alert` 与 `aria-live`; Pagination 真正设置 `disabled` 并在回调层再次 clamp。

### P2-7：全局 Toast 的定时器没有清理，且随机短 ID 不是可靠唯一键

- **文件/位置**：[`src/shared/components/Toast.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/components/Toast.tsx) `showToast`，约 26–33 行。
- **证据**：每次 `showToast` 都 `setTimeout(() => removeToast(id), 3500)`，Provider 卸载时没有保存/清理 timer；ID 为 `Math.random().toString(36).substring(2, 9)`。
- **风险**：页面测试、热更新或 Provider 卸载后仍执行状态更新；低概率 ID 碰撞会同时删除错误 toast。普通用户风险低，但容易造成 flaky test。
- **修复**：`useRef<Set<number>>` 管理 timer，在 cleanup 中清理；使用递增计数器或 `crypto.randomUUID()`；为消息做长度上限和敏感字段脱敏。

## 任务/页面逻辑和重复代码

### P2-8：KeywordTasksPage 与 LingxiTasksPage 是逐段复制，业务差异只剩 endpoint/文案

- **文件/位置**：[`KeywordTasksPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordTasksPage.tsx) 与 [`LingxiTasksPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/pages/LingxiTasksPage.tsx)，两者各 14,696 bytes；`useQuery`、5 个 mutation、追加/移除/删除 Dialog、表格列结构全部相同。
- **证据**：两文件从 `appendModalTaskId`、`appendWordsInput`、`removeWordSelect` 状态，到 `runNow/toggle/append/remove/deleteMutation` 的 onSuccess/onError，再到列表和三个 Dialog 结构逐段一致；区别主要是 `/api/keyword` vs `/api/lingxi` 和标题。
- **修复/拆分**：抽出 `useKeywordTaskActions({kind, basePath})`、`TaskTable`、`AppendKeywordsDialog`、`RemoveKeywordsDialog`、`DeleteTaskDialog`、`TaskStatusCell`；以泛型 `TaskBase` + feature adapter 注入列差异（关键词页有 update_mode，灵犀页可能不需要）。同理抽出 `RunsTable`/`usePaginatedRuns`；保留每个 feature 只负责 endpoint 和文案。

### P2-9：Keyword Insight/ Lingxi Insight 重复搜索、选词、复制、建表流程，但没有共享 hook；大组件难以测试

- **文件/位置**：[`KeywordInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordInsightPage.tsx)（39,460 bytes）；[`LingxiInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/pages/LingxiInsightPage.tsx)；[`KeywordSearchBar.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/KeywordSearchBar.tsx)、[`KeywordResultTable.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/KeywordResultTable.tsx)、[`DirectSheetDialog.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/DirectSheetDialog.tsx)。
- **证据**：两个 Insight 都维护 `inputWord/selectedWords/directSheetOpen/taskModalOpen/taskName`，都 POST search/direct_create/tasks，处理失败词和复制 TSV；KeywordInsight 自己又内嵌搜索栏、结果表、两个 Dialog，虽已有抽出的组件却没有复用 `KeywordSearchBar/KeywordResultTable/DirectSheetDialog`。Lingxi 甚至 import 复用 `DirectSheetDialog`，形成不一致。
- **修复/拆分**：建议 `useKeywordSelection`（normalize/dedupe/max）、`useDateRange`、`useInsightSearch`（提交快照/取消）、`ResultToolbar`、`InsightResultTable`、`CreateSheetDialog`、`CreateScheduledTaskDialog`；feature adapter 只提供 metric columns、日期模式、endpoint 与文案。把 DOM 拖拽选择拆成 `useBoxSelection`，避免页面直接操作 DOM。

### P2-10：关键副作用和浏览器 API 没有考虑卸载/兼容失败

- **文件/位置**：[`KeywordInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordInsightPage.tsx) 拖拽 `useEffect`、`handleCopyTableData`；[`LingxiInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/pages/LingxiInsightPage.tsx) `handleCopyTable`；[`KeywordLibrary.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/KeywordLibrary.tsx) pointer handlers。
- **证据**：复制成功后 `setTimeout(() => setCopied(false), 2000)` 没有 cleanup；Clipboard API 直接调用 `navigator.clipboard.writeText(...).then(...).catch(...)`，在不安全上下文/旧浏览器中 `navigator.clipboard` 可能不存在，访问 `.writeText` 会在 `.catch` 链之前同步抛错。拖拽逻辑依赖 `window` 全局 mouse listener 和直接改 DOM style/class，难以覆盖触摸/键盘和卸载竞态。
- **修复**：封装 `useClipboard`，先 feature detect，必要时提供 textarea fallback；所有 timeout/listener/AbortController 在 cleanup 中处理；优先 Pointer Events + React state，或使用经过测试的选择组件。

## 组件、类型、构建配置

### P3-1：共享 UI 组件存在重复样式系统，两个 30–45 KB 全局 CSS 相互覆盖

- **文件/位置**：[`src/main.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/main.tsx) 导入顺序（约 5–6 行）；[`styles/original.css`](https://github.com/JFJLL/automation/blob/master/frontend/src/styles/original.css)；[`styles/keyword.css`](https://github.com/JFJLL/automation/master/frontend/src/styles/keyword.css)；[`styles/tokens.css`](https://github.com/JFJLL/automation/blob/master/frontend/src/styles/tokens.css)。
- **证据**：main 先导入 `original.css` 再导入 `keyword.css`；两文件都定义 `:root`、`*`、`body`、`.header`、`.container`、`.card`、`.btn`、表格、badge、modal 等。keyword.css 后定义的 `--primary/#ef2b3a`、body 背景和 `.header/.container` 会覆盖 original 的相同选择器；同一文件后半段也再次重定义 body/header/container。`tokens.css` 虽有设计 token，却没有在 main 中导入。
- **风险**：修改任意页面样式会受导入顺序和文件后半段影响；线上 CSS 体积和死规则增加，组件内联 style 又进一步分裂主题。
- **修复**：删掉旧版 CSS 或将 legacy 样式隔离为 `.legacy-console`；只保留 tokens + feature scoped CSS，避免全局 `body/.card/.btn`；将 inline style 迁移到统一 Button/Form/Table 组件。

### P3-2：构建配置和依赖版本缺少可重复性/大页面拆包

- **文件/位置**：[`package.json`](https://github.com/JFJLL/automation/blob/master/frontend/package.json)；[`tsconfig.json`](https://github.com/JFJLL/automation/blob/master/frontend/tsconfig.json)；[`vite.config.ts`](https://github.com/JFJLL/automation/blob/master/frontend/vite.config.ts)；[`src/app/router.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/app/router.tsx)。
- **证据**：package 使用 `^` 范围（React、React Query、lucide-react、Vite、TypeScript、Vitest），虽有 lock 文件但本审查按要求未读取/验证 lock；router 静态 import 所有页面，包含约 39 KB 的 KeywordInsightPage 和约 21 KB ImportPage，首屏会把所有 feature 打入初始 chunk。tsconfig `skipLibCheck: true`、`noUnusedLocals/noUnusedParameters: false` 会隐藏一部分质量信号；vite proxy 只覆盖本地 `127.0.0.1:8088`。
- **修复**：CI 使用 lockfile install 并定期升级、在应用层固定经验证的版本；路由用 `React.lazy`/`Suspense` 拆分 feature；开启 unused checks（逐步清理）、保留 `skipLibCheck` 但不要把它当作应用类型安全；配置生产 API、source map 和 bundle budget。`lucide-react` 应作为 React 图标唯一来源，不需要另加载旧 UMD 图标库。

### P3-3：`sync_console/web/lucide.min.js` 对当前 React 前端没有必要，应由构建链移除

- **文件/位置**：仓库目录 [`sync_console/web`](https://github.com/JFJLL/automation/tree/master/sync_console/web)；其 `lucide.min.js` 文件大小 397,450 bytes；当前 React 代码在 [`package.json`](https://github.com/JFJLL/automation/blob/master/frontend/package.json) 依赖 `lucide-react`，各组件从 `lucide-react` import 图标。
- **证据**：web 目录索引只显示 favicon、assets 与 `lucide.min.js`；frontend 源码统一使用 `lucide-react`，没有任何源码 import `/lucide.min.js` 或调用全局 `lucide`。`frontend/public/assets` 与 `frontend/public/static/assets` 共享同一 Git tree SHA `ccca75...`，其中三张 platform PNG 的 blob SHA 相同，属于重复路径。
- **修复**：确认旧 server-rendered 控制台仍无引用后删除 `sync_console/web/lucide.min.js`；React 构建只保留按需打包的 lucide-react 图标。对 `public/static/assets` 与 `public/assets` 做一次部署引用搜索，保留单一路径并调整 URL；不要直接删除仍被旧后端模板引用的路径。

## 各文件逐项观察

### 入口、应用壳和路由

- [`src/main.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/main.tsx)：正确使用 `createRoot` 和 `StrictMode`，但 root 缺失时静默不渲染；可在启动失败时抛出明确错误。两个全局 CSS 导入顺序产生冲突（P3-1）。
- [`src/app/App.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/app/App.tsx)：Provider 层次合理（QueryClient → Toast → Router）；没有 error boundary，渲染异常会白屏，建议增加路由级 errorElement 和全局 ErrorBoundary。
- [`src/app/AppShell.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/app/AppShell.tsx)：全局同时查询三类任务并以 `array.length` 做徽标；缺少分页总数语义、错误态及 section gating；帮助 Drawer 无 Escape/focus trap/aria。文本输出没有 innerHTML，React 会转义。
- [`src/app/queryClient.ts`](https://github.com/JFJLL/automation/blob/master/frontend/src/app/queryClient.ts)：30 秒 stale、禁止 focus refetch、retry 1 的默认值过于粗糙；没有按错误类型决定 retry，没有 query cache 错误监听、轮询或持久化策略。
- [`src/app/router.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/app/router.tsx)：路径覆盖 import/tasks/runs/keyword/lingxi/settings；`/admin` 仅 Navigate 到 settings，不是权限控制；所有页面同步 import，建议 lazy；缺少 route errorElement。

### Keywords 功能

- [`features/keywords/components/CreateKeywordTaskDialog.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/CreateKeywordTaskDialog.tsx)：展示失败词告警但不阻止提交；任务名和 RRULE 无校验；更新模式、RRULE 选项应使用共享常量/结构化类型。
- [`DirectSheetDialog.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/DirectSheetDialog.tsx)：HTTPS 前缀检查优于直接信任 href，但应统一 URL helper；标题空值、失败词只是提示；可抽为通用表格创建对话框。
- [`KeywordLibrary.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/KeywordLibrary.tsx)：localStorage 读取未保护（隐私模式/禁用存储可能抛异常）；拖拽/框选是 DOM 查询与 pointer 状态混合，缺少键盘等效操作；分类数组硬编码，未由 API 元数据驱动。
- [`KeywordResultTable.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/KeywordResultTable.tsx)：表格宽度随日期增长，缺少 `caption`/scope/小屏方案；数字直接渲染 any；失败项显示 `-` 的策略合理，仍需 schema 与格式化函数；重试按钮只由父页提供，组件自身无法表达 retry pending 粒度。
- [`KeywordSearchBar.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/components/KeywordSearchBar.tsx)：输入与 chip 基本可用，但日期变更完全委托父层；清除按钮/移除按钮的 aria 基本存在，日期 input 应有明确 label/id 关联；`isSearching` 应真正传给 Button 的 loading/disabled。
- [`KeywordInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordInsightPage.tsx)：39 KB 单组件同时负责日期、词库、DOM 框选、搜索、复制、表格、建表、建任务；重复实现抽出的 KeywordSearchBar/KeywordResultTable/Dialog；见 P1-5、P2-2、P2-4、P2-9、P2-10。直接建表结果读取 `directCreateMutation.data?.spreadsheet_url`，而 Lingxi/通用对话框使用 `data.data.spreadsheet_url`；若两个 endpoint 响应 envelope 一致，关键词页成功链接不会显示，需核对 API schema。
- [`KeywordTasksPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordTasksPage.tsx)：操作 mutation 未按行禁用；追加/减词空数组、无上限；状态/keywords/tasks 全是 any；与 Lingxi 页逐段重复（P2-8）。
- [`KeywordRunsPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/keywords/pages/KeywordRunsPage.tsx)：分页 query key 正确包含 page，错误态、轮询、类型和 URL 协议约束不足；`error_detail` React 文本插值不会执行 HTML。

### Lingxi 功能

- [`CreateLingxiTaskDialog.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/components/CreateLingxiTaskDialog.tsx)：与关键词创建对话框重复；只有文案/RRULE 选项不同；失败词告警不阻止提交，名称/RRULE/关键词数无验证。
- [`LingxiInsightPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/pages/LingxiInsightPage.tsx)：推荐词来自 `any`，缺少字段保护；创建任务两步不可回滚（P1-3）；Clipboard API 兼容性差；查询结果/当前选词没有快照绑定（P2-2）。
- [`LingxiTasksPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/pages/LingxiTasksPage.tsx)：与 KeywordTasksPage 几乎完全复制，且相同操作校验/并发/错误态问题。
- [`LingxiRunsPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/lingxi/pages/LingxiRunsPage.tsx)：分页 key 正确，但没有轮询/错误态/强类型；相比 Keyword Runs 去掉 days 列应通过共享列配置实现，而不是复制整页。

### Sync 功能

- [`features/sync/components/PlatformSelector.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/components/PlatformSelector.tsx)：平台卡片是可点击 div，disabled 主要靠样式；需要 button/aria-pressed；子账号 ID/name 应是受 schema 验证的 API 数据。
- [`PreviewPanel.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/components/PreviewPanel.tsx)：错误数组用 `join('; ')` 直接展示会形成很长文本；表格缺少空数据/行列 schema/可访问表头细节；`isLoading` 应绑定按钮 loading/disabled。
- [`SheetSelector.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/components/SheetSelector.tsx)：可点击容器不支持键盘；平台不匹配只警告仍可选择；`sheets:any[]`；需用 checkbox/listbox 语义并在创建前阻止 mismatch。
- [`ImportPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/pages/ImportPage.tsx)：21 KB 单组件负责上传、平台、子账号、分析、预览、任务创建；文件类型/大小只在文案中说明，没有客户端校验；`selectedSheetIndices` 初始 `[0]`，上传空 sheets 后状态可能保留无效索引；创建任务依赖 `previewMutation.data` 却不强制预览成功，`initial_rows` 可能回退 sample rows；切换平台后没有清空旧分析/预览结果，可能把旧平台数据提交到新平台；应拆成步骤状态机并使 preview/upload 按 platform/file 绑定。
- [`TasksPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/pages/TasksPage.tsx)：P2-1/P1-4；删除称“归档”但直接 DELETE，UI 语义必须与 API 明确一致；外链和任务字段需 schema。
- [`RunsPage.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/features/sync/pages/RunsPage.tsx)：运行状态没有轮询；按页 query key 正确；日期 substring 不是时区格式化，异常日期会显示错误；表格无可访问语义。

### Shared 组件与工具

- [`shared/api/client.ts`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/api/client.ts)：核心问题见 P1-1；优点是识别 FormData 后不覆盖 Content-Type，并将 JSON/文本错误统一为 ApiError，但应处理空响应、超时、401、CSRF、`unknown`。
- [`Badge.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/components/Badge.tsx)：状态表未覆盖 `pending/cancelled` 等常见状态，未知值直接显示原文；颜色仅通过 inline style，建议 role/status 文案和可访问对比度测试。
- [`Button.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/components/Button.tsx)：loading 只改内容/样式时应强制 `disabled` 并设置 `aria-busy`；组件没有默认 `type="button"`，一旦放入 `<form>` 会意外 submit；可抽 shared focus/size styles。
- [`Dialog.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/components/Dialog.tsx)：P2-6；backdrop 点击判定合理，但缺失 modal semantics/focus/escape/scroll lock。
- [`Pagination.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/components/Pagination.tsx)：P2-6；第一页/末页只是视觉 disabled，必须设置 `disabled`；总页数应 clamp，服务端 page 超界时要回退。
- [`Toast.tsx`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/components/Toast.tsx)：P2-6/P2-7；context API 清晰，但 timer cleanup、aria-live、消息脱敏缺失。
- [`formatRrule.ts`](https://github.com/JFJLL/automation/blob/master/frontend/src/shared/utils/formatRrule.ts)：只做字符串匹配/正则显示，不是 RRULE parser；未知 token 原文回显可能给用户错误的“可读频率”；与各页面输入常量应由一份 typed builder 生成。
- [`styles/tokens.css`](https://github.com/JFJLL/automation/blob/master/frontend/src/styles/tokens.css)：设计 token 定义清晰但 main 未导入，实际页面使用 keyword/original 自己的另一套变量；应成为唯一 token 入口。

## 测试覆盖

[`src/__tests__/app.test.ts`](https://github.com/JFJLL/automation/blob/master/frontend/src/__tests__/app.test.ts) 只有两个无业务价值的测试：`expect(true).toBe(true)`，以及对手写 `validPaths` 数组长度/内容断言。它没有 render `App`/router，没有 mock fetch，没有验证 401、错误态、表单边界、日期、RRULE、重复提交、任务 mutation、Dialog 可访问性或外链策略。建议至少补：

1. `fetchJson`：JSON/text/空 body、非 2xx、401、FormData、Abort/timeout、CSRF header。
2. 日期与 RRULE：90 天边界、空值、start>end、business time 前后、时区和规范化字符串。
3. 关键词 selection：逗号/空白/中文逗号、去重、最大数量、失败词阻止。
4. React Query 页面：MSW mock 成功/失败、mutation pending 防双击、invalidate key、running 轮询停止。
5. 组件无障碍：Dialog focus/escape、Pagination disabled、键盘选择平台/工作表、Toast live region。
6. `ImportPage`：切平台清空旧分析、文件类型大小、无预览不能创建、空 sheet。

## 已读文件清单

下列列出的源文件已按要求从 raw GitHub 内容逐文件读取；“完整”指 TS/TSX/配置/工具/测试源码完整读取；两个大 CSS 按要求只做整体浏览，不宣称逐行完整审查。`package-lock.json` 明确未读。

| 文件 | 状态 |
|---|---|
| `frontend/index.html` | 完整 |
| `frontend/package.json` | 完整 |
| `frontend/tsconfig.json` | 完整 |
| `frontend/vite.config.ts` | 完整 |
| `frontend/src/main.tsx` | 完整 |
| `frontend/src/app/App.tsx` | 完整 |
| `frontend/src/app/AppShell.tsx` | 完整 |
| `frontend/src/app/queryClient.ts` | 完整 |
| `frontend/src/app/router.tsx` | 完整 |
| `frontend/src/__tests__/app.test.ts` | 完整 |
| `frontend/src/features/keywords/components/CreateKeywordTaskDialog.tsx` | 完整 |
| `frontend/src/features/keywords/components/DirectSheetDialog.tsx` | 完整 |
| `frontend/src/features/keywords/components/KeywordLibrary.tsx` | 完整 |
| `frontend/src/features/keywords/components/KeywordResultTable.tsx` | 完整 |
| `frontend/src/features/keywords/components/KeywordSearchBar.tsx` | 完整 |
| `frontend/src/features/keywords/pages/KeywordInsightPage.tsx` | 完整 |
| `frontend/src/features/keywords/pages/KeywordRunsPage.tsx` | 完整 |
| `frontend/src/features/keywords/pages/KeywordTasksPage.tsx` | 完整 |
| `frontend/src/features/lingxi/components/CreateLingxiTaskDialog.tsx` | 完整 |
| `frontend/src/features/lingxi/pages/LingxiInsightPage.tsx` | 完整 |
| `frontend/src/features/lingxi/pages/LingxiRunsPage.tsx` | 完整 |
| `frontend/src/features/lingxi/pages/LingxiTasksPage.tsx` | 完整 |
| `frontend/src/features/settings/pages/SettingsPage.tsx` | 完整 |
| `frontend/src/features/sync/components/PlatformSelector.tsx` | 完整 |
| `frontend/src/features/sync/components/PreviewPanel.tsx` | 完整 |
| `frontend/src/features/sync/components/SheetSelector.tsx` | 完整 |
| `frontend/src/features/sync/pages/ImportPage.tsx` | 完整 |
| `frontend/src/features/sync/pages/RunsPage.tsx` | 完整 |
| `frontend/src/features/sync/pages/TasksPage.tsx` | 完整 |
| `frontend/src/shared/api/client.ts` | 完整 |
| `frontend/src/shared/components/Badge.tsx` | 完整 |
| `frontend/src/shared/components/Button.tsx` | 完整 |
| `frontend/src/shared/components/Dialog.tsx` | 完整 |
| `frontend/src/shared/components/Pagination.tsx` | 完整 |
| `frontend/src/shared/components/Toast.tsx` | 完整 |
| `frontend/src/shared/utils/formatRrule.ts` | 完整 |
| `frontend/src/styles/tokens.css` | 完整 |
| `frontend/src/styles/keyword.css` | 大致浏览（按要求） |
| `frontend/src/styles/original.css` | 大致浏览（按要求） |
| `sync_console/web/lucide.min.js` | 未读（按要求，仅评估是否需要） |
| `frontend/package-lock.json` | 未读（按要求） |


---
# 附录 D：feishu_three_sync 旧脚本
# `feishu_three_sync`（master）逐文件/逐函数代码审查

审查对象：[`JFJLL/automation`](https://github.com/JFJLL/automation/tree/master/feishu_three_sync)，`master`。读取入口采用 raw GitHub URL；淘宝 45–50KB 文件再请求了 GitHub Contents API，但工具输出在文件中段截断，详见“读取限制”。本文不重复任何凭据原值。

## 结论摘要（最重要的 10 条）

1. **P0：仓库确实把凭据/会话作为版本内容打包。** README 明示“账号凭据、飞书密钥及登录会话”；`manifest.sha256.json` 列出了 `jzt_sync/.env`、`jzt_sync/token.txt`、`taobao/.env`、`taobao/adstar.txt`、`jg_sync/session_headers.json`、`jg_sync/browser_state.json`。`jzt_sync/config_loader.py` 还有 app secret 回退值，`local_login.py` 有明文登录密码。应立即吊销/轮换并从历史移除，而不是只加 `.gitignore`。
2. **P0：`jg_sync/daily.py` 与 `jg_sync/refresh_session.py` 直接读取并持久化会话；** `session_headers.json` 中的 cookie 会被用于聚光报表接口，浏览器状态也会写回 `browser_state.json`。这不是“配置存在但未使用”，而是生产认证链路。
3. **P1：三个子项目在 Feishu 客户端、cookie 读取、日期/合并/回读、调度上重复实现。** `jzt_sync/daily_client.py`、`taobao/taobaoxinghe_feishu_order_effect.py`、`taobao/sync_configured_table.py` 与 `sync_console/platforms/{taobao,jzt,juguang}.py` 均各自实现请求、鉴权、分页和写入；修一个限流/重试/列映射 bug 不会自动覆盖其他入口。
4. **P1：JZT 实际不是“全表日期扫描”。** `daily_client.fetch_report()` 的 payload 固定 `dataCycle='30'`，没有 start/end 参数；`daily_sync.sync_one()` 之后虽然读取整个 sheet，却最多只能拿平台最近 30 日数据。旧数据缺口超过 30 日无法自动补齐。
5. **P1：JZT `--dry-run` 逻辑错误。** `daily.py` 只有在 `not args.dry_run` 时才把类别加入 `ready`，因此 dry-run 不执行预检同步、结果通常为失败/0 tasks，和 help 文案“Read/report only”不一致。
6. **P1：Juguang 也依赖 `msvcrt`，不是仅 JZT Windows 限制。** `jg_sync/daily.py` 导入 `msvcrt` 并使用 `msvcrt.locking`；在 Linux/macOS 直接 ImportError。两者还分别在 refresh 和 daily 之间加锁，refresh 阶段没有锁，可能并发操作同一 Chrome profile/会话文件。
7. **P1：Juguang 错列修复会丢历史人工/非管理字段。** `repair_misaligned_rows()` 的 `repair_headers` 只保留部分身份和指标，不包括跳转链接、单元/计划等字段；随后用空字符串填充未列入集合的列再整行写回。63 条无法匹配的行也只是插入空定向列，仍可能保留移位语义，需要专项人工复核。
8. **P1：Juguang 日期格式仍为未补零的 `YYYY/M/D`。** `format_date()` 直接 `f'{d.year}/{d.month}/{d.day}'`；这正是 README 已记录的已知问题。`sync_console/platforms/juguang.py` 也只写原始日期，没有统一格式校验。
9. **P1：淘宝与 JZT 的 API 读写错误处理不统一。** 淘宝 legacy scraper 对 HTTP 200 的 `success=false` 通常不统一拦截，分页依赖“短页”可能无限循环；JZT/淘宝 Feishu 客户端对 JSON 形状、重试边界和网络异常缺少统一处理。回读比较还普遍用 `zip`，旧行短于目标列时可被错误判定为一致。
10. **P1：计划任务依赖交互式登录。** JZT `refresh_login.py` 使用 `headless=False`，主体 Principal 为 `Interactive`；淘宝 CDP 登录和 Juguang Chrome profile 也要求桌面/人工验证码。锁屏、注销、无人值守服务器上会失败；PowerShell 只做 transcript/控制台告警，没有邮件、事件日志或任务失败通知。

## P0/P1 凭据与认证面

### P0-1 已提交敏感文件和硬编码回退

- **位置：** `feishu_three_sync/README.md`（开头）；`manifest.sha256.json` 中的 `.env`、`token.txt`、`adstar.txt`、`session_headers.json`、`browser_state.json` 条目；`jzt_sync/config_loader.py` `APP_ID/APP_SECRET`（约 8–10 行）；`jzt_sync/local_login.py` 模块常量（约 2–3 行）。
- **证据：** README 明确写“包含账号凭据、飞书密钥及登录会话”；manifest 明确列出敏感文件。`config_loader.py` 使用 `os.getenv(...) or` 的硬编码 app id/secret 兜底；`local_login.py` 以模块常量保存用户名/密码。
- **风险：** 即使当前 raw 端点对部分敏感文件拒绝返回，manifest、README、源码已经证明它们进入了打包清单；Git 历史和 fork/cache 均应视为泄露。`.gitignore` 只对未来提交有效。
- **修复：** 立即轮换飞书 secret、平台 cookie、JD 登录密码和相关会话；用环境变量/Windows Credential Manager/Secret Manager；启动时缺失配置直接失败，不设置真实默认值；从 Git 历史 purge，并检查所有 fork、构建产物、备份。将敏感文件改为只存在本机的模板（`.example`）。
- **参考：** [README](https://raw.githubusercontent.com/JFJLL/automation/master/feishu_three_sync/README.md)、[manifest](https://raw.githubusercontent.com/JFJLL/automation/master/feishu_three_sync/manifest.sha256.json)、[config_loader.py](https://raw.githubusercontent.com/JFJLL/automation/master/feishu_three_sync/jzt_sync/config_loader.py)、[local_login.py](https://raw.githubusercontent.com/JFJLL/automation/master/feishu_three_sync/jzt_sync/local_login.py)。

### P1-2 Juguang 会话文件被直接用于 API 请求

- **位置：** `jg_sync/daily.py` `ReportClient.__init__`（约 38–44 行）；`refresh_session.py` `refresh()`（约 10–47 行）。
- **证据：** `ReportClient` 从 `session_headers.json` 反序列化 headers 并 `self.session.headers.update(headers)`；`refresh()` 将浏览器 cookies 拼接回 `headers['cookie']`，然后原子替换文件并写 `browser_state.json`。
- **修复：** 会话文件权限限制到当前用户，永不进仓库；按域名和必需字段最小化 cookie；使用短期 token/secret store；日志禁止输出 header，轮换时记录指纹而非值；在 CI/pre-commit 做 secret scan。

### P1-3 JZT 浏览器登录硬编码账号且会把业务 cookie 写回 token 文件

- **位置：** `jzt_sync/refresh_login.py` `submit_login()`（约 34–39 行）、`save_cookie()`（约 20–31 行）、`refresh_in_context()`（约 45–90 行）。
- **证据：** `submit_login` 从 `local_login.USERNAME/PASSWORD` 填充页面；`merge_login_cookie()` 特意保留 `skpp_s/skpp_p`；`save_cookie()` 备份 `token.txt`，然后覆盖写回 cookie。此处没有文件权限、加密或版本泄露保护。
- **修复：** 去除自动填充密码，改人工/企业 SSO 或系统凭据；业务 cookie 迁移到 secret store；提交前阻断 `token.txt`；保存前校验响应归属和有效期；备份不要落在可能被同步的项目树。

## 逐项目详细发现

## A. `jg_sync`

### A-1 报表请求没有网络重试；分页有固定上限但没有可观测的预期校验（P1）

- **位置：** `jg_sync/daily.py` `ReportClient.fetch()`（约 50–87 行）。
- **证据：** 每页直接 `self.session.post(..., timeout=60)`；仅 `raise_for_status()` 和 JSON/schema/`totalCount` 检查，没有对连接重置、超时、429/5xx 进行退避重试。循环固定 `range(1,501)`，平台返回大于 500 页时会在最后 `Incomplete pagination`，但没有记录已读页/最后响应。
- **修复：** 只对连接错误、429、502/503/504 做有限指数退避并加 jitter；响应校验 success/code/data/page 的类型；把 page/total/page-size 写入结构化日志；超过上限立即失败且保留原表不写。

### A-2 日期输出不符合严格格式（P1，已知问题复现）

- **位置：** `jg_sync/daily.py` `format_date()`（约 29–31 行）；`date_value()`（约 23–27 行）。
- **证据：** `format_date` 返回 `f'{d.year}/{d.month}/{d.day}'`，一位月/日不补零；README 与 PROJECT 同时承认 `YYYY/M/D`。
- **修复：** 统一 `d.strftime('%Y/%m/%d')`，并在写入前对全量 source rows 做 schema/date invariant 检查；为历史 `YYYY/M/D` 建一次性迁移，不要让 dedupe 同时接受多个表示。

### A-3 错列修复函数的字段丢失风险（P1）

- **位置：** `jg_sync/daily.py` `repair_misaligned_rows()`（约 126–180 行）。
- **证据：** `repair_headers` 集合只列时间、定向、创意名称/ID、笔记 ID 及一组管理指标；没有 `笔记跳转链接`、`单元名称/ID`、`计划名称/ID` 等 `IDENTITY` 字段。`converted` 只对 repair_headers 转换，最终 `converted` row 用 `by_header.get(h, '')`，未列入字段被置为空；`repairs[i] = list(managed[:width])` 整行写回。
- **修复：** 修复应仅重排缺失的定向单元/管理指标，而不是由部分投影重构整行；先保存 row 的未管理列，按 header 名称合并；把“平台无历史源”标记为 unresolved，禁止自动覆盖原值；增加带非空 URL/计划字段的回归测试。

### A-4 错列的根因已定位，但候选匹配可能仍产生错误归并（P1/P2）

- **位置：** `repair_misaligned_rows()`（约 145–177 行）、`changes_for()`（约 95–125 行）。
- **证据：** 代码注释说明历史行“少了精准定向列”，因此 `创意名称/创意ID/笔记ID` 整体左移；匹配 key 是日期+`creativityId`+`noteId`，多候选时仅用旧快照等价值计分，`best==0` 或并列才 unresolved。`changes_for` 又把非数字 creative ID 直接跳过，防止将移位 note ID 当 creative ID。
- **风险：** 同一天同创意/笔记出现多个定向或候选指标相似时，`equivalent` 可能选中错误候选；代码把 1749 条中 63 条“无法匹配”保留为空列，日志成功并不代表业务语义恢复。
- **修复：** 用完整复合键（日期、创意 ID、笔记 ID、拆分维度、定向/关键词）和明确唯一性；候选并列一律不写；输出每行 old/new/key/confidence；把 63 条单独导出待人工确认。
- **参考：** [jg daily.py](https://raw.githubusercontent.com/JFJLL/automation/master/feishu_three_sync/jg_sync/daily.py)、[README 已知状态](https://raw.githubusercontent.com/JFJLL/automation/master/feishu_three_sync/README.md)。

### A-5 Juguang 任务锁只保护同步阶段，未保护会话刷新（P1）

- **位置：** `jg_sync/run_daily.ps1`、`refresh_session.py`、`daily.py` `main()`（约 184–230 行）。
- **证据：** PowerShell 先执行 `refresh_session.py`，成功后才执行 `daily.py`；锁只在 `daily.py` 创建/锁定 `daily.lock`。两次手动/计划运行可同时 launch persistent Chrome、读写 `.report-profile`、原子替换 session headers。
- **修复：** 把锁提升到 PowerShell 全流程或独立 wrapper，覆盖 refresh+sync；用 Windows named mutex 或可回收锁；刷新写入前做版本/文件锁；并发时明确 exit 2。

### A-6 Windows 专属实现与桌面依赖（P1）

- **位置：** `jg_sync/daily.py` 顶部 `import msvcrt`、`main()` `msvcrt.locking`；`refresh_session.py` `launch_persistent_context(... channel='chrome')`。
- **证据：** `msvcrt` 在非 Windows 不可用；Chrome channel/profile、计划任务和 README 又锁定 Windows。用户线索只点到 JZT，但 Juguang 也有相同限制。
- **修复：** 若只支持 Windows，在启动检查中给出可读错误；若要迁移 sync_console，使用跨平台 `filelock`/`portalocker` 或服务端锁，并把浏览器刷新从数据同步进程剥离。

### A-7 登录态检测只验证一个 API 成功，不验证账号/字段完整性（P2）

- **位置：** `refresh_session.py` `page.evaluate()` 内 report POST（约 26–44 行）。
- **证据：** 只检查返回 `success is True`，未检查 `code==0`、`data.page`、`v-seller-id` 回显或报表行属于配置账户；然后把全部 cookies 写回。
- **修复：** 校验 HTTP status、JSON 类型、code、分页 metadata、账户字段与最小业务字段；区分登录页/权限错误/空报表；刷新后用 `ReportClient` 同一请求做一次端到端验证。

### A-8 `jg_sync/PROJECT.md` 宣称的测试和文件与清单不一致（P2）

- **位置：** `jg_sync/PROJECT.md`；根目录 `manifest.sha256.json`。
- **证据：** PROJECT 声称有 `test_daily.py`、`logs/last_run.json`、`backups/`，manifest 的受审清单没有 test_daily.py，且 README 说明本次只是打包。文档中的历史运行/测试成功不能替代当前源码审查。
- **修复：** 将“历史运行记录”与“当前可复现测试”分开；把测试脚本纳入版本或删除声明；CI 中执行静态检查和 mock API 测试。

## B. `jzt_sync`

### B-1 `--dry-run` 永远不把类别加入 ready（P1）

- **位置：** `jzt_sync/daily.py` `main()`（约 18–71 行）。
- **证据：** `ready.append(cat)` 位于 `if not args.dry_run:` 分支内；dry-run 跳过登录检查，也跳过 ready，随后 `if ready:` 不调用 `sync_all`，最终 `failed = ... or not status['tasks']`，所以没有真实读取/校验报告。
- **修复：** dry-run 应读取 token、验证 identity（不刷新浏览器），或明确只做配置检查并以 success/专门状态退出；至少对 `--dry-run` 运行 `sync_all(dry_run=True, categories=args.categories)`，并让 `sync_all` 的 dry-run 不写入。

### B-2 固定 30 日接口窗口与“全表扫描”文档矛盾（P1）

- **位置：** `jzt_sync/daily_client.py` `fetch_report()` payload（约 43–48 行）；`jzt_sync/daily_sync.py` `sync_one()`（约 57–114 行）。
- **证据：** `fetch_report` 固定 `'dataCycle':'30'`，不接 start/end；`sync_one` 只在 Feishu 目标表中读取全 `rowCount`，并只对最近三条日期更新。读取全表不能使上游返回缺失的 31 日以前数据。
- **修复：** 确认平台 API 支持的日期参数；按 target 缺口分段请求并显式过滤 start/end；若 API 只能 30 日，文档必须改成“最近 30 日”，并提供一次性历史回补工具。

### B-3 JZT API/Feishu 客户端响应校验不完整（P1/P2）

- **位置：** `daily_client.py` `fetch_report()`、`Feishu._call()`、`Feishu.get_token()`（约 34–110 行）。
- **证据：** `fetch_report` 校验 Excel 魔数、25 列、任务 ID，但不校验 HTTP Content-Type/下载内容长度及日期列值；`_call` `r.raise_for_status()` 后直接 `r.json()`，再取 `d['data']`，缺字段会以 KeyError 退出；token 直接取 `d['expire']`。`call()` 只对字符串中包含 90217/99991400 的 `SyncError` 退避，对网络超时/JSON 错误不重试。
- **修复：** 统一 HTTP wrapper：状态码、Content-Type、JSON schema、业务 code、请求 ID；只对安全请求或可证明幂等的写入重试；把网络结果未知的追加写入标为 unknown，先读后决策，不盲目 replay。

### B-4 回读和追加的正确性边界不足（P1/P2）

- **位置：** `daily_sync.py` `plan_rows()`、`sync_one()`；`daily_client.py` `Feishu.append()`。
- **证据：** `plan_rows` 只更新 `ordered[-3:]`，其余历史指标不会校准；`sync_one` 的追加 payload 固定 range `f'{sheet_id}!A1:Y{len(rows)}'`，把“表锚点/请求 values 行数/已有尾行”交给 append API 推断；回读只验证 expected 的日期行，未验证未变更的目标范围、task ID 和完整行数。
- **修复：** 使用 API 明确的 append table range；先取服务端尾行/请求幂等键；追加前做 source key 集合校验，追加后检查新增数、所有字段、task ID；指标回刷窗口由配置显式指定并记录。

### B-5 并发写锁只在进程内，不能防跨进程/跨机器覆盖（P2）

- **位置：** `daily_client.py` `Feishu.write_lock`、`call()`；`daily.py` `msvcrt.locking`。
- **证据：** `write_lock` 是单个 `Feishu` 对象的 `threading.Lock`；`msvcrt` 只锁本机 `logs/daily.lock`。另一台机器或手工脚本仍可在读后写前修改同一飞书表；API 没有 revision/ETag 条件更新。
- **修复：** 使用飞书服务端幂等键/版本条件（若 API 不支持则迁移到单写入队列）；锁范围包含 refresh、read-plan-write-readback；检测冲突后停止而不是覆盖。

### B-6 登录自动化仅适合有桌面交互的机器（P1）

- **位置：** `refresh_login.py` `refresh_all()`、`refresh_in_context()`（约 87–124 行）；`install_qicui_daily_task.ps1`。
- **证据：** Playwright `headless=False`，遇到 puzzle/SMS 打印并等待最多 1800 秒；计划任务 Principal 使用 `-LogonType Interactive`。无人值守时页面不可见或无用户登录，任务将超时；PowerShell没有告警通道。
- **修复：** 把登录刷新变成单独人工任务，日常任务检测凭据并快速失败；对任务注册使用明确的运行账户/凭据，或换成服务账号/短期 token；失败写 Windows Event Log/监控 webhook（不得带 cookie）。

### B-7 配置重复和失效来源（P2）

- **位置：** `configs/a_sheets_tasks.json`、`b_sheets_tasks.json`、`tasks_mapping.json`、`all_tasks_merged.json`、`all_23_accounts.json`、`jzt_columns.json`；`daily_sync.task_mappings()`（约 9–14 行）。
- **证据：** `task_mappings()` 只读取 `tasks_mapping.json['zhangxiaoyi']` 和 `b_sheets_tasks.json`；`a_sheets_tasks.json`、`all_tasks_merged.json`、`all_23_accounts.json`、`jzt_columns.json` 不参与当前入口。`tasks_mapping` 的另一组名称也和 `b_sheets_tasks` 不同且存在历史缩写，容易形成误映射。
- **修复：** 保留一个 canonical schema，启动时生成/校验 mappings；按 task_id 检查 sheet/title/token/category 唯一；未使用的历史配置移出运行目录。

## C. `taobao`

### C-1 配置表同步没有跨进程锁（P1）

- **位置：** `taobao/sync_configured_table.py` `main()`（约 154–260 行）；`run_daily.ps1`。
- **证据：** `main()` 创建备份并直接计划/写入，没有 lock；PowerShell 先刷新 cookie 再运行同步，手工运行与计划任务可同时读取并覆盖同一表。旧订单入口也有独立脚本/计划任务说明。
- **修复：** 三个平台共享一个按目标表/账户的互斥锁；锁住 refresh+fetch+write；冲突返回明确非零码，保留 backup。

### C-2 Feishu Table API 只对 90217 重试，异常响应会以解析错误失败（P1/P2）

- **位置：** `sync_configured_table.py` `Table.api()`（约 52–65 行）。
- **证据：** 先 `response.json()` 再看业务 code；HTTP 429/5xx、超时、非 JSON 均未分类处理；写操作遇到未知结果不能判断是否落地。只对 code=90217 做 3 次线性等待。
- **修复：** 设置 connect/read timeout；按 429 Retry-After、短暂 5xx 有界退避；非幂等写超时后先读目标 key 再决定是否重试；记录 request id。

### C-3 `merge_changes()` 和回读比较可漏检短行（P1）

- **位置：** `sync_configured_table.py` `merge_changes()`（约 34–49 行）、`Table.write_changes()`（约 77–90 行）。
- **证据：** `all(equivalent(a,b) for a,b in zip(old[index-1][:width], row))` 只比较 zip 交集；旧行少列时可能 all([])/部分相等而跳过写入；回读同样使用 `zip(verify[index-1][:width], row)`。
- **修复：** 两边先补齐到 width，再逐列比较；显式检查 `len(row) == width`、服务端返回行宽和目标 key。

### C-4 淘宝任务查找/分页存在漏项和无限循环风险（P1/P2）

- **位置：** `sync_configured_table.py` `resolve_order()`、`fetch()`；`taobaoxinghe_feishu_order_effect.py` / `taobaoxinghe_scraper.py` 的列表/报表分页函数。
- **证据：** 非任务管理分支 `search_orders(keyword=name, page_size=100)` 只拿一个 search 结果集，若平台搜索结果分页且同名项超过 100，可能漏掉唯一匹配；多个 legacy 方法按 `len(items) < page_size` 决定结束，不优先使用 `hasNext`，接口重复满页时没有页数上限。新配置 `fetch()` 只有 500 页上限，但对 `model.hasNext` 与短页的组合判断仍依赖上游字段可靠。
- **修复：** 所有列表都读取 total/hasNext，设置最大页数和重复页检测；同名匹配必须唯一并校验项目、saleType、settleSeqId；空/重复满页作为 upstream anomaly，不当成成功。

### C-5 Legacy scraper 对 HTTP 200 业务失败校验不一致（P1）

- **位置：** `taobaoxinghe_scraper.py` `TaobaoXingheScraperV5.get_json()`（约 350 行附近及后续调用）；各 `get_*` 方法。
- **证据：** `get_json()` 仅在 HTTP >=400 时抛错；HTTP 200 的 `success=false` 仍返回 data。部分调用方检查 `success`，但商品列表、达人详情等函数直接读取 `model/data`，可能把权限失败当作空列表/成功。
- **修复：** wrapper 强制检查 success/code，并返回明确的 auth/empty/upstream 三态；只有声明允许空数据的 endpoint 才可接受空 model。

### C-6 Legacy Feishu 全表覆盖可能抹除管理列（P1）

- **位置：** `taobaoxinghe_feishu_order_effect.py` `FeishuSheetsClient.read_sheet_rows()`、`replace_rows()`、`upsert_rows()`（约 430 行以后，完整文件因输出截断无法给出精确行）。
- **证据：** `OUTPUT_COLUMNS` 是脚本固定的业务列；`read_sheet_rows()` 只抽取这些列；`replace_rows()` PUT `A1:<end_col><total_rows>`，不会保留 OUTPUT_COLUMNS 之外的人工列。相比之下 `sync_configured_table.py` 明确只写 `[A:width]` 的管理区并声称保留右侧列，两个入口行为不一致。
- **修复：** 读取完整表头并按列名映射，只更新拥有者列；禁止全表 replace，或在事务前备份并把未知列 merge 回去；写后校验未知列未变。

### C-7 淘宝时间使用本机时区，未固定北京时间（P2）

- **位置：** `taobaoxinghe_feishu_order_effect.py` `yesterday_date()`、`cutoff_time_range()`、`order_start_time()`；`sync_configured_table.py` `main()` 使用 `date.today()`；`taobaoxinghe_scraper.py` 的日期工具。
- **证据：** 代码多处调用 naive `datetime.now()`/`date.today()`。README 任务时间是北京时间，但未使用 `zoneinfo Asia/Shanghai`；服务器/夏令时或计划账户时区变化会造成边界日错取。`cutoff_time_range()` 同时把 startTime 和 endTime 设为目标日 `00:00:00`，若调用者期待整日区间会成为零时长边界。
- **修复：** 统一 `now_bjt = datetime.now(ZoneInfo('Asia/Shanghai'))`；所有 API 区间以半开 `[start, end+1 day)` 或明确 `23:59:59.999`；对日期输入加时区测试。

### C-8 Feishu legacy 客户端反复取 token、无统一代理/重试策略（P2）

- **位置：** `taobaoxinghe_feishu_order_effect.py` `FeishuSheetsClient`、`FeishuBitableClient` 及 token helpers；`sync_configured_table.py` `Table`。
- **证据：** legacy `tenant_access_token()` 每次 read/write 都重新请求 token；这些 sessions 未统一 `trust_env=False`，而新配置同步显式关闭代理。不同入口在同一台机器上对代理、超时、认证缓存行为不一致。
- **修复：** 抽出共享 `FeishuClient`，缓存 token 至 expiry-120 秒、统一 connect/read timeout/response schema/限流策略；按 endpoint 声明幂等性。

### C-9 CDP 刷新流程有 TOCTOU、页面选择和进程清理边界（P2）

- **位置：** `refresh_adstar_cookie.py` `pick_free_port()`、`wait_for_devtools()`、`choose_page_target()`、`launch_browser()`、`fill_login_form_dom()`。
- **证据：** 先 bind 临时端口再关闭再启动浏览器，存在端口竞态；找不到偏好域名时退化到第一个 page target；CDP websocket 自行实现，连接/读取固定 30 秒；工具输出中后段无法读到最终 orchestration/cleanup，因此不能确认所有异常路径都 terminate/等待子进程。
- **修复：** 让浏览器由 Playwright 管理或启动后从实际 DevTools endpoint 发现端口；校验 target URL/origin；所有资源使用 context manager，异常时 terminate/wait，记录可诊断错误但不打印 cookie；增加浏览器崩溃/登录 iframe 变化测试。

### C-10 旧入口与新配置入口重复、默认行为容易误用（P2）

- **位置：** `taobao/PROJECT.md`、`run_daily.ps1`、`taobaoxinghe_feishu_order_effect.py`、`sync_configured_table.py`。
- **证据：** PROJECT 说“原启萃表订单明细同步，原目标保持启用”，新入口只同步信息表配置；两套 exporter、两套 Feishu 写入模型并存，均可在计划任务/手工入口被调用。
- **修复：** 明确唯一 production entrypoint；legacy 只读/归档；为每张表注册 owner 与 source；把旧数据导出脚本改为显式 `--legacy` 且默认拒绝写入。

## D. 根目录与 PowerShell

### D-1 `setup.ps1` 未固定解释器、未安装 Playwright 浏览器/锁版本（P2）

- **位置：** `feishu_three_sync/setup.ps1`（约 1–7 行）、根 `requirements.txt`。
- **证据：** `python -m venv .venv` 依赖 PATH 中的 Python；pip 安装无版本 pin/hash；requirements 仅列包名，没有 `playwright install chrome`，首次运行可能缺浏览器；脚本没有记录 Python/pip 版本或校验安装结果以外的运行时依赖。
- **修复：** 使用 `py -3.10`/显式解释器；锁定兼容版本并生成 hash lock；安装/检测 Playwright 浏览器；设置 UTF-8、执行策略说明；安装后运行 `python -m compileall` 和 smoke test。

### D-2 `run_daily.ps1` 的 `$LASTEXITCODE` 依赖和失败告警（P2）

- **位置：** `jg_sync/run_daily.ps1`、`jzt_sync/run_daily_jzt.ps1`、`taobao/run_daily.ps1`。
- **证据：** 三者大多依赖子进程 `$LASTEXITCODE`，只做 transcript/`Write-Host`/`Write-Warning`，没有统一的 `try/finally`、事件日志、邮件或 webhook；JZT runner 的 `finally Stop-Transcript` 若 transcript 初始化失败还可能覆盖原错误。淘宝脚本没有日志目录/Start-Transcript。
- **修复：** 统一 runner：显式捕获每一步、保留原 exit code、创建日志目录、限制日志保留期、事件日志告警；写入脚本路径使用 `-LiteralPath`，检查 Python/Chrome 存在；不要把 `ExecutionPolicy Bypass` 当作安全边界。

### D-3 计划任务路径和时区/交互假设（P1/P2）

- **位置：** `jg_sync/install_daily_task.ps1`、`jzt_sync/install_qicui_daily_task.ps1`。
- **证据：** action 使用 `powershell.exe -ExecutionPolicy Bypass -File "$ProjectDir..."`，路径引号拼接在长路径/特殊字符场景缺乏统一封装；Principal 是 current user + Interactive；计划时间没有 `TimeZone` 显式定义，依赖系统时区。Juguang 任务设置 `-MultipleInstances IgnoreNew` 只对任务实例生效，不覆盖手工 runner/refresh。
- **修复：** 通过 `New-ScheduledTaskAction` 的安全参数构造并验证实际 action；显式记录机器时区/北京时间转换；安装后执行一次 `Get-ScheduledTaskInfo` 和 dry-run；失败通知到事件日志。

## 逐文件/逐函数审阅清单

标记：✅ = 本次读取完整；◐ = raw 与 Contents API 均在工具输出中段截断，未能逐行完成；— = 数据配置/文档无函数，以结构和安全性审阅。

| 文件 | 读取状态 | 关键函数/结构审阅 |
|---|---:|---|
| `feishu_three_sync/PROJECT.md` | ✅ | 目录意图、相对依赖/打包说明；未发现函数。 |
| `feishu_three_sync/README.md` | ✅ | 启动、调度、已知问题、敏感内容声明；已与实现交叉核对。 |
| `manifest.sha256.json` | ✅ | 清单确认敏感文件和会话文件存在于打包版本。 |
| `requirements.txt` | ✅ | 无版本锁、无 Playwright 浏览器安装步骤。 |
| `setup.ps1` | ✅ | venv/pip/退出码；见 D-1。 |
| `jg_sync/PROJECT.md` | ✅ | 文档称有测试和日志；与 manifest/当前清单存在差异。 |
| `jg_sync/daily.py` | ✅ | `date_value`、`format_date`、`scalar`、`ReportClient.__init__/fetch`、`convert`、`row_key`、`changes_for`、`repair_misaligned_rows`、`main`；见 A-1–A-6。 |
| `jg_sync/install_daily_task.ps1` | ✅ | 任务 action、Interactive principal、2h 限制；见 D-3。 |
| `jg_sync/login_browser.py` | ✅ | 仅转调 `refresh(interactive=True)`；安全性取决 refresh。 |
| `jg_sync/refresh_session.py` | ✅ | persistent Chrome、cookie 导入/导出、单接口登录检查；见 P0-2/A-5/A-7。 |
| `jg_sync/run_daily.ps1` | ✅ | refresh→daily 顺序、transcript、exit code；refresh 未纳入锁。 |
| `jzt_sync/PROJECT.md` | ✅ | 运行和历史声明；固定 30 日与“全表扫描”需核实。 |
| `jzt_sync/config_loader.py` | ✅ | dotenv 优先但真实 app secret 回退；见 P0-1。 |
| `jzt_sync/daily.py` | ✅ | argparse、dry-run、类别 ready、msvcrt 锁、退出码；见 B-1/B-5。 |
| `jzt_sync/daily_client.py` | ✅ | `session`、`read_accounts`、`identity`、`fetch_report`、`Feishu.get_token/call/_call/resolve/sheets/read/write/append`；见 B-2–B-5。 |
| `jzt_sync/daily_sync.py` | ✅ | `task_mappings`、`date_key`、`normalize`、`index_dates`、`plan_rows`、`sync_one`、`sync_all`；见 B-2/B-4/B-7。 |
| `jzt_sync/install_qicui_daily_task.ps1` | ✅ | 两触发器、Interactive、IgnoreNew、ExecutionPolicy；见 D-3。 |
| `jzt_sync/local_login.py` | ✅ | 明文凭据常量；P0-1/P1-3。 |
| `jzt_sync/refresh_login.py` | ✅ | cookie parse/merge/save、Playwright 登录、身份验证、业务报表验证；见 P1-3/B-6。 |
| `jzt_sync/requirements.txt` | ✅ | 与根依赖重复、无版本锁。 |
| `jzt_sync/run_daily_jzt.ps1` | ✅ | Categories 参数、transcript、exit code；见 D-2。 |
| `configs/a_sheets_tasks.json` | ✅ | 33 条卓睿映射；当前 daily 未直接读取。 |
| `configs/all_23_accounts.json` | ✅ | 23 个账号标识；与当前 two-account runtime 无调用关系，仍属敏感业务资产。 |
| `configs/all_tasks_merged.json` | ✅ | 合并 task→book/token/sheet 配置；当前入口未读取；含可定位目标表 token，需按敏感配置处理。 |
| `configs/b_sheets_tasks.json` | ✅ | 19 条启萃映射；daily 当前使用。 |
| `configs/jzt_columns.json` | ✅ | 25 列定义；当前 `daily_sync` 依赖接口 Excel 列检查但未读取此文件。 |
| `configs/tasks_mapping.json` | ✅ | 卓睿/历史启萃映射；当前只读 zhangxiaoyi；与 b 配置重复。 |
| `taobao/PROJECT.md` | ✅ | 新旧入口、空报表边界、时区/计划说明；见 C-10。 |
| `taobao/refresh_adstar_cookie.py` | ◐ | 已读至 CDP/WebSocket、cookie flatten、登录 iframe 主体；Contents API 文件大小约 46KB，工具仍在中段截断；末尾 orchestration/cleanup 未完成核验，限制见 C-9。 |
| `taobao/run_daily.ps1` | ✅ | refresh→sync，错误只返回 exit code；见 D-2。 |
| `taobao/sync_configured_table.py` | ✅ | `cell/day/equivalent/row_key/merge_changes`、`Table`、`resolve_order/fetch/main`；见 C-1–C-4。 |
| `taobao/taobaoxinghe_feishu_order_effect.py` | ◐ | raw 和 Contents API 均在约 50KB 文件中段截断；已读到日期/行合并、Feishu 客户端等主体，后半 main/所有函数无法宣称完整，限制见 C-6–C-8。 |
| `taobao/taobaoxinghe_scraper.py` | ◐ | raw 和 Contents API 均在约 46KB 文件中段截断；已读 cookie、分页、`get_json`、订单/效果/达人主体，末尾函数未完整核验，限制见 C-4/C-5/C-9。 |

## 重复实现与迁移/下线建议

### 应迁移到 `sync_console`

1. **统一 Feishu transport/client：** token 缓存、`trust_env=False`、connect/read timeout、429/90217/5xx 退避、JSON schema、request-id、幂等写入和读后校验。优先吸收 JZT 的写限速/并发锁思路，但重写成可证明幂等的 upsert，而不是直接复制。
2. **统一数据契约：** `ProviderFetchResult` 三态（success/empty/auth/upstream）、字段映射、日期解析、source key 唯一性、范围边界和分页上限。`sync_console/platforms/juguang.py`、`jzt.py`、`taobao.py` 已有雏形，应迁移“结构化错误分类”而非各项目的硬编码 token 路径。
3. **迁移 Juguang 的领域逻辑：** `METRICS`/`IDENTITY`、placement 映射、T+2 字段说明、严格字段校验和错列修复工具；错列修复要独立为 dry-run + diff + 人工确认命令，不能放进每日自动写入口。
4. **迁移 JZT 的安全写入逻辑：** full allocated sheet read、日期唯一性检查、task ID/标题归属校验、最近窗口更新、写后回读；先修复固定 30 日数据窗口及 dry-run，再迁移。
5. **迁移淘宝新版的当前任务解析：** `saleType=4` 任务列表→详情校验→报表查询，保留名称唯一性、project/saleType/settleSeqId 交叉校验；把 `merge_changes` 修成严格宽度比较。
6. **统一调度/锁/告警：** console 只负责数据 job；浏览器登录刷新单独运行并把短期凭据放 secret store；任务计划脚本只做 wrapper，失败写 Event Log/监控。

### 可以直接下线/归档

- `jzt_sync/configs/all_23_accounts.json`、`jzt_sync/configs/all_tasks_merged.json`、`jzt_sync/configs/jzt_columns.json`、未使用的 `a_sheets_tasks.json`：若确认无外部工具依赖，迁移 canonical 配置后移出运行包；尤其 `all_tasks_merged` 含表格 token，不应保留。
- `taobao/taobaoxinghe_feishu_order_effect.py` 与 `taobaoxinghe_scraper.py` 的旧写入/导出路径：在新版配置表入口完成 parity、历史数据核对和回滚演练后，改为只读归档并删除生产计划任务。
- `jg_sync/login_browser.py`：可由 `refresh_session.py --login` 统一替代，只保留一个登录入口。
- `jzt_sync/local_login.py`：迁移密码后立即删除。
- `setup.ps1`/各子项目重复 requirements：保留一个锁定依赖和一个安装入口；各子目录脚本仅做兼容 wrapper。

## 读取限制与未验证项

- 根目录、Juguang、JZT、配置 JSON、淘宝 `sync_configured_table.py`、PowerShell 文件均已完整读到工具返回内容。
- `refresh_adstar_cookie.py`（约 46KB）、`taobaoxinghe_feishu_order_effect.py`（约 50KB）、`taobaoxinghe_scraper.py`（约 46KB）按要求先读 raw；因工具返回截断，再读 Contents API；API 的 base64 内容同样在中段截断。因此不能声称这 3 个大文件逐函数完整读完，行号只能给已见函数附近的约数；若必须满足“完整读完”，需要父代理使用可保存 HTTP 响应/按 blob 分段解码的工具，并针对这 3 文件补充逐函数清单。
- 敏感文件 raw/API 读取被端点拒绝；其存在由 README、manifest 和源码引用交叉确认，未输出任何原值。不能据此断言每个敏感文件当前内容是否可解密/可用，但必须按已泄露处理。
- 未执行真实飞书/平台写入或登录；所有结论是静态审查，不代表当前线上数据实际状态。未审计 `sync_console` 其他模块、计划任务 XML 或 Git 历史全量。

## 淘宝三大文件复审（新增；替代来源重试结果）

本轮额外尝试了 jsDelivr、GitHub `blob?plain=1`、raw.githack、GitHub blob API，并使用 GitHub 页面锚点请求后半段；jsDelivr/Sourcegraph/Jina 端点无法取回，其他端点仍由读取工具在约固定响应大小处截断。未创建 `taobao_src/`，因为没有拿到可验证的完整原始文件。以下新增发现仅来自本轮成功看到的代码片段，未把未见后半段推断为已审阅。

### C-11 淘宝旧导出合并键会按日期维度删除未返回订单（P1）

- **文件/函数：** `taobaoxinghe_feishu_order_effect.py` `merge_sheet_rows()`（约 190–215 行）。
- **代码证据：** `row_identity()` 包含 `任务组名称、日期、订单ID、流量类型、归因周期`，但 `row_match_key()` 故意不含 `订单ID`；`merge_sheet_rows()` 先计算 `new_match_keys`，再执行 `existing_rows if row_match_key(row) not in new_match_keys`，因此同一任务组/日期/流量/归因下的所有历史订单都会先被移除，只保留本次 API 返回的订单。若接口因延迟/权限只返回部分订单，未返回订单的历史行会被静默删除。
- **修复：** 以完整业务主键（至少含订单 ID）做 upsert；如果业务确实需要按日期重算，先校验 source 集合完整性/总数，缺失时拒绝覆盖；永远不要用“本次出现的非订单维度 key”删除已有记录。

### C-12 `cutoff_time_range()` 将整日查询的结束时间设为当天零点（P1）

- **文件/函数：** `taobaoxinghe_feishu_order_effect.py` `cutoff_time_range()`（约 55–64 行）。
- **代码证据：** 同一 `target_date` 下同时生成 `startTime=f'{target_date} 00:00:00'` 和 `endTime=f'{target_date} 00:00:00'`。若调用方把它作为当天报表区间，区间为空或只落在零点；函数名/字段 `cutoffDate` 又容易掩盖这一边界错误。
- **修复：** 统一采用半开区间 `[target 00:00:00, next_day 00:00:00)`，或明确使用 `23:59:59`；增加单元测试断言 end > start 且覆盖目标日期。

### C-13 淘宝旧抓取器将异常响应/异常数据静默降级为空或零（P1/P2）

- **文件/函数：** `taobaoxinghe_scraper.py` `list_from_model()`、`to_number()`、`get_json()`（约 65–115、300–350 行）。
- **代码证据：** `list_from_model()` 对非 list/dict 或未命中 `result/list/data/records/items` 的 model 返回 `([], model)`；`to_number()` 对任何 `ValueError` 返回 `0.0`；`get_json()` 虽在非 JSON 时构造 `success=False`，但对 HTTP 200 不强制检查 `success`。因此业务失败、schema 漂移、格式错误可能被上层当成“空列表/0 指标”继续。
- **修复：** wrapper 强制校验 HTTP status、JSON object、success/code 和必需 model schema；把 malformed/permission/error 与合法 empty 分离；数值字段遇到非法值应失败或保留原始值并标记校验错误，不能改写为零。

### C-14 淘宝旧抓取器的分页缺少硬上限和重复页保护（P1/P2）

- **文件/函数：** `TaobaoXingheScraperV5.get_order_products()`、`get_effect_details()`、`get_creator_list()`（各自可见主体约 350 行以后）；`list_from_model()`。
- **代码证据：** 多个循环以 `len(items) < page_size` / `len(page_records) < page_size` 为唯一结束条件；未看到 `hasNext`、total 或最大页数/重复页指纹检查。若服务端持续返回满页、分页字段失真或同一页重复，任务可能无限请求或重复写入。
- **修复：** 同时校验 `hasNext/total`，设置最大页数；记录 page fingerprint，重复页立即失败；按主键去重并检查跨页重复。

### C-15 `refresh_adstar_cookie.py` 的 CDP 目标选择和错误降级不安全（P1/P2）

- **文件/函数：** `choose_page_target()`、`open_page_session()`、`read_cookie_dict()`、`clear_login_state()`、`fill_login_form_dom()`。
- **代码证据：** `choose_page_target()` 找不到 `preferred_host` 时直接返回第一个 page；`read_cookie_dict()` 捕获 `CookieRefreshError` 后返回 `{}`；`clear_login_state()` 对各 origin 清理失败直接 `pass`；`fill_login_form_dom()` 对 websocket 连接异常直接返回 `False`。这些降级会把“选错页面/会话不可读/清理不完整/浏览器通信异常”和“确实没有 cookie/登录控件不存在”混为一谈。
- **修复：** preferred host 不匹配时失败而不是退化到首个页面；将错误分类写入结构化状态；只在明确允许的 origin 上清理；登录表单和 CDP 异常保留诊断信息（不含 cookie/密码），并让调用方返回非零码。

### C-16 CDP WebSocket 实现缺少协议完整性保护（P2）

- **文件/函数：** `refresh_adstar_cookie.py` `WebSocket.recv_text()`、`_read_frame()`、`CdpSession.call()`。
- **代码证据：** `recv_text()`只处理 opcode 0x1/0x0 和 ping/close，未对未知控制帧、RSV 位、fragmented control frame、消息大小作限制；`CdpSession.call()`只按 id 等待消息，未设置按调用的超时，依赖底层 socket 固定 30 秒。`launch_browser()` 将 stdout/stderr 丢弃，异常诊断不足。
- **修复：** 优先 Playwright/Selenium 管理 CDP；若保留自实现，严格校验 WebSocket 帧、控制帧和最大消息大小，按调用设超时，保留安全诊断日志，并在异常路径 terminate/wait 浏览器子进程。

### C-17 legacy Feishu 客户端会反复获取 token 且各 API 未统一 HTTP 校验（P2）

- **文件/函数：** `taobaoxinghe_feishu_order_effect.py` `feishu_tenant_access_token()`、`FeishuSheetsClient.tenant_access_token()`、`FeishuSheetsClient.read_values/replace_rows/append_rows`、`FeishuBitableClient.batch_create_records()`。
- **代码证据：** 每次 client 操作都调用 `tenant_access_token()`，没有 expiry 缓存；helper 直接 `response.json()`，未先检查 HTTP 状态，也无网络重试/限流退避；各写 API 使用 PUT/POST 后仅检查业务 `code`。
- **修复：** 抽出共享、缓存 token 的 Feishu transport；统一 connect/read timeout、429/5xx 分类、Retry-After、schema 检查和未知写入结果处理；非幂等写超时后先读主键再决定是否重放。

### C-18 旧抓取器 API ID 转换和数据截断边界（P2）

- **文件/函数：** `taobaoxinghe_scraper.py` `infer_input()`、`json_cell()`、`build_effect_ext()`；`taobaoxinghe_feishu_order_effect.py` `order_id_corrections_from_orders()`。
- **代码证据：** `infer_input()` 用“纯数字且长度 >=11”推断 project ID，接口输入歧义时可能路由错误；`json_cell()` 对 dict/list 序列化后直接截断到 32000 字符；`build_effect_ext()` 对 ID 强制 `int()`；`order_id_corrections_from_orders()` 对内部订单 ID 强制 `int()`。这些都会导致合法非纯数字 ID、超长原始字段或 ID 类型变化时失败/丢数据。
- **修复：** ID 全程按字符串保留，仅在 API schema 明确要求数字时校验；输入使用显式参数而非长度猜测；超长字段拒绝写入并记录原始快照/哈希，不静默截断。

## 本轮读取状态更新

| 文件 | 最终状态 | 说明 |
|---|---:|---|
| `taobao/refresh_adstar_cookie.py` | ◐ 未完整 | raw、GitHub blob API、GitHub `blob?plain=1`、raw.githack均在约 `key_code_for_char()` 附近截断；文件 API 元数据标称 46,064 bytes。未能用 `wc -l`/结尾校验，未保存至 `taobao_src/`。 |
| `taobao/taobaoxinghe_feishu_order_effect.py` | ◐ 未完整 | raw、GitHub blob API、GitHub `blob?plain=1`、raw.githack均在 `feishu_sheets_client_from_args()` 附近截断；API 元数据标称 50,197 bytes。未能用 `wc -l`/结尾校验，未保存至 `taobao_src/`。 |
| `taobao/taobaoxinghe_scraper.py` | ◐ 未完整 | raw、GitHub blob API、GitHub `blob?plain=1`、raw.githack均在 `get_order_list()` 附近截断；API 元数据标称 45,922 bytes。未能用 `wc -l`/结尾校验，未保存至 `taobao_src/`。 |

本轮未把“读取到的开头”误标为完整；若要完成用户要求的 `wc -l`、末尾校验和逐函数全审查，仍需一个能保存完整 HTTP 响应或支持按字节/行范围下载的工具通道。