from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import json
import sys
from typing import Any, TextIO

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize App settings through the canonical settings and repository boundaries."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    repository = PostgresOpsTaxEtcRepository(connection)
    current = repository.load_settings("app_settings")
    plan = _normalization_plan(current)
    if args.execute and plan["changed"]:
        with connection.transaction() as transaction:
            repository.replace_normalized_app_settings_in_transaction(
                plan.pop("normalized_payload"),
                transaction=transaction,
            )
        plan["written"] = True
    else:
        plan.pop("normalized_payload")
        plan["written"] = False
    plan["mode"] = "execute" if args.execute else "dry-run"
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def _normalization_plan(current: dict[str, Any] | None) -> dict[str, Any]:
    current_payload = dict(current or {})
    normalized_payload = AppSettingsService.normalize_settings_payload(
        current_payload,
        validate_pending_invoice_tag_groups=False,
    )
    changed_keys = sorted(
        key
        for key in set(current_payload) | set(normalized_payload)
        if current_payload.get(key) != normalized_payload.get(key)
    )
    return {
        "changed": bool(changed_keys),
        "changed_keys": changed_keys,
        "before_sha256": _payload_sha256(current_payload),
        "after_sha256": _payload_sha256(normalized_payload),
        "normalized_payload": normalized_payload,
    }


def _payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
