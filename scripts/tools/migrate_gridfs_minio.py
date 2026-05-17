#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.services.app_gridfs_migration import (
    AppGridFSToObjectStorageMigrator,
    Boto3ObjectStorageClient,
    GridFSMigrationMode,
    build_gridfs_minio_export_dry_run_report,
    write_gridfs_minio_report_files,
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
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="06A app Mongo export directory. In dry-run mode this reads gridfs-files-manifest.ndjson only.",
    )
    parser.add_argument(
        "--migration-run-id",
        default=None,
        help="Stable migration run UUID for report-only/export manifest mode.",
    )
    parser.add_argument(
        "--bucket",
        default=os.environ.get("FIN_OPS_S3_BUCKET") or os.environ.get("S3_BUCKET"),
        help="Target MinIO/S3 bucket name. May be omitted for export-dir dry-run NO_GO reporting.",
    )
    parser.add_argument(
        "--environment",
        default="staging",
        help="Object key environment prefix such as staging, dryrun, or prod-migration.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for live GridFS migration manifest outputs.",
    )
    parser.add_argument("--report-json-path", type=Path, default=None, help="Path for paired 06D summary JSON report.")
    parser.add_argument("--report-md-path", type=Path, default=None, help="Path for paired 06D summary Markdown report.")
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Deprecated alias for --mode dry-run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mode: GridFSMigrationMode = "upload" if args.execute else ("dry-run" if args.dry_run else args.mode)
    migration_run_id = args.migration_run_id or str(uuid.uuid4())
    if args.export_dir is not None:
        report = build_gridfs_minio_export_dry_run_report(
            export_dir=args.export_dir,
            migration_run_id=migration_run_id,
            environment=args.environment,
            bucket=args.bucket,
            storage_provider=args.storage_provider,
            env=os.environ,
        )
        if args.report_json_path is not None and args.report_md_path is not None:
            write_gridfs_minio_report_files(report, json_path=args.report_json_path, md_path=args.report_md_path)
        elif args.report_json_path is not None or args.report_md_path is not None:
            raise SystemExit("--report-json-path and --report-md-path must be provided together.")
        print(
            json.dumps(
                {
                    "mode": mode,
                    "export_dir": str(args.export_dir),
                    "status": report["status"],
                    "go_no_go": report["decision"]["go_no_go"],
                    "summary": report["metadata_summary"],
                    "report_json_path": str(args.report_json_path) if args.report_json_path else None,
                    "report_md_path": str(args.report_md_path) if args.report_md_path else None,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1 if report["blocking"] else 0

    if args.bucket is None:
        raise SystemExit("--bucket or FIN_OPS_S3_BUCKET/S3_BUCKET is required for live GridFS migration.")
    if args.output_dir is None:
        raise SystemExit("--output-dir is required for live GridFS migration.")
    store = ApplicationStateStore(args.data_dir)
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
