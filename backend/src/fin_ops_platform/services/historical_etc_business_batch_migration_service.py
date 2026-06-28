from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from fin_ops_platform.services.etc_service import EtcService
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


@dataclass(frozen=True, slots=True)
class HistoricalEtcBusinessBatchMigrationSpec:
    label: str
    business_batch_id: str
    task_id: str
    submission_batch_id: str
    external_batch_id: str
    reported_amount: Decimal
    relation_case_id: str
    oa_row_id: str | None = None
    scope_month: str | None = None
    gap_reason: str | None = None


@dataclass(slots=True)
class HistoricalEtcBusinessBatchMigrationResult:
    label: str
    status: str
    message: str
    business_batch_id: str
    submission_batch_id: str
    external_batch_id: str
    relation_case_id: str
    invoice_count: int
    invoice_total: Decimal
    reported_amount: Decimal
    amount_delta: Decimal
    changed_months: list[str]

    def to_payload(self) -> dict[str, object]:
        return {
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "business_batch_id": self.business_batch_id,
            "submission_batch_id": self.submission_batch_id,
            "external_batch_id": self.external_batch_id,
            "relation_case_id": self.relation_case_id,
            "invoice_count": self.invoice_count,
            "invoice_total": f"{self.invoice_total:.2f}",
            "reported_amount": f"{self.reported_amount:.2f}",
            "amount_delta": f"{self.amount_delta:.2f}",
            "changed_months": list(self.changed_months),
        }


class HistoricalEtcBusinessBatchMigrationService:
    """Promote already-submitted legacy ETC batches into the ETC business batch model."""

    def __init__(
        self,
        *,
        etc_service: EtcService,
        relation_command_service: Any | None = None,
        link_etc_invoices_to_existing_invoices: Callable[[list[Any]], list[str]] | None = None,
        refresh_after_etc_invoice_link: Callable[[list[str], str], None] | None = None,
        persist_pair_relations: Callable[[list[str]], None] | None = None,
        persist_etc_state: Callable[[], None] | None = None,
    ) -> None:
        self._etc_service = etc_service
        self._relation_command_service = relation_command_service
        self._link_etc_invoices_to_existing_invoices = link_etc_invoices_to_existing_invoices or (lambda _invoices: [])
        self._refresh_after_etc_invoice_link = refresh_after_etc_invoice_link or (lambda _months, _reason: None)
        self._persist_pair_relations = persist_pair_relations or (lambda _case_ids: None)
        self._persist_etc_state = persist_etc_state or (lambda: None)

    def migrate(self, spec: HistoricalEtcBusinessBatchMigrationSpec) -> HistoricalEtcBusinessBatchMigrationResult:
        relation = self._validated_relation(spec)
        command_update = self._relation_metadata_update_command()
        batch = self._etc_service.create_historical_submitted_business_batch(
            business_batch_id=spec.business_batch_id,
            task_id=spec.task_id,
            submission_batch_id=spec.submission_batch_id,
            external_etc_batch_id=spec.external_batch_id,
            reported_amount=spec.reported_amount,
            relation_case_id=spec.relation_case_id,
            linked_oa_row_id=spec.oa_row_id,
            gap_reason=spec.gap_reason,
            scope_month=spec.scope_month,
        )
        invoices = self._etc_service.list_invoices_by_ids(list(getattr(batch, "invoice_ids", []) or []))
        invoice_total = sum((Decimal(str(getattr(invoice, "total_amount", "0.00"))) for invoice in invoices), Decimal("0.00")).quantize(
            Decimal("0.01")
        )
        reported_amount = Decimal(str(spec.reported_amount)).quantize(Decimal("0.01"))
        amount_delta = (reported_amount - invoice_total).quantize(Decimal("0.01"))
        changed_months = self._changed_months(
            [
                *self._link_etc_invoices_to_existing_invoices(invoices),
                str(spec.scope_month or "").strip(),
            ]
        )
        if changed_months:
            self._refresh_after_etc_invoice_link(changed_months, f"historical_etc_business_batch_migration:{spec.external_batch_id}")
        self._update_relation_metadata(
            spec,
            relation,
            invoice_count=len(invoices),
            invoice_total=invoice_total,
            amount_delta=amount_delta,
            command_update=command_update,
        )
        self._persist_pair_relations([spec.relation_case_id])
        self._persist_etc_state()
        return HistoricalEtcBusinessBatchMigrationResult(
            label=spec.label,
            status="ok",
            message=f"{spec.label} 已迁移到 ETC 业务批次模型。",
            business_batch_id=batch.business_batch_id,
            submission_batch_id=str(batch.submission_batch_id or ""),
            external_batch_id=str(batch.external_etc_batch_id or ""),
            relation_case_id=spec.relation_case_id,
            invoice_count=len(invoices),
            invoice_total=invoice_total,
            reported_amount=reported_amount,
            amount_delta=amount_delta,
            changed_months=changed_months,
        )

    def _validated_relation(self, spec: HistoricalEtcBusinessBatchMigrationSpec) -> dict[str, Any]:
        get_relation = getattr(self._relation_command_service, "get_active_relation_by_case_id", None)
        if not callable(get_relation):
            raise WorkbenchRelationCommandError(
                "workbench_relation_command_unavailable",
                "Historical ETC business batch migration requires WorkbenchRelationCommandService.get_active_relation_by_case_id.",
            )
        try:
            relation = get_relation(spec.relation_case_id)
        except WorkbenchRelationCommandError as exc:
            if exc.error_code == "workbench_relation_not_found":
                raise KeyError("workbench_relation_not_found") from exc
            raise
        amount_check = relation.get("amount_check") if isinstance(relation.get("amount_check"), dict) else {}
        relation_external_id = str(amount_check.get("external_etc_batch_id") or "").strip()
        if relation_external_id and relation_external_id != spec.external_batch_id:
            raise ValueError(
                f"{spec.label} active relation points to {relation_external_id}, not {spec.external_batch_id}."
            )
        if spec.oa_row_id:
            row_ids = {str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()}
            if str(spec.oa_row_id).strip() not in row_ids:
                raise ValueError(f"{spec.label} OA row does not belong to active relation {spec.relation_case_id}.")
        submission_batch = self._etc_service.get_batch(spec.submission_batch_id)
        if str(getattr(submission_batch, "etc_batch_id", "") or "").strip() != spec.external_batch_id:
            raise ValueError(f"{spec.label} submission batch does not match external ETC batch id.")
        return relation

    def _update_relation_metadata(
        self,
        spec: HistoricalEtcBusinessBatchMigrationSpec,
        relation: dict[str, Any],
        *,
        invoice_count: int,
        invoice_total: Decimal,
        amount_delta: Decimal,
        command_update: Callable[..., dict[str, Any]],
    ) -> None:
        amount_check = dict(relation.get("amount_check") if isinstance(relation.get("amount_check"), dict) else {})
        amount_check.update(
            {
                "external_etc_batch_id": spec.external_batch_id,
                "business_batch_id": spec.business_batch_id,
                "etc_business_batch_id": spec.business_batch_id,
                "etc_batch_id": spec.submission_batch_id,
                "invoice_count": invoice_count,
                "invoice_total": f"{invoice_total:.2f}",
                "delta": f"{amount_delta:.2f}",
                "amount_delta": f"{amount_delta:.2f}",
                "source": "historical_etc_business_batch_migration",
            }
        )
        special_metadata = {
            "historical_etc_business_batch_migration": {
                "label": spec.label,
                "business_batch_id": spec.business_batch_id,
                "submission_batch_id": spec.submission_batch_id,
                "external_etc_batch_id": spec.external_batch_id,
                "gap_reason": str(spec.gap_reason or "").strip(),
            },
        }
        note = spec.gap_reason or f"{spec.label} 迁移到 ETC 业务批次模型。"
        command_update(
            case_id=spec.relation_case_id,
            amount_check=amount_check,
            special_metadata=special_metadata,
            display_tags=["ETC批次"],
            actor_id="system_historical_etc_business_batch_migration",
            note=note,
            history_operation_type="historical_etc_business_batch_migration",
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
                "Historical ETC business batch migration requires WorkbenchRelationCommandService.update_relation_metadata_for_case_id.",
            )
        return command_update

    @staticmethod
    def _changed_months(months: list[str]) -> list[str]:
        normalized = [
            str(month or "").strip()
            for month in months
            if len(str(month or "").strip()) == 7 and str(month or "").strip()[4:5] == "-"
        ]
        return sorted(dict.fromkeys(normalized))
