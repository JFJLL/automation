# -*- coding: utf-8 -*-
"""
便捷命令行入口：一键原样恢复指定批次被暂停的小红书简单投笔记
用法：
  python sync_console/restore_notes.py --run-id 1
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BASE_DIR.parent))

from simple_promo.restore import rollback_simple_promo_run
import argparse
import json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="简单投老笔记一键原样恢复脚本")
    parser.add_argument("--run-id", type=int, required=True, help="需要恢复的运行批次ID (如 1)")
    args = parser.parse_args()

    print(f"▶ 正在恢复 Run #{args.run_id} 中已暂停的全部笔记...")
    res = rollback_simple_promo_run(args.run_id)
    print(json.dumps(res, ensure_ascii=False, indent=2))
