# 三张飞书表自动更新脚本包
整理日期：2026-09-20。Windows + Python 3.10及以上 + 已安装Google Chrome。
包含当前本机配置、账号凭据、飞书密钥及登录会话，仅供本人/授权维护人员使用。未打包浏览器缓存、历史数据备份和运行日志。
解压后保持目录结构；在根目录运行 powershell -ExecutionPolicy Bypass -File setup.ps1 安装依赖。首次登录或会话过期可能需要扫码/验证码，浏览器会话不能保证迁移后仍有效。

## 目标与手动运行
1. 淘宝星河：https://yimeichuanbo.feishu.cn/wiki/OOpNw9CBJiqNrCkFjcIc5Q8bnXc?sheet=46d7a5
   powershell -ExecutionPolicy Bypass -File taobao/run_daily.ps1
   按信息表同步其配置的内容/任务底表；包内入口仅运行此配置表同步。
2. 京准通启萃：https://yimeichuanbo.feishu.cn/wiki/GMsTwebnniW6wDkFRt0ckFrAnTg?sheet=Iz7TUM
   powershell -ExecutionPolicy Bypass -File jzt_sync/run_daily_jzt.ps1 -Categories qicui
   启萃19个配置任务；映射文件保留原结构，入口限定qicui。
3. 聚光童年故事：https://yimeichuanbo.feishu.cn/wiki/S1USwIVTJisg3EkPPBTcFLisnPh?sheet=928H1M
   powershell -ExecutionPolicy Bypass -File jg_sync/run_daily.ps1
   按信息表同步创意、定向、关键词、账户四张底表。仅需全量时，登录有效后：
   .venv/Scripts/python.exe jg_sync/daily.py --full-refresh

## 当前调度
本机实际任务：淘宝每日09:00；启萃每日13:30、周一额外09:00；聚光每日09:00（北京时间）。
本次仅打包，未注册新任务、未执行同步。移机后可手动运行验证，再使用各目录安装脚本；淘宝可在任务计划程序每日09:00调用 taobao/run_daily.ps1。
原计划任务安装脚本会使用既有任务名称，请在目标机器上按需运行。
登录工具：淘宝 refresh_adstar_cookie.py；京准通由 daily.py 检查登录；聚光 refresh_session.py --login。

## 已知状态（按现有代码如实保留）
聚光常规入口仍是最近三日回刷，全历史需要 --full-refresh；本次打包没有修改业务更新策略。
聚光历史日志记录63条错列仍未解析；此前“全部修复”的描述不准确，现有代码也会跳过重复历史键。需要后续专项修复，不能将success日志当作这些历史问题已解决的证明。
时间格式当前代码为 YYYY/M/D（日期未强制补零），与严格YYYY/M/DD有差异。
登录Cookie随平台状态可能失效；京准通业务Cookie失效需重新获取。
公共飞书模块位于taobao目录，聚光已改为包内相对引用。
PROJECT.md为各来源项目历史说明，运行命令以本README为准。
