from __future__ import annotations

from typing import Any

from fin_ops_platform.services.pending_invoice_relation_identity import is_valid_pending_invoice_oa_row_id


PENDING_INVOICE_BASE_SCOPE_KEYS = (
    "expense:all",
    "expense:requires_invoice",
    "expense:bank_statement_as_invoice",
    "expense:no_invoice_required",
    "income:all",
    "income:requires_invoice",
    "income:no_invoice_required",
    "income:cash_income",
)


class PendingInvoiceOaIdentityBackfillService:
    def __init__(self, *, repository: Any, queue_repository: Any | None = None) -> None:
        self._repository = repository
        self._queue_repository = queue_repository

    def inspect(self) -> dict[str, Any]:
        invalid_read_model_rows = self._invalid_read_model_rows()
        invalid_relation_rows = self._invalid_relation_rows()
        missing_oa_relation_rows = self._missing_oa_relation_rows()
        return {
            "invalid_read_model_rows": invalid_read_model_rows,
            "invalid_relation_rows": invalid_relation_rows,
            "missing_oa_relation_rows": missing_oa_relation_rows,
            "affected_scope_keys": self._affected_scope_keys(invalid_read_model_rows),
            "manual_repair_required": bool(invalid_relation_rows or missing_oa_relation_rows),
        }

    def enqueue_affected_scopes(self, *, reason: str = "pending_invoice_oa_identity_backfill") -> list[str]:
        report = self.inspect()
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        if not callable(enqueue):
            return []
        scope_keys = list(report.get("affected_scope_keys") or [])
        if report.get("manual_repair_required"):
            scope_keys = list(dict.fromkeys([*scope_keys, *PENDING_INVOICE_BASE_SCOPE_KEYS]))
        for scope_key in scope_keys:
            enqueue(scope_type="pending_invoice", scope_key=scope_key, reason=reason)
        return scope_keys

    def _invalid_read_model_rows(self) -> list[dict[str, Any]]:
        rows = self._repository.invalid_read_model_rows()
        result: list[dict[str, Any]] = []
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            oa_payload = row.get("oa_payload") if isinstance(row.get("oa_payload"), dict) else {}
            primary = oa_payload.get("primary") if isinstance(oa_payload.get("primary"), dict) else {}
            oa_id = str(primary.get("id") or "").strip()
            if not oa_id or is_valid_pending_invoice_oa_row_id(oa_id):
                continue
            result.append(
                {
                    "row_id": str(row.get("row_id") or ""),
                    "direction": str(row.get("direction") or ""),
                    "scope_key": str(row.get("scope_key") or ""),
                    "oa_id": oa_id,
                }
            )
        return result

    def _invalid_relation_rows(self) -> list[dict[str, Any]]:
        return list(self._repository.invalid_relation_rows())

    def _missing_oa_relation_rows(self) -> list[dict[str, Any]]:
        return list(self._repository.missing_oa_relation_rows())

    @staticmethod
    def _affected_scope_keys(invalid_read_model_rows: list[dict[str, Any]]) -> list[str]:
        scope_keys: list[str] = []
        for row in invalid_read_model_rows:
            scope_key = str(row.get("scope_key") or "").strip()
            if scope_key and scope_key not in scope_keys:
                scope_keys.append(scope_key)
            direction = str(row.get("direction") or "").strip()
            base_scope = f"{direction}:all" if direction in {"expense", "income"} else ""
            if base_scope and base_scope not in scope_keys:
                scope_keys.append(base_scope)
        return scope_keys
