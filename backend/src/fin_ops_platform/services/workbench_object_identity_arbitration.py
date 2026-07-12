from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy, ObjectIdentity


HARD_INVOICE_IDENTITY_KINDS = frozenset({"digital_invoice_no", "invoice_code_no"})
CLAIMED_RELATION_CODES = frozenset(
    {"fully_linked", "automatic_match", "manual_confirmed", "auto_closed", "processed_exception", "ignored"}
)


class WorkbenchObjectIdentityArbitrationService:
    """Apply canonical object identity rules before workbench rows are grouped."""

    def __init__(self, *, identity_policy: FinancialObjectIdentityPolicy | None = None) -> None:
        self._identity_policy = identity_policy or FinancialObjectIdentityPolicy()

    def arbitrate_rows(self, rows_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
        identities_by_row_id: dict[str, ObjectIdentity] = {}
        invoice_rows_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        bank_rows_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for row_id, row in list(rows_by_id.items()):
            identity = self._identify_workbench_row(row_id, row)
            if identity is None:
                continue
            identities_by_row_id[row_id] = identity
            self._apply_identity_payload(row, identity)
            if identity.object_type in {"invoice", "oa_attachment_invoice"} and self._is_hard_invoice_identity(identity):
                invoice_rows_by_key[str(identity.canonical_key)].append(row)
            elif identity.object_type == "bank_transaction" and identity.canonical_key:
                bank_rows_by_key[str(identity.canonical_key)].append(row)

        suppressed = []
        for identity_key, rows in invoice_rows_by_key.items():
            suppressed.extend(
                self._suppress_duplicate_identity_rows(
                    rows_by_id,
                    identity_key=identity_key,
                    rows=rows,
                    row_type="invoice",
                    collapse_open_duplicates=True,
                )
            )
        for identity_key, rows in bank_rows_by_key.items():
            suppressed.extend(
                self._suppress_duplicate_identity_rows(
                    rows_by_id,
                    identity_key=identity_key,
                    rows=rows,
                    row_type="bank",
                    collapse_open_duplicates=False,
                )
            )

        return {
            "suppressed_row_ids": suppressed,
            "identity_count": len(identities_by_row_id),
        }

    def _identify_workbench_row(self, row_id: str, row: dict[str, Any]) -> ObjectIdentity | None:
        row_type = _text(row.get("type"))
        source_kind = _text(row.get("source_kind"))
        if row_type == "invoice":
            if source_kind == "oa_attachment_invoice":
                return self._identity_policy.identify_oa_attachment_invoice(
                    row,
                    source_kind=source_kind,
                    source_row_id=row_id,
                )
            return self._identity_policy.identify_invoice_mapping(
                row,
                source_kind=source_kind,
                source_row_id=row_id,
                object_type="invoice",
            )
        if row_type == "bank":
            return self._identity_policy.identify_bank_transaction_mapping(
                {
                    **row,
                    "counterparty_name": row.get("counterparty_name") or row.get("counterparty_name_raw"),
                },
                source_kind=source_kind,
                source_row_id=row_id,
            )
        if row_type == "oa":
            return ObjectIdentity(
                object_type="oa",
                source_kind=source_kind,
                source_row_id=row_id,
                canonical_key=row_id,
                canonical_key_kind="oa_row_id",
                confidence="canonical",
                audit_fields={
                    "form_id": _text(row.get("form_id")),
                    "workflow_no": _text(row.get("workflow_no")),
                },
            )
        return None

    @staticmethod
    def _apply_identity_payload(row: dict[str, Any], identity: ObjectIdentity) -> None:
        payload = asdict(identity)
        payload["missing_fields"] = list(identity.missing_fields)
        row["object_identity"] = payload
        row["object_identity_key"] = identity.canonical_key
        row["object_identity_kind"] = identity.canonical_key_kind
        row["object_identity_source"] = identity.source_kind
        row["object_identity_confidence"] = identity.confidence

    @staticmethod
    def _is_hard_invoice_identity(identity: ObjectIdentity) -> bool:
        return bool(identity.canonical_key) and identity.canonical_key_kind in HARD_INVOICE_IDENTITY_KINDS

    def _suppress_duplicate_identity_rows(
        self,
        rows_by_id: dict[str, dict[str, Any]],
        *,
        identity_key: str,
        rows: list[dict[str, Any]],
        row_type: str,
        collapse_open_duplicates: bool,
    ) -> list[str]:
        if len(rows) < 2:
            return []
        claimed_rows = [row for row in rows if self._is_claimed_row(row)]
        if not claimed_rows and not collapse_open_duplicates:
            self._mark_duplicate_identity_warning(rows, identity_key=identity_key, row_type=row_type)
            return []

        primary = self._select_primary_row(claimed_rows or rows)
        primary_id = _row_id(primary)
        if primary_id is None:
            return []
        aliases = [row for row in rows if _row_id(row) != primary_id]
        if not aliases:
            return []

        alias_bucket = dict(primary.get("identity_alias_rows") or {})
        existing_aliases = list(alias_bucket.get(row_type) or [])
        existing_alias_ids = {_row_id(row) for row in existing_aliases if isinstance(row, dict)}
        suppressed_ids: list[str] = []
        for alias in aliases:
            alias_id = _row_id(alias)
            if alias_id is None:
                continue
            if alias_id not in existing_alias_ids:
                alias_payload = deepcopy(alias)
                alias_payload["identity_alias_reason"] = "same_canonical_identity"
                existing_aliases.append(alias_payload)
                existing_alias_ids.add(alias_id)
            if alias_id in rows_by_id:
                rows_by_id.pop(alias_id, None)
                suppressed_ids.append(alias_id)

        alias_bucket[row_type] = existing_aliases
        primary["identity_alias_rows"] = alias_bucket
        primary["identity_arbitration"] = {
            "canonical_key": identity_key,
            "row_type": row_type,
            "suppressed_row_ids": list(suppressed_ids),
        }
        return suppressed_ids

    @staticmethod
    def _mark_duplicate_identity_warning(
        rows: list[dict[str, Any]],
        *,
        identity_key: str,
        row_type: str,
    ) -> None:
        for row in rows:
            warnings = list(row.get("identity_warnings") or [])
            warnings.append(
                {
                    "code": "duplicate_stable_identity",
                    "object_identity_key": identity_key,
                    "row_type": row_type,
                }
            )
            row["identity_warnings"] = warnings

    @staticmethod
    def _select_primary_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return sorted(rows, key=_primary_sort_key)[0]

    @staticmethod
    def _is_claimed_row(row: dict[str, Any]) -> bool:
        status = _text(row.get("status"))
        if status == "paired":
            return True
        if _text(row.get("case_id")):
            return True
        for key in ("oa_bank_relation", "invoice_relation", "invoice_bank_relation", "relation"):
            relation = row.get(key)
            if isinstance(relation, dict) and _text(relation.get("code")) in CLAIMED_RELATION_CODES:
                return True
        exception_case = row.get("exception_case")
        if isinstance(exception_case, dict) and _text(exception_case.get("case_id")):
            return True
        return bool(
            row.get("ignored")
            or row.get("exception_case_id")
            or row.get("auto_close_suppressed")
        )


def _primary_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    source_kind = _text(row.get("source_kind")) or ""
    claimed_rank = 0 if WorkbenchObjectIdentityArbitrationService._is_claimed_row(row) else 1
    source_rank = 0 if source_kind == "invoice" else 1
    return (claimed_rank, source_rank, _row_id(row) or "")


def _row_id(row: dict[str, Any]) -> str | None:
    return _text(row.get("id") or row.get("row_id"))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
