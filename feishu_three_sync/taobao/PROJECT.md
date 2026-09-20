# 淘宝星河每日飞书更新

## 概述
Windows 任务 `TaobaoXingheDailyFeishuSync` 每日北京时间 **09:00** 执行。先用现有浏览器配置检查登录、更新 `adstar.txt` Cookie，再通过平台接口更新飞书。

## 目录和启动
- `run_daily_taobao_feishu.ps1`：定时入口；解释器 `D:\python\python.exe`。
- `refresh_adstar_cookie.py`：复用登录，过期时按 `.env` 凭据登录；验证码仍需人工。
- `taobaoxinghe_feishu_order_effect.py`：原启萃表订单明细同步，原目标保持启用。
- `sync_configured_table.py`：新增配置表驱动的分子表同步。
- `.env`、`adstar.txt`、浏览器 profile：本机凭据，不应提交或输出。
- `logs/configured_table_last_run.json`：新增表每项执行状态。
- `backups/configured_时间/`：每次更新前完整读取的子表数据。
- `test_configured_table.py`：日期、数值兼容、去重及保留人工列测试。

手动运行新增表：`D:\python\python.exe sync_configured_table.py`。
只读预检：在上面命令后加 `--dry-run`。
完整运行：`powershell -NoProfile -ExecutionPolicy Bypass -File run_daily_taobao_feishu.ps1`。

## 新目标与规则
https://yimeichuanbo.feishu.cn/wiki/OOpNw9CBJiqNrCkFjcIc5Q8bnXc

每次从“信息表”读取账户名称、维度、更新页、开始时间、位置。按开始日期与已有最新日期前两天中较晚者开始取数，截止昨日；信息表的固定“结束时间”不作为永久停止日期。按日期、任务/内容ID、流量类型、30日归因口径去重，校准最近数据，只写变更行的指标区，保留右侧人工列。空结果不清除历史数据。写入前备份、写后回读核验。

## 当前状态和边界
- 童年故事、启萃按原订单入口同步。
- 黄天鹅5/6/7/8月已接入截图对应的新版“我的任务”：saleType=4列表→当前内部orderId详情→selfOfficial_orderInfo_detail报表。以信息表名称匹配自动生成名称，再校验项目名、saleType、settleSeqId。
- 原判断“账号无权限”已纠正：旧表任务ID请求旧详情接口报50109不能代表新版任务无权限。无需用户更换账号。
- 新版映射：8月117472777/130692875，7月117453821/127793205，6月117442395/125443771，5月117428572/122760003（内部orderId/报表ID）。旧历史任务ID不改写。
- 2026-09-15已复现8月任务详情页面及其推广效果网络请求，均success=true；页面汇总model为空、明细totalCount=0。另外3个任务按投放开始日到9月14日查询也返回0条。因此当前没有黄天鹅新明细可补写，每日继续查询；不能将空结果当作权限失败或生成零值记录。
- 真正失败项返回退出码1；空报表标注note，保留历史内容。具体状态看JSON日志。
- 平台有数据延迟；只写实际返回明细。

## 更新日志
### 2026-09-15
- 新增用户指定Wiki表的分子表同步，保留已有启萃同步及9点计划。
- 使用当前Cookie直接取数，调试不额外打开浏览器。
- 新增表备份、去重、限速、回读；4个合并测试通过，PowerShell解析通过。
- 运行入口修改前已备份至 `backups/runner_时间/`。

- 实际运行：7/11项成功，新增44行，校准5行；写入回读通过。运行时信息表新增了电商-启萃-9月-小红星-图文-F配置，也已成功同步。黄天鹅4项权限失败。平台最新数据2026-09-13。

### 2026-09-15 用户截图纠正后
- 移除旧任务ID权限前置检查和人工启用保护，接通当前任务列表/详情/报表流程。
- 依据实际页面请求验证；新版页面本身返回空报表。
- 6项测试通过，包括当前任务ID路由和多匹配拒绝。
- 修正后重跑退出码0：11项请求成功，黄天鹅4项明细0条，其余7项无需变更；不将无数据宣称为已补齐。
