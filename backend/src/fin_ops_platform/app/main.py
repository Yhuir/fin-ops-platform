from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fin_ops_platform.app.server import build_application, run_http_server
from fin_ops_platform.services.state_store import default_data_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="fin-ops-platform foundation service")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the HTTP service")
    parser.add_argument("--port", default=8000, type=int, help="Port to bind the HTTP service")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print readiness summary and exit without starting the server",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = build_application(data_dir=default_data_dir())
    if args.check:
        print(json.dumps(app.readiness_summary(), ensure_ascii=False, indent=2))
        return 0

    run_http_server(args.host, args.port, app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
