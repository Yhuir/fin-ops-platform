from __future__ import annotations

from dataclasses import fields
from typing import Any

from fin_ops_platform.services.oa_adapter import OAApplicationRecord, OAReadStatus
from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    jsonb,
    month_start,
    row_payload,
    run_in_transaction,
    serialize_value,
    text,
)


class PostgresOAProjectionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
        normalized_records = [record for record in list(records or []) if isinstance(record, OAApplicationRecord)]
        if not normalized_records:
            self._record_watermark(scope_key=scope_key, status="succeeded", upserted_count=0)
            return 0

        def write(connection: Any) -> None:
            for record in normalized_records:
                payload = serialize_value(record)
                connection.execute(
                    """
                    insert into app.oa_applications(
                        oa_source_id, form_id, row_id, form_type, workflow_no, status,
                        applicant, application_date, project_name, amount, currency,
                        scope_month, normalized_payload, raw_payload, synced_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s, %s, %s::date, %s, %s, now())
                    on conflict (row_id) do update set
                        oa_source_id = excluded.oa_source_id,
                        form_id = excluded.form_id,
                        form_type = excluded.form_type,
                        workflow_no = excluded.workflow_no,
                        status = excluded.status,
                        applicant = excluded.applicant,
                        application_date = excluded.application_date,
                        project_name = excluded.project_name,
                        amount = excluded.amount,
                        currency = excluded.currency,
                        scope_month = excluded.scope_month,
                        normalized_payload = excluded.normalized_payload,
                        raw_payload = excluded.raw_payload,
                        synced_at = now(),
                        updated_at = now()
                    """,
                    (
                        record.id,
                        self._form_id_for_record(record),
                        record.id,
                        record.apply_type,
                        record.case_id,
                        record.section,
                        record.applicant,
                        month_start(record.month),
                        record.project_name,
                        decimal_text(record.amount),
                        "CNY",
                        month_start(record.month),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            self._record_watermark(
                scope_key=scope_key,
                status="succeeded",
                upserted_count=len(normalized_records),
                connection=connection,
            )

        run_in_transaction(self._connection, write)
        return len(normalized_records)

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        normalized_month = str(month or "").strip()
        if normalized_month == "all":
            return self.list_all_application_records()
        rows = self._connection.fetch_all(
            """
            select row_id, normalized_payload, raw_payload
            from app.oa_applications
            where scope_month = %s::date
            order by row_id
            """,
            (month_start(normalized_month),),
        )
        return self._records_from_rows(rows)

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        rows = self._connection.fetch_all(
            """
            select row_id, normalized_payload, raw_payload
            from app.oa_applications
            order by scope_month, row_id
            """
        )
        return self._records_from_rows(rows)

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized_row_ids = [row_id for row_id in [text(row_id) for row_id in list(row_ids or [])] if row_id]
        if not normalized_row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select row_id, normalized_payload, raw_payload
            from app.oa_applications
            where row_id = any(%s)
            order by row_id
            """,
            (normalized_row_ids,),
        )
        records_by_id = {record.id: record for record in self._records_from_rows(rows)}
        return [records_by_id[row_id] for row_id in normalized_row_ids if row_id in records_by_id]

    def list_available_months(self) -> list[str]:
        rows = self._connection.fetch_all(
            """
            select distinct to_char(scope_month, 'YYYY-MM') as month
            from app.oa_applications
            where scope_month is not null
            order by month
            """
        )
        return [month for row in rows if (month := text(row.get("month")))]

    def get_read_status(self) -> OAReadStatus:
        return OAReadStatus(code="ready", message="OA projection ready")

    def record_sync_run(self, payload: dict[str, object]) -> None:
        normalized_payload = serialize_value(payload if isinstance(payload, dict) else {})
        self._connection.execute(
            """
            insert into app.oa_sync_runs(
                sync_type, status, finished_at, scanned_count, upserted_count,
                skipped_count, error_count, last_error, payload, raw_payload
            )
            values (%s, %s, now(), %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                text(normalized_payload.get("sync_type")) or "oa_projection",
                text(normalized_payload.get("status")) or "succeeded",
                int(normalized_payload.get("scanned_count") or 0),
                int(normalized_payload.get("upserted_count") or 0),
                int(normalized_payload.get("skipped_count") or 0),
                int(normalized_payload.get("error_count") or 0),
                text(normalized_payload.get("last_error")),
                jsonb(normalized_payload),
                jsonb({"normalized_payload": normalized_payload}),
            ),
        )

    def _record_watermark(
        self,
        *,
        scope_key: str,
        status: str,
        upserted_count: int,
        connection: Any | None = None,
    ) -> None:
        target = connection or self._connection
        payload = {"scope_key": scope_key, "upserted_count": upserted_count}
        target.execute(
            """
            insert into app.oa_sync_watermarks(sync_key, form_id, last_success_at, status, payload, raw_payload)
            values (%s, %s, now(), %s, %s, %s)
            on conflict (sync_key) do update set
                last_success_at = excluded.last_success_at,
                status = excluded.status,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                version = app.oa_sync_watermarks.version + 1,
                updated_at = now()
            """,
            (
                f"projection:{text(scope_key) or 'all'}",
                text(scope_key),
                status,
                jsonb(payload),
                jsonb({"normalized_payload": payload}),
            ),
        )

    @staticmethod
    def _form_id_for_record(record: OAApplicationRecord) -> str:
        row_id = str(record.id or "")
        if row_id.startswith("oa-pay-"):
            return "payment_request"
        if row_id.startswith("oa-exp-"):
            return "expense_claim"
        return str(record.apply_type or "oa_application")

    @classmethod
    def _records_from_rows(cls, rows: list[dict[str, Any]]) -> list[OAApplicationRecord]:
        records: list[OAApplicationRecord] = []
        for row in list(rows or []):
            payload = row_payload(row, "normalized_payload", "payload", "raw_payload")
            if not isinstance(payload, dict):
                continue
            records.append(cls._record_from_payload(payload, row_id=text(row.get("row_id"))))
        return records

    @staticmethod
    def _record_from_payload(payload: dict[str, Any], *, row_id: str | None = None) -> OAApplicationRecord:
        data = serialize_value(payload)
        field_names = {field.name for field in fields(OAApplicationRecord)}
        kwargs = {name: data.get(name) for name in field_names if name in data}
        kwargs.setdefault("id", row_id or text(data.get("id")) or "oa-unknown")
        kwargs.setdefault("month", text(data.get("month")) or "all")
        kwargs.setdefault("section", text(data.get("section")) or "open")
        kwargs.setdefault("case_id", data.get("case_id"))
        kwargs.setdefault("applicant", text(data.get("applicant")) or "")
        kwargs.setdefault("project_name", text(data.get("project_name")) or "--")
        kwargs.setdefault("apply_type", text(data.get("apply_type")) or "")
        kwargs.setdefault("amount", text(data.get("amount")) or "0")
        kwargs.setdefault("counterparty_name", text(data.get("counterparty_name")) or "")
        kwargs.setdefault("reason", text(data.get("reason")) or "")
        kwargs.setdefault("relation_code", text(data.get("relation_code")) or "pending_match")
        kwargs.setdefault("relation_label", text(data.get("relation_label")) or "待找流水与发票")
        kwargs.setdefault("relation_tone", text(data.get("relation_tone")) or "warn")
        return OAApplicationRecord(**kwargs)


class PostgresOAProjectionAdapter:
    name = "postgres_oa_projection"

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        return list(self._repository.list_application_records(month))

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        list_all = getattr(self._repository, "list_all_application_records", None)
        if callable(list_all):
            return list(list_all())
        records: list[OAApplicationRecord] = []
        for month in self.list_available_months():
            records.extend(self.list_application_records(month))
        return records

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        list_by_ids = getattr(self._repository, "list_application_records_by_row_ids", None)
        if callable(list_by_ids):
            return list(list_by_ids(row_ids))
        wanted = {str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()}
        return [record for record in self.list_all_application_records() if record.id in wanted]

    def list_available_months(self) -> list[str]:
        list_months = getattr(self._repository, "list_available_months", None)
        return list(list_months()) if callable(list_months) else []

    def get_read_status(self) -> OAReadStatus:
        get_status = getattr(self._repository, "get_read_status", None)
        if callable(get_status):
            return get_status()
        return OAReadStatus(code="ready", message="OA projection ready")

