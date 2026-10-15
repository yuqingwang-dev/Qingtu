"""Check local Qingtu dependencies without printing secrets.

Examples (from backend):
  python scripts/check_environment.py
  python scripts/check_environment.py --probe-llm  # one real model request
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--probe-llm", action="store_true", help="send one real model request")
    args = parser.parse_args()
    from app.db.session import SessionLocal
    from app.services.service_status import build_status

    with SessionLocal() as db:
        result = asyncio.run(build_status(db, probe_llm=args.probe_llm))
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Qingtu environment: {result['status']} ({result['environment']})")
        for name, check in result["checks"].items():
            print(f"- {name}: {check['status']} — {check['message']}")
        if not args.probe_llm:
            print("提示：LLM 当前只检查配置；使用 --probe-llm 才会真实调用模型并可能消耗配额。")
    return 0 if result["status"] == "healthy" else 2


if __name__ == "__main__":
    sys.exit(main())
