#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.services.app_gridfs_migration import (
    AppGridFSToObjectStorageMigrator,
    Boto3ObjectStorageClient,
    GridFSMigrationMode,
)
from fin_ops_platform.services.state_store import ApplicationStateStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate app Mongo GridFS files to MinIO/S3 with checksum validation.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Application data dir containing app_mongo_config.json. Defaults to FIN_OPS_DATA_DIR/default_data_dir.",
    )
    parser.add_argument("--bucket", required=True, help="Target MinIO/S3 bucket name.")
    parser.add_argument(
        "--environment",
        default="staging",
        help="Object key environment prefix such as staging, dryrun, or prod-migration.",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for migration manifest outputs.")
    parser.add_argument("--storage-provider", choices=("minio", "s3"), default="minio")
    parser.add_argument("--endpoint-url", default=os.environ.get("FIN_OPS_S3_ENDPOINT_URL"))
    parser.add_argument("--sample-size", type=int, default=20, help="Number of uploaded/skipped objects to download verify.")
    parser.add_argument("--max-workers", type=int, default=1, help="Maximum concurrent GridFS file workers.")
    parser.add_argument("--max-retries", type=int, default=3, help="Retries for object storage head/upload/download operations.")
    parser.add_argument(
        "--mode",
        choices=("dry-run", "upload", "verify"),
        default="dry-run",
        help="dry-run plans only, upload writes missing/mismatched objects, verify only checks existing objects.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Deprecated alias for --mode upload.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = ApplicationStateStore(args.data_dir)
    mode: GridFSMigrationMode = "upload" if args.execute else args.mode
    object_storage = None if mode == "dry-run" else Boto3ObjectStorageClient(endpoint_url=args.endpoint_url)
    result = AppGridFSToObjectStorageMigrator(store, object_storage).migrate(
        bucket=args.bucket,
        environment=args.environment,
        output_dir=args.output_dir,
        mode=mode,
        storage_provider=args.storage_provider,
        sample_size=args.sample_size,
        max_workers=max(1, args.max_workers),
        max_retries=max(0, args.max_retries),
    )
    print(
        json.dumps(
            {
                "mode": result.manifest["mode"],
                "output_dir": str(result.output_dir),
                "status": result.manifest["status"],
                "summary": result.manifest["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if result.manifest["blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
