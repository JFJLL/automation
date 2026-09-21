import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKUPS_DIR = BASE_DIR / "backups"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "cli_a668f3d00db9100e")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "LloP4DjXfH1YqE9DL6ObwfVU5uRhI7TF")
SHARED_FOLDER_TOKEN = os.getenv("SHARED_FOLDER_TOKEN", "")
SHARED_FOLDER_NAME = os.getenv("SHARED_FOLDER_NAME", "数据自动同步表")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "admin123456")

ADSTAR_OSS_BASE_URL = os.getenv("ADSTAR_OSS_BASE_URL", "https://redmagic.oss-cn-beijing.aliyuncs.com")
ADSTAR_OSS_OBJECT_KEY = os.getenv("ADSTAR_OSS_OBJECT_KEY", "KOL/adstar_token.txt")
JZT_OSS_OBJECT_KEY = os.getenv("JZT_OSS_OBJECT_KEY", "KOL/jzt_token.txt")
JUGUANG_OSS_OBJECT_KEY = os.getenv("JUGUANG_OSS_OBJECT_KEY", "KOL/juguang_token.txt")

FEISHU_CHAT_ID = os.getenv("FEISHU_CHAT_ID", "")
NOTIFICATION_WEBHOOK = os.getenv("NOTIFICATION_WEBHOOK", "")
NOTIFICATION_POLICY = os.getenv("NOTIFICATION_POLICY", "failed_runs_only")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Shanghai")
DB_PATH = DATA_DIR / "sync_console.db"
