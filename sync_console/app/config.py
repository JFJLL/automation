import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKUPS_DIR = BASE_DIR / "backups"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "").strip()
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "").strip()
SHARED_FOLDER_TOKEN = os.getenv("SHARED_FOLDER_TOKEN", "").strip()
SHARED_FOLDER_NAME = os.getenv("SHARED_FOLDER_NAME", "数据自动同步表").strip()
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "").strip()
AUTH_MODE = os.getenv("AUTH_MODE", "token").strip().lower()

OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "https://oss-cn-beijing.aliyuncs.com").strip()
OSS_BUCKET = os.getenv("OSS_BUCKET", "redmagic").strip()
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "").strip()
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "").strip()

ADSTAR_OSS_BASE_URL = os.getenv("ADSTAR_OSS_BASE_URL", "https://redmagic.oss-cn-beijing.aliyuncs.com")
ADSTAR_OSS_OBJECT_KEY = os.getenv("ADSTAR_OSS_OBJECT_KEY", "KOL/adstar.txt")
JZT_OSS_OBJECT_KEY = os.getenv("JZT_OSS_OBJECT_KEY", "KOL/jzt_token.txt")
JUGUANG_OSS_OBJECT_KEY = os.getenv("JUGUANG_OSS_OBJECT_KEY", "KOL/juguang_token.txt")
JUGUANG_OSS_SUBACCOUNT_PREFIX = os.getenv("JUGUANG_OSS_SUBACCOUNT_PREFIX", "token/")

FEISHU_CHAT_ID = os.getenv("FEISHU_CHAT_ID", "")
NOTIFICATION_WEBHOOK = os.getenv("NOTIFICATION_WEBHOOK", "")
NOTIFICATION_POLICY = os.getenv("NOTIFICATION_POLICY", "failed_runs_only")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Shanghai")
DB_PATH = DATA_DIR / "sync_console.db"
