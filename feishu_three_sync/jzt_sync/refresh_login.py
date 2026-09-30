"""Refresh JD login cookies, retaining the original per-business cookie context."""
import io
import json
import shutil
import time

from daily_client import ROOT, SyncError, fetch_report, identity, read_accounts
from local_login import PASSWORD, USERNAME
from playwright.sync_api import sync_playwright

LOGIN_URL = 'https://passport.jd.com/common/loginPage?from=jzt&ReturnUrl=https%3A%2F%2Fjzt.jd.com%2Fhome%2F'
HOME_URL = 'https://jzt.jd.com/home/'
# These are the original package's business-account session cookies.
# Refresh JD login credentials without replacing one business's context with another.
ACCOUNT_COOKIES = ('skpp_s', 'skpp_p')


def cookie_header(context):
    return '; '.join(f'{c["name"]}={c["value"]}' for c in context.cookies(['https://jzt-api.jd.com/']))


def parse_cookie(header):
    return dict(part.strip().split('=', 1) for part in header.split(';') if '=' in part)


def merge_login_cookie(old, fresh):
    previous = parse_cookie(old)
    merged = {**previous, **parse_cookie(fresh)}
    for key in ACCOUNT_COOKIES:
        if key in previous:
            merged[key] = previous[key]
    return '; '.join(f'{key}={value}' for key, value in merged.items())


def save_cookie(category, header):
    cfg = read_accounts()
    if identity(header) != cfg[category]['pin']:
        raise SyncError(f'{category}: business account identity mismatch; original cookies preserved')
    source = ROOT / 'token.txt'
    shutil.copy2(source, ROOT / 'token.txt.bak')
    cfg[category]['cookie'] = header
    output = io.StringIO()
    cfg.write(output)
    temporary = ROOT / 'token.txt.tmp'
    temporary.write_text(output.getvalue(), encoding='utf-8')
    temporary.replace(source)


def submit_login(page):
    username = USERNAME
    password = PASSWORD
    if not username or not password:
        from local_login import get_credentials
        username, password = get_credentials()
    if not username or not password:
        raise SyncError('JZT_USERNAME and JZT_PASSWORD must be configured in environment or Credential Manager')
    page.goto(LOGIN_URL, wait_until='domcontentloaded', timeout=60000)
    page.locator('#loginname').fill(username)
    page.locator('#nloginpwd').fill(password)
    page.locator('#paipaiLoginSubmit').click()
    print('Login submitted once. If JD requests a puzzle/SMS, complete it in this Chrome window.', flush=True)


def refresh_in_context(context, timeout=1800, categories=('zhuorui', 'qicui')):
    """One window and at most one login submission for the entire daily run."""
    page = context.pages[0] if context.pages else context.new_page()
    state_path = ROOT / '.profiles' / 'master_state.json'
    # Restore this tool's own saved master session, never a user's browser profile.
    header = cookie_header(context)
    if (not header or identity(header) != USERNAME) and state_path.exists():
        state = json.loads(state_path.read_text(encoding='utf-8'))
        context.clear_cookies()
        context.add_cookies(state['cookies'])
    page.goto(HOME_URL, wait_until='domcontentloaded', timeout=60000)
    header = cookie_header(context)
    if not header or identity(header) != USERNAME:
        submit_login(page)
        deadline = time.monotonic() + timeout
        last_message = 0
        while time.monotonic() < deadline:
            header = cookie_header(context)
            if header and identity(header) == USERNAME:
                break
            if time.monotonic() - last_message >= 30:
                print('Waiting in the same window for JD login/verification.', flush=True)
                last_message = time.monotonic()
            page.wait_for_timeout(3000)
        else:
            raise SyncError('JD login/verification timed out; original token file preserved')
    context.storage_state(path=str(state_path))
    print('JD master login verified. Refreshing original business cookies.', flush=True)
    mappings_a = json.loads((ROOT / 'configs/tasks_mapping.json').read_text(encoding='utf-8'))['zhangxiaoyi']
    mappings_b = json.loads((ROOT / 'configs/b_sheets_tasks.json').read_text(encoding='utf-8'))
    results = {}
    for category, mappings in [('zhuorui', mappings_a), ('qicui', mappings_b)]:
        if category not in categories:
            continue
        try:
            cfg = read_accounts()[category]
            merged = merge_login_cookie(cfg['cookie'], header)
            if identity(merged) != cfg['pin']:
                raise SyncError('Original business session expired; renew its business Cookie in token.txt')
            fetch_report(merged, mappings[0]['task_id'])
            save_cookie(category, merged)
            results[category] = 'ready'
            print(f'{category}: refreshed Cookie verified with original report request.', flush=True)
        except Exception as exc:
            results[category] = str(exc) if isinstance(exc, SyncError) else type(exc).__name__
            print(f'{category}: {results[category]}', flush=True)
    return results


def refresh_all(timeout=1800, categories=('zhuorui', 'qicui')):
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(str(ROOT / '.profiles' / 'daily'), channel='chrome',
                    headless=False, args=['--no-proxy-server'], viewport={'width': 1280, 'height': 850})
        try:
            return refresh_in_context(context, timeout, categories)
        finally:
            context.close()


if __name__ == '__main__':
    results = refresh_all()
    raise SystemExit(0 if all(v == 'ready' for v in results.values()) else 1)
