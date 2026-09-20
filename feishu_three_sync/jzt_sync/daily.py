"""Daily entry point. Status and exit code represent verified results."""
import argparse
from datetime import datetime
import json
import msvcrt
import sys
import warnings

from daily_client import ROOT, SyncError, identity, read_accounts
from daily_sync import sync_all
from refresh_login import refresh_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Read/report only; no browser login or Feishu writes')
    parser.add_argument('--login-timeout', type=int, default=1800)
    parser.add_argument('--reuse-verified-cookies', action='store_true', help='Manual recovery: validate existing cookies without opening Chrome')
    parser.add_argument('--categories', nargs='+', choices=('zhuorui', 'qicui'), default=['zhuorui', 'qicui'], help='表格范围；默认同步两张表')
    args = parser.parse_args()
    warnings.filterwarnings('ignore', message='Workbook contains no default style')
    logs = ROOT / 'logs'
    logs.mkdir(exist_ok=True)
    status = {'started_at': datetime.now().isoformat(), 'mode': 'dry_run' if args.dry_run else 'sync', 'accounts': {}, 'tasks': []}
    with (logs / 'daily.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('Another daily sync is running; skipped.', flush=True)
            return 2
        try:
            ready = []
            browser_results = None
            if not args.dry_run and not args.reuse_verified_cookies:
                browser_results = refresh_all(args.login_timeout, args.categories)
            for cat in args.categories:
                try:
                    if not args.dry_run:
                        if args.reuse_verified_cookies:
                            account = read_accounts()[cat]
                            if identity(account['cookie']) != account['pin']:
                                raise SyncError('Login refresh required')
                        else:
                            if browser_results[cat] != 'ready':
                                raise SyncError(browser_results[cat])
                    ready.append(cat)
                    status['accounts'][cat] = 'ready'
                except Exception as exc:
                    reason = str(exc) if isinstance(exc, SyncError) else type(exc).__name__
                    status['accounts'][cat] = reason
                    print(f'{cat}: {reason}', flush=True)
            if ready:
                status['tasks'] = sync_all(args.dry_run, ready)
            failed = len(ready) != len(args.categories) or any(t['status'] == 'failed' for t in status['tasks']) or not status['tasks']
            status['status'] = 'failed' if failed else 'success'
        except Exception as exc:
            status['status'] = 'failed'
            status['reason'] = str(exc) if isinstance(exc, SyncError) else type(exc).__name__
        finally:
            status['finished_at'] = datetime.now().isoformat()
            data = json.dumps(status, ensure_ascii=False, indent=2)
            (logs / ('last_dry_run.json' if args.dry_run else 'last_run.json')).write_text(data, encoding='utf-8')
            (logs / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + status['mode'] + '.json')).write_text(data, encoding='utf-8')
            print(f'Run {status.get("status", "failed")}: {len(status["tasks"])} tasks; status saved to logs.', flush=True)
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    return 0 if status.get('status') == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
