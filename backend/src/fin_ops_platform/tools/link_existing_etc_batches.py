from __future__ import annotations

import argparse
from collections.abc import Sequence
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from fin_ops_platform.services.etc_existing_invoice_link_service import EtcExistingInvoiceLinkService
from fin_ops_platform.services.existing_etc_batch_link_service import (
    ExistingEtcBatchLinkService,
    ExistingEtcBatchLinkSpec,
)
from fin_ops_platform.tools.runtime_application import (
    build_tool_runtime_application,
    etc_state_persister,
    etc_service,
    import_service,
    invalidate_workbench_scopes,
    invoice_etc_metadata_persister,
    object_identity_repository,
    persist_workbench_pair_relations,
    workbench_relation_command_service,
    workbench_relation_reader,
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
    app = build_tool_runtime_application(args.data_dir)
    if args.execute:
        link_service = EtcExistingInvoiceLinkService(
            import_service=import_service(app),
            etc_service=etc_service(app),
            persist_linked_invoices=invoice_etc_metadata_persister(app),
        )
        service = ExistingEtcBatchLinkService(
            etc_service=etc_service(app),
            import_service=import_service(app),
            relation_command_service=workbench_relation_command_service(app),
            link_import_result_to_existing_invoices=link_service.link_import_result_to_existing_invoices,
            link_etc_invoices_to_existing_invoices=link_service.link_etc_invoices_to_existing_invoices,
            refresh_after_etc_invoice_link=lambda _months, _reason: None,
            persist_pair_relations=lambda case_ids: persist_workbench_pair_relations(app, case_ids),
            invalidate_workbench_scopes=lambda scope_keys: invalidate_workbench_scopes(app, scope_keys),
            persist_etc_state=etc_state_persister(app),
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
    relation = _active_relation_by_case_id(app, spec.case_id)
    identity_repository = _object_identity_repository(app)
    if identity_repository is None:
        return {
            "label": spec.label,
            "status": "attention",
            "error": "identity_repository_unavailable",
            "case_id": spec.case_id,
            "external_batch_id": spec.external_batch_id,
            "active_relation_found": isinstance(relation, dict),
            "requested_invoice_count": len(spec.invoice_numbers),
            "found_invoice_count": 0,
            "invoice_total": "0.00",
            "missing_invoice_numbers": list(spec.invoice_numbers),
        }
    canonical_by_number = _canonical_invoices_by_number(identity_repository, list(spec.invoice_numbers))
    canonical_numbers = set(canonical_by_number)
    etc_numbers = {invoice.invoice_number for invoice in etc_service(app).list_invoices_by_numbers(list(spec.invoice_numbers))}
    found_numbers = sorted(set(canonical_numbers).union(etc_numbers))
    missing_numbers = [invoice_number for invoice_number in spec.invoice_numbers if invoice_number not in found_numbers]
    invoice_total = _invoice_total(app, canonical_by_number, found_numbers)
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


def _active_relation_by_case_id(app: Any, case_id: str) -> dict[str, object] | None:
    command_service = _workbench_relation_reader(app)
    get_relation = getattr(command_service, "get_active_relation_by_case_id", None)
    if not callable(get_relation):
        return None
    try:
        relation = get_relation(case_id)
    except Exception:
        return None
    return relation if isinstance(relation, dict) else None


def _workbench_relation_reader(app: Any) -> Any | None:
    return workbench_relation_reader(app)


def _link_etc_invoices_to_existing_invoices(app: Any, invoice_ids: list[str]) -> dict[str, object]:
    link_service = EtcExistingInvoiceLinkService(
        import_service=import_service(app),
        etc_service=etc_service(app),
        persist_linked_invoices=invoice_etc_metadata_persister(app),
    )
    return link_service.link_etc_invoices_to_existing_invoices(invoice_ids)


def _object_identity_repository(app: Any) -> Any | None:
    return object_identity_repository(app)


def _canonical_invoices_by_number(identity_repository: Any, invoice_numbers: list[str]) -> dict[str, Any]:
    finder = getattr(identity_repository, "find_invoice_by_identity", None)
    if not callable(finder):
        return {}
    invoices_by_number: dict[str, Any] = {}
    for raw_number in invoice_numbers:
        invoice_number = str(raw_number or "").strip()
        if not invoice_number:
            continue
        invoice = finder(canonical_key=invoice_number)
        if invoice is not None:
            invoices_by_number.setdefault(invoice_number, invoice)
    return invoices_by_number


def _invoice_total(app: Any, canonical_by_number: dict[str, Any], invoice_numbers: list[str]) -> Decimal:
    numbers = set(invoice_numbers)
    total = Decimal("0.00")
    counted = set(canonical_by_number)
    for invoice in canonical_by_number.values():
        amount = getattr(invoice, "total_with_tax", None) or getattr(invoice, "amount", None) or Decimal("0.00")
        total += Decimal(str(amount))
    missing_canonical_numbers = sorted(numbers - counted)
    for invoice in etc_service(app).list_invoices_by_numbers(missing_canonical_numbers):
        total += Decimal(str(invoice.total_amount))
    return total.quantize(Decimal("0.01"))


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


if __name__ == "__main__":
    raise SystemExit(main())
