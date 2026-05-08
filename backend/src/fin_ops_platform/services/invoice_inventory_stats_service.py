from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


MANUAL_INVOICE_IMPORT_SOURCE_TYPE = "manual_invoice_import"
ETC_INVOICE_IMPORT_SOURCE_TYPES = {"etc_import", "etc_invoice_import"}
HIDDEN_AFTER_ETC_SUBMISSION = "hidden_after_etc_submission"
OA_ATTACHMENT_INVOICE_SOURCE_KIND = "oa_attachment_invoice"


@dataclass(slots=True)
class InvoiceInventoryStats:
    system_total: int
    manual_import_total: int
    workbench_visible_total: int
    hidden_submitted_etc_total: int
    extra_etc_total: int
    etc_summary_batch_count: int
    oa_attachment_total: int

    def to_payload(self) -> dict[str, int]:
        return asdict(self)


class InvoiceInventoryStatsService:
    def build_stats(
        self,
        *,
        invoices: Iterable[object],
        etc_summary_batch_count: int = 0,
        oa_attachment_total: int | None = None,
        workbench_snapshots: Iterable[dict[str, object]] | None = None,
    ) -> InvoiceInventoryStats:
        invoice_list = list(invoices)
        manual_import_total = 0
        hidden_invoice_total = 0
        hidden_submitted_etc_total = 0
        extra_etc_total = 0

        for invoice in invoice_list:
            has_manual_import_source = self._has_source_type(invoice, {MANUAL_INVOICE_IMPORT_SOURCE_TYPE})
            has_etc_source = self._has_etc_source(invoice)
            is_hidden_after_etc_submission = (
                getattr(invoice, "workbench_visibility", "visible") == HIDDEN_AFTER_ETC_SUBMISSION
            )
            if has_manual_import_source:
                manual_import_total += 1
            if is_hidden_after_etc_submission:
                hidden_invoice_total += 1
            if has_manual_import_source and is_hidden_after_etc_submission:
                hidden_submitted_etc_total += 1
            if has_etc_source and not has_manual_import_source:
                extra_etc_total += 1

        if oa_attachment_total is None:
            oa_attachment_total = self._count_oa_attachment_invoice_snapshots(workbench_snapshots or [])

        return InvoiceInventoryStats(
            system_total=len(invoice_list),
            manual_import_total=manual_import_total,
            workbench_visible_total=len(invoice_list) - hidden_invoice_total,
            hidden_submitted_etc_total=hidden_submitted_etc_total,
            extra_etc_total=extra_etc_total,
            etc_summary_batch_count=max(0, int(etc_summary_batch_count or 0)),
            oa_attachment_total=max(0, int(oa_attachment_total or 0)),
        )

    @classmethod
    def _has_etc_source(cls, invoice: object) -> bool:
        if cls._has_source_type(invoice, ETC_INVOICE_IMPORT_SOURCE_TYPES):
            return True
        tags = [str(tag).strip() for tag in list(getattr(invoice, "tags", []) or [])]
        if "ETC" in tags:
            return True
        return bool(
            str(getattr(invoice, "etc_invoice_id", "") or "").strip()
            or str(getattr(invoice, "etc_import_batch_id", "") or "").strip()
        )

    @staticmethod
    def _has_source_type(invoice: object, source_types: set[str]) -> bool:
        for source_link in list(getattr(invoice, "source_links", []) or []):
            if not isinstance(source_link, dict):
                continue
            source_type = str(source_link.get("source_type", "")).strip()
            if source_type in source_types:
                return True
        return False

    @staticmethod
    def _count_oa_attachment_invoice_snapshots(workbench_snapshots: Iterable[dict[str, object]]) -> int:
        return sum(
            1
            for row in workbench_snapshots
            if isinstance(row, dict)
            and str(row.get("type", "")).strip() == "invoice"
            and str(row.get("source_kind", "")).strip() == OA_ATTACHMENT_INVOICE_SOURCE_KIND
        )
