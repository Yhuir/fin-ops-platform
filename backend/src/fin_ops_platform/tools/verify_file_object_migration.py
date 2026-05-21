from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fin_ops_platform.services.file_object_migration import GridFSObjectMigrationService
from fin_ops_platform.services.object_storage import ObjectStorageSettings, S3ObjectStorageRepository
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify migrated app.file_objects against S3-compatible object storage.")
    parser.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = ObjectStorageSettings.from_env()
    service = GridFSObjectMigrationService(
        connection=PostgresConnection(PostgresSettings.from_env()),
        object_storage_repository=S3ObjectStorageRepository(settings),
        legacy_file_reader=None,
        storage_backend=settings.backend,
        bucket_name=settings.bucket,
    )
    result = service.verify_verified_objects(limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
