from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


CHECKS: tuple[tuple[str, str], ...] = (
    (
        "invoice_rows_without_invoice",
        """
        select count(*)::bigint as count
        from app.import_batch_rows rows
        where rows.linked_object_type = 'invoice'
          and rows.linked_object_id is not null
          and not exists (
              select 1
              from app.invoices invoices
              where invoices.legacy_mongo_id = rows.linked_object_id
                 or invoices.id::text = rows.linked_object_id
          )
        """,
    ),
    (
        "bank_rows_without_transaction",
        """
        select count(*)::bigint as count
        from app.import_batch_rows rows
        where rows.linked_object_type = 'bank_transaction'
          and rows.linked_object_id is not null
          and not exists (
              select 1
              from app.bank_transactions transactions
              where transactions.legacy_mongo_id = rows.linked_object_id
                 or transactions.id::text = rows.linked_object_id
          )
        """,
    ),
    (
        "invoices_without_batch",
        """
        select count(*)::bigint as count
        from app.invoices invoices
        where invoices.legacy_source_batch_id is not null
          and not exists (
              select 1
              from app.import_batches batches
              where batches.legacy_mongo_id = invoices.legacy_source_batch_id
                 or batches.id::text = invoices.legacy_source_batch_id
          )
        """,
    ),
    (
        "bank_transactions_without_batch",
        """
        select count(*)::bigint as count
        from app.bank_transactions transactions
        where transactions.legacy_source_batch_id is not null
          and not exists (
              select 1
              from app.import_batches batches
              where batches.legacy_mongo_id = transactions.legacy_source_batch_id
                 or batches.id::text = transactions.legacy_source_batch_id
          )
        """,
    ),
    (
        "unresolved_import_files",
        """
        select count(*)::bigint as count
        from app.import_files import_files
        where import_files.status not in ('stored', 'preview_ready', 'confirmed', 'deleted')
        """,
    ),
)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="Check SQL import fact referential consistency after snapshot cutover.")


def _count(row: dict[str, Any] | None) -> int:
    try:
        return int((row or {}).get("count") or 0)
    except (TypeError, ValueError):
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    checks = {name: _count(connection.fetch_one(sql)) for name, sql in CHECKS}
    failed = {name: count for name, count in checks.items() if count}
    payload = {
        "status": "failed" if failed else "ok",
        "checks": checks,
        "failed_checks": failed,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
