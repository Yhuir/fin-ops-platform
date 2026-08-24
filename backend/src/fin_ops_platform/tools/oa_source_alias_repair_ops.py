from __future__ import annotations

import argparse
from collections.abc import Sequence
from hashlib import sha256
import json
import re
import sys
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_source_alias_repair import (
    PostgresOASourceAliasRepairRepository,
)


SAFE_ROW_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
REPAIR_REASON = "verified_attachment_identity_migration"
REVIEWED_BY = "codex-production-repair"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or activate one historical OA alias from exact attachment identity evidence."
    )
    parser.add_argument("--alias-row-id", required=True)
    parser.add_argument("--canonical-row-id", required=True)
    parser.add_argument("--expected-bridge-count", required=True, type=int)
    parser.add_argument("--expected-invoice-count", required=True, type=int)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-fingerprint")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    repository: Any | None = None,
    stdout: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    alias_row_id = str(args.alias_row_id or "").strip()
    canonical_row_id = str(args.canonical_row_id or "").strip()
    if not SAFE_ROW_ID.fullmatch(alias_row_id) or not SAFE_ROW_ID.fullmatch(canonical_row_id):
        raise SystemExit("OA row ids must contain only safe identity characters")
    if alias_row_id == canonical_row_id:
        raise SystemExit("alias and canonical OA row ids must differ")
    if args.expected_bridge_count <= 0 or args.expected_invoice_count <= 0:
        raise SystemExit("expected evidence counts must be positive")
    if args.dry_run and args.expected_fingerprint:
        raise SystemExit("--dry-run does not accept --expected-fingerprint")
    if args.execute and not args.expected_fingerprint:
        raise SystemExit("--execute requires --expected-fingerprint")

    active_repository = repository or PostgresOASourceAliasRepairRepository(
        PostgresConnection(PostgresSettings.from_env())
    )
    evidence = active_repository.inspect_candidate(
        alias_row_id=alias_row_id,
        canonical_row_id=canonical_row_id,
    )
    plan = _validated_plan(
        evidence,
        alias_row_id=alias_row_id,
        canonical_row_id=canonical_row_id,
        expected_bridge_count=args.expected_bridge_count,
        expected_invoice_count=args.expected_invoice_count,
    )
    fingerprint = _fingerprint(plan)
    if args.execute and str(args.expected_fingerprint) != fingerprint:
        raise RuntimeError("OA source alias evidence changed after dry-run; rerun dry-run before execute.")

    already_active = bool(plan["already_active"])
    written = False
    if args.execute and not already_active:
        written = bool(
            active_repository.activate_alias(
                alias_row_id=alias_row_id,
                canonical_row_id=canonical_row_id,
                reason=REPAIR_REASON,
                evidence_hash=fingerprint,
                reviewed_by=REVIEWED_BY,
                raw_payload={
                    "contract": "oa-source-alias-repair-v1",
                    "bridge_count": plan["bridge_count"],
                    "invoice_count": plan["invoice_count"],
                    "row_indexes": plan["row_indexes"],
                    "attachment_key_hashes": plan["attachment_key_hashes"],
                },
            )
        )
        if not written:
            raise RuntimeError("OA source alias facts changed during execute; no alias was activated.")

    report = {
        "action": "oa_source_alias_repair",
        "mode": "execute" if args.execute else "dry_run",
        "alias_row_id": alias_row_id,
        "canonical_row_id": canonical_row_id,
        "bridge_count": plan["bridge_count"],
        "invoice_count": plan["invoice_count"],
        "row_indexes": plan["row_indexes"],
        "already_active": already_active,
        "fingerprint": fingerprint,
        "written": written,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def _validated_plan(
    evidence: dict[str, Any],
    *,
    alias_row_id: str,
    canonical_row_id: str,
    expected_bridge_count: int,
    expected_invoice_count: int,
) -> dict[str, Any]:
    if int(evidence.get("canonical_count") or 0) != 1:
        raise RuntimeError("Canonical OA row was not found exactly once.")
    if int(evidence.get("alias_application_count") or 0) != 0:
        raise RuntimeError("Alias OA row is still canonical; refusing to merge identities.")
    existing_status = str(evidence.get("existing_status") or "").strip()
    existing_canonical = str(evidence.get("existing_canonical_row_id") or "").strip()
    already_active = existing_status == "active" and existing_canonical == canonical_row_id
    if existing_status and not already_active:
        raise RuntimeError("OA alias already has a different or non-active review record.")

    bridge_item_ids = _texts(evidence.get("bridge_item_ids"))
    invoice_ids = _texts(evidence.get("invoice_ids"))
    invoice_item_ids = _texts(evidence.get("invoice_item_ids"))
    bridge_indexes = _texts(evidence.get("bridge_row_indexes"))
    invoice_indexes = _texts(evidence.get("invoice_row_indexes"))
    if len(bridge_item_ids) != expected_bridge_count:
        raise RuntimeError("Attachment identity bridge count does not match the approved expectation.")
    if len(invoice_ids) != expected_invoice_count or len(invoice_item_ids) != expected_invoice_count:
        raise RuntimeError("Canonical OA attachment invoice count does not match the approved expectation.")
    if bridge_item_ids != invoice_item_ids:
        raise RuntimeError("Attachment bridge and canonical invoice source item identities disagree.")
    if not bridge_indexes or bridge_indexes != invoice_indexes:
        raise RuntimeError("Attachment bridge and canonical invoice row indexes disagree.")
    if any(not item_id.startswith(f"{alias_row_id}:item:") for item_id in bridge_item_ids):
        raise RuntimeError("Attachment evidence contains a foreign OA item identity.")
    attachment_key_hashes = _texts(evidence.get("attachment_key_hashes"))
    if not attachment_key_hashes:
        raise RuntimeError("Attachment identity bridge has no exact key evidence.")
    return {
        "contract": "oa-source-alias-repair-v1",
        "alias_row_id": alias_row_id,
        "canonical_row_id": canonical_row_id,
        "bridge_count": len(bridge_item_ids),
        "invoice_count": len(invoice_ids),
        "row_indexes": bridge_indexes,
        "bridge_item_ids": bridge_item_ids,
        "invoice_ids": invoice_ids,
        "attachment_key_hashes": attachment_key_hashes,
        "already_active": already_active,
    }


def _texts(value: Any) -> list[str]:
    return sorted({str(item or "").strip() for item in list(value or []) if str(item or "").strip()})


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
