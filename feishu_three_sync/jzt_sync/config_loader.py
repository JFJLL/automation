# -*- coding: utf-8 -*-
import os

from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(CURRENT_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

APP_ID = os.getenv('appid') or os.getenv('FEISHU_APP_ID')
APP_SECRET = os.getenv('app_secret') or os.getenv('FEISHU_APP_SECRET')

if not APP_ID or not APP_SECRET:
    # Notice: In production or test environments, these must be supplied via env or .env
    pass

def get_feishu_credentials():
    app_id = os.getenv('appid') or os.getenv('FEISHU_APP_ID')
    app_secret = os.getenv('app_secret') or os.getenv('FEISHU_APP_SECRET')
    if not app_id or not app_secret:
        raise ValueError('Missing Feishu credentials: FEISHU_APP_ID / FEISHU_APP_SECRET (or appid / app_secret) must be set in environment.')
    return app_id, app_secret

FEISHU_SHEET_ZHANGXIAOYI = os.getenv(
    'FEISHU_SHEET_ZHANGXIAOYI', 
    'https://yimeichuanbo.feishu.cn/wiki/ICvnwiVmLi63iYk84xbcj2gZnch'
)
FEISHU_SHEET_SHENXIANSHUANG = os.getenv(
    'FEISHU_SHEET_SHENXIANSHUANG', 
    'https://yimeichuanbo.feishu.cn/wiki/GMsTwebnniW6wDkFRt0ckFrAnTg'
)
