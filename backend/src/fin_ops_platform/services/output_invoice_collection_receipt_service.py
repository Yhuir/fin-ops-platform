from __future__ import annotations

from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.output_invoice_collection_models import (
    OutputInvoiceCollectionRowRef,
    output_invoice_collection_freshness_metadata,
)
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionError, OutputInvoiceReceiptPreviewService


RowProvider = Callable[[str], dict[str, Any] | None]


class OutputInvoiceCollectionReceiptService:
    def __init__(self, *, repository: Any, row_provider: RowProvider) -> None:
        self._repository = repository
        self._row_provider = row_provider
        self._preview_service = OutputInvoiceReceiptPreviewService()

    def preview(self, row_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = dict(payload or {})
        row = self._require_row(row_id)
        preview = self._preview_service.preview(
            row=row,
            selected_bank_transaction_id=str(body.get("bankTransactionId") or body.get("selectedBankTransactionId") or "").strip() or None,
        )
        if preview.get("canPreview"):
            receipt = dict(preview.get("receipt") or {})
            receipt["canCreateFormalReceipt"] = True
            receipt["nextAction"] = "create_formal_receipt"
            preview["receipt"] = receipt
            preview["warnings"] = []
        return preview

    def create_receipt(
        self,
        row_id: str,
        payload: dict[str, Any] | None,
        *,
        actor_id: str,
        tenant_id: str = "default",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        body = dict(payload or {})
        row = self._require_row(row_id)
        selected_bank_id = str(body.get("bankTransactionId") or body.get("selectedBankTransactionId") or "").strip() or None
        preview = self._preview_service.preview(row=row, selected_bank_transaction_id=selected_bank_id)
        if not preview.get("canPreview"):
            raise OutputInvoiceCollectionError(
                "receipt_not_available",
                str(preview.get("reason") or "当前记录不能创建正式收据。"),
                details={"reasonCode": preview.get("reasonCode")},
            )
        idempotency_key = str(body.get("idempotencyKey") or body.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise OutputInvoiceCollectionError("idempotency_key_required", "创建正式收据必须提供 Idempotency-Key。")
        receipt_payload = dict(preview.get("receipt") or {})
        amount = _money(receipt_payload.get("amount"))
        bank_summary = _bank_summary(row, str(receipt_payload.get("bankTransactionId") or selected_bank_id or ""))
        row_ref = OutputInvoiceCollectionRowRef.from_row(row)

        def mutate(transaction: Any | None = None) -> dict[str, Any]:
            kwargs = {
                "row_ref": row_ref,
                "bank_summary": bank_summary,
                "amount": amount,
                "idempotency_key": idempotency_key,
                "payload": {**receipt_payload, "invoiceNo": row.get("invoice", {}).get("displayNo")},
                "actor_id": actor_id,
                "tenant_id": tenant_id,
            }
            if transaction is not None:
                kwargs["transaction"] = transaction
            return self._repository.create_receipt(**kwargs)

        receipt = self._run_mutation(row, reason="receipt_created", mutate=mutate, trace_id=trace_id)
        return {**output_invoice_collection_freshness_metadata(row), "receipt": receipt}

    def void_receipt(
        self,
        receipt_id: str,
        payload: dict[str, Any] | None,
        *,
        actor_id: str,
        tenant_id: str = "default",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        body = dict(payload or {})
        def mutate(transaction: Any | None = None) -> dict[str, Any]:
            kwargs = {
                "receipt_id": str(receipt_id or "").strip(),
                "reason": str(body.get("reason") or "").strip(),
                "actor_id": actor_id,
                "tenant_id": tenant_id,
            }
            if transaction is not None:
                kwargs["transaction"] = transaction
            return self._repository.void_receipt(**kwargs)

        receipt = self._run_receipt_mutation(receipt_id, reason="receipt_voided", mutate=mutate, trace_id=trace_id, tenant_id=tenant_id)
        row = self._row_for_receipt(receipt)
        return {**output_invoice_collection_freshness_metadata(row), "receipt": receipt}

    def reissue_receipt(
        self,
        receipt_id: str,
        payload: dict[str, Any] | None,
        *,
        actor_id: str,
        tenant_id: str = "default",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        body = dict(payload or {})
        def mutate(transaction: Any | None = None) -> dict[str, Any]:
            kwargs = {
                "receipt_id": str(receipt_id or "").strip(),
                "reason": str(body.get("reason") or "").strip(),
                "actor_id": actor_id,
                "tenant_id": tenant_id,
            }
            if transaction is not None:
                kwargs["transaction"] = transaction
            return self._repository.reissue_receipt(**kwargs)

        receipt = self._run_receipt_mutation(receipt_id, reason="receipt_reissued", mutate=mutate, trace_id=trace_id, tenant_id=tenant_id)
        row = self._row_for_receipt(receipt)
        return {**output_invoice_collection_freshness_metadata(row), "receipt": receipt}

    def history(self, *, invoice_id: str, tenant_id: str = "default") -> dict[str, Any]:
        receipts = self._repository.list_receipts(invoice_id=str(invoice_id or "").strip(), tenant_id=tenant_id)
        return {
            "invoiceId": invoice_id,
            "sourceAvailable": True,
            "sourceName": "formal_receipt_lifecycle",
            "receipts": receipts,
        }

    def get_settings(self, *, tenant_id: str = "default") -> dict[str, Any]:
        return {"settings": self._repository.get_receipt_settings(tenant_id=tenant_id)}

    def update_settings(self, payload: dict[str, Any] | None, *, actor_id: str, tenant_id: str = "default") -> dict[str, Any]:
        body = dict(payload or {})
        prefix = str(body.get("prefix") or "").strip().upper()
        if not prefix or len(prefix) > 12 or not prefix.replace("-", "").isalnum():
            raise OutputInvoiceCollectionError("invalid_receipt_prefix", "收据编号前缀必须是 1-12 位字母数字。")
        reset_period = str(body.get("resetPeriod") or body.get("reset_period") or "monthly").strip().lower()
        if reset_period not in {"monthly", "yearly", "none"}:
            raise OutputInvoiceCollectionError("invalid_receipt_reset_period", "resetPeriod must be monthly, yearly or none.")
        settings = self._repository.update_receipt_settings(
            tenant_id=tenant_id,
            prefix=prefix,
            reset_period=reset_period,
            actor_id=actor_id,
        )
        return {"settings": settings}

    def _require_row(self, row_id: str) -> dict[str, Any]:
        normalized = str(row_id or "").strip()
        if not normalized:
            raise OutputInvoiceCollectionError("row_id_required", "row_id is required.")
        row = self._row_provider(normalized)
        if row is None:
            raise OutputInvoiceCollectionError("row_not_found", "销项发票收款行不存在。", status_code=HTTPStatus.NOT_FOUND)
        return row

    def _run_mutation(
        self,
        row: dict[str, Any],
        *,
        reason: str,
        mutate: Callable[[Any | None], dict[str, Any]],
        trace_id: str | None,
    ) -> dict[str, Any]:
        transaction_runner = getattr(self._repository, "run_in_transaction", None)
        if callable(transaction_runner):
            def callback(transaction: Any) -> dict[str, Any]:
                return mutate(transaction)

            return transaction_runner(callback)
        return mutate(None)

    def _run_receipt_mutation(
        self,
        receipt_id: str,
        *,
        reason: str,
        mutate: Callable[[Any | None], dict[str, Any]],
        trace_id: str | None,
        tenant_id: str,
    ) -> dict[str, Any]:
        before = self._repository.get_receipt(receipt_id=str(receipt_id or "").strip(), tenant_id=tenant_id)
        row = self._row_provider(str((before or {}).get("invoiceId") or "")) if before else None
        return self._run_mutation(row or {"invoice": {"invoiceDate": ""}}, reason=reason, mutate=mutate, trace_id=trace_id)

    def _row_for_receipt(self, receipt: dict[str, Any]) -> dict[str, Any]:
        row = self._row_provider(str(receipt.get("invoiceId") or ""))
        return row or {"invoice": {"invoiceDate": ""}}


def _bank_summary(row: dict[str, Any], bank_transaction_id: str) -> dict[str, Any]:
    for summary in list((row.get("bankTransactions") or {}).get("summaries") or []):
        if str(summary.get("bankTransactionId") or "") == bank_transaction_id:
            return dict(summary)
    raise OutputInvoiceCollectionError("bank_transaction_not_found", "选中的收入流水不存在。", status_code=HTTPStatus.NOT_FOUND)


def _money(value: Any) -> str:
    try:
        return f"{Decimal(str(value or '0').replace(',', '')).quantize(Decimal('0.01')):.2f}"
    except (InvalidOperation, ValueError):
        raise OutputInvoiceCollectionError("invalid_receipt_amount", "收据金额无效。") from None
