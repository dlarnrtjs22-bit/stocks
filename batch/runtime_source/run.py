#!/usr/bin/env python3
"""
Closing-bet quick launcher.

Usage:
  python run.py scan
  python run.py serve --host 0.0.0.0 --port 5001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from engine.freshness import DataReadinessError
from engine.generator import run_screener
from engine.llm_analyzer import LLMProviderError


def _cmd_scan(args: argparse.Namespace) -> None:
    try:
        result = asyncio.run(run_screener(capital=args.capital))
        print(f"date={result.date.isoformat()} filtered={result.filtered_count}")
    except DataReadinessError as e:
        payload = {
            "status": e.status,
            "summary": e.report.get("summary", ""),
            "errors": e.report.get("errors", []),
            "warnings": e.report.get("warnings", []),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    except LLMProviderError as e:
        payload = {
            "status": "LLM_NOT_READY",
            "message": str(e),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(3)


def _cmd_serve(args: argparse.Namespace) -> None:
    from app import create_app

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Closing-bet v2 launcher")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Run screener once and write JSON output")
    scan.add_argument("--capital", type=float, default=50_000_000)
    scan.set_defaults(func=_cmd_scan)

    serve = sub.add_parser("serve", help="Run Flask API server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=5001)
    serve.add_argument("--debug", action="store_true")
    serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
