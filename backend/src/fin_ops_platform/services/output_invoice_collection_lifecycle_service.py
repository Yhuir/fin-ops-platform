from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime
from http import HTTPStatus
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from fin_ops_platform.services.output_invoice_collection_models import (
    OutputInvoiceCollectionRowRef,
    output_invoice_collection_freshness_metadata,
    output_invoice_collection_scope_key,
)
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionError
from fin_ops_platform.services.output_invoice_collection_status_service import OutputInvoiceCollectionStatusOverlayService
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway


RowProvider = Callable[[str], dict[str, Any] | None]


class InMemoryOutputInvoiceCollectionLifecycleRepository:
    """Local/test lifecycle adapter. Production uses the PostgreSQL repository."""

    def __init__(self) -> None:
        self._overrides: dict[tuple[str, str], dict[str, Any]] = {}
        self._reminders: dict[str, dict[str, Any]] = {}
        self._red_relations: dict[str, dict[str, Any]] = {}
        self._receipt_settings: dict[str, Any] = {
            "tenantId": "default",
            "prefix": "SK",
            "resetPeriod": "monthly",
            "version": 1,
        }
        self._receipt_counters: dict[tuple[str, str, str], int] = {}
        self._receipts: dict[str, dict[str, Any]] = {}
        self._receipt_events: list[dict[str, Any]] = []
        self._receipt_idempotency: dict[tuple[str, str], str] = {}
        self._receipt_lock = RLock()

    def overlays_for_identity_keys(self, identity_keys: list[str], *, tenant_id: str = "default") -> dict[str, dict[str, Any]]:
        selected = {str(item) for item in identity_keys}
        result: dict[str, dict[str, Any]] = {}
        for identity_key in selected:
            with self._receipt_lock:
                receipts = [
                    deepcopy(receipt)
                    for receipt in self._receipts.values()
                    if receipt.get("invoiceIdentityKey") == identity_key and receipt.get("status") in {"issued", "voided", "reissued"}
                    and receipt.get("tenantId") == tenant_id
                ]
            receipts.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
            red_relations = [
                deepcopy(relation)
                for relation in self._red_relations.values()
                if relation.get("invoiceIdentityKey") == identity_key and relation.get("status") == "active"
                and relation.get("tenantId") == tenant_id
            ]
            reminders = [
                deepcopy(reminder)
                for reminder in self._reminders.values()
                if reminder.get("invoiceIdentityKey") == identity_key and reminder.get("status") == "active"
                and reminder.get("tenantId") == tenant_id
            ]
            reminders.sort(key=lambda item: str(item.get("updatedAt") or item.get("createdAt") or ""), reverse=True)
            result[identity_key] = {
                "override": deepcopy(self._overrides.get((tenant_id, identity_key))) if self._overrides.get((tenant_id, identity_key)) else None,
                "reminder": reminders[0] if reminders else None,
                "redRelations": red_relations,
                "receipts": receipts,
            }
        return result

    def set_status_override(
        self,
        *,
        row_ref: OutputInvoiceCollectionRowRef,
        status_code: str | None,
        expected_collection_date: str | None,
        note: str,
        expected_version: int | None,
        actor_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        override_key = (tenant_id, row_ref.invoice_identity_key)
        current = self._overrides.get(override_key)
        current_version = int((current or {}).get("version") or 0)
        if expected_version is not None and expected_version != current_version:
            raise OutputInvoiceCollectionError(
                "version_conflict",
                "收款状态已被其他用户修改，请刷新后重试。",
                status_code=HTTPStatus.CONFLICT,
                details={"expectedVersion": expected_version, "actualVersion": current_version},
            )
        now = _now_iso()
        version = current_version + 1
        status = "active" if status_code else "revoked"
        override = {
            "id": str((current or {}).get("id") or uuid4()),
            "tenantId": tenant_id,
            "invoiceIdentityKey": row_ref.invoice_identity_key,
            "invoiceId": row_ref.invoice_id,
            "statusCode": status_code,
            "expectedCollectionDate": expected_collection_date,
            "note": note,
            "version": version,
            "status": status,
            "updatedBy": actor_id,
            "updatedAt": now,
            "createdBy": (current or {}).get("createdBy") or actor_id,
            "createdAt": (current or {}).get("createdAt") or now,
        }
        if status == "active":
            self._overrides[override_key] = override
        else:
            self._overrides.pop(override_key, None)
        return deepcopy(override)

    def upsert_reminder(
        self,
        *,
        row_ref: OutputInvoiceCollectionRowRef,
        remind_at: str,
        channel: str,
        note: str,
        actor_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        current = next(
            (
                reminder
                for reminder in self._reminders.values()
                if reminder.get("invoiceIdentityKey") == row_ref.invoice_identity_key and reminder.get("status") == "active"
                and reminder.get("tenantId") == tenant_id
            ),
            None,
        )
        now = _now_iso()
        reminder = {
            "id": str((current or {}).get("id") or uuid4()),
            "tenantId": tenant_id,
            "invoiceIdentityKey": row_ref.invoice_identity_key,
            "invoiceId": row_ref.invoice_id,
            "remindAt": remind_at,
            "channel": channel,
            "note": note,
            "status": "active",
            "sentAt": None,
            "result": None,
            "createdBy": (current or {}).get("createdBy") or actor_id,
            "createdAt": (current or {}).get("createdAt") or now,
            "updatedBy": actor_id,
            "updatedAt": now,
        }
        self._reminders[reminder["id"]] = reminder
        return deepcopy(reminder)

    def cancel_reminder(self, *, reminder_id: str, actor_id: str, tenant_id: str) -> dict[str, Any]:
        reminder = self._reminders.get(reminder_id)
        if reminder is None or reminder.get("tenantId") != tenant_id or reminder.get("status") != "active":
            raise OutputInvoiceCollectionError("reminder_not_found", "提醒不存在或已取消。", status_code=HTTPStatus.NOT_FOUND)
        reminder = dict(reminder)
        reminder.update({"status": "cancelled", "updatedBy": actor_id, "updatedAt": _now_iso()})
        self._reminders[reminder_id] = reminder
        return deepcopy(reminder)

    def confirm_red_relation(
        self,
        *,
        row_ref: OutputInvoiceCollectionRowRef,
        related_invoice_identity_key: str,
        related_invoice_id: str,
        relation_type: str,
        evidence: str,
        confidence: str,
        actor_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        now = _now_iso()
        relation = {
            "id": str(uuid4()),
            "tenantId": tenant_id,
            "invoiceIdentityKey": row_ref.invoice_identity_key,
            "invoiceId": row_ref.invoice_id,
            "relatedInvoiceIdentityKey": related_invoice_identity_key,
            "relatedInvoiceId": related_invoice_id,
            "relationType": relation_type,
            "evidence": evidence,
            "confidence": confidence,
            "source": "manual",
            "version": 1,
            "status": "active",
            "createdBy": actor_id,
            "createdAt": now,
            "updatedBy": actor_id,
            "updatedAt": now,
        }
        for item in self._red_relations.values():
            if (
                item.get("invoiceIdentityKey") == row_ref.invoice_identity_key
                and item.get("relatedInvoiceIdentityKey") == related_invoice_identity_key
                and item.get("status") == "active"
                and item.get("tenantId") == tenant_id
            ):
                item.update({**relation, "id": item["id"], "version": int(item.get("version") or 1) + 1})
                return deepcopy(item)
        self._red_relations[relation["id"]] = relation
        return deepcopy(relation)

    def revoke_red_relation(self, *, relation_id: str, actor_id: str, tenant_id: str) -> dict[str, Any]:
        relation = self._red_relations.get(relation_id)
        if relation is None or relation.get("tenantId") != tenant_id or relation.get("status") != "active":
            raise OutputInvoiceCollectionError("relation_not_found", "红蓝票关系不存在或已撤销。", status_code=HTTPStatus.NOT_FOUND)
        relation = dict(relation)
        relation.update({"status": "revoked", "updatedBy": actor_id, "updatedAt": _now_iso()})
        self._red_relations[relation_id] = relation
        return deepcopy(relation)

    def get_receipt_settings(self, *, tenant_id: str) -> dict[str, Any]:
        with self._receipt_lock:
            settings = dict(self._receipt_settings)
            settings["tenantId"] = tenant_id
            return settings

    def update_receipt_settings(self, *, tenant_id: str, prefix: str, reset_period: str, actor_id: str) -> dict[str, Any]:
        with self._receipt_lock:
            self._receipt_settings = {
                "tenantId": tenant_id,
                "prefix": prefix,
                "resetPeriod": reset_period,
                "version": int(self._receipt_settings.get("version") or 1) + 1,
                "updatedBy": actor_id,
                "updatedAt": _now_iso(),
            }
            return dict(self._receipt_settings)

    def create_receipt(
        self,
        *,
        row_ref: OutputInvoiceCollectionRowRef,
        bank_summary: dict[str, Any],
        amount: str,
        idempotency_key: str,
        payload: dict[str, Any],
        actor_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._receipt_lock:
            idempotency = (tenant_id, idempotency_key)
            existing_id = self._receipt_idempotency.get(idempotency)
            if existing_id and existing_id in self._receipts:
                return deepcopy(self._receipts[existing_id])
            settings = self.get_receipt_settings(tenant_id=tenant_id)
            prefix = str(settings.get("prefix") or "SK")
            period = _period_key(row_ref.invoice_date, str(settings.get("resetPeriod") or "monthly"))
            counter_key = (tenant_id, prefix, period)
            sequence = self._receipt_counters.get(counter_key, 0) + 1
            self._receipt_counters[counter_key] = sequence
            now = _now_iso()
            receipt = {
                "id": str(uuid4()),
                "tenantId": tenant_id,
                "invoiceIdentityKey": row_ref.invoice_identity_key,
                "invoiceId": row_ref.invoice_id,
                "bankTransactionId": str(bank_summary.get("bankTransactionId") or ""),
                "receiptNo": f"{prefix}{period}{sequence:04d}",
                "amount": amount,
                "status": "issued",
                "idempotencyKey": idempotency_key,
                "payload": deepcopy(payload),
                "createdBy": actor_id,
                "createdAt": now,
                "updatedBy": actor_id,
                "updatedAt": now,
                "voidedBy": None,
                "voidedAt": None,
                "voidReason": None,
                "reissuedFromReceiptId": None,
            }
            self._receipts[receipt["id"]] = receipt
            self._receipt_idempotency[idempotency] = receipt["id"]
            self._append_receipt_event(receipt, "created", actor_id, payload)
            return deepcopy(receipt)

    def list_receipts(self, *, invoice_id: str | None = None, invoice_identity_key: str | None = None, tenant_id: str = "default") -> list[dict[str, Any]]:
        with self._receipt_lock:
            receipts = [
                deepcopy(receipt)
                for receipt in self._receipts.values()
                if receipt.get("tenantId") == tenant_id
                and (not invoice_id or receipt.get("invoiceId") == invoice_id)
                and (not invoice_identity_key or receipt.get("invoiceIdentityKey") == invoice_identity_key)
            ]
            receipts.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
            return receipts

    def get_receipt(self, *, receipt_id: str, tenant_id: str) -> dict[str, Any] | None:
        with self._receipt_lock:
            receipt = self._receipts.get(receipt_id)
            if receipt is None or receipt.get("tenantId") != tenant_id:
                return None
            return deepcopy(receipt)

    def void_receipt(self, *, receipt_id: str, reason: str, actor_id: str, tenant_id: str) -> dict[str, Any]:
        with self._receipt_lock:
            receipt = self.get_receipt(receipt_id=receipt_id, tenant_id=tenant_id)
            if receipt is None:
                raise OutputInvoiceCollectionError("receipt_not_found", "收据不存在。", status_code=HTTPStatus.NOT_FOUND)
            if receipt.get("status") != "issued":
                raise OutputInvoiceCollectionError("invalid_receipt_status", "只有已开具收据可以作废。", status_code=HTTPStatus.CONFLICT)
            receipt.update(
                {
                    "status": "voided",
                    "voidReason": reason,
                    "voidedBy": actor_id,
                    "voidedAt": _now_iso(),
                    "updatedBy": actor_id,
                    "updatedAt": _now_iso(),
                }
            )
            self._receipts[receipt_id] = receipt
            self._append_receipt_event(receipt, "voided", actor_id, {"reason": reason})
            return deepcopy(receipt)

    def reissue_receipt(
        self,
        *,
        receipt_id: str,
        reason: str,
        actor_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._receipt_lock:
            old = self.get_receipt(receipt_id=receipt_id, tenant_id=tenant_id)
            if old is None:
                raise OutputInvoiceCollectionError("receipt_not_found", "收据不存在。", status_code=HTTPStatus.NOT_FOUND)
            if old.get("status") != "voided":
                raise OutputInvoiceCollectionError("invalid_receipt_status", "只有已作废收据可以重开。", status_code=HTTPStatus.CONFLICT)
            if any(
                receipt.get("tenantId") == tenant_id
                and receipt.get("reissuedFromReceiptId") == receipt_id
                for receipt in self._receipts.values()
            ):
                raise OutputInvoiceCollectionError("invalid_receipt_status", "该收据已重开，不能重复重开。", status_code=HTTPStatus.CONFLICT)
            row_ref = OutputInvoiceCollectionRowRef(
                row_id="",
                invoice_id=str(old.get("invoiceId") or ""),
                invoice_identity_key=str(old.get("invoiceIdentityKey") or ""),
                invoice_date=str((old.get("payload") or {}).get("date") or "") or None,
                invoice_no=str((old.get("payload") or {}).get("invoiceNo") or "") or None,
                buyer_name=str((old.get("payload") or {}).get("payerName") or "") or None,
                taxable_item_name=str((old.get("payload") or {}).get("summary") or "") or None,
                total_with_tax=str(old.get("amount") or "0.00"),
            )
            new_receipt = self.create_receipt(
                row_ref=row_ref,
                bank_summary={"bankTransactionId": old.get("bankTransactionId")},
                amount=str(old.get("amount") or "0.00"),
                idempotency_key=f"reissue:{receipt_id}:{uuid4()}",
                payload=dict(old.get("payload") or {}),
                actor_id=actor_id,
                tenant_id=tenant_id,
            )
            new_receipt["reissuedFromReceiptId"] = receipt_id
            self._receipts[new_receipt["id"]] = new_receipt
            self._append_receipt_event(new_receipt, "reissued", actor_id, {"reason": reason, "fromReceiptId": receipt_id})
            return deepcopy(new_receipt)

    def _append_receipt_event(self, receipt: dict[str, Any], event_type: str, actor_id: str, payload: dict[str, Any]) -> None:
        self._receipt_events.append(
            {
                "id": str(uuid4()),
                "receiptId": receipt["id"],
                "eventType": event_type,
                "actorId": actor_id,
                "payload": deepcopy(payload),
                "createdAt": _now_iso(),
            }
        )


class OutputInvoiceCollectionLifecycleService:
    def __init__(self, *, repository: Any, row_provider: RowProvider, queue_repository: Any | None = None) -> None:
        self._repository = repository
        self._row_provider = row_provider
        self._queue_repository = queue_repository
        self._status_service = OutputInvoiceCollectionStatusOverlayService()

    def set_collection_status(
        self,
        row_id: str,
        payload: dict[str, Any],
        *,
        actor_id: str,
        tenant_id: str = "default",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._require_row(row_id)
        status_code = str(payload.get("statusCode") or payload.get("status_code") or "").strip() or None
        if status_code and not self._status_service.can_set_status(status_code):
            raise OutputInvoiceCollectionError("invalid_collection_status", "不支持的手动收款状态。")
        expected_version = _optional_int(payload.get("expectedVersion") if "expectedVersion" in payload else payload.get("expected_version"))
        row_ref = OutputInvoiceCollectionRowRef.from_row(row)
        def mutate(transaction: Any | None = None) -> dict[str, Any]:
            kwargs = {
                "row_ref": row_ref,
                "status_code": status_code,
                "expected_collection_date": _date_or_none(payload.get("expectedCollectionDate") or payload.get("expected_collection_date")),
                "note": _trim(payload.get("note"), max_length=1000),
                "expected_version": expected_version,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
            }
            if transaction is not None:
                kwargs["transaction"] = transaction
            return self._repository.set_status_override(**kwargs)

        override = self._run_mutation(row, reason="lifecycle_status_changed", mutate=mutate, trace_id=trace_id)
        return {**output_invoice_collection_freshness_metadata(row), "override": override}

    def upsert_collection_reminder(
        self,
        row_id: str,
        payload: dict[str, Any],
        *,
        actor_id: str,
        tenant_id: str = "default",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._require_row(row_id)
        remind_at = _datetime_text(payload.get("remindAt") or payload.get("remind_at"))
        channel = str(payload.get("channel") or "oa").strip().lower()
        if channel not in {"oa", "email", "manual"}:
            raise OutputInvoiceCollectionError("invalid_reminder_channel", "提醒渠道必须是 oa、email 或 manual。")
        row_ref = OutputInvoiceCollectionRowRef.from_row(row)

        def mutate(transaction: Any | None = None) -> dict[str, Any]:
            kwargs = {
                "row_ref": row_ref,
                "remind_at": remind_at,
                "channel": channel,
                "note": _trim(payload.get("note"), max_length=1000),
                "actor_id": actor_id,
                "tenant_id": tenant_id,
            }
            if transaction is not None:
                kwargs["transaction"] = transaction
            return self._repository.upsert_reminder(**kwargs)

        reminder = self._run_mutation(row, reason="lifecycle_reminder_changed", mutate=mutate, trace_id=trace_id)
        return {**output_invoice_collection_freshness_metadata(row), "reminder": reminder}

    def cancel_collection_reminder(
        self,
        row_id: str,
        reminder_id: str,
        *,
        actor_id: str,
        tenant_id: str = "default",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._require_row(row_id)
        def mutate(transaction: Any | None = None) -> dict[str, Any]:
            kwargs = {"reminder_id": str(reminder_id or "").strip(), "actor_id": actor_id, "tenant_id": tenant_id}
            if transaction is not None:
                kwargs["transaction"] = transaction
            return self._repository.cancel_reminder(**kwargs)

        reminder = self._run_mutation(row, reason="lifecycle_reminder_cancelled", mutate=mutate, trace_id=trace_id)
        return {**output_invoice_collection_freshness_metadata(row), "reminder": reminder}

    def confirm_red_invoice_relation(
        self,
        row_id: str,
        payload: dict[str, Any],
        *,
        actor_id: str,
        tenant_id: str = "default",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._require_row(row_id)
        related_identity_key = str(payload.get("relatedInvoiceIdentityKey") or payload.get("related_invoice_identity_key") or "").strip()
        related_invoice_id = str(payload.get("relatedInvoiceId") or payload.get("related_invoice_id") or "").strip()
        if not related_identity_key and not related_invoice_id:
            raise OutputInvoiceCollectionError("related_invoice_required", "必须提供关联红蓝票发票标识。")
        relation_type = str(payload.get("relationType") or payload.get("relation_type") or "red_invoice").strip()
        if relation_type not in {"red_invoice", "blue_invoice"}:
            raise OutputInvoiceCollectionError("invalid_relation_type", "relationType must be red_invoice or blue_invoice.")
        row_ref = OutputInvoiceCollectionRowRef.from_row(row)

        def mutate(transaction: Any | None = None) -> dict[str, Any]:
            kwargs = {
                "row_ref": row_ref,
                "related_invoice_identity_key": related_identity_key or f"id:{related_invoice_id}",
                "related_invoice_id": related_invoice_id,
                "relation_type": relation_type,
                "evidence": _trim(payload.get("evidence"), max_length=2000),
                "confidence": _trim(payload.get("confidence") or "manual_confirmed", max_length=80),
                "actor_id": actor_id,
                "tenant_id": tenant_id,
            }
            if transaction is not None:
                kwargs["transaction"] = transaction
            return self._repository.confirm_red_relation(**kwargs)

        relation = self._run_mutation(row, reason="lifecycle_red_relation_changed", mutate=mutate, trace_id=trace_id)
        return {**output_invoice_collection_freshness_metadata(row), "relation": relation}

    def revoke_red_invoice_relation(
        self,
        relation_id: str,
        *,
        actor_id: str,
        tenant_id: str = "default",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        row = {"invoice": {"invoiceDate": ""}}

        def mutate(transaction: Any | None = None) -> dict[str, Any]:
            kwargs = {"relation_id": str(relation_id or "").strip(), "actor_id": actor_id, "tenant_id": tenant_id}
            if transaction is not None:
                kwargs["transaction"] = transaction
            return self._repository.revoke_red_relation(**kwargs)

        relation = self._run_mutation(row, reason="lifecycle_red_relation_revoked", mutate=mutate, trace_id=trace_id)
        return {**output_invoice_collection_freshness_metadata(row), "relation": relation}

    def _require_row(self, row_id: str) -> dict[str, Any]:
        normalized = str(row_id or "").strip()
        if not normalized:
            raise OutputInvoiceCollectionError("row_id_required", "row_id is required.")
        row = self._row_provider(normalized)
        if row is None:
            raise OutputInvoiceCollectionError("row_not_found", "销项发票收款行不存在。", status_code=HTTPStatus.NOT_FOUND)
        return row

    def _enqueue(self, row: dict[str, Any], *, reason: str, trace_id: str | None = None) -> None:
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            return
        refresh_gateway.enqueue_one(
            "output_invoice_collection",
            output_invoice_collection_scope_key(row),
            reason=reason,
            trace_id=trace_id,
        )

    def _run_mutation(
        self,
        row: dict[str, Any],
        *,
        reason: str,
        mutate: Callable[[Any | None], dict[str, Any]],
        trace_id: str | None,
    ) -> dict[str, Any]:
        transaction_runner = getattr(self._repository, "run_in_transaction", None)
        enqueue_in_transaction = getattr(self._queue_repository, "enqueue_read_model_refresh_in_transaction", None)
        if callable(transaction_runner) and callable(enqueue_in_transaction):
            def callback(transaction: Any) -> dict[str, Any]:
                result = mutate(transaction)
                enqueue_in_transaction(
                    transaction=transaction,
                    scope_type="output_invoice_collection",
                    scope_key=output_invoice_collection_scope_key(row),
                    reason=reason,
                    trace_id=trace_id,
                )
                return result

            return transaction_runner(callback)
        result = mutate(None)
        self._enqueue(row, reason=reason, trace_id=trace_id)
        return result


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _trim(value: Any, *, max_length: int) -> str:
    return str(value or "").strip()[:max_length]


def _date_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise OutputInvoiceCollectionError("invalid_date", "日期必须是 YYYY-MM-DD。") from None


def _datetime_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise OutputInvoiceCollectionError("remind_at_required", "remindAt is required.")
    try:
        normalized = text.replace("Z", "+00:00")
        datetime.fromisoformat(normalized)
    except ValueError:
        raise OutputInvoiceCollectionError("invalid_remind_at", "remindAt must be an ISO datetime string.") from None
    return text


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise OutputInvoiceCollectionError("invalid_version", "expectedVersion must be an integer.") from None


def _period_key(invoice_date: str | None, reset_period: str) -> str:
    today = date.today().isoformat()
    source = str(invoice_date or today)
    if reset_period == "yearly":
        return source[:4]
    if reset_period == "none":
        return "000000"
    return source[:7].replace("-", "")
