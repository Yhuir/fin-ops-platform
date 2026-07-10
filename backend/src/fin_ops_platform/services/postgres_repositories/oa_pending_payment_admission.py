from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import json
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    jsonb,
    run_in_transaction,
    serialize_value,
    text,
)


class PostgresOaPendingPaymentAdmissionRepository:
    """Durable App boundary for externally admitted in-progress OA records."""

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
