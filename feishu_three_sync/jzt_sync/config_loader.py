# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

# 优先加载 jzt_sync 目录下的 .env
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(CURRENT_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

APP_ID = os.getenv("appid") or "cli_a668f3d00db9100e"
APP_SECRET = os.getenv("app_secret") or "LloP4DjXfH1YqE9DL6ObwfVU5uRhI7TF"

FEISHU_SHEET_ZHANGXIAOYI = os.getenv(
    "FEISHU_SHEET_ZHANGXIAOYI", 
    "https://yimeichuanbo.feishu.cn/wiki/ICvnwiVmLi63iYk84xbcj2gZnch"
)
FEISHU_SHEET_SHENXIANSHUANG = os.getenv(
    "FEISHU_SHEET_SHENXIANSHUANG", 
    "https://yimeichuanbo.feishu.cn/wiki/GMsTwebnniW6wDkFRt0ckFrAnTg"
)
