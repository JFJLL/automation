import json
import logging
import re
from typing import Any, Dict

from core.business_time import now_business_tz


class SensitiveDataFilter(logging.Filter):
    REDACT_PATTERNS = [
        re.compile(r"([?&][a-zA-Z0-9_-]*(?:token|key|secret|password|cookie|auth)[a-zA-Z0-9_-]*=)[^&\s]+", re.IGNORECASE),
        re.compile(r"(Cookie:\s*)[^\r\n]+", re.IGNORECASE),
        re.compile(r"(Bearer\s+)[a-zA-Z0-9_.-]+", re.IGNORECASE),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pat in self.REDACT_PATTERNS:
                record.msg = pat.sub(r"\1[REDACTED]", record.msg)
        return True

class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {
            "timestamp": now_business_tz().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Extra fields if present
        for field in ("task_id", "run_id", "platform"):
            val = getattr(record, field, None)
            if val is not None:
                data[field] = val

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)

def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        handler.addFilter(SensitiveDataFilter())
        root.addHandler(handler)
