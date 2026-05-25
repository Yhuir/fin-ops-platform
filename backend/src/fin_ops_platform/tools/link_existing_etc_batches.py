from __future__ import annotations

import argparse
from collections.abc import Sequence
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.existing_etc_batch_link_service import (
    ExistingEtcBatchLinkService,
    ExistingEtcBatchLinkSpec,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Link existing ETC invoices to active OA-bank workbench relations.")
    parser.add_argument("--spec-file", required=True, type=Path, help="JSON file containing an array of ETC batch link specs.")
    parser.add_argument("--data-dir", type=Path, default=None, help="Optional local state directory for non-Postgres runs.")
    parser.add_argument("--execute", action="store_true", help="Persist changes. Without this flag the command is a dry run.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    specs = _load_specs(args.spec_file)
    app = _build_full_snapshot_application(args.data_dir)
    if args.execute:
        service = ExistingEtcBatchLinkService(
            etc_service=app._etc_service,
            import_service=app._import_service,
            pair_relation_service=app._workbench_pair_relation_service,
            sync_import_result_to_canonical_invoices=lambda result: _sync_import_result_to_canonical_invoices(app, result),
            sync_etc_invoices_to_canonical_invoices=lambda invoices: _sync_etc_invoices_to_canonical_invoices(app, invoices),
            refresh_after_etc_invoice_sync=lambda _months, _reason: None,
            persist_pair_relations=lambda case_ids: app._persist_workbench_pair_relations(
                changed_case_ids=case_ids,
            ),
            invalidate_workbench_scopes=app._invalidate_workbench_read_model_scopes,
            persist_etc_state=lambda: app._state_store.save_etc_state(app._etc_service.snapshot()),
        )
        results = [service.link_existing_invoices(spec).to_payload() for spec in specs]
        status = "ok" if all(result.get("status") == "ok" for result in results) else "attention"
        print(json.dumps({"status": status, "mode": "execute", "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if status == "ok" else 1

    plans = [_dry_run_spec(app, spec) for spec in specs]
    status = "ok" if all(plan.get("status") == "ready" for plan in plans) else "attention"
    print(json.dumps({"status": status, "mode": "dry-run", "results": plans}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == "ok" else 1


def _load_specs(path: Path) -> list[ExistingEtcBatchLinkSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("spec file must contain a JSON array.")
    specs: list[ExistingEtcBatchLinkSpec] = []
    for raw_spec in payload:
        if not isinstance(raw_spec, dict):
            raise ValueError("each spec must be a JSON object.")
        specs.append(
            ExistingEtcBatchLinkSpec(
                label=str(raw_spec.get("label") or ""),
                case_id=str(raw_spec.get("case_id") or ""),
                external_batch_id=str(raw_spec.get("external_batch_id") or ""),
                oa_row_id=str(raw_spec.get("oa_row_id") or ""),
                bank_row_id=_optional_text(raw_spec.get("bank_row_id")),
                oa_amount=Decimal(str(raw_spec.get("oa_amount") or "0")),
                bank_amount=Decimal(str(raw_spec.get("bank_amount"))) if raw_spec.get("bank_amount") not in (None, "") else None,
                invoice_numbers=tuple(str(item).strip() for item in list(raw_spec.get("invoice_numbers") or []) if str(item).strip()),
                note=_optional_text(raw_spec.get("note")),
            )
        )
    return specs


def _dry_run_spec(app: Any, spec: ExistingEtcBatchLinkSpec) -> dict[str, object]:
    relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(spec.case_id)
    canonical_numbers = _canonical_invoice_numbers(app, set(spec.invoice_numbers))
    etc_numbers = {invoice.invoice_number for invoice in app._etc_service.list_invoices_by_numbers(list(spec.invoice_numbers))}
    found_numbers = sorted(set(canonical_numbers).union(etc_numbers))
    missing_numbers = [invoice_number for invoice_number in spec.invoice_numbers if invoice_number not in found_numbers]
    invoice_total = _invoice_total(app, found_numbers)
    return {
        "label": spec.label,
        "status": "ready" if isinstance(relation, dict) and not missing_numbers else "attention",
        "case_id": spec.case_id,
        "external_batch_id": spec.external_batch_id,
        "active_relation_found": isinstance(relation, dict),
        "requested_invoice_count": len(spec.invoice_numbers),
        "found_invoice_count": len(found_numbers),
        "invoice_total": f"{invoice_total:.2f}",
        "missing_invoice_numbers": missing_numbers,
    }


def _canonical_invoice_numbers(app: Any, wanted: set[str]) -> set[str]:
    found: set[str] = set()
    for invoice in app._import_service.list_invoices():
        for value in (
            getattr(invoice, "digital_invoice_no", None),
            getattr(invoice, "invoice_no", None),
            getattr(invoice, "source_unique_key", None),
        ):
            invoice_number = str(value or "").strip()
            if invoice_number in wanted:
                found.add(invoice_number)
    return found


def _invoice_total(app: Any, invoice_numbers: list[str]) -> Decimal:
    numbers = set(invoice_numbers)
    total = Decimal("0.00")
    counted: set[str] = set()
    for invoice in app._import_service.list_invoices():
        invoice_identifiers = {
            str(getattr(invoice, "digital_invoice_no", "") or "").strip(),
            str(getattr(invoice, "invoice_no", "") or "").strip(),
            str(getattr(invoice, "source_unique_key", "") or "").strip(),
        }
        if numbers.isdisjoint(invoice_identifiers):
            continue
        amount = getattr(invoice, "total_with_tax", None) or getattr(invoice, "amount", None) or Decimal("0.00")
        total += Decimal(str(amount))
        counted.update(identifier for identifier in invoice_identifiers if identifier in numbers)
    missing_canonical_numbers = sorted(numbers - counted)
    for invoice in app._etc_service.list_invoices_by_numbers(missing_canonical_numbers):
        total += Decimal(str(invoice.total_amount))
    return total.quantize(Decimal("0.01"))


def _sync_import_result_to_canonical_invoices(app: Any, result: Any) -> list[str]:
    invoice_numbers = [
        str(getattr(item, "invoice_number", "") or "").strip()
        for item in list(getattr(result, "items", []) or [])
        if str(getattr(item, "invoice_number", "") or "").strip()
    ]
    return _sync_etc_invoices_to_canonical_invoices(
        app,
        app._etc_service.list_invoices_by_numbers(invoice_numbers),
    )


def _sync_etc_invoices_to_canonical_invoices(app: Any, etc_invoices: list[Any]) -> list[str]:
    changed_months: set[str] = set()
    changed_invoices: list[Any] = []
    for etc_invoice in etc_invoices:
        invoice = app._import_service.upsert_etc_invoice(etc_invoice)
        changed_invoices.append(invoice)
        for date_value in (
            getattr(invoice, "invoice_date", None),
            getattr(etc_invoice, "issue_date", None),
            getattr(etc_invoice, "passage_start_date", None),
            getattr(etc_invoice, "passage_end_date", None),
        ):
            text_value = str(date_value or "").strip()
            if len(text_value) >= 7 and text_value[4:5] == "-" and text_value[:4].isdigit() and text_value[5:7].isdigit():
                changed_months.add(text_value[:7])
    save_invoice_etc_metadata = getattr(app._state_store, "save_invoice_etc_metadata", None)
    if callable(save_invoice_etc_metadata) and changed_invoices:
        save_invoice_etc_metadata(changed_invoices)
    return sorted(changed_months)


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _build_full_snapshot_application(data_dir: Path | None) -> Any:
    if data_dir is None:
        return build_application(data_dir=None)
    app = build_application(data_dir=data_dir, bootstrap_mode="lightweight")
    state_store = getattr(app, "_state_store", None)
    if state_store is not None:
        app._initialize_runtime_services(state_store.load())
    return app


if __name__ == "__main__":
    raise SystemExit(main())
