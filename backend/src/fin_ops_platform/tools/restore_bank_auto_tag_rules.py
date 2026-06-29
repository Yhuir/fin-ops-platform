from __future__ import annotations

import argparse
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.tools.runtime_application import bank_auto_tag_rules_runtime


DEFAULT_ACTOR_ID = "system:bank-auto-tag-rule-restore"
DEFAULT_BACKUP_DIR = Path(".runtime/bank-auto-tag-rule-restore-backups")
CRITICAL_BANK_AUTO_TAG_CODES = (
    "external_turnover",
    "custom_0f16f8a24eca",
    "custom_29fa40d16fc1",
    "custom_85d44e9ec32d",
    "custom_874d3601774c",
    "custom_a1c21e4bc4c6",
    "custom_aaadbde9c024",
    "custom_e12aff53264f",
    "custom_e2dd8f5ab5c1",
    "fee",
    "salary",
    "social_security",
    "tax_payment",
    "treasury_tax_collection",
    "bonus",
    "holiday_bonus",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Restore bank transaction auto tag rules from the bank details auto-rule file. "
            "The command is a dry run unless --apply and --confirm-write are both provided."
        )
    )
    parser.add_argument("--source", type=Path, required=True, help="Path to 银行流水标签 UI/rule file (.xlsx or tabular rows).")
    parser.add_argument("--data-dir", type=Path, default=None, help="Optional local app data directory. Omit in deployed runtime.")
    parser.add_argument("--apply", action="store_true", help="Persist the restored rules through the bank details application service.")
    parser.add_argument(
        "--confirm-write",
        action="store_true",
        help="Required with --apply to guard production settings writes.",
    )
    parser.add_argument("--actor-id", default=DEFAULT_ACTOR_ID)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply and not args.confirm_write:
        raise SystemExit("--confirm-write is required when --apply is used.")
    if not args.source.exists() or not args.source.is_file():
        raise SystemExit(f"source file not found: {args.source}")

    runtime = bank_auto_tag_rules_runtime(args.data_dir)
    settings_before = runtime.get_settings_payload()
    dry_run = build_restore_plan(args.source, previous_settings=settings_before)

    backup_path: Path | None = None
    applied = False
    settings_after: dict[str, Any] | None = None
    if args.apply:
        backup_path = write_settings_backup(
            settings_before,
            backup_dir=args.backup_dir,
            actor_id=str(args.actor_id),
            source=args.source,
        )
        runtime.replace_auto_tag_rules_from_file_source(
            args.source,
            actor_id=str(args.actor_id),
        )
        settings_after = runtime.get_settings_payload()
        applied = True

    summary = build_restore_summary(
        dry_run,
        mode="apply" if applied else "dry_run",
        backup_path=backup_path,
        settings_after=settings_after,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, default=_json_default))
    return 0


def build_restore_plan(source: Any, *, previous_settings: dict[str, Any]) -> dict[str, Any]:
    return BankTransactionCategoryService.normalize_auto_tag_rules_file_replacement(
        source,
        previous_tag_dictionary=previous_settings["bank_transaction_tags"],
    )


def build_restore_summary(
    restore_plan: dict[str, Any],
    *,
    mode: str,
    backup_path: Path | None = None,
    settings_after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tag_dictionary = (
        settings_after.get("bank_transaction_tags")
        if isinstance(settings_after, dict) and isinstance(settings_after.get("bank_transaction_tags"), dict)
        else restore_plan["tag_dictionary"]
    )
    changes = dict(restore_plan.get("changes") or {})
    return {
        "mode": mode,
        "write_executed": mode == "apply",
        "old_version": int(restore_plan.get("old_version") or 0),
        "new_version": int(restore_plan.get("new_version") or 0),
        "changed": bool(changes.get("changed")),
        "backup_path": str(backup_path) if backup_path is not None else None,
        "source": changes.get("source"),
        "reused_codes": sorted(str(code) for code in changes.get("reused_codes") or []),
        "added_codes": sorted(str(code) for code in changes.get("added_codes") or []),
        "archived_codes": sorted(str(code) for code in changes.get("archived_codes") or []),
        "recovered_legacy_external_turnover_codes": sorted(
            str(code) for code in changes.get("recovered_legacy_external_turnover_codes") or []
        ),
        "skipped_rows": [dict(row) for row in changes.get("skipped_rows") or [] if isinstance(row, dict)],
        "critical_code_status": critical_code_status(tag_dictionary),
    }


def critical_code_status(tag_dictionary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalized = BankTransactionCategoryService._normalize_tag_dictionary_payload(tag_dictionary)
    by_code = {
        str(definition.get("code") or ""): definition
        for definition in normalized.get("definitions", [])
        if str(definition.get("code") or "")
    }
    result: dict[str, dict[str, Any]] = {}
    for code in CRITICAL_BANK_AUTO_TAG_CODES:
        definition = by_code.get(code)
        if definition is None:
            result[code] = {"exists": False}
            continue
        result[code] = {
            "exists": True,
            "status": definition.get("status"),
            "label": definition.get("label"),
            "output_primary_label": definition.get("output_primary_label"),
            "output_sub_label": definition.get("output_sub_label"),
            "turnover_action_type": definition.get("turnover_action_type"),
            "turnover_family": definition.get("turnover_family"),
            "has_rules": bool(definition.get("rules")),
        }
    return result


def write_settings_backup(
    settings: dict[str, Any],
    *,
    backup_dir: Path,
    actor_id: str,
    source: Path,
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    source_digest = _source_sha256(source)
    path = backup_dir / f"bank-auto-tag-rules-before-restore-{timestamp}-{source_digest[:12]}.json"
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "actor_id": actor_id,
        "source": str(source),
        "source_sha256": source_digest,
        "settings": deepcopy(settings),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    return path


def _source_sha256(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
