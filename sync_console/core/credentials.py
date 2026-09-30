import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from app.config import (
    ADSTAR_OSS_OBJECT_KEY,
    BASE_DIR,
    JUGUANG_OSS_OBJECT_KEY,
    JUGUANG_OSS_SUBACCOUNT_PREFIX,
    JZT_OSS_OBJECT_KEY,
    OSS_ACCESS_KEY_ID,
    OSS_ACCESS_KEY_SECRET,
    OSS_BUCKET,
    OSS_ENDPOINT,
)
from filelock import FileLock

NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
MAX_PAYLOAD_SIZE = 64 * 1024  # 64KB

def calc_fingerprint(text: str) -> str:
    if not text:
        return ''
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]

class CredentialStore:
    def __init__(self, credentials_dir: Optional[Union[str, Path]] = None):
        if credentials_dir is None:
            configured = os.getenv('CREDENTIALS_DIR', str(BASE_DIR / 'tokens'))
            self.credentials_dir = Path(configured).resolve()
        else:
            self.credentials_dir = Path(credentials_dir).resolve()
        self.credentials_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, name: str, ext: str = '.json') -> Path:
        if not name or not NAME_PATTERN.match(name):
            raise ValueError(f'Invalid credential name: {name}')
        target_path = (self.credentials_dir / f'{name}{ext}').resolve()
        try:
            target_path.relative_to(self.credentials_dir)
        except ValueError:
            raise ValueError(f'Path traversal detected for name: {name}')
        return target_path

    def fingerprint(self, name: str) -> str:
        data = self.get(name)
        if not data:
            return ''
        cookie_val = data.get('cookie') or data.get('token') or ''
        if isinstance(cookie_val, str) and cookie_val:
            return calc_fingerprint(cookie_val)
        return calc_fingerprint(json.dumps(data, sort_keys=True))

    def get(self, name: str) -> Dict[str, Any]:
        json_path = self._resolve_safe_path(name, ext='.json')
        txt_path = self._resolve_safe_path(name, ext='.txt')

        if json_path.exists():
            try:
                content = json_path.read_text(encoding='utf-8')
                if len(content.encode('utf-8')) <= MAX_PAYLOAD_SIZE:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        return parsed
            except Exception:
                pass

        if txt_path.exists():
            try:
                content = txt_path.read_text(encoding='utf-8').strip()
                if len(content.encode('utf-8')) <= MAX_PAYLOAD_SIZE and content:
                    return {'cookie': content, 'token': content}
            except Exception:
                pass

        data = self._fetch_from_oss(name)
        if data:
            try:
                self.set(name, data)
            except Exception:
                pass
            return data

        return {}

    def set(self, name: str, data: Union[Dict[str, Any], str]) -> None:
        json_path = self._resolve_safe_path(name, ext='.json')
        lock_path = json_path.with_suffix('.lock')

        if isinstance(data, str):
            payload_dict = {'cookie': data.strip(), 'token': data.strip()}
        else:
            payload_dict = dict(data)

        content = json.dumps(payload_dict, ensure_ascii=False, indent=2)
        encoded = content.encode('utf-8')
        if len(encoded) > MAX_PAYLOAD_SIZE:
            raise ValueError(f'Payload size exceeds maximum allowed {MAX_PAYLOAD_SIZE} bytes.')

        with FileLock(str(lock_path), timeout=10):
            tmp_path = json_path.with_suffix('.tmp')
            with open(tmp_path, 'wb') as f:
                f.write(encoded)
                f.flush()
                os.fsync(f.fileno())

            if os.name != 'nt':
                try:
                    os.chmod(tmp_path, 0o600)
                except OSError:
                    pass

            os.replace(tmp_path, json_path)

    def _fetch_from_oss(self, name: str) -> Optional[Dict[str, Any]]:
        if not (OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET and OSS_BUCKET):
            return None

        object_key = self._map_name_to_oss_key(name)
        if not object_key:
            return None

        try:
            import oss2
            auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
            endpoint = OSS_ENDPOINT
            if not endpoint.startswith('http'):
                endpoint = f'https://{endpoint}'
            bucket = oss2.Bucket(auth, endpoint, OSS_BUCKET)

            obj = bucket.get_object(object_key)
            content_bytes = obj.read(MAX_PAYLOAD_SIZE + 1)
            if len(content_bytes) > MAX_PAYLOAD_SIZE:
                return None

            raw_text = content_bytes.decode('utf-8', errors='ignore').strip()
            if not raw_text:
                return None

            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            return {'cookie': raw_text, 'token': raw_text}
        except Exception:
            return None

    def _map_name_to_oss_key(self, name: str) -> Optional[str]:
        if name in ('jzt', 'jzt_token'):
            return JZT_OSS_OBJECT_KEY
        if name in ('adstar', 'taobao'):
            return ADSTAR_OSS_OBJECT_KEY
        if name in ('juguang', 'juguang_token'):
            return JUGUANG_OSS_OBJECT_KEY
        if name in ('lingxi', 'lingxi_cookie'):
            prefix = (JUGUANG_OSS_SUBACCOUNT_PREFIX or 'token/').rstrip('/')
            return f'{prefix}/lingxi_cookie.txt'
        if name.startswith('subaccount_'):
            prefix = (JUGUANG_OSS_SUBACCOUNT_PREFIX or 'token/').rstrip('/')
            sub_id = name.replace('subaccount_', '')
            return f'{prefix}/{sub_id}.txt'
        return None

default_credential_store = CredentialStore()
