from __future__ import annotations

import argparse
from collections.abc import Sequence
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from fin_ops_platform.services.historical_etc_business_batch_migration_service import (
    HistoricalEtcBusinessBatchMigrationService,
    HistoricalEtcBusinessBatchMigrationSpec,
)
from fin_ops_platform.tools.link_existing_etc_batches import (
    _build_full_snapshot_application,
    _sync_etc_invoices_to_canonical_invoices,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate submitted legacy ETC batches into ETC business batches.")
    parser.add_argument("--spec-file", required=True, type=Path, help="JSON file containing historical ETC migration specs.")
    parser.add_argument("--data-dir", type=Path, default=None, help="Optional local state directory for non-Postgres runs.")
    parser.add_argument("--execute", action="store_true", help="Persist changes. Without this flag the command is a dry run.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    specs = _load_specs(args.spec_file)
    app = _build_full_snapshot_application(args.data_dir)
    if args.execute:
        service = HistoricalEtcBusinessBatchMigrationService(
            etc_service=app._etc_service,
            pair_relation_service=app._workbench_pair_relation_service,
            sync_etc_invoices_to_canonical_invoices=lambda invoices: _sync_etc_invoices_to_canonical_invoices(app, invoices),
            refresh_after_etc_invoice_sync=lambda months, reason: _refresh_after_historical_migration(app, months, reason),
            persist_pair_relations=lambda case_ids: app._persist_workbench_pair_relations(changed_case_ids=case_ids),
            invalidate_workbench_scopes=app._invalidate_workbench_read_model_scopes,
            persist_etc_state=lambda: app._state_store.save_etc_state(app._etc_service.snapshot()),
        )
        results = [service.migrate(spec).to_payload() for spec in specs]
        status = "ok" if all(result.get("status") == "ok" for result in results) else "attention"
        print(json.dumps({"status": status, "mode": "execute", "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if status == "ok" else 1

    plans = [_dry_run_spec(app, spec) for spec in specs]
    status = "ok" if all(plan.get("status") == "ready" for plan in plans) else "attention"
    print(json.dumps({"status": status, "mode": "dry-run", "results": plans}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == "ok" else 1


def _load_specs(path: Path) -> list[HistoricalEtcBusinessBatchMigrationSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("spec file must contain a JSON array.")
    specs: list[HistoricalEtcBusinessBatchMigrationSpec] = []
    for raw_spec in payload:
        if not isinstance(raw_spec, dict):
            raise ValueError("each spec must be a JSON object.")
        specs.append(
            HistoricalEtcBusinessBatchMigrationSpec(
                label=str(raw_spec.get("label") or ""),
                business_batch_id=str(raw_spec.get("business_batch_id") or raw_spec.get("businessBatchId") or ""),
                task_id=str(raw_spec.get("task_id") or raw_spec.get("taskId") or ""),
                submission_batch_id=str(raw_spec.get("submission_batch_id") or raw_spec.get("submissionBatchId") or ""),
                external_batch_id=str(raw_spec.get("external_batch_id") or raw_spec.get("externalBatchId") or ""),
                reported_amount=Decimal(str(raw_spec.get("reported_amount") or raw_spec.get("reportedAmount") or "0")),
                relation_case_id=str(raw_spec.get("relation_case_id") or raw_spec.get("relationCaseId") or ""),
                oa_row_id=_optional_text(raw_spec.get("oa_row_id") or raw_spec.get("oaRowId")),
                scope_month=_optional_text(raw_spec.get("scope_month") or raw_spec.get("scopeMonth")),
                gap_reason=_optional_text(raw_spec.get("gap_reason") or raw_spec.get("gapReason")),
            )
        )
    return specs


def _dry_run_spec(app: Any, spec: HistoricalEtcBusinessBatchMigrationSpec) -> dict[str, object]:
    relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(spec.relation_case_id)
    active_relation_found = isinstance(relation, dict)
    relation_external_id = ""
    oa_row_in_relation = False
    if active_relation_found:
        amount_check = relation.get("amount_check") if isinstance(relation.get("amount_check"), dict) else {}
        relation_external_id = str(amount_check.get("external_etc_batch_id") or "").strip()
        row_ids = {str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()}
        oa_row_in_relation = not spec.oa_row_id or str(spec.oa_row_id).strip() in row_ids

    submission_batch = None
    submission_error = None
    try:
        submission_batch = app._etc_service.get_batch(spec.submission_batch_id)
    except Exception as exc:  # pragma: no cover - concrete store errors differ by repository.
        submission_error = str(exc)

    existing_business_batch_found = False
    try:
        app._etc_service.get_business_batch(spec.business_batch_id)
        existing_business_batch_found = True
    except Exception:
        existing_business_batch_found = False

    invoice_count = 0
    invoice_total = Decimal("0.00")
    external_batch_matches = False
    if submission_batch is not None:
        external_batch_matches = str(getattr(submission_batch, "etc_batch_id", "") or "").strip() == spec.external_batch_id
        invoices = app._etc_service.list_invoices_by_ids([str(invoice_id) for invoice_id in list(getattr(submission_batch, "invoice_ids", []) or [])])
        invoice_count = len(invoices)
        invoice_total = sum((Decimal(str(getattr(invoice, "total_amount", "0.00"))) for invoice in invoices), Decimal("0.00")).quantize(
            Decimal("0.01")
        )

    relation_external_matches = not relation_external_id or relation_external_id == spec.external_batch_id
    amount_delta = (Decimal(str(spec.reported_amount)).quantize(Decimal("0.01")) - invoice_total).quantize(Decimal("0.01"))
    ready = (
        active_relation_found
        and oa_row_in_relation
        and submission_batch is not None
        and external_batch_matches
        and relation_external_matches
        and invoice_count > 0
    )
    return {
        "label": spec.label,
        "status": "ready" if ready else "attention",
        "business_batch_id": spec.business_batch_id,
        "submission_batch_id": spec.submission_batch_id,
        "external_batch_id": spec.external_batch_id,
        "relation_case_id": spec.relation_case_id,
        "active_relation_found": active_relation_found,
        "oa_row_in_relation": oa_row_in_relation,
        "relation_external_batch_id": relation_external_id,
        "submission_batch_found": submission_batch is not None,
        "submission_error": submission_error,
        "submission_external_batch_matches": external_batch_matches,
        "existing_business_batch_found": existing_business_batch_found,
        "invoice_count": invoice_count,
        "invoice_total": f"{invoice_total:.2f}",
        "reported_amount": f"{Decimal(str(spec.reported_amount)).quantize(Decimal('0.01')):.2f}",
        "amount_delta": f"{amount_delta:.2f}",
    }


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _refresh_after_historical_migration(app: Any, months: list[str], reason: str) -> None:
    # The migration service invalidates Workbench scopes after relation metadata
    # is persisted. Avoid full lifecycle refresh here because it can rewrite
    # unrelated import snapshots in production.
    return


if __name__ == "__main__":
    raise SystemExit(main())
