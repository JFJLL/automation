# 生产部署与运维加固指南 (DEPLOY.md)

## 1. 架构与进程约束 (调度器单实例)
- 系统采用内置统一 APScheduler 调度引擎，统一负责京准通、淘宝星河、小红书聚光以及灵犀关键词的自动触发。
- **并发与 Worker 约束**：
  - 启动 Uvicorn / Gunicorn 时必须保持单个工作进程（即 `--workers 1` 或 `WEB_CONCURRENCY=1`）。
  - 若系统检测到 `WEB_CONCURRENCY > 1` 或 `WORKERS > 1`，调度器将拒绝在从属子进程中重复启动，以防止跨进程竞态和重复数据拉取。

## 2. 关键环境变量配置
| 变量名 | 说明 | 推荐值 / 约束 |
|---|---|---|
| `SESSION_SECRET` | 核心安全 HMAC 密钥 | **必须大于等于 32 字符**，为空或长度不足时系统拒绝启动 |
| `COOKIE_SECURE` | Cookie Secure 传输标记 | 生产环境务必设置为 `true` |
| `FEISHU_SHEET_SHARE_MODE` | 飞书表格创建默认权限 | 默认为 `private`（私有），可选 `tenant_readable` / `tenant_editable` |
| `MISSED_RUN_POLICY` | 停机后错失运行处理策略 | 默认为 `run_once`（启动后自动补跑一次），可选 `skip` |
| `CREDENTIALS_DIR` | 本地安全凭据存储目录 | 默认指向 `tokens/`，POSIX 下权限设为 0600 |
| `NOTIFICATION_WEBHOOK` | 告警飞书机器人地址 | 域名必须严格限制为 `open.feishu.cn` |

## 3. Systemd 运维配置示例
服务运行于非 root 用户，配合反向代理与 Linux 内核安全沙箱加固：

```ini
[Unit]
Description=JFJLL Automation Sync Console Service
After=network.target

[Service]
Type=simple
User=automation
Group=automation
WorkingDirectory=/opt/automation
EnvironmentFile=/opt/automation/.env
ExecStart=/opt/automation/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8088 --proxy-headers --forwarded-allow-ips=127.0.0.1 --workers 1
Restart=always
RestartSec=5

# Linux 内核加固
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/automation/sync_console/data /opt/automation/sync_console/backups /opt/automation/sync_console/tokens /opt/automation/logs

[Install]
WantedBy=multi-user.target
```

## 4. 反向代理配置 (Nginx)
系统绑定在 127.0.0.1:8088，由 Nginx 提供 HTTPS 证书终结与安全头传递：
```nginx
server {
    listen 443 ssl http2;
    server_name sync.example.com;

    ssl_certificate /etc/nginx/ssl/sync.crt;
    ssl_certificate_key /etc/nginx/ssl/sync.key;

    location / {
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
