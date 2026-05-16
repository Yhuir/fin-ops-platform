#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.services.app_mongo_exporter import AppMongoExporter
from fin_ops_platform.services.state_store import ApplicationStateStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export app Mongo state into normalized NDJSON and a secret-free manifest.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Application data dir containing app_mongo_config.json. Defaults to FIN_OPS_DATA_DIR/default_data_dir.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Target export directory. Not created when --dry-run is used.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read app Mongo and print record counts without writing export files.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Read app Mongo, build the manifest in memory, and return non-zero if validation has blocking errors.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = ApplicationStateStore(args.data_dir)
    result = AppMongoExporter(store).export(
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        validate_only=args.validate_only,
    )
    validation = result.manifest.get("validation") or {}
    print(
        json.dumps(
            {
                "dry_run": result.dry_run,
                "validate_only": result.validate_only,
                "output_dir": str(result.output_dir),
                "record_counts": result.record_counts,
                "schema_version": result.manifest.get("schema_version"),
                "aggregate_sha256": (result.manifest.get("hashes") or {}).get("aggregate_sha256"),
                "warning_count": len(validation.get("warnings") or []),
                "error_count": len(validation.get("errors") or []),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 2 if result.has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
