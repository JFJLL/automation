# 聚光童年故事飞书自动更新

## 概述
目标：https://yimeichuanbo.feishu.cn/wiki/S1USwIVTJisg3EkPPBTcFLisnPh
账户：易美-童年故事；v-seller-id=659e1399096eae00013086d6，开放平台advertiser_id=737411。
四张底表通过当前聚光后台报表接口更新，按信息表读取账户、底表名称及拆分维度。

## 目录与启动
- daily.py：分页取数、严格字段校验、去重、备份、写入及回读。
- refresh_session.py：专用Chrome配置持久化，恢复并自动更新登录会话。
- run_daily.ps1：先刷新登录，再更新飞书；失败返回非零状态。
- install_daily_task.ps1：每日09:00本机任务JuguangChildStoryDailyFeishuSync。
- login_browser.py：必要时手动完成一次登录，无需复制Cookie。
- test_daily.py：7项字段、日期、百分比、去重、历史错位保护测试。
- session_headers.json、browser_state.json、.report-profile/：本机登录状态，不纳入Git。
- logs/last_run.json：最近运行每张表结果；backups/时间戳/：写前表格与来源快照。

完整手动运行：powershell -NoProfile -ExecutionPolicy Bypass -File run_daily.ps1。
只读预检：D:\python\python.exe daily.py --dry-run。
重新登录：D:\python\python.exe refresh_session.py --login。

## 登录机制
首次使用用户提供的已登录请求建立本机专用浏览器状态。后续每次从保存的浏览器登录状态恢复，访问聚光页面并实际调用报表检查登录，保存当前Cookie和浏览器状态，再交给同步脚本。浏览器关闭后仍保留会话Cookie，通常无需每天手工复制。
服务器主动登出或短信、扫码验证无法保证无人干预；届时任务明确失败并记录日志，运行--login完成验证即可。固定Cookie不是长期运行的唯一依据。

## 报表字段
POST https://ad.xiaohongshu.com/api/leona/rtb/common/data/report
- account + splitColumns=[placement]：只选账户维度字段，不能混入creativityId，否则返回粒度会改变。
- creativity：创意底表。
- creativity + targetDetail：精准定向底表。
- creativity + keyword：关键词底表。
小红星30日UV=outsideShopVisit，成本=outsideShopVisitPrice；任务期消费=tbTaskFee（已核对网站表头配置），fee为总消费。该归因指标有T+2延迟。
按日期+创意ID+拆分维度去重；账户按日期+投放位置。保留创意表右侧博主、内容类型、笔记归属原业务标签。分组不支持的人群字段保持“-”，绝不补成零。

## 更新策略与限制
常规运行从表内最新日期前2天开始，补至昨日，既补缺口也回刷最近3天；--full-refresh 从每张底表当前最早日期开始，覆盖到昨日。写前备份，仅更新管理指标区，追加新行后回读核验；缺字段、分页异常或重复来源键阻止该表写入。
第一列时间统一写为 YYYY/M/DD 文本格式。定向表历史中有部分原始行少了“精准定向”列，创意ID位置实际为笔记ID；全量运行会按日期、创意ID、笔记ID及管理指标尝试恢复真实定向，平台已不再返回的历史记录则仅补回空定向列并保留其余值，避免误归类。此次全量预检识别到1749条错列行，其中1686条完成匹配或结构修复，63条因平台缺少对应历史源数据保留空定向并记录在日志中。

## 更新日志
### 2026-09-15
- 刷新并确认开放平台账户授权；开放平台部分字段缺失，改用用户提供的聚光后台接口。
- 实测后台接口不需要复用动态x-s签名；浏览器管理会话。
- 核实四类完整报表字段、任务期消费真实字段及T+2说明。
- 修复Windows PowerShell UTF-8 BOM和浏览器关闭后会话恢复。
- 7项测试通过；真实首次同步及计划状态见logs与后续记录。

- 2026-09-15完整运行退出码0，4/4表成功，新增2000行、校准1060行，写后回读通过；补数范围9月8日至9月14日。
- 计划任务已注册Ready，下一次2026-09-16 09:00。定向表1749行历史错位内容保留并计入日志。
