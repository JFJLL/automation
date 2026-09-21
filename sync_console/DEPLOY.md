# 广告数据跨平台自动同步服务部署手册 (Ubuntu Server)

## 1. 系统要求
- 操作系统：Ubuntu 20.04 / 22.04+ (纯命令行，无需安装桌面/浏览器)
- Python版本：Python 3.9+

## 2. 快速部署 (服务器端执行)
1. 将 sync_console 目录上传到服务器 /opt/sync_console
2. 安装环境包：
   sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
3. 配置守护服务：
   sudo cp /opt/sync_console/sync_console.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable sync_console
   sudo systemctl start sync_console

## 3. 登录与访问
- 浏览器访问：http://服务器IP:8088
- 默认口令：admin123456

## 4. 凭据与共享文件夹
- 淘宝星河：自动拉取 OSS 凭据。
- 京准通/聚光：将 token.txt / session_headers.json 分别上传至对应 OSS 路径。
- 飞书文件夹：管理员在飞书网页端对【数据自动同步表】共享文件夹勾选一次【组织内获得链接的人可编辑】即可。
