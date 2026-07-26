from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus
from typing import Any, Callable, TypeVar
from uuid import uuid4

from fin_ops_platform.services.output_invoice_collection_lifecycle_service import InMemoryOutputInvoiceCollectionLifecycleRepository
from fin_ops_platform.services.output_invoice_collection_models import OutputInvoiceCollectionRowRef
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionError
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_connection import PostgresConnection


T = TypeVar("T")


class PostgresOutputInvoiceCollectionLifecycleRepository:
    """PostgreSQL lifecycle facts for the 销项发票收款情况 module."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def run_in_transaction(self, callback: Callable[[Any], T]) -> T:
        with self._connection.transaction() as transaction:
            return callback(transaction)

    def overlays_for_identity_keys(
        self,
        identity_keys: list[str],
        *,
        tenant_id: str = "default",
        transaction: Any | None = None,
    ) -> dict[str, dict[str, Any]]:
        keys = [str(item).strip() for item in identity_keys if str(item).strip()]
        if not keys:
            return {}
        if transaction is not None:
            return self._overlays_from_transaction(
                transaction,
                keys=keys,
                tenant_id=tenant_id,
            )
        with self._connection.transaction() as current:
            return self._overlays_from_transaction(
                current,
                keys=keys,
                tenant_id=tenant_id,
            )

    @staticmethod
    def _overlays_from_transaction(
        transaction: Any,
        *,
        keys: list[str],
        tenant_id: str,
    ) -> dict[str, dict[str, Any]]:
        overrides = transaction.fetch_all(
                """
                select *
                from app.output_invoice_collection_status_overrides
                where tenant_id = %s
                  and status = 'active'
                  and invoice_identity_key = any(%s)
                """,
                (tenant_id, keys),
            )
        reminders = transaction.fetch_all(
                """
                select distinct on (invoice_identity_key) *
                from app.output_invoice_collection_reminders
                where tenant_id = %s
                  and status = 'active'
                  and invoice_identity_key = any(%s)
                order by invoice_identity_key, updated_at desc, created_at desc
                """,
                (tenant_id, keys),
            )
        red_relations = transaction.fetch_all(
                """
                select *
                from app.output_invoice_collection_red_relations
                where tenant_id = %s
                  and status = 'active'
                  and invoice_identity_key = any(%s)
                order by updated_at desc, created_at desc
                """,
                (tenant_id, keys),
            )
        receipts = transaction.fetch_all(
                """
                select *
                from app.output_invoice_receipts
                where tenant_id = %s
                  and invoice_identity_key = any(%s)
                order by created_at desc
                """,
                (tenant_id, keys),
        )
        result = {key: {"override": None, "reminder": None, "redRelations": [], "receipts": []} for key in keys}
        for row in overrides:
            result.setdefault(str(row.get("invoice_identity_key")), {"override": None, "reminder": None, "redRelations": [], "receipts": []})[
                "override"
            ] = _override_payload(row)
        for row in reminders:
            result.setdefault(str(row.get("invoice_identity_key")), {"override": None, "reminder": None, "redRelations": [], "receipts": []})[
                "reminder"
            ] = _reminder_payload(row)
        for row in red_relations:
            result.setdefault(str(row.get("invoice_identity_key")), {"override": None, "reminder": None, "redRelations": [], "receipts": []})[
                "redRelations"
            ].append(_red_relation_payload(row))
        for row in receipts:
            result.setdefault(str(row.get("invoice_identity_key")), {"override": None, "reminder": None, "redRelations": [], "receipts": []})[
                "receipts"
            ].append(_receipt_payload(row))
        return result

    def set_status_override(self, *, transaction: Any | None = None, **kwargs: Any) -> dict[str, Any]:
        tx = transaction or self._connection
        row_ref: OutputInvoiceCollectionRowRef = kwargs["row_ref"]
        status_code = kwargs.get("status_code")
        current = tx.fetch_one(
            """
            select version
            from app.output_invoice_collection_status_overrides
            where tenant_id = %s and invoice_identity_key = %s and status = 'active'
            """,
            (kwargs["tenant_id"], row_ref.invoice_identity_key),
        )
        current_version = int((current or {}).get("version") or 0)
        expected_version = kwargs.get("expected_version")
        if expected_version is not None and int(expected_version) != current_version:
            raise OutputInvoiceCollectionError(
                "version_conflict",
                "收款状态已被其他用户修改，请刷新后重试。",
                status_code=HTTPStatus.CONFLICT,
                details={"expectedVersion": expected_version, "actualVersion": current_version},
            )
        if status_code:
            row = tx.fetch_one(
                """
                insert into app.output_invoice_collection_status_overrides(
                    tenant_id, invoice_identity_key, invoice_id, status_code,
                    expected_collection_date, note, version, status,
                    created_by, updated_by, raw_payload
                )
                values (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s, %s)
                on conflict (tenant_id, invoice_identity_key)
                where status = 'active'
                do update set
                    invoice_id = excluded.invoice_id,
                    status_code = excluded.status_code,
                    expected_collection_date = excluded.expected_collection_date,
                    note = excluded.note,
                    version = app.output_invoice_collection_status_overrides.version + 1,
                    updated_by = excluded.updated_by,
                    updated_at = now(),
                    raw_payload = excluded.raw_payload
                returning *
                """,
                (
                    kwargs["tenant_id"],
                    row_ref.invoice_identity_key,
                    row_ref.invoice_id,
                    status_code,
                    kwargs.get("expected_collection_date"),
                    kwargs.get("note") or "",
                    current_version + 1,
                    kwargs["actor_id"],
                    kwargs["actor_id"],
                    jsonb({"row": row_ref.__dict__}),
                ),
            )
        else:
            row = tx.fetch_one(
                """
                update app.output_invoice_collection_status_overrides
                set status = 'revoked', revoked_by = %s, revoked_at = now(), updated_by = %s, updated_at = now()
                where tenant_id = %s and invoice_identity_key = %s and status = 'active'
                returning *
                """,
                (kwargs["actor_id"], kwargs["actor_id"], kwargs["tenant_id"], row_ref.invoice_identity_key),
            )
        return _override_payload(row or {})

    def upsert_reminder(self, *, transaction: Any | None = None, **kwargs: Any) -> dict[str, Any]:
        tx = transaction or self._connection
        row_ref: OutputInvoiceCollectionRowRef = kwargs["row_ref"]
        row = tx.fetch_one(
            """
            insert into app.output_invoice_collection_reminders(
                tenant_id, invoice_identity_key, invoice_id, remind_at, channel, note,
                status, created_by, updated_by, raw_payload
            )
            values (%s, %s, %s, %s, %s, %s, 'active', %s, %s, %s)
            on conflict (tenant_id, invoice_identity_key)
            where status = 'active'
            do update set
                invoice_id = excluded.invoice_id,
                remind_at = excluded.remind_at,
                channel = excluded.channel,
                note = excluded.note,
                updated_by = excluded.updated_by,
                updated_at = now(),
                raw_payload = excluded.raw_payload
            returning *
            """,
            (
                kwargs["tenant_id"],
                row_ref.invoice_identity_key,
                row_ref.invoice_id,
                kwargs["remind_at"],
                kwargs["channel"],
                kwargs.get("note") or "",
                kwargs["actor_id"],
                kwargs["actor_id"],
                jsonb({"row": row_ref.__dict__}),
            ),
        )
        if row is None:
            raise OutputInvoiceCollectionError("reminder_not_found", "提醒不存在或已取消。", status_code=HTTPStatus.NOT_FOUND)
        return _reminder_payload(row)

    def cancel_reminder(self, *, reminder_id: str, actor_id: str, tenant_id: str, transaction: Any | None = None) -> dict[str, Any]:
        tx = transaction or self._connection
        row = tx.fetch_one(
            """
            update app.output_invoice_collection_reminders
            set status = 'cancelled', updated_by = %s, updated_at = now()
            where id = %s and tenant_id = %s and status = 'active'
            returning *
            """,
            (actor_id, reminder_id, tenant_id),
        )
        return _reminder_payload(row or {})

    def confirm_red_relation(self, *, transaction: Any | None = None, **kwargs: Any) -> dict[str, Any]:
        tx = transaction or self._connection
        row_ref: OutputInvoiceCollectionRowRef = kwargs["row_ref"]
        row = tx.fetch_one(
            """
            insert into app.output_invoice_collection_red_relations(
                tenant_id, invoice_identity_key, invoice_id, related_invoice_identity_key,
                related_invoice_id, relation_type, evidence, confidence, source,
                status, created_by, updated_by, raw_payload
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, 'manual', 'active', %s, %s, %s)
            on conflict (tenant_id, invoice_identity_key, related_invoice_identity_key)
            where status = 'active'
            do update set
                related_invoice_id = excluded.related_invoice_id,
                relation_type = excluded.relation_type,
                evidence = excluded.evidence,
                confidence = excluded.confidence,
                version = app.output_invoice_collection_red_relations.version + 1,
                updated_by = excluded.updated_by,
                updated_at = now(),
                raw_payload = excluded.raw_payload
            returning *
            """,
            (
                kwargs["tenant_id"],
                row_ref.invoice_identity_key,
                row_ref.invoice_id,
                kwargs["related_invoice_identity_key"],
                kwargs.get("related_invoice_id") or "",
                kwargs["relation_type"],
                kwargs.get("evidence") or "",
                kwargs.get("confidence") or "manual_confirmed",
                kwargs["actor_id"],
                kwargs["actor_id"],
                jsonb({"row": row_ref.__dict__}),
            ),
        )
        if row is None:
            raise OutputInvoiceCollectionError("relation_not_found", "红蓝票关系不存在或已撤销。", status_code=HTTPStatus.NOT_FOUND)
        return _red_relation_payload(row)

    def revoke_red_relation(self, *, relation_id: str, actor_id: str, tenant_id: str, transaction: Any | None = None) -> dict[str, Any]:
        tx = transaction or self._connection
        row = tx.fetch_one(
            """
            update app.output_invoice_collection_red_relations
            set status = 'revoked', updated_by = %s, updated_at = now()
            where id = %s and tenant_id = %s and status = 'active'
            returning *
            """,
            (actor_id, relation_id, tenant_id),
        )
        if row is None:
            raise OutputInvoiceCollectionError("relation_not_found", "红蓝票关系不存在或已撤销。", status_code=HTTPStatus.NOT_FOUND)
        return _red_relation_payload(row or {})

    def get_receipt_settings(self, *, tenant_id: str) -> dict[str, Any]:
        row = self._connection.fetch_one("select * from app.output_invoice_receipt_settings where tenant_id = %s", (tenant_id,))
        return _receipt_settings_payload(row or {"tenant_id": tenant_id, "prefix": "SK", "reset_period": "monthly", "version": 1})

    def update_receipt_settings(self, *, tenant_id: str, prefix: str, reset_period: str, actor_id: str) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            insert into app.output_invoice_receipt_settings(tenant_id, prefix, reset_period, updated_by)
            values (%s, %s, %s, %s)
            on conflict (tenant_id)
            do update set
                prefix = excluded.prefix,
                reset_period = excluded.reset_period,
                version = app.output_invoice_receipt_settings.version + 1,
                updated_by = excluded.updated_by,
                updated_at = now()
            returning *
            """,
            (tenant_id, prefix, reset_period, actor_id),
        )
        return _receipt_settings_payload(row or {})

    def create_receipt(self, *, transaction: Any | None = None, **kwargs: Any) -> dict[str, Any]:
        tx = transaction or self._connection
        existing = tx.fetch_one(
            "select * from app.output_invoice_receipts where tenant_id = %s and idempotency_key = %s",
            (kwargs["tenant_id"], kwargs["idempotency_key"]),
        )
        if existing:
            return _receipt_payload(existing)
        row_ref: OutputInvoiceCollectionRowRef = kwargs["row_ref"]
        settings = tx.fetch_one("select * from app.output_invoice_receipt_settings where tenant_id = %s", (kwargs["tenant_id"],))
        prefix = str((settings or {}).get("prefix") or "SK")
        reset_period = str((settings or {}).get("reset_period") or "monthly")
        period_key = _period_key(row_ref.invoice_date, reset_period)
        counter = tx.fetch_one(
            """
            insert into app.output_invoice_receipt_number_counters(tenant_id, prefix, period_key, next_sequence)
            values (%s, %s, %s, 2)
            on conflict (tenant_id, prefix, period_key)
            do update set next_sequence = app.output_invoice_receipt_number_counters.next_sequence + 1, updated_at = now()
            returning next_sequence - 1 as sequence
            """,
            (kwargs["tenant_id"], prefix, period_key),
        )
        sequence = int((counter or {}).get("sequence") or 1)
        row = tx.fetch_one(
            """
            insert into app.output_invoice_receipts(
                tenant_id, receipt_no, invoice_identity_key, invoice_id, bank_transaction_id,
                amount, status, idempotency_key, payload, created_by, updated_by, raw_payload
            )
            values (%s, %s, %s, %s, %s, %s, 'issued', %s, %s, %s, %s, %s)
            returning *
            """,
            (
                kwargs["tenant_id"],
                f"{prefix}{period_key}{sequence:04d}",
                row_ref.invoice_identity_key,
                row_ref.invoice_id,
                str(kwargs.get("bank_summary", {}).get("bankTransactionId") or ""),
                Decimal(str(kwargs["amount"])),
                kwargs["idempotency_key"],
                jsonb(kwargs.get("payload") or {}),
                kwargs["actor_id"],
                kwargs["actor_id"],
                jsonb({"row": row_ref.__dict__}),
            ),
        )
        self._append_receipt_event(tx, row_id=str((row or {}).get("id") or ""), event_type="created", actor_id=kwargs["actor_id"], tenant_id=kwargs["tenant_id"], payload=kwargs.get("payload") or {})
        return _receipt_payload(row or {})

    def list_receipts(
        self,
        *,
        invoice_id: str | None = None,
        invoice_identity_key: str | None = None,
        tenant_id: str = "default",
    ) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select *
            from app.output_invoice_receipts
            where tenant_id = %s
              and (%s = '' or invoice_id = %s)
              and (%s = '' or invoice_identity_key = %s)
            order by created_at desc
            """,
            (tenant_id, invoice_id or "", invoice_id or "", invoice_identity_key or "", invoice_identity_key or ""),
        )
        return [_receipt_payload(row) for row in rows]

    def get_receipt(self, *, receipt_id: str, tenant_id: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one("select * from app.output_invoice_receipts where id = %s and tenant_id = %s", (receipt_id, tenant_id))
        return _receipt_payload(row) if row else None

    def void_receipt(self, *, receipt_id: str, reason: str, actor_id: str, tenant_id: str, transaction: Any | None = None) -> dict[str, Any]:
        tx = transaction or self._connection
        row = tx.fetch_one(
            """
            update app.output_invoice_receipts
            set status = 'voided',
                void_reason = %s,
                voided_by = %s,
                voided_at = coalesce(voided_at, now()),
                updated_by = %s,
                updated_at = now()
            where id = %s and tenant_id = %s and status = 'issued'
            returning *
            """,
            (reason, actor_id, actor_id, receipt_id, tenant_id),
        )
        if row is None:
            current = tx.fetch_one(
                "select status from app.output_invoice_receipts where id = %s and tenant_id = %s",
                (receipt_id, tenant_id),
            )
            if current is None:
                raise OutputInvoiceCollectionError("receipt_not_found", "收据不存在。", status_code=HTTPStatus.NOT_FOUND)
            raise OutputInvoiceCollectionError("invalid_receipt_status", "只有已开具收据可以作废。", status_code=HTTPStatus.CONFLICT)
        self._append_receipt_event(tx, row_id=receipt_id, event_type="voided", actor_id=actor_id, tenant_id=tenant_id, payload={"reason": reason})
        return _receipt_payload(row)

    def reissue_receipt(self, *, receipt_id: str, reason: str, actor_id: str, tenant_id: str, transaction: Any | None = None) -> dict[str, Any]:
        tx = transaction or self._connection
        old_row = tx.fetch_one("select * from app.output_invoice_receipts where id = %s and tenant_id = %s", (receipt_id, tenant_id))
        if old_row is None:
            raise OutputInvoiceCollectionError("receipt_not_found", "收据不存在。", status_code=HTTPStatus.NOT_FOUND)
        old = _receipt_payload(old_row)
        if old.get("status") != "voided":
            raise OutputInvoiceCollectionError("invalid_receipt_status", "只有已作废收据可以重开。", status_code=HTTPStatus.CONFLICT)
        existing_reissue = tx.fetch_one(
            "select id from app.output_invoice_receipts where tenant_id = %s and reissued_from_receipt_id = %s",
            (tenant_id, receipt_id),
        )
        if existing_reissue is not None:
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
        receipt = self.create_receipt(
            transaction=tx,
            row_ref=row_ref,
            bank_summary={"bankTransactionId": old.get("bankTransactionId")},
            amount=str(old.get("amount") or "0.00"),
            idempotency_key=f"reissue:{receipt_id}:{uuid4()}",
            payload=dict(old.get("payload") or {}),
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
        if receipt:
            tx.execute(
                "update app.output_invoice_receipts set reissued_from_receipt_id = %s where id = %s",
                (receipt_id, receipt["id"]),
            )
            receipt["reissuedFromReceiptId"] = receipt_id
            self._append_receipt_event(tx, row_id=receipt["id"], event_type="reissued", actor_id=actor_id, tenant_id=tenant_id, payload={"reason": reason, "fromReceiptId": receipt_id})
        return receipt

    @staticmethod
    def _append_receipt_event(tx: Any, *, row_id: str, event_type: str, actor_id: str, tenant_id: str, payload: dict[str, Any]) -> None:
        tx.execute(
            """
            insert into app.output_invoice_receipt_events(tenant_id, receipt_id, event_type, actor_id, payload)
            values (%s, %s, %s, %s, %s)
            """,
            (tenant_id, row_id, event_type, actor_id, jsonb(payload)),
        )


def build_output_invoice_collection_lifecycle_repository(connection: PostgresConnection | None) -> Any:
    if connection is None:
        return InMemoryOutputInvoiceCollectionLifecycleRepository()
    return PostgresOutputInvoiceCollectionLifecycleRepository(connection)


def _override_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "tenantId": row.get("tenant_id") or row.get("tenantId") or "default",
        "invoiceIdentityKey": row.get("invoice_identity_key") or row.get("invoiceIdentityKey"),
        "invoiceId": row.get("invoice_id") or row.get("invoiceId"),
        "statusCode": row.get("status_code") or row.get("statusCode"),
        "expectedCollectionDate": _date_text(row.get("expected_collection_date") or row.get("expectedCollectionDate")),
        "note": row.get("note") or "",
        "version": int(row.get("version") or 0),
        "status": row.get("status") or "active",
        "updatedBy": row.get("updated_by") or row.get("updatedBy") or "",
        "updatedAt": _date_text(row.get("updated_at") or row.get("updatedAt")),
        "createdBy": row.get("created_by") or row.get("createdBy") or "",
        "createdAt": _date_text(row.get("created_at") or row.get("createdAt")),
    }


def _reminder_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "tenantId": row.get("tenant_id") or row.get("tenantId") or "default",
        "invoiceIdentityKey": row.get("invoice_identity_key") or row.get("invoiceIdentityKey"),
        "invoiceId": row.get("invoice_id") or row.get("invoiceId"),
        "remindAt": _date_text(row.get("remind_at") or row.get("remindAt")),
        "channel": row.get("channel") or "oa",
        "note": row.get("note") or "",
        "status": row.get("status") or "active",
        "sentAt": _date_text(row.get("sent_at") or row.get("sentAt")),
        "result": row.get("result") or {},
        "updatedBy": row.get("updated_by") or row.get("updatedBy") or "",
        "updatedAt": _date_text(row.get("updated_at") or row.get("updatedAt")),
    }


def _red_relation_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "tenantId": row.get("tenant_id") or row.get("tenantId") or "default",
        "invoiceIdentityKey": row.get("invoice_identity_key") or row.get("invoiceIdentityKey"),
        "invoiceId": row.get("invoice_id") or row.get("invoiceId"),
        "relatedInvoiceIdentityKey": row.get("related_invoice_identity_key") or row.get("relatedInvoiceIdentityKey"),
        "relatedInvoiceId": row.get("related_invoice_id") or row.get("relatedInvoiceId"),
        "relationType": row.get("relation_type") or row.get("relationType"),
        "evidence": row.get("evidence") or "",
        "confidence": row.get("confidence") or "manual_confirmed",
        "source": row.get("source") or "manual",
        "version": int(row.get("version") or 0),
        "status": row.get("status") or "active",
    }


def _receipt_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "tenantId": row.get("tenant_id") or row.get("tenantId") or "default",
        "receiptNo": row.get("receipt_no") or row.get("receiptNo"),
        "invoiceIdentityKey": row.get("invoice_identity_key") or row.get("invoiceIdentityKey"),
        "invoiceId": row.get("invoice_id") or row.get("invoiceId"),
        "bankTransactionId": row.get("bank_transaction_id") or row.get("bankTransactionId"),
        "amount": str(row.get("amount") or "0.00"),
        "status": row.get("status") or "issued",
        "idempotencyKey": row.get("idempotency_key") or row.get("idempotencyKey"),
        "payload": row.get("payload") or {},
        "createdBy": row.get("created_by") or row.get("createdBy") or "",
        "createdAt": _date_text(row.get("created_at") or row.get("createdAt")),
        "voidedBy": row.get("voided_by") or row.get("voidedBy"),
        "voidedAt": _date_text(row.get("voided_at") or row.get("voidedAt")),
        "voidReason": row.get("void_reason") or row.get("voidReason"),
        "reissuedFromReceiptId": row.get("reissued_from_receipt_id") or row.get("reissuedFromReceiptId"),
    }


def _receipt_settings_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenantId": row.get("tenant_id") or row.get("tenantId") or "default",
        "prefix": row.get("prefix") or "SK",
        "resetPeriod": row.get("reset_period") or row.get("resetPeriod") or "monthly",
        "version": int(row.get("version") or 1),
        "updatedBy": row.get("updated_by") or row.get("updatedBy") or "",
        "updatedAt": _date_text(row.get("updated_at") or row.get("updatedAt")),
    }


def _date_text(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else str(value) if value else None


def _period_key(invoice_date: str | None, reset_period: str) -> str:
    source = str(invoice_date or "")
    if reset_period == "yearly":
        return source[:4] or "0000"
    if reset_period == "none":
        return "000000"
    return (source[:7] or "0000-00").replace("-", "")
