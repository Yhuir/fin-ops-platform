from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fin_ops_platform.services.file_object_migration import GridFSObjectMigrationService
from fin_ops_platform.services.object_storage import ObjectStorageSettings, S3ObjectStorageRepository
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Short-term rollback for verified file object rows back to legacy GridFS pointers.")
    parser.add_argument("--legacy-gridfs-id", action="append", default=[], help="Legacy GridFS id to roll back. Repeatable.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.legacy_gridfs_id:
        raise SystemExit("--legacy-gridfs-id is required.")
    settings = ObjectStorageSettings.from_env()
    service = GridFSObjectMigrationService(
        connection=PostgresConnection(PostgresSettings.from_env()),
        object_storage_repository=S3ObjectStorageRepository(settings),
        legacy_file_reader=None,
        storage_backend=settings.backend,
        bucket_name=settings.bucket,
    )
    updated = service.rollback_verified_to_legacy(legacy_gridfs_ids=list(args.legacy_gridfs_id))
    print(json.dumps({"rolled_back": updated}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
