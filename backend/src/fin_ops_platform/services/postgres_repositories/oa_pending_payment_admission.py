from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
import hashlib
import json
from typing import Any

from fin_ops_platform.services.oa_adapter import OAApplicationRecord, OAReadStatus
from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    jsonb,
    run_in_transaction,
    serialize_value,
    text,
)


class PostgresOaPendingPaymentAdmissionRepository:
    """Durable App boundary for externally admitted in-progress OA records."""

    payment_admission_filtered = True

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def replace_scope(self, *, scope_key: str, records: list[object], tenant_id: str = "default") -> None:
        normalized_scope_key = str(scope_key or "").strip()
        if len(normalized_scope_key) != 7 or normalized_scope_key[4] != "-":
            raise ValueError("OA pending payment admission scope must be YYYY-MM.")
        normalized_records = [_record_payload(record) for record in list(records or [])]

        def write(connection: Any) -> None:
            connection.execute(
                "delete from app.oa_pending_payment_admissions where tenant_id = %s and scope_key = %s",
                (tenant_id, normalized_scope_key),
            )
            for payload in normalized_records:
                oa_id = text(payload.get("id"))
                if not oa_id:
                    continue
                project_name = text(payload.get("project_name"))
                project_name_display = text(payload.get("project_name_display")) or project_name
                amount = decimal_text(str(payload.get("amount") or "").replace(",", ""))
                connection.execute(
                    """
                    insert into app.oa_pending_payment_admissions(
                        tenant_id, scope_key, oa_id, workflow_status, applicant,
                        project_name, project_name_display, amount, source_signature,
                        source_payload, raw_payload, registered_at, updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                    """,
                    (
                        tenant_id,
                        normalized_scope_key,
                        oa_id,
                        text(payload.get("workflow_status")),
                        text(payload.get("applicant")),
                        project_name,
                        project_name_display,
                        amount,
                        _payload_signature(payload),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def list_application_records(self, month: str, *, tenant_id: str = "default") -> list[OAApplicationRecord]:
        normalized_scope_key = str(month or "").strip()
        if len(normalized_scope_key) != 7 or normalized_scope_key[4] != "-":
            raise ValueError("OA pending payment admission scope must be YYYY-MM.")
        rows = self._connection.fetch_all(
            """
            select source_payload
            from app.oa_pending_payment_admissions
            where tenant_id = %s and scope_key = %s
            order by oa_id
            """,
            (tenant_id, normalized_scope_key),
        )
        return _application_records(rows)

    def list_all_application_records(self, *, tenant_id: str = "default") -> list[OAApplicationRecord]:
        rows = self._connection.fetch_all(
            """
            select source_payload
            from app.oa_pending_payment_admissions
            where tenant_id = %s
            order by scope_key desc, oa_id
            """,
            (tenant_id,),
        )
        return _application_records(rows)

    def list_available_months(self, *, tenant_id: str = "default") -> list[str]:
        rows = self._connection.fetch_all(
            """
            select distinct scope_key
            from app.oa_pending_payment_admissions
            where tenant_id = %s
            order by scope_key desc
            """,
            (tenant_id,),
        )
        return [
            scope_key
            for row in list(rows or [])
            if isinstance(row, dict) and (scope_key := str(row.get("scope_key") or "").strip())
        ]

    def list_application_records_by_row_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> list[OAApplicationRecord]:
        normalized_row_ids = sorted({str(row_id or "").strip() for row_id in row_ids if str(row_id or "").strip()})
        if not normalized_row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select source_payload
            from app.oa_pending_payment_admissions
            where tenant_id = %s and oa_id = any(%s::text[])
            order by scope_key desc, oa_id
            """,
            (tenant_id, normalized_row_ids),
        )
        return _application_records(rows)

    @staticmethod
    def get_read_status() -> OAReadStatus:
        return OAReadStatus(code="ready", message="PostgreSQL OA pending payment admission snapshot ready")

    def prune_scopes(self, current_scope_keys: list[str], *, tenant_id: str = "default") -> None:
        normalized_scope_keys: list[str] = []
        for scope_key in list(current_scope_keys or []):
            normalized_scope_key = str(scope_key or "").strip()
            if len(normalized_scope_key) != 7 or normalized_scope_key[4] != "-":
                continue
            if normalized_scope_key not in normalized_scope_keys:
                normalized_scope_keys.append(normalized_scope_key)

        def write(connection: Any) -> None:
            if normalized_scope_keys:
                placeholders = ", ".join(["%s"] * len(normalized_scope_keys))
                connection.execute(
                    f"""
                    delete from app.oa_pending_payment_admissions
                    where tenant_id = %s
                      and scope_key not in ({placeholders})
                    """,
                    (tenant_id, *normalized_scope_keys),
                )
                return
            connection.execute(
                "delete from app.oa_pending_payment_admissions where tenant_id = %s",
                (tenant_id,),
            )

        run_in_transaction(self._connection, write)


def oa_pending_payment_records_signature(records: list[object]) -> str:
    payloads = sorted(
        (_record_payload(record) for record in list(records or [])),
        key=lambda payload: str(payload.get("id") or ""),
    )
    return _payload_signature(payloads)


def _record_payload(record: object) -> dict[str, Any]:
    if is_dataclass(record):
        raw = asdict(record)
    elif isinstance(record, dict):
        raw = dict(record)
    else:
        raw = dict(vars(record)) if hasattr(record, "__dict__") else {}
    payload = serialize_value(raw)
    return dict(payload) if isinstance(payload, dict) else {}


def _payload_signature(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _application_records(rows: list[dict[str, Any]] | None) -> list[OAApplicationRecord]:
    field_names = {field.name for field in fields(OAApplicationRecord)}
    records: list[OAApplicationRecord] = []
    for row in list(rows or []):
        payload = row.get("source_payload") if isinstance(row, dict) else None
        if not isinstance(payload, dict):
            continue
        values = {name: payload.get(name) for name in field_names if name in payload}
        try:
            records.append(OAApplicationRecord(**values))
        except (TypeError, ValueError):
            continue
    return records
