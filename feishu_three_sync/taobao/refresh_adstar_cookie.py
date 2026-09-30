#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refresh adstar.alimama.com cookies by opening a real browser login session.

The script uses Chrome DevTools Protocol through a dedicated browser profile.
It does not print cookie values. It overwrites adstar.txt with a single JSON
cookie object that taobaoxinghe_scraper.py can already parse.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_URL = "https://adstar.alimama.com/"
DEFAULT_PORTAL_URL = "https://adstar.alimama.com/portal/v2/pages/home/index.htm"
DEFAULT_OUTPUT = SCRIPT_DIR / "adstar.txt"
DEFAULT_PROFILE_DIR = SCRIPT_DIR / ".adstar_chrome_profile"
DEFAULT_DOMAINS = ("alimama.com", "taobao.com", "tmall.com")
DEFAULT_CLEAR_ORIGINS = (
    "https://adstar.alimama.com",
    "https://alimama.com",
    "https://www.alimama.com",
    "https://login.taobao.com",
    "https://www.taobao.com",
    "https://taobao.com",
    "https://tmall.com",
    "https://www.tmall.com",
)
REQUIRED_COOKIE = "_tb_token_"
LOGIN_COOKIE_CANDIDATES = ("cookie2", "cookie2_alimama", "t_alimama", "login", "sgcookie")
DEFAULT_MIN_FIELDS = 8
DEFAULT_CLEAR_DELAY_SECONDS = 5


class CookieRefreshError(RuntimeError):
    pass


def load_env_file(path: Path = SCRIPT_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def find_browser(explicit_path: str = "") -> Path:
    candidates: List[str] = []
    if explicit_path:
        candidates.append(explicit_path)
    candidates.extend(
        [
            env_first("ADSTAR_BROWSER_PATH", "BROWSER_PATH", "CHROME_PATH"),
            shutil.which("chrome") or "",
            shutil.which("chrome.exe") or "",
            shutil.which("msedge") or "",
            shutil.which("msedge.exe") or "",
        ]
    )

    program_files = [
        os.environ.get("PROGRAMFILES", ""),
        os.environ.get("PROGRAMFILES(X86)", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for base in program_files:
        if not base:
            continue
        candidates.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    for base in program_files:
        if not base:
            continue
        candidates.append(str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    raise CookieRefreshError("Chrome or Edge was not found. Pass --browser with the browser exe path.")


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(url: str, timeout: float = 3.0) -> Any:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_devtools(port: int, timeout_seconds: int) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error: Optional[BaseException] = None
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            data = http_json(url, timeout=2.0)
            if data.get("Browser"):
                return data
        except BaseException as exc:  # DevTools is not ready yet.
            last_error = exc
        time.sleep(0.5)
    raise CookieRefreshError(f"Browser DevTools did not start in time: {last_error}")


def mark_profile_exited_cleanly(profile_dir: Path) -> None:
    for path in (profile_dir / "Default" / "Preferences", profile_dir / "Local State"):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        profile = data.setdefault("profile", {})
        if isinstance(profile, dict):
            profile["exit_type"] = "Normal"
            profile["exited_cleanly"] = True
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        except OSError:
            continue


def launch_browser(browser: Path, profile_dir: Path, port: int, url: str) -> subprocess.Popen:
    profile_dir.mkdir(parents=True, exist_ok=True)
    mark_profile_exited_cleanly(profile_dir)
    args = [
        str(browser),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--disable-default-browser-check",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "--new-window",
        url,
    ]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class WebSocket:
    def __init__(self, sock: socket.socket):
        self.sock = sock

    @classmethod
    def connect(cls, ws_url: str, timeout: float = 5.0) -> "WebSocket":
        parsed = urlparse(ws_url)
        if parsed.scheme != "ws":
            raise CookieRefreshError(f"Only ws:// DevTools URLs are supported: {ws_url}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        status = response.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            sock.close()
            raise CookieRefreshError(f"DevTools WebSocket handshake failed: {status.decode('latin1', 'replace')}")
        accept_expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if accept_expected not in response.decode("latin1", "replace"):
            sock.close()
            raise CookieRefreshError("DevTools WebSocket handshake returned an invalid accept key.")
        sock.settimeout(30)
        return cls(sock)

    def close(self) -> None:
        try:
            self._send_frame(b"", opcode=0x8)
        except OSError:
            pass
        self.sock.close()

    def send_text(self, text: str) -> None:
        self._send_frame(text.encode("utf-8"), opcode=0x1)

    def recv_text(self) -> str:
        chunks: List[bytes] = []
        while True:
            opcode, payload, fin = self._read_frame()
            if opcode == 0x8:
                raise CookieRefreshError("DevTools WebSocket closed.")
            if opcode == 0x9:
                self._send_frame(payload, opcode=0xA)
                continue
            if opcode in (0x1, 0x0):
                chunks.append(payload)
                if fin:
                    return b"".join(chunks).decode("utf-8")

    def _send_frame(self, payload: bytes, opcode: int) -> None:
        first = 0x80 | opcode
        length = len(payload)
        header = bytearray([first])
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _read_exact(self, length: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self.sock.recv(length - len(chunks))
            if not chunk:
                raise CookieRefreshError("DevTools WebSocket ended unexpectedly.")
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_frame(self) -> Tuple[int, bytes, bool]:
        first, second = self._read_exact(2)
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload, fin


class CdpSession:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.next_id = 1

    def close(self) -> None:
        self.websocket.close()

    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        call_id = self.next_id
        self.next_id += 1
        message: Dict[str, Any] = {"id": call_id, "method": method}
        if params:
            message["params"] = params
        self.websocket.send_text(json.dumps(message, separators=(",", ":")))
        while True:
            raw = self.websocket.recv_text()
            data = json.loads(raw)
            if data.get("id") != call_id:
                continue
            if "error" in data:
                raise CookieRefreshError(f"CDP {method} failed: {data['error']}")
            return data.get("result") or {}


def list_targets(port: int) -> List[Dict[str, Any]]:
    try:
        data = http_json(f"http://127.0.0.1:{port}/json/list", timeout=3.0)
    except BaseException:
        return []
    return data if isinstance(data, list) else []


def choose_page_target(targets: Iterable[Dict[str, Any]], preferred_host: str) -> Optional[Dict[str, Any]]:
    pages = [target for target in targets if target.get("type") == "page" and target.get("webSocketDebuggerUrl")]
    if not pages:
        return None
    preferred_host = preferred_host.lower()
    for target in pages:
        if preferred_host and preferred_host in str(target.get("url", "")).lower():
            return target
    return pages[0]


def open_page_session(port: int, preferred_host: str) -> CdpSession:
    target = choose_page_target(list_targets(port), preferred_host)
    if not target:
        raise CookieRefreshError("No browser page target was found.")
    websocket = WebSocket.connect(str(target["webSocketDebuggerUrl"]))
    return CdpSession(websocket)


def domain_matches(domain: str, domains: Iterable[str]) -> bool:
    normalized = domain.lower().lstrip(".")
    for allowed in domains:
        allowed = allowed.lower().lstrip(".")
        if normalized == allowed or normalized.endswith("." + allowed):
            return True
    return False


def cookie_score(cookie: Dict[str, Any]) -> Tuple[int, int]:
    domain = str(cookie.get("domain") or "").lower().lstrip(".")
    if "adstar.alimama.com" in domain:
        domain_score = 0
    elif domain == "alimama.com" or domain.endswith(".alimama.com"):
        domain_score = 1
    elif domain == "taobao.com" or domain.endswith(".taobao.com"):
        domain_score = 2
    elif domain == "tmall.com" or domain.endswith(".tmall.com"):
        domain_score = 3
    else:
        domain_score = 4
    expires = cookie.get("expires") or 0
    try:
        expires_score = -int(float(expires))
    except (TypeError, ValueError):
        expires_score = 0
    return domain_score, expires_score


def flatten_cookies(cookies: Iterable[Dict[str, Any]], domains: Iterable[str]) -> Dict[str, str]:
    best: Dict[str, Tuple[Tuple[int, int], str]] = {}
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = cookie.get("value")
        domain = str(cookie.get("domain") or "")
        if not name or value in (None, ""):
            continue
        if domains and not domain_matches(domain, domains):
            continue
        score = cookie_score(cookie)
        if name not in best or score < best[name][0]:
            best[name] = (score, str(value))
    return {name: value for name, (_score, value) in sorted(best.items())}


def read_cookie_dict(port: int, preferred_host: str, domains: Tuple[str, ...]) -> Dict[str, str]:
    try:
        session = open_page_session(port, preferred_host)
    except CookieRefreshError:
        return {}
    try:
        session.call("Network.enable")
        result = session.call("Network.getAllCookies")
        cookies = result.get("cookies") or []
        if not isinstance(cookies, list):
            return {}
        return flatten_cookies(cookies, domains)
    finally:
        session.close()


def clear_login_state(
    port: int,
    preferred_host: str,
    url: str,
    origins: Tuple[str, ...],
    *,
    clear_storage: bool = False,
) -> None:
    session = open_page_session(port, preferred_host)
    try:
        session.call("Network.enable")
        session.call("Page.enable")
        session.call("Network.clearBrowserCookies")
        session.call("Network.clearBrowserCache")
        if clear_storage:
            for origin in origins:
                try:
                    session.call(
                        "Storage.clearDataForOrigin",
                        {
                            "origin": origin,
                            "storageTypes": "cookies,local_storage,session_storage,indexeddb,cache_storage",
                        },
                    )
                except CookieRefreshError:
                    pass
        session.call("Page.navigate", {"url": url})
    finally:
        session.close()


def eval_expr(session: CdpSession, expression: str) -> Any:
    result = session.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        },
    )
    remote = result.get("result") or {}
    return remote.get("value")


def visible_login_iframe_rect(session: CdpSession) -> Optional[Dict[str, int]]:
    expression = r"""
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const iframe = [...document.querySelectorAll('iframe')]
    .find((el) => visible(el) && String(el.src || '').includes('login.taobao.com'));
  if (!iframe) return null;
  const r = iframe.getBoundingClientRect();
  return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
})()
"""
    value = eval_expr(session, expression)
    if not isinstance(value, dict):
        return None
    try:
        return {key: int(value[key]) for key in ("x", "y", "w", "h")}
    except (KeyError, TypeError, ValueError):
        return None


def wait_for_login_iframe(
    *,
    port: int,
    preferred_host: str,
    timeout_seconds: int,
) -> Dict[str, int]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        session = open_page_session(port, preferred_host)
        try:
            session.call("Runtime.enable")
            rect = visible_login_iframe_rect(session)
            if rect:
                return rect
        finally:
            session.close()
        time.sleep(1)
    raise CookieRefreshError("Timed out waiting for the Taobao login iframe.")


def find_login_iframe_target(port: int, timeout_seconds: int) -> Optional[Dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        targets = list_targets(port)
        for target in targets:
            if (
                target.get("type") == "iframe"
                and "login.taobao.com" in str(target.get("url") or "")
                and target.get("webSocketDebuggerUrl")
            ):
                return target
        time.sleep(1)
    return None


def fill_login_form_dom(port: int, username: str, password: str, timeout_seconds: int) -> bool:
    target = find_login_iframe_target(port, timeout_seconds)
    if not target:
        return False
    try:
        websocket = WebSocket.connect(str(target["webSocketDebuggerUrl"]))
    except BaseException:
        return False
    session = CdpSession(websocket)
    try:
        session.call("Runtime.enable")
        controls = eval_expr(
            session,
            r"""
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const textOf = (el) => (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim();
  const inputs = [...document.querySelectorAll('input')].filter(visible);
  const userInput = inputs.find((el) => {
    const haystack = [el.type, el.name, el.id, el.placeholder, el.getAttribute('aria-label')].join(' ');
    return el.type !== 'password' && /(账号|账户|邮箱|手机|会员|登录名|username|login|user)/i.test(haystack);
  }) || inputs.find((el) => el.type !== 'password' && el.type !== 'hidden');
  const passInput = inputs.find((el) => el.type === 'password');
  const buttons = [...document.querySelectorAll('button,input[type=submit],a,[role=button]')].filter(visible);
  const loginButton = buttons.find((el) => {
    const text = (textOf(el) || String(el.value || '')).replace(/\s+/g, '');
    const type = String(el.getAttribute('type') || '').toLowerCase();
    const r = el.getBoundingClientRect();
    return (type === 'submit' || text === '登录' || /^login$/i.test(text)) && r.width >= 120 && r.height >= 30;
  }) || buttons.find((el) => (textOf(el) || String(el.value || '')).replace(/\s+/g, '') === '登录');

  if (!userInput || !passInput || !loginButton) {
    return {
      ok: false,
      reason: 'missing_control',
      inputCount: inputs.length,
      buttonTexts: buttons.map(textOf).slice(0, 10),
    };
  }
  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
  };
  return {
    ok: true,
    user: rectOf(userInput),
    pass: rectOf(passInput),
    login: rectOf(loginButton),
    buttonText: textOf(loginButton),
  };
})()
"""
        )
        if not isinstance(controls, dict) or not controls.get("ok"):
            return False

        user_rect = controls.get("user")
        pass_rect = controls.get("pass")
        login_rect = controls.get("login")
        if not all(isinstance(item, dict) for item in (user_rect, pass_rect, login_rect)):
            return False

        def center(rect: Dict[str, Any]) -> Tuple[int, int]:
            return int(rect["x"] + rect["w"] / 2), int(rect["y"] + rect["h"] / 2)

        session.call("Input.setIgnoreInputEvents", {"ignore": False})
        click_point(session, *center(user_rect))
        clear_active_text(session)
        type_text(session, username)
        time.sleep(0.3)
        click_point(session, *center(pass_rect))
        clear_active_text(session)
        type_text(session, password)
        time.sleep(0.3)

        result = eval_expr(
            session,
            r"""
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const inputs = [...document.querySelectorAll('input')].filter(visible);
  const userInput = inputs.find((el) => el.type !== 'password' && el.type !== 'hidden');
  const passInput = inputs.find((el) => el.type === 'password');
  return {
    ok: Boolean(userInput && passInput),
    userLength: userInput ? userInput.value.length : null,
    passLength: passInput ? passInput.value.length : null,
  };
})()
""",
        )
        if isinstance(result, dict):
            print(
                "Login iframe input: "
                f"ok={bool(result.get('ok'))}, "
                f"user_len={result.get('userLength')}, "
                f"pass_len={result.get('passLength')}",
                flush=True,
            )
            if result.get("userLength") != len(username) or result.get("passLength") != len(password):
                return False
        click_point(session, *center(login_rect))
        return True
    finally:
        session.close()


def click_point(session: CdpSession, x: int, y: int) -> None:
    session.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    session.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    session.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


def clear_active_text(session: CdpSession) -> None:
    session.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17, "nativeVirtualKeyCode": 17})
    session.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "nativeVirtualKeyCode": 65, "modifiers": 2})
    session.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "nativeVirtualKeyCode": 65, "modifiers": 2})
    session.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17, "nativeVirtualKeyCode": 17})
    session.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8, "nativeVirtualKeyCode": 8})
    session.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8, "nativeVirtualKeyCode": 8})


def key_code_for_char(char: str) -> int:
    if len(char) != 1 or not char.isascii():
        return 0
    upper = char.upper()
    if "A" <= upper <= "Z" or "0" <= upper <= "9":
        return ord(upper)
    return 0


def type_text(session: CdpSession, text: str) -> None:
    for char in text:
        key_code = key_code_for_char(char)
        session.call(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown",
                "key": char,
                "text": char,
                "unmodifiedText": char,
                "windowsVirtualKeyCode": key_code,
                "nativeVirtualKeyCode": key_code,
            },
        )
        session.call(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": char,
                "windowsVirtualKeyCode": key_code,
                "nativeVirtualKeyCode": key_code,
            },
        )
        time.sleep(0.04)


def visible_login_status(port: int, preferred_host: str) -> str:
    targets = [
        str(target.get("url") or "")
        for target in list_targets(port)
        if target.get("type") == "iframe" and "login.taobao.com" in str(target.get("url") or "")
    ]
    if not targets:
        return ""
    session = open_page_session(port, preferred_host)
    try:
        session.call("Runtime.enable")
        if not visible_login_iframe_rect(session):
            return ""
    except CookieRefreshError:
        return ""
    finally:
        session.close()
    if any("login_unusual" in url or "iv_check" in url for url in targets):
        return "verification_required"
    if login_iframe_has_text(port, "快速进入", 1):
        return "quick_enter_available"
    return "login_form_visible"


def login_iframe_has_text(port: int, text: str, timeout_seconds: int) -> bool:
    target = find_login_iframe_target(port, timeout_seconds)
    if not target:
        return False
    try:
        websocket = WebSocket.connect(str(target["webSocketDebuggerUrl"]))
    except BaseException:
        return False
    session = CdpSession(websocket)
    try:
        session.call("Runtime.enable")
        state = eval_expr(
            session,
            r"""
((targetText) => {
  const body = document.body ? document.body.innerText : '';
  return body.includes(targetText);
})
"""
            + f"({json.dumps(text, ensure_ascii=False)})",
        )
        return bool(state)
    finally:
        session.close()


def click_login_iframe_text_control(port: int, text: str, timeout_seconds: int) -> bool:
    target = find_login_iframe_target(port, timeout_seconds)
    if not target:
        return False
    try:
        websocket = WebSocket.connect(str(target["webSocketDebuggerUrl"]))
    except BaseException:
        return False
    session = CdpSession(websocket)
    try:
        session.call("Runtime.enable")
        rect = eval_expr(
            session,
            r"""
((targetText) => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const textOf = (el) => (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim();
  const candidates = [...document.querySelectorAll('*')]
    .filter((el) => visible(el) && textOf(el).includes(targetText))
    .map((el) => {
      const r = el.getBoundingClientRect();
      return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: textOf(el).slice(0, 80)};
    })
    .sort((a, b) => (a.w * a.h) - (b.w * b.h));
  return candidates[0] || null;
})
"""
            + f"({json.dumps(text, ensure_ascii=False)})",
        )
        if isinstance(rect, dict):
            click_point(session, int(rect["x"] + rect["w"] / 2), int(rect["y"] + rect["h"] / 2))
            return True
        if text == "快速进入" and login_iframe_has_text(port, text, 1):
            size = eval_expr(session, "(() => ({width: innerWidth, height: innerHeight}))()")
            if isinstance(size, dict):
                click_point(session, int(float(size.get("width") or 350) * 0.50), int(float(size.get("height") or 400) * 0.63))
                return True
        return False
    finally:
        session.close()


def login_iframe_point(rect: Dict[str, int], x_ratio: float, y_ratio: float) -> Tuple[int, int]:
    return (
        int(rect["x"] + rect["w"] * x_ratio),
        int(rect["y"] + rect["h"] * y_ratio),
    )


def fill_login_form(
    *,
    port: int,
    preferred_host: str,
    username: str,
    password: str,
    timeout_seconds: int,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        attempt_timeout = max(1, min(5, int(deadline - time.time())))
        if click_login_iframe_text_control(port, "快速进入", attempt_timeout):
            print("Login iframe quick-enter clicked.", flush=True)
            return
        if fill_login_form_dom(port, username, password, attempt_timeout):
            return
        time.sleep(1)
    print("Login iframe input was unavailable; falling back to coordinate input.", flush=True)
    rect = wait_for_login_iframe(
        port=port,
        preferred_host=preferred_host,
        timeout_seconds=timeout_seconds,
    )
    session = open_page_session(port, preferred_host)
    try:
        session.call("Input.setIgnoreInputEvents", {"ignore": False})
        user_x, user_y = login_iframe_point(rect, 0.50, 0.25)
        pass_x, pass_y = login_iframe_point(rect, 0.50, 0.405)
        login_x, login_y = login_iframe_point(rect, 0.50, 0.58)
        click_point(session, user_x, user_y)
        type_text(session, username)
        time.sleep(0.4)
        click_point(session, pass_x, pass_y)
        type_text(session, password)
        time.sleep(0.4)
        click_point(session, login_x, login_y)
    finally:
        session.close()


def visible_text_control_rect(session: CdpSession, text: str) -> Optional[Dict[str, int]]:
    expression = (
        r"""
((targetText) => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const textOf = (el) => (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim();
  const candidates = [...document.querySelectorAll('*')]
    .filter((el) => visible(el) && textOf(el).includes(targetText))
    .sort((a, b) => {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      return (ar.width * ar.height) - (br.width * br.height);
    });
  const el = candidates[0];
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: textOf(el).slice(0, 80)};
})
"""
        + f"({json.dumps(text, ensure_ascii=False)})"
    )
    value = eval_expr(session, expression)
    if not isinstance(value, dict):
        return None
    try:
        return {key: int(value[key]) for key in ("x", "y", "w", "h")}
    except (KeyError, TypeError, ValueError):
        return None


def navigate_page(port: int, preferred_host: str, url: str) -> None:
    session = open_page_session(port, preferred_host)
    try:
        session.call("Page.enable")
        session.call("Page.navigate", {"url": url})
    finally:
        session.close()


def click_visible_text_control(
    *,
    port: int,
    preferred_host: str,
    text: str,
    timeout_seconds: int,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        session = open_page_session(port, preferred_host)
        try:
            session.call("Runtime.enable")
            rect = visible_text_control_rect(session, text)
            if rect:
                click_point(session, int(rect["x"] + rect["w"] / 2), int(rect["y"] + rect["h"] / 2))
                return True
        finally:
            session.close()
        time.sleep(1)
    return False


def page_text_state(session: CdpSession) -> Dict[str, Any]:
    value = eval_expr(
        session,
        r"""
(() => ({
  href: location.href,
  title: document.title,
  body: document.body ? document.body.innerText.slice(0, 2000) : '',
  width: innerWidth,
  height: innerHeight,
}))()
""",
    )
    return value if isinstance(value, dict) else {}


def page_looks_like_home(state: Dict[str, Any]) -> bool:
    body = str(state.get("body") or "")
    href = str(state.get("href") or "")
    return (
        "/portal/v2/pages/home/" in href
        or "我的星河" in body
        or "发布订单" in body
        or "数据洞察" in body
    )


def click_top_quick_enter_control(
    session: CdpSession,
    *,
    wait_seconds: int = 3,
) -> bool:
    result = eval_expr(
        session,
        r"""
(() => {
  const body = document.body ? document.body.innerText : '';
  const shouldClick = body.includes('快速进入')
    && (body.includes('确认登录') || location.href.includes('/index.htm?forward='));
  if (!shouldClick) return {clicked: false, reason: 'not_visible'};
  const x = Math.floor(innerWidth * 0.764);
  const y = Math.floor(innerHeight * 0.294);
  const el = document.elementFromPoint(x, y);
  if (!el) return {clicked: false, reason: 'no_element', x, y};
  el.click();
  return {
    clicked: true,
    x,
    y,
    tag: el.tagName,
    text: (el.innerText || el.textContent || el.value || '').trim().slice(0, 80),
  };
})()
""",
    )
    if not isinstance(result, dict) or not result.get("clicked"):
        return False
    time.sleep(max(0, wait_seconds))
    return True


def click_employee_login_control(
    *,
    port: int,
    preferred_host: str,
    timeout_seconds: int,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        session = open_page_session(port, preferred_host)
        try:
            session.call("Runtime.enable")
            if click_top_quick_enter_control(session):
                state = page_text_state(session)
                if page_looks_like_home(state):
                    return True
            state = page_text_state(session)
            if page_looks_like_home(state):
                return True
            rect = visible_text_control_rect(session, "员工登录")
            if rect:
                click_point(session, int(rect["x"] + rect["w"] / 2), int(rect["y"] + rect["h"] / 2))
                time.sleep(3)
                state = page_text_state(session)
                if page_looks_like_home(state):
                    return True
            href = str(state.get("href") or "")
            body = str(state.get("body") or "")
            if "/role/picker/" in href or "员工登录" in body:
                width = int(float(state.get("width") or 0))
                height = int(float(state.get("height") or 0))
                if width > 0 and height > 0:
                    click_point(session, int(width * 0.50), int(height * 0.59))
                    time.sleep(3)
                    state = page_text_state(session)
                    if page_looks_like_home(state):
                        return True
        finally:
            session.close()
        time.sleep(1)
    return False


def run_post_login_steps(
    *,
    port: int,
    preferred_host: str,
    portal_url: str,
    quick_enter_clicks: int,
    timeout_seconds: int,
    final_wait_seconds: int,
) -> bool:
    if not portal_url:
        return True
    print(f"Opening portal page: {portal_url}", flush=True)
    navigate_page(port, preferred_host, portal_url)
    time.sleep(3)

    employee_clicked = False
    for index in range(max(1, quick_enter_clicks)):
        session = open_page_session(port, preferred_host)
        try:
            session.call("Runtime.enable")
            if click_top_quick_enter_control(session):
                state = page_text_state(session)
                if page_looks_like_home(state):
                    employee_clicked = True
                    break
            state = page_text_state(session)
            if page_looks_like_home(state):
                employee_clicked = True
                break
        finally:
            session.close()

        clicked = False
        if index < max(0, quick_enter_clicks):
            clicked = click_visible_text_control(
                port=port,
                preferred_host=preferred_host,
                text="快速进入",
                timeout_seconds=max(3, min(timeout_seconds, 10)),
            )
            if not clicked:
                clicked = click_login_iframe_text_control(port, "快速进入", 3)
            print(f"Quick enter click {index + 1}/{quick_enter_clicks}: {'clicked' if clicked else 'not found'}", flush=True)
            if clicked:
                time.sleep(3)

        employee_clicked = click_employee_login_control(
            port=port,
            preferred_host=preferred_host,
            timeout_seconds=max(5, min(timeout_seconds, 15)),
        )
        if employee_clicked:
            break

    print(f"Employee login: {'clicked/ready' if employee_clicked else 'not found'}", flush=True)
    if final_wait_seconds > 0:
        print(f"Waiting {final_wait_seconds}s after portal steps.", flush=True)
        time.sleep(final_wait_seconds)
    return employee_clicked


def wait_for_login_cookies(
    *,
    port: int,
    preferred_host: str,
    domains: Tuple[str, ...],
    min_fields: int,
    timeout_seconds: int,
) -> Dict[str, str]:
    deadline = time.time() + timeout_seconds
    last_count = 0
    last_status = ""
    while time.time() < deadline:
        cookies = read_cookie_dict(port, preferred_host, domains)
        last_count = len(cookies)
        has_login_marker = any(cookies.get(name) for name in LOGIN_COOKIE_CANDIDATES)
        status = visible_login_status(port, preferred_host)
        if cookies.get(REQUIRED_COOKIE) and has_login_marker and len(cookies) >= min_fields and not status:
            return cookies
        if status and status != last_status:
            if status == "verification_required":
                print(
                    "Taobao verification is visible in Chrome. Complete SMS/identity verification there; waiting...",
                    flush=True,
                )
            elif status == "quick_enter_available":
                print("Taobao quick-enter is visible in Chrome; clicking it.", flush=True)
            else:
                print("Taobao login form is still visible in Chrome; waiting...", flush=True)
            last_status = status
        if status == "quick_enter_available":
            click_login_iframe_text_control(port, "快速进入", 3)
            time.sleep(3)
            continue
        remaining = max(0, int(deadline - time.time()))
        print(
            "Waiting for login completion... "
            f"parsed={last_count}, token={bool(cookies.get(REQUIRED_COOKIE))}, "
            f"login_marker={has_login_marker}, status={status or 'ready'}, "
            f"min_fields={min_fields}, remaining={remaining}s",
            flush=True,
        )
        time.sleep(3)
    raise CookieRefreshError(
        f"Timed out waiting for complete login. Last parsed cookie count: {last_count}; "
        f"last status: {last_status or 'unknown'}"
    )


def write_cookie_file(path: Path, cookies: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cookies, ensure_ascii=False, separators=(",", ":"))
    temp_path = path.with_name(path.name + ".tmp")
    if path.exists():
        backup_path = path.with_name(path.name + ".bak")
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    temp_path.write_text(payload + "\n", encoding="utf-8")
    temp_path.replace(path)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open browser login and refresh Taobao Xinghe adstar.txt cookies.")
    parser.add_argument("--url", default=env_first("ADSTAR_LOGIN_URL", "TAOBAOXINGHE_LOGIN_URL") or DEFAULT_URL)
    parser.add_argument("--portal-url", default=env_first("ADSTAR_PORTAL_URL", "TAOBAOXINGHE_PORTAL_URL") or DEFAULT_PORTAL_URL)
    parser.add_argument("--output", default=env_first("ADSTAR_COOKIE_OUTPUT", "TAOBAOXINGHE_COOKIE_OUTPUT") or str(DEFAULT_OUTPUT))
    parser.add_argument("--profile-dir", default=env_first("ADSTAR_COOKIE_PROFILE_DIR") or str(DEFAULT_PROFILE_DIR))
    parser.add_argument("--browser", default=env_first("ADSTAR_BROWSER_PATH", "BROWSER_PATH", "CHROME_PATH"))
    parser.add_argument("--port", type=int, default=0, help="DevTools port. Default chooses a free local port.")
    parser.add_argument("--timeout", type=int, default=int(env_first("ADSTAR_COOKIE_TIMEOUT") or "300"))
    parser.add_argument("--min-fields", type=int, default=int(env_first("ADSTAR_COOKIE_MIN_FIELDS") or str(DEFAULT_MIN_FIELDS)))
    parser.add_argument("--username", default=env_first("ADSTAR_USERNAME", "TAOBAO_USERNAME", "TAOBAOXINGHE_USERNAME"))
    parser.add_argument("--password", default=env_first("ADSTAR_PASSWORD", "TAOBAO_PASSWORD", "TAOBAOXINGHE_PASSWORD"))
    parser.add_argument("--manual-login", action="store_true", help="Do not fill username/password automatically.")
    parser.add_argument("--skip-post-login", action="store_true", help="Skip portal quick-enter steps after login cookies appear.")
    parser.add_argument("--quick-enter-clicks", type=int, default=int(env_first("ADSTAR_QUICK_ENTER_CLICKS") or "2"))
    parser.add_argument("--post-login-wait", type=int, default=int(env_first("ADSTAR_POST_LOGIN_WAIT") or "10"))
    parser.add_argument("--reuse-session", action="store_true", help="Do not clear existing browser cookies first.")
    parser.add_argument("--clear-storage", action="store_true", help="Also clear local/session storage; default matches RPA and clears cookies only.")
    parser.add_argument(
        "--clear-delay",
        type=int,
        default=int(env_first("ADSTAR_COOKIE_CLEAR_DELAY") or str(DEFAULT_CLEAR_DELAY_SECONDS)),
        help="Seconds to wait after opening the page before clearing cookies.",
    )
    parser.add_argument(
        "--domains",
        default=",".join(DEFAULT_DOMAINS),
        help="Comma-separated cookie domains to export.",
    )
    parser.add_argument(
        "--clear-origins",
        default=",".join(DEFAULT_CLEAR_ORIGINS),
        help="Comma-separated origins whose local browser storage should be cleared.",
    )
    parser.add_argument("--keep-browser-open", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    load_env_file()
    args = parse_args(argv)
    url = str(args.url)
    output_path = Path(args.output)
    profile_dir = Path(args.profile_dir)
    browser = find_browser(args.browser)
    port = int(args.port) if args.port else pick_free_port()
    domains = tuple(item.strip() for item in str(args.domains).split(",") if item.strip())
    clear_origins = tuple(item.strip() for item in str(args.clear_origins).split(",") if item.strip())
    preferred_host = urlparse(url).hostname or "adstar.alimama.com"

    print(f"Browser: {browser}")
    print(f"Profile: {profile_dir}")
    print(f"Login URL: {url}")
    print(f"Output: {output_path}")
    print("A browser window will open. Log in if needed; cookie values will not be printed.")

    process = launch_browser(browser, profile_dir, port, url)
    try:
        wait_for_devtools(port, min(max(args.timeout, 10), 60))
        if not args.reuse_session:
            print(
                f"Clearing existing login state after {max(0, int(args.clear_delay))}s, "
                "then reopening the login page...",
                flush=True,
            )
            time.sleep(max(0, int(args.clear_delay)))
            clear_login_state(port, preferred_host, url, clear_origins, clear_storage=bool(args.clear_storage))
            print("Login cookies cleared and login page reopened.", flush=True)
        if not args.manual_login and args.username and args.password:
            print("Filling username/password in the Chrome login iframe.", flush=True)
            try:
                fill_login_form(
                    port=port,
                    preferred_host=preferred_host,
                    username=str(args.username),
                    password=str(args.password),
                    timeout_seconds=min(max(args.timeout, 10), 90),
                )
                print("Login form submitted. Waiting for login cookies or any manual verification.", flush=True)
            except CookieRefreshError as exc:
                print(f"Auto-fill skipped: {exc}. Continue manually in the Chrome window.", flush=True)
        else:
            print("Complete the login in the Chrome window.", flush=True)
        cookies = wait_for_login_cookies(
            port=port,
            preferred_host=preferred_host,
            domains=domains,
            min_fields=max(1, int(args.min_fields)),
            timeout_seconds=max(args.timeout, 10),
        )
        if not args.skip_post_login:
            post_login_ok = run_post_login_steps(
                port=port,
                preferred_host=preferred_host,
                portal_url=str(args.portal_url),
                quick_enter_clicks=max(0, int(args.quick_enter_clicks)),
                timeout_seconds=30,
                final_wait_seconds=max(0, int(args.post_login_wait)),
            )
            if not post_login_ok:
                raise CookieRefreshError(
                    "Post-login role selection did not reach the Adstar home page. "
                    "Cookie file was not updated; complete quick-enter/employee-login in Chrome and rerun."
                )
            refreshed_cookies = read_cookie_dict(port, preferred_host, domains)
            has_login_marker = any(refreshed_cookies.get(name) for name in LOGIN_COOKIE_CANDIDATES)
            if (
                refreshed_cookies.get(REQUIRED_COOKIE)
                and has_login_marker
                and len(refreshed_cookies) >= max(1, int(args.min_fields))
            ):
                cookies = refreshed_cookies
        write_cookie_file(output_path, cookies)
        print(f"Cookie refreshed: {output_path} ({len(cookies)} fields)")
        return 0
    finally:
        if not args.keep_browser_open and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
