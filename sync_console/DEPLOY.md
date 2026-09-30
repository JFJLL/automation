# 广告数据跨平台自动同步与关键词监控看板部署手册 (Ubuntu / Linux)

## 1. 架构总览
- 后端：FastAPI + APScheduler + SQLite (WAL模式)
- 前端：React + TypeScript + Vite + TanStack Query SPA (构建输出至 `frontend/dist`)
- 包含模块：`sync_console` (数据同步) 与 `keyword_service` (小红书聚光关键词分析)

## 2. 目录规范与生产权限 (非 root 运行)
整个仓库统一部署在 `/opt/automation`：
```bash
# 1. 创建独立低权限系统用户
sudo useradd -r -s /bin/false -d /opt/automation sync-console

# 2. 将整个项目上传或拉取至 /opt/automation
# 确保包含 sync_console, keyword_service, frontend/dist 等完整目录
sudo chown -R sync-console:sync-console /opt/automation

# 3. 授权运行时写目录
sudo chmod 750 /opt/automation
sudo chmod -R 770 /opt/automation/sync_console/data
sudo chmod -R 770 /opt/automation/sync_console/backups
```

## 3. 环境安装与构建
```bash
# 安装 Python 3.9+ 与 Node.js 20+
sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip

# 创建 Python 虚拟环境并安装依赖
cd /opt/automation
python3 -m venv .venv
source .venv/bin/activate
pip install -r sync_console/requirements.txt

# 构建前端产物 (或在 CI/本地构建后打包上传)
cd /opt/automation/frontend
npm install
npm run build
```

## 4. 敏感环境变量配置 (.env)
复制模板并配置：
```bash
cp /opt/automation/sync_console/.env.example /opt/automation/sync_console/.env
chmod 600 /opt/automation/sync_console/.env
```
必须修改以下关键变量：
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：飞书自建应用凭据
- `ACCESS_TOKEN`：系统管理员口令 (禁止使用弱口令)
- `TIMEZONE`：默认 `Asia/Shanghai`

## 5. Systemd 服务配置
```bash
sudo cp /opt/automation/sync_console/sync_console.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sync_console
sudo systemctl start sync_console
sudo systemctl status sync_console
```

## 6. 反向代理与网络安全 (禁止裸暴露 8088 端口)
后端服务监听本地 `127.0.0.1:8088`，生产环境必须通过 Nginx / Caddy 开启 HTTPS：
```nginx
server {
    listen 443 ssl http2;
    server_name sync.yourdomain.com;

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

