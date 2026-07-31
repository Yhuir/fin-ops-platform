from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fin_ops_platform.app.application_factory import create_application
from fin_ops_platform.services.runtime_paths import default_data_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="fin-ops-platform foundation service")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print readiness summary and exit without starting the server",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("HTTP serving moved to Gunicorn; use fin_ops_platform.app.wsgi:application.")
    app = create_application(data_dir=default_data_dir())
    try:
        print(json.dumps(app.readiness_summary(), ensure_ascii=False, indent=2))
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
