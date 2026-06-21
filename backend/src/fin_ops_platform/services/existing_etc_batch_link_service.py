from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable

from fin_ops_platform.services.etc_service import EtcService
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


@dataclass(frozen=True, slots=True)
class ExistingEtcBatchLinkSpec:
    label: str
    case_id: str
    external_batch_id: str
    oa_row_id: str
    oa_amount: Decimal
    invoice_numbers: tuple[str, ...] | list[str]
    bank_row_id: str | None = None
    bank_amount: Decimal | None = None
    note: str | None = None


@dataclass(slots=True)
class ExistingEtcBatchLinkResult:
    label: str
    status: str
    message: str
    invoice_count: int = 0
    imported_count: int = 0
    invoice_total: Decimal = Decimal("0.00")
    delta: Decimal = Decimal("0.00")
    batch_id: str | None = None
    external_batch_id: str | None = None
    relation_case_id: str | None = None
    missing_invoice_numbers: list[str] | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "invoice_count": self.invoice_count,
            "imported_count": self.imported_count,
            "invoice_total": f"{self.invoice_total:.2f}",
            "delta": f"{self.delta:.2f}",
            "batch_id": self.batch_id,
            "external_batch_id": self.external_batch_id,
            "relation_case_id": self.relation_case_id,
            "missing_invoice_numbers": list(self.missing_invoice_numbers or []),
        }


class ExistingEtcBatchLinkService:
    """Attach already-imported ETC invoices to an existing OA-bank relation."""

    def __init__(
        self,
        *,
        etc_service: EtcService,
        import_service: Any,
        relation_command_service: Any | None = None,
        object_identity_repository: Any | None = None,
        link_import_result_to_existing_invoices: Callable[[Any], list[str]] | None = None,
        link_etc_invoices_to_existing_invoices: Callable[[list[Any]], list[str]] | None = None,
        refresh_after_etc_invoice_link: Callable[[list[str], str], None] | None = None,
        persist_pair_relations: Callable[[list[str]], None] | None = None,
        invalidate_workbench_scopes: Callable[[list[str]], None] | None = None,
        persist_etc_state: Callable[[], None] | None = None,
    ) -> None:
        self._etc_service = etc_service
        self._import_service = import_service
        self._relation_command_service = relation_command_service
        self._object_identity_repository = object_identity_repository or import_service
        self._link_import_result_to_existing_invoices = link_import_result_to_existing_invoices or (lambda _result: [])
        self._link_etc_invoices_to_existing_invoices = link_etc_invoices_to_existing_invoices or (lambda _invoices: [])
        self._refresh_after_etc_invoice_link = refresh_after_etc_invoice_link or (lambda _months, _reason: None)
        self._persist_pair_relations = persist_pair_relations or (lambda _case_ids: None)
        self._invalidate_workbench_scopes = invalidate_workbench_scopes or (lambda _scopes: None)
        self._persist_etc_state = persist_etc_state or (lambda: None)

    def link_existing_invoices(self, spec: ExistingEtcBatchLinkSpec) -> ExistingEtcBatchLinkResult:
        relation = self._active_relation_for_spec(spec)
        requested_numbers = self._normalize_invoice_numbers(spec.invoice_numbers)
        if not requested_numbers:
            return ExistingEtcBatchLinkResult(
                label=spec.label,
                status="attention",
                message=f"{spec.label} 未提供可关联的 ETC 发票号码。",
            )

        canonical_by_number = self._canonical_invoices_by_number(requested_numbers)
        etc_by_number = {invoice.invoice_number: invoice for invoice in self._etc_service.list_invoices_by_numbers(requested_numbers)}
        missing_numbers = [
            invoice_number
            for invoice_number in requested_numbers
            if invoice_number not in canonical_by_number and invoice_number not in etc_by_number
        ]
        if missing_numbers:
            return ExistingEtcBatchLinkResult(
                label=spec.label,
                status="attention",
                message=f"{spec.label} 仍有 ETC 发票未导入，已跳过关联。",
                missing_invoice_numbers=missing_numbers,
            )

        command_update = self._relation_metadata_update_command()
        imported_count = 0
        if missing_etc_numbers := [invoice_number for invoice_number in requested_numbers if invoice_number not in etc_by_number]:
            records = [
                self._canonical_invoice_record(canonical_by_number[invoice_number])
                for invoice_number in missing_etc_numbers
                if invoice_number in canonical_by_number
            ]
            import_result = self._etc_service.import_historical_invoices_from_records(
                records=records,
                source_name=f"{spec.external_batch_id}.existing_canonical_invoices",
            )
            imported_count = int(getattr(import_result, "imported", 0) or 0)
            changed_months = self._link_import_result_to_existing_invoices(import_result)
            self._refresh_after_etc_invoice_link(changed_months, f"existing_etc_batch_link_import:{spec.external_batch_id}")

        batch = self._etc_service.create_historical_submitted_batch(
            case_id=spec.case_id,
            external_batch_id=spec.external_batch_id,
            invoice_numbers=requested_numbers,
            linked_oa_row_id=spec.oa_row_id,
            oa_amount=spec.oa_amount,
            note=spec.note or f"{spec.label} ETC 发票关联到现有 OA-银行配对。",
        )
        batch_invoices = self._etc_service.list_invoices_by_ids(list(batch.invoice_ids))
        changed_months = self._link_etc_invoices_to_existing_invoices(batch_invoices)
        self._refresh_after_etc_invoice_link(changed_months, f"existing_etc_batch_link_submit:{spec.external_batch_id}")

        invoice_total = Decimal(batch.total_amount).quantize(Decimal("0.01"))
        settlement_amount = self._quantize(spec.bank_amount if spec.bank_amount is not None else spec.oa_amount)
        oa_amount = self._quantize(spec.oa_amount)
        bank_amount = self._quantize(spec.bank_amount) if spec.bank_amount is not None else None
        delta = (settlement_amount - invoice_total).quantize(Decimal("0.01"))
        amount_check = {
            **dict(relation.get("amount_check") or {}),
            "status": "matched" if delta == Decimal("0.00") else "mismatch",
            "direction": "expense",
            "oa_amount": f"{oa_amount:.2f}",
            "invoice_total": f"{invoice_total:.2f}",
            "delta": f"{delta:.2f}",
            "amount_delta": f"{delta:.2f}",
            "etc_batch_id": batch.id,
            "external_etc_batch_id": batch.etc_batch_id,
            "invoice_count": len(batch_invoices),
            "source": "existing_etc_batch_link",
            "coverage_status": "matched" if delta == Decimal("0.00") else "partial",
        }
        if bank_amount is not None:
            amount_check["bank_amount"] = f"{bank_amount:.2f}"

        special_metadata = {
            "etc_batch_link": {
                "source": "existing_etc_batch_link",
                "label": spec.label,
                "external_etc_batch_id": batch.etc_batch_id,
                "etc_batch_id": batch.id,
                "invoice_numbers": requested_numbers,
                "invoice_count": len(batch_invoices),
                "invoice_total": f"{invoice_total:.2f}",
                "delta": f"{delta:.2f}",
            },
        }
        note = spec.note or f"{spec.label} ETC 发票关联到现有配对批次。"
        command_result = command_update(
            case_id=spec.case_id,
            amount_check=amount_check,
            special_metadata=special_metadata,
            display_tags=["ETC发票已关联"],
            actor_id="system_existing_etc_batch_link",
            note=note,
            history_operation_type="link_existing_etc_batch",
        )
        updated_relation = command_result.get("relation") if isinstance(command_result, dict) else None
        if not isinstance(updated_relation, dict):
            updated_relation = {"case_id": spec.case_id}
        relation_case_id = str(updated_relation.get("case_id") or spec.case_id)
        self._persist_pair_relations([relation_case_id])
        self._invalidate_workbench_scopes(["all", *changed_months])
        self._persist_etc_state()

        return ExistingEtcBatchLinkResult(
            label=spec.label,
            status="ok",
            message=f"{spec.label} ETC 发票已关联到现有配对批次。",
            invoice_count=len(batch_invoices),
            imported_count=imported_count,
            invoice_total=invoice_total,
            delta=delta,
            batch_id=str(batch.id),
            external_batch_id=str(batch.etc_batch_id),
            relation_case_id=relation_case_id,
            missing_invoice_numbers=[],
        )

    def _relation_metadata_update_command(self) -> Callable[..., dict[str, Any]]:
        command_update = (
            getattr(self._relation_command_service, "update_relation_metadata_for_case_id", None)
            if self._relation_command_service is not None
            else None
        )
        if not callable(command_update):
            raise WorkbenchRelationCommandError(
                "workbench_relation_command_unavailable",
                "Existing ETC batch link requires WorkbenchRelationCommandService.update_relation_metadata_for_case_id.",
            )
        return command_update

    def _active_relation_for_spec(self, spec: ExistingEtcBatchLinkSpec) -> dict[str, Any]:
        get_relation = getattr(self._relation_command_service, "get_active_relation_by_case_id", None)
        if not callable(get_relation):
            raise WorkbenchRelationCommandError(
                "workbench_relation_command_unavailable",
                "Existing ETC batch link requires WorkbenchRelationCommandService.get_active_relation_by_case_id.",
            )
        try:
            relation = get_relation(spec.case_id)
        except WorkbenchRelationCommandError as exc:
            if exc.error_code == "workbench_relation_not_found":
                raise KeyError("workbench_relation_not_found") from exc
            raise
        relation_row_ids = {str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()}
        required_row_ids = {str(spec.oa_row_id or "").strip()}
        if spec.bank_row_id:
            required_row_ids.add(str(spec.bank_row_id).strip())
        if not required_row_ids.issubset(relation_row_ids):
            raise ValueError(f"{spec.label} target rows do not belong to active relation {spec.case_id}.")
        return relation

    @staticmethod
    def _normalize_invoice_numbers(invoice_numbers: Iterable[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_number in list(invoice_numbers or []):
            invoice_number = str(raw_number or "").strip()
            if not invoice_number or invoice_number in seen:
                continue
            seen.add(invoice_number)
            normalized.append(invoice_number)
        return normalized

    def _canonical_invoices_by_number(self, invoice_numbers: list[str]) -> dict[str, Any]:
        invoices_by_number: dict[str, Any] = {}
        finder = getattr(self._object_identity_repository, "find_invoice_by_identity", None)
        if not callable(finder):
            return invoices_by_number
        for invoice_number in invoice_numbers:
            invoice = finder(canonical_key=invoice_number)
            if invoice is not None:
                invoices_by_number.setdefault(invoice_number, invoice)
        return invoices_by_number

    def _canonical_invoice_record(self, invoice: Any) -> dict[str, object]:
        total_amount = self._quantize(getattr(invoice, "total_with_tax", None) or getattr(invoice, "amount", None) or Decimal("0.00"))
        tax_amount = self._quantize(getattr(invoice, "tax_amount", None) or Decimal("0.00"))
        amount_without_tax = self._quantize(total_amount - tax_amount)
        invoice_number = str(
            getattr(invoice, "digital_invoice_no", None)
            or getattr(invoice, "invoice_no", None)
            or getattr(invoice, "source_unique_key", None)
            or ""
        ).strip()
        return {
            "invoice_number": invoice_number,
            "issue_date": str(getattr(invoice, "invoice_date", None) or ""),
            "passage_start_date": str(getattr(invoice, "invoice_date", None) or ""),
            "passage_end_date": str(getattr(invoice, "invoice_date", None) or ""),
            "plate_number": "",
            "vehicle_type": "",
            "seller_name": str(getattr(invoice, "seller_name", None) or getattr(getattr(invoice, "counterparty", None), "name", "") or ""),
            "seller_tax_no": str(getattr(invoice, "seller_tax_no", None) or ""),
            "buyer_name": str(getattr(invoice, "buyer_name", None) or ""),
            "buyer_tax_no": str(getattr(invoice, "buyer_tax_no", None) or ""),
            "amount_without_tax": f"{amount_without_tax:.2f}",
            "tax_amount": f"{tax_amount:.2f}",
            "total_amount": f"{total_amount:.2f}",
            "tax_rate": str(getattr(invoice, "tax_rate", None) or ""),
        }

    @staticmethod
    def _quantize(value: Any) -> Decimal:
        return Decimal(str(value if value is not None else "0")).quantize(Decimal("0.01"))
