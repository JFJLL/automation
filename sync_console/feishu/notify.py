import json
import re
from typing import Optional
from urllib.parse import urlparse

import requests
from app.config import FEISHU_CHAT_ID, NOTIFICATION_POLICY, NOTIFICATION_WEBHOOK
from feishu.client import FeishuClient


def sanitize_notification_message(msg: str) -> str:
    if not msg:
        return ""
    # Truncate
    text = str(msg)[:1000]
    # Redact query params containing token/secret/key/cookie/pwd
    text = re.sub(r"([?&][a-zA-Z0-9_-]*(?:token|key|secret|password|cookie|auth)[a-zA-Z0-9_-]*=)[^&s]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    # Redact cookie/bearer headers
    text = re.sub(r"(Cookie:\s*)[^\r\n]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"(Bearer\s+)[a-zA-Z0-9_.-]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    return text

class Notifier:
    def __init__(self, client: Optional[FeishuClient] = None):
        self.client = client or FeishuClient()
        self.chat_id = FEISHU_CHAT_ID
        self.webhook = NOTIFICATION_WEBHOOK
        self.policy = NOTIFICATION_POLICY

    def send_group_message(self, chat_id: str, content_text: str) -> bool:
        if not chat_id:
            return False
        clean_text = sanitize_notification_message(content_text)
        try:
            self.client.request("POST", "im/v1/messages?receive_id_type=chat_id", json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": clean_text}, ensure_ascii=False)
            })
            return True
        except Exception as e:
            print(f"Failed to send feishu group message: {e}")
            return False

    def send_webhook_message(self, webhook_url: str, content_text: str) -> bool:
        if not webhook_url:
            return False
        parsed = urlparse(webhook_url)
        if parsed.hostname != "open.feishu.cn":
            print(f"Webhook host rejected (only open.feishu.cn permitted): {parsed.hostname}")
            return False

        clean_text = sanitize_notification_message(content_text)
        try:
            r = requests.post(webhook_url, json={"msg_type": "text", "content": {"text": clean_text}}, timeout=10)
            return r.status_code == 200
        except Exception as e:
            print(f"Failed to send webhook message: {e}")
            return False

    def notify_failure(self, task_name: str, platform: str, error_msg: str, chat_id_override: str = "", webhook_override: str = ""):
        cid = chat_id_override or self.chat_id
        wb = webhook_override or self.webhook
        msg = f"⚠️ [自动同步异常] 任务: {task_name}\n平台: {platform}\n错误: {error_msg}\n请检查登录态或网络。"
        if cid:
            self.send_group_message(cid, msg)
        if wb:
            self.send_webhook_message(wb, msg)

    def create_chat_group(self, group_name: str = "数据同步告警群") -> str:
        res = self.client.request("POST", "im/v1/chats", json={"name": group_name})
        return res.get("chat_id", "")
