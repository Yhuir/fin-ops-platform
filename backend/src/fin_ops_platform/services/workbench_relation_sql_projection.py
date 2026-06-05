from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy, ObjectIdentity
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload, text, text_list
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
WORKBENCH_RELATION_SQL_PROJECTION_SCHEMA_VERSION = "2026-06-workbench-relation-object-identity-v1"
OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()
HARD_INVOICE_IDENTITY_KINDS = frozenset({"digital_invoice_no", "invoice_code_no"})


class WorkbenchRelationSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: PostgresReadModelRepository | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or PostgresReadModelRepository(connection)
        self._tenant_id = text(tenant_id) or "default"

    def list_workbench_relation_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope = text(scope_key) or ""
        if normalized_scope != "all":
            return [normalized_scope] if MONTH_RE.match(normalized_scope) else []
        rows = self._connection.fetch_all(
            """
            select distinct to_char(scope_month, 'YYYY-MM') as scope_key
            from (
                select txn_month as scope_month from app.bank_transactions where txn_month is not null and status <> 'deleted'
                union
                select invoice_month as scope_month from app.invoices where invoice_month is not null and status <> 'deleted'
                union
                select date_trunc('month', application_date)::date as scope_month from app.oa_applications where application_date is not null
                union
                select scope_month from read_model.workbench_rows where scope_month is not null and source_kind = 'oa_attachment_invoice'
            ) months
            order by scope_key desc
            """
        )
        return [text(row.get("scope_key")) for row in rows if MONTH_RE.match(text(row.get("scope_key")) or "")]

    def rebuild_workbench_relation_read_model_scope(self, scope_key: str) -> dict[str, Any]:
        normalized_scope = text(scope_key) or ""
        if not MONTH_RE.match(normalized_scope):
            raise ValueError("workbench relation SQL projection scope_key must be a month shard YYYY-MM.")
        monthly_objects = self._source_objects_for_month(normalized_scope, relation_row_ids=[])
        monthly_row_ids = sorted(monthly_objects)
        relations = [
            *self._active_relations_for_scope(month=normalized_scope, row_ids=monthly_row_ids),
            *self._automatic_decision_relations_for_scope(month=normalized_scope, row_ids=monthly_row_ids),
        ]
        relation_row_ids = _dedupe_preserve_order(row_id for relation in relations for row_id in text_list(relation.get("row_ids")))
        objects = self._source_objects_for_month(normalized_scope, relation_row_ids=relation_row_ids)
        groups = [_relation_group_payload(relation, objects=objects, month=normalized_scope) for relation in relations]
        relation_groups_by_row_id: dict[str, list[dict[str, Any]]] = {}
        for group in groups:
            for row_id in [
                *text_list(group.get("oa_row_ids")),
                *text_list(group.get("bank_transaction_ids")),
                *text_list(group.get("input_invoice_ids")),
                *text_list(group.get("output_invoice_ids")),
            ]:
                relation_groups_by_row_id.setdefault(row_id, []).append(group)
        rows = [
            _relation_row_payload(
                object_payload=objects[row_id],
                groups=relation_groups_by_row_id.get(row_id, []),
                month=normalized_scope,
            )
            for row_id in sorted(monthly_objects)
            if row_id in objects
        ]
        source_versions = self._source_versions()
        self._read_model_repository.save_workbench_relation_distribution(
            scope_key=normalized_scope,
            rows=rows,
            groups=groups,
            source_versions=source_versions,
            tenant_id=self._tenant_id,
        )
        return {
            "scope_key": normalized_scope,
            "row_count": len(rows),
            "group_count": len(groups),
            "source_versions": source_versions,
        }

    def mark_workbench_relation_scope_empty(self, scope_key: str) -> dict[str, Any]:
        normalized_scope = text(scope_key) or ""
        if not normalized_scope:
            raise ValueError("workbench relation scope_key is required.")
        source_versions = self._source_versions()
        mark_empty = getattr(self._read_model_repository, "mark_workbench_relation_scope_empty", None)
        if callable(mark_empty):
            mark_empty(scope_key=normalized_scope, source_versions=source_versions, tenant_id=self._tenant_id)
        return {"scope_key": normalized_scope, "row_count": 0, "group_count": 0, "source_versions": source_versions}

    def _source_objects_for_month(self, month: str, *, relation_row_ids: list[str]) -> dict[str, dict[str, Any]]:
        ids = _dedupe_preserve_order(text(row_id) for row_id in list(relation_row_ids or []))
        objects: dict[str, dict[str, Any]] = {}
        for row in self._bank_transaction_rows(month, ids):
            _put_object(objects, _bank_transaction_object(row, month=month))
        for row in self._oa_rows(month, ids):
            _put_object(objects, _oa_object(row, month=month))
        for row in self._formal_invoice_rows(month, ids):
            _put_object(objects, _formal_invoice_object(row, month=month))
        for row in self._oa_attachment_invoice_rows(month, ids):
            _put_object(objects, _oa_attachment_invoice_object(row, month=month))
        return objects

    def _bank_transaction_rows(self, month: str, row_ids: list[str]) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, counterparty_name_raw, trade_time, txn_date,
                   amount, txn_direction, summary, remark, bank_serial_no, account_name, account_no, txn_month,
                   raw_payload
            from app.bank_transactions
            where status <> 'deleted'
              and (txn_month = %s::date or coalesce(legacy_mongo_id, id::text) = any(%s))
            """,
            (month_start(month), row_ids),
        )

    def _oa_rows(self, month: str, row_ids: list[str]) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select row_id, form_id, form_type, status, applicant, application_date, project_name, amount, raw_payload
            from app.oa_applications
            where (date_trunc('month', application_date)::date = %s::date or row_id = any(%s))
            """,
            (month_start(month), row_ids),
        )

    def _formal_invoice_rows(self, month: str, row_ids: list[str]) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_code, invoice_no, digital_invoice_no,
                   invoice_date, invoice_month, seller_name, seller_tax_no, buyer_name, buyer_tax_no,
                   amount, total_with_tax, raw_payload
            from app.invoices
            where status <> 'deleted'
              and (invoice_month = %s::date or coalesce(legacy_mongo_id, id::text) = any(%s))
            """,
            (month_start(month), row_ids),
        )

    def _oa_attachment_invoice_rows(self, month: str, row_ids: list[str]) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select r.row_id, r.scope_month, r.payload, r.raw_payload
            from read_model.workbench_rows r
            join read_model.workbench_generations gen
              on gen.generation_id = r.generation_id
             and gen.tenant_id = %s
             and gen.scope_key = r.scope_key
             and gen.status = 'active'
            where r.source_kind = 'oa_attachment_invoice'
              and (r.scope_month = %s::date or r.row_id = any(%s))
            """,
            (self._tenant_id, month_start(month), row_ids),
        )

    def _active_relations_for_scope(self, *, month: str, row_ids: list[str]) -> list[dict[str, Any]]:
        if not row_ids:
            return []
        return self._connection.fetch_all(
            """
            select case_id, relation_mode, month_scope, row_ids, row_types, note, amount_check, special_metadata, source_versions, raw_payload
            from app.workbench_pair_relations
            where status = 'active'
              and (month_scope = %s::date or row_ids && %s::text[])
            order by updated_at, case_id
            """,
            (month_start(month), row_ids),
        )

    def _automatic_decision_relations_for_scope(self, *, month: str, row_ids: list[str]) -> list[dict[str, Any]]:
        if not row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select decision_key, scope_month, row_ids, row_types, oa_row_ids, bank_row_ids, invoice_row_ids,
                   amount, payment_amount_closed, invoice_amount_closed, source_versions, raw_payload
            from read_model.workbench_reconciliation_decisions d
            where d.tenant_id = %s
              and d.scope_month = %s::date
              and d.decision_status = 'paired'
              and d.display_state = 'paired'
              and d.row_ids && %s::text[]
              and not exists (
                  select 1
                  from app.workbench_pair_relations pr
                  where pr.status = 'active'
                    and pr.row_ids && d.row_ids
              )
            order by d.generated_at nulls last, d.decision_key
            """,
            (self._tenant_id, month_start(month), row_ids),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            row_ids_payload = text_list(row.get("row_ids"))
            row_types_payload = text_list(row.get("row_types"))
            if not row_types_payload:
                row_types_payload = _decision_row_types(row)
            result.append(
                {
                    "case_id": text(row.get("decision_key")),
                    "relation_mode": "automatic_decision",
                    "month_scope": month_start(month),
                    "row_ids": row_ids_payload,
                    "row_types": row_types_payload,
                    "amount_check": {
                        "matched": bool(row.get("payment_amount_closed")) or bool(row.get("invoice_amount_closed")),
                        "status": "matched" if bool(row.get("payment_amount_closed")) or bool(row.get("invoice_amount_closed")) else "",
                        "amount": _decimal_text(row.get("amount")),
                    },
                    "special_metadata": {},
                    "source_versions": row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
                    "raw_payload": row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {},
                }
            )
        return result

    def _source_versions(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            select
              (select max(updated_at)::text from app.workbench_pair_relations) as pair_relations_updated_at,
              (select max(updated_at)::text from read_model.workbench_reconciliation_decisions) as reconciliation_decisions_updated_at,
              (select max(updated_at)::text from app.bank_transactions) as bank_transactions_updated_at,
              (select max(updated_at)::text from app.invoices) as invoices_updated_at,
              (select max(updated_at)::text from app.oa_applications) as oa_projection_updated_at
            """
        )
        payload = row if isinstance(row, dict) else {}
        return {
            "workbench_relation_schema_version": WORKBENCH_RELATION_SQL_PROJECTION_SCHEMA_VERSION,
            "workbench_pair_relations_updated_at": text(payload.get("pair_relations_updated_at")),
            "workbench_reconciliation_decisions_updated_at": text(payload.get("reconciliation_decisions_updated_at")),
            "bank_transactions_updated_at": text(payload.get("bank_transactions_updated_at")),
            "invoices_updated_at": text(payload.get("invoices_updated_at")),
            "oa_projection_updated_at": text(payload.get("oa_projection_updated_at")),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
            "oa_attachment_invoice_parser_version": MongoOAAdapter._attachment_invoice_cache_parser_version(),
        }


def _bank_transaction_object(row: dict[str, Any], *, month: str) -> dict[str, Any]:
    row_id = text(row.get("row_id")) or ""
    identity = OBJECT_IDENTITY_POLICY.identify_bank_transaction_mapping(
        {
            "account_no": row.get("account_no"),
            "trade_time": row.get("trade_time") or row.get("txn_date"),
            "txn_direction": row.get("txn_direction"),
            "amount": row.get("amount"),
            "counterparty_name": row.get("counterparty_name_raw"),
            "bank_serial_no": row.get("bank_serial_no"),
        },
        source_kind="bank_transaction",
        source_row_id=row_id,
    )
    return {
        "row_id": row_id,
        "row_type": "bank_transaction",
        "scope_month": month,
        **_object_identity_columns(identity),
        "summary": {
            "id": row_id,
            "amount": _decimal_text(row.get("amount")),
            "counterparty_name": text(row.get("counterparty_name_raw")),
            "trade_time": text(row.get("trade_time") or row.get("txn_date")),
            "txn_direction": text(row.get("txn_direction")),
            "summary": text(row.get("summary")),
            "remark": text(row.get("remark")),
            "statement_serial_no": text(row.get("bank_serial_no")),
            "account_name": text(row.get("account_name")),
            "account_last4": text(row.get("account_no"))[-4:] if text(row.get("account_no")) else "",
            **_object_identity_columns(identity),
        },
    }


def _oa_object(row: dict[str, Any], *, month: str) -> dict[str, Any]:
    row_id = text(row.get("row_id")) or ""
    return {
        "row_id": row_id,
        "row_type": "oa",
        "scope_month": month,
        "object_identity_key": row_id,
        "object_identity_kind": "oa_row_id",
        "object_identity_source": "oa",
        "object_identity_confidence": "canonical",
        "summary": {
            "id": row_id,
            "applicant": text(row.get("applicant")),
            "application_type": text(row.get("form_type")),
            "project_name": text(row.get("project_name")),
            "status": text(row.get("status")),
            "form_no": text(row.get("form_id")),
            "amount": _decimal_text(row.get("amount")),
            "detail_available": True,
            "object_identity_key": row_id,
            "object_identity_kind": "oa_row_id",
            "object_identity_source": "oa",
            "object_identity_confidence": "canonical",
        },
    }


def _formal_invoice_object(row: dict[str, Any], *, month: str) -> dict[str, Any]:
    row_id = text(row.get("row_id")) or ""
    invoice_type = "output" if text(row.get("invoice_type")) == "output" else "input"
    identity = OBJECT_IDENTITY_POLICY.identify_invoice_mapping(
        {
            "digital_invoice_no": row.get("digital_invoice_no"),
            "invoice_code": row.get("invoice_code"),
            "invoice_no": row.get("invoice_no"),
            "seller_tax_no": row.get("seller_tax_no"),
            "buyer_tax_no": row.get("buyer_tax_no"),
            "seller_name": row.get("seller_name"),
            "buyer_name": row.get("buyer_name"),
            "invoice_date": row.get("invoice_date"),
            "total_with_tax": row.get("total_with_tax") or row.get("amount"),
        },
        source_kind="formal_invoice",
        source_row_id=row_id,
        object_type="invoice",
    )
    return {
        "row_id": row_id,
        "row_type": f"{invoice_type}_invoice",
        "scope_month": month,
        **_object_identity_columns(identity),
        "summary": {
            "id": row_id,
            "invoice_no": text(row.get("invoice_no")),
            "digital_invoice_no": text(row.get("digital_invoice_no")),
            "issue_date": text(row.get("invoice_date")),
            "total_with_tax": _decimal_text(row.get("total_with_tax") or row.get("amount")),
            "amount": _decimal_text(row.get("amount")),
            "seller_name": text(row.get("seller_name")),
            "seller_tax_no": text(row.get("seller_tax_no")),
            "buyer_name": text(row.get("buyer_name")),
            "buyer_tax_no": text(row.get("buyer_tax_no")),
            "invoice_type": invoice_type,
            "source_kind": "formal_invoice",
            **_object_identity_columns(identity),
        },
    }


def _oa_attachment_invoice_object(row: dict[str, Any], *, month: str) -> dict[str, Any]:
    payload = row_payload(row, "payload", "raw_payload")
    payload = payload if isinstance(payload, dict) else {}
    row_id = text(row.get("row_id") or payload.get("id") or payload.get("row_id")) or ""
    identity = OBJECT_IDENTITY_POLICY.identify_oa_attachment_invoice(
        payload,
        source_kind="oa_attachment_invoice",
        source_row_id=row_id,
    )
    return {
        "row_id": row_id,
        "row_type": "input_invoice",
        "scope_month": month,
        **_object_identity_columns(identity),
        "summary": {
            "id": row_id,
            "invoice_no": text(payload.get("invoice_no") or payload.get("invoiceNumber") or payload.get("seller_tax_no")),
            "digital_invoice_no": text(payload.get("digital_invoice_no")),
            "issue_date": text(payload.get("issue_date") or payload.get("invoice_date") or payload.get("date")),
            "total_with_tax": _decimal_text(payload.get("total_with_tax") or payload.get("amount")),
            "amount": _decimal_text(payload.get("amount")),
            "seller_name": text(payload.get("seller_name") or payload.get("counterparty_name")),
            "seller_tax_no": text(payload.get("seller_tax_no") or payload.get("tax_no")),
            "buyer_name": text(payload.get("buyer_name")),
            "buyer_tax_no": text(payload.get("buyer_tax_no")),
            "invoice_type": "input",
            "source_kind": "oa_attachment_invoice",
            **_object_identity_columns(identity),
        },
    }


def _relation_group_payload(relation: dict[str, Any], *, objects: dict[str, dict[str, Any]], month: str) -> dict[str, Any]:
    group_id = text(relation.get("case_id")) or ""
    typed_ids = _relation_typed_row_ids(relation, objects=objects)
    relation_kind = _relation_kind(typed_ids)
    summaries_by_id = {
        row_id: dict(summary)
        for row_id, object_payload in objects.items()
        if isinstance((summary := object_payload.get("summary")), dict)
    }
    return {
        "group_id": group_id,
        "scope_key": month,
        "scope_month": month,
        "relation_source": _relation_source(relation),
        "relation_kind": relation_kind,
        "relation_status": "linked",
        "oa_row_ids": typed_ids["oa"],
        "bank_transaction_ids": typed_ids["bank_transaction"],
        "input_invoice_ids": typed_ids["input_invoice"],
        "output_invoice_ids": typed_ids["output_invoice"],
        "_summaries_by_id": summaries_by_id,
        "payload": {
            "group_id": group_id,
            "relation_mode": text(relation.get("relation_mode")),
            "relation_kind": relation_kind,
            "row_ids": text_list(relation.get("row_ids")),
            "row_types": text_list(relation.get("row_types")),
            "amount_check": relation.get("amount_check") if isinstance(relation.get("amount_check"), dict) else {},
            "special_metadata": relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {},
            "source_versions": relation.get("source_versions") if isinstance(relation.get("source_versions"), dict) else {},
            "note": text(relation.get("note")),
            "raw_payload": relation.get("raw_payload") if isinstance(relation.get("raw_payload"), dict) else {},
        },
    }


def _relation_row_payload(*, object_payload: dict[str, Any], groups: list[dict[str, Any]], month: str) -> dict[str, Any]:
    row_id = text(object_payload.get("row_id")) or ""
    row_type = text(object_payload.get("row_type")) or ""
    group_ids = _dedupe_preserve_order(group.get("group_id") for group in groups)
    linked_oa = _linked_summaries(groups, "oa_row_ids")
    linked_bank = _linked_summaries(
        groups,
        "bank_transaction_ids",
    )
    linked_input = _linked_summaries(
        groups,
        "input_invoice_ids",
    )
    linked_output = _linked_summaries(
        groups,
        "output_invoice_ids",
    )
    return {
        "row_id": row_id,
        "row_type": row_type,
        "scope_key": month,
        "scope_month": month,
        "relation_status": "linked" if group_ids else "unlinked",
        "group_ids": group_ids,
        "linked_oa": linked_oa,
        "linked_bank_transactions": linked_bank,
        "linked_input_invoices": linked_input,
        "linked_output_invoices": linked_output,
        "payload": {"source_summary": object_payload.get("summary") if isinstance(object_payload.get("summary"), dict) else {}},
    }


def _linked_summaries(
    groups: list[dict[str, Any]],
    key: str,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        summaries_by_id = group.get("_summaries_by_id") if isinstance(group.get("_summaries_by_id"), dict) else {}
        for row_id in text_list(group.get(key)):
            if row_id in seen:
                continue
            summary = summaries_by_id.get(row_id)
            if summary is None:
                continue
            item = dict(summary)
            item["relation_case_id"] = text(group.get("group_id"))
            summaries.append(item)
            seen.add(row_id)
    return summaries

def _relation_typed_row_ids(relation: dict[str, Any], *, objects: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    result = {"oa": [], "bank_transaction": [], "input_invoice": [], "output_invoice": []}
    row_ids = text_list(relation.get("row_ids"))
    row_types = text_list(relation.get("row_types"))
    for index, row_id in enumerate(row_ids):
        row_type = _normalize_relation_row_type(
            row_types[index] if index < len(row_types) else "",
            objects.get(row_id),
        )
        if row_type in result:
            result[row_type].append(row_id)
    deduped = {key: _dedupe_preserve_order(value) for key, value in result.items()}
    deduped["input_invoice"] = _dedupe_invoice_ids_by_identity(deduped["input_invoice"], objects)
    deduped["output_invoice"] = _dedupe_invoice_ids_by_identity(deduped["output_invoice"], objects)
    return deduped


def _dedupe_invoice_ids_by_identity(row_ids: list[str], objects: dict[str, dict[str, Any]]) -> list[str]:
    seen_identity_keys: set[str] = set()
    result: list[str] = []
    for row_id in row_ids:
        object_payload = objects.get(row_id) if isinstance(objects.get(row_id), dict) else {}
        identity_key = text(object_payload.get("object_identity_key"))
        identity_kind = text(object_payload.get("object_identity_kind"))
        if identity_key and identity_kind in HARD_INVOICE_IDENTITY_KINDS:
            identity_marker = f"{identity_kind}:{identity_key}"
            if identity_marker in seen_identity_keys:
                continue
            seen_identity_keys.add(identity_marker)
        result.append(row_id)
    return result


def _normalize_relation_row_type(row_type: str, object_payload: dict[str, Any] | None) -> str:
    normalized = text(row_type) or ""
    if normalized == "bank":
        return "bank_transaction"
    if normalized == "oa":
        return "oa"
    if normalized == "invoice":
        inferred = text((object_payload or {}).get("row_type")) or "input_invoice"
        return inferred if inferred in {"input_invoice", "output_invoice"} else "input_invoice"
    inferred = text((object_payload or {}).get("row_type")) or normalized
    if inferred in {"bank_transaction", "oa", "input_invoice", "output_invoice"}:
        return inferred
    return ""


def _relation_kind(typed_ids: dict[str, list[str]]) -> str:
    parts: list[str] = []
    if typed_ids.get("oa"):
        parts.append("oa")
    if typed_ids.get("bank_transaction"):
        parts.append("bank")
    if typed_ids.get("input_invoice"):
        parts.append("input_invoice")
    if typed_ids.get("output_invoice"):
        parts.append("output_invoice")
    return "_".join(parts) or "linked"


def _relation_source(relation: dict[str, Any]) -> str:
    mode = text(relation.get("relation_mode")) or ""
    if mode == "automatic_decision":
        return "automatic_decision"
    return "manual"


def _decision_row_types(row: dict[str, Any]) -> list[str]:
    row_types: list[str] = []
    row_types.extend("oa" for _row_id in text_list(row.get("oa_row_ids")))
    row_types.extend("bank" for _row_id in text_list(row.get("bank_row_ids")))
    row_types.extend("invoice" for _row_id in text_list(row.get("invoice_row_ids")))
    return row_types


def _put_object(objects: dict[str, dict[str, Any]], object_payload: dict[str, Any]) -> None:
    row_id = text(object_payload.get("row_id")) or ""
    if row_id:
        objects[row_id] = object_payload


def _object_identity_columns(identity: ObjectIdentity) -> dict[str, str | None]:
    return {
        "object_identity_key": text(identity.canonical_key),
        "object_identity_kind": text(identity.canonical_key_kind),
        "object_identity_source": text(identity.source_kind),
        "object_identity_confidence": text(identity.confidence),
    }


def _dedupe_preserve_order(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _decimal_text(value: object) -> str:
    try:
        return str(Decimal(str(value or "0").strip() or "0").quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return "0.00"
