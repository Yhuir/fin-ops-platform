from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy, ObjectIdentity
from fin_ops_platform.services.postgres_repositories.common import int_value, month_start, text, text_list
from fin_ops_platform.services.postgres_repositories.oa_projection import COMPLETED_WORKFLOW_STATUS_SQL, OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_relation_read_model_repository import WorkbenchRelationReadModelRepositoryPort


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
WORKBENCH_RELATION_SQL_PROJECTION_SCHEMA_VERSION = "2026-07-10-active-relations-force-rebuild-v2"
OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()
HARD_INVOICE_IDENTITY_KINDS = frozenset({"digital_invoice_no", "invoice_code_no"})


class WorkbenchRelationSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: Any | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or WorkbenchRelationReadModelRepositoryPort(PostgresReadModelRepository(connection))
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
                select date_trunc('month', application_date)::date as scope_month
                from app.oa_applications
                where application_date is not null
                  and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
            ) months
            order by scope_key desc
            """
        )
        return [text(row.get("scope_key")) for row in rows if MONTH_RE.match(text(row.get("scope_key")) or "")]

    def rebuild_workbench_relation_read_model_scope(
        self,
        scope_key: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        normalized_scope = text(scope_key) or ""
        if not MONTH_RE.match(normalized_scope):
            raise ValueError("workbench relation SQL projection scope_key must be a month shard YYYY-MM.")
        source_versions = self._source_versions(normalized_scope)
        if not force_refresh:
            unchanged = self._unchanged_scope_result(
                scope_key=normalized_scope,
                source_versions=source_versions,
            )
            if unchanged is not None:
                return unchanged
        pending_claimed_bank_ids = set(self._pending_claimed_bank_transaction_ids_for_month(normalized_scope))
        monthly_objects = self._source_objects_for_month(
            normalized_scope,
            relation_row_ids=[],
            excluded_bank_transaction_ids=pending_claimed_bank_ids,
        )
        monthly_row_ids = sorted(monthly_objects)
        relations = self._active_relations_for_scope(month=normalized_scope, row_ids=monthly_row_ids)
        relation_row_ids = _dedupe_preserve_order(row_id for relation in relations for row_id in text_list(relation.get("row_ids")))
        objects = dict(monthly_objects)
        missing_relation_row_ids = [row_id for row_id in relation_row_ids if row_id not in objects]
        if missing_relation_row_ids:
            objects.update(
                self._source_objects_for_month(
                    normalized_scope,
                    relation_row_ids=missing_relation_row_ids,
                    excluded_bank_transaction_ids=pending_claimed_bank_ids,
                    include_month_scope=False,
                    source_kinds=_source_kinds_for_relation_row_ids(relations, missing_relation_row_ids),
                )
            )
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
            for row_id in sorted(objects)
            if row_id in objects
        ]
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

    def rebuild_workbench_relation_read_model_rows(self, scope_key: str, *, row_ids: list[str]) -> dict[str, Any]:
        normalized_scope = text(scope_key) or ""
        if not MONTH_RE.match(normalized_scope):
            raise ValueError("workbench relation SQL projection scope_key must be a month shard YYYY-MM.")
        affected_row_ids = _dedupe_preserve_order(text(row_id) for row_id in list(row_ids or []))
        if not affected_row_ids:
            return self.rebuild_workbench_relation_read_model_scope(normalized_scope)
        save_rows = getattr(self._read_model_repository, "save_workbench_relation_distribution_rows", None)
        if not callable(save_rows):
            return self.rebuild_workbench_relation_read_model_scope(normalized_scope)
        source_versions = self._source_versions(normalized_scope)
        unchanged = self._unchanged_scope_result(
            scope_key=normalized_scope,
            source_versions=source_versions,
        )
        if unchanged is not None:
            return {**unchanged, "partial": True, "affected_row_count": len(affected_row_ids)}

        pending_claimed_bank_ids = set(self._pending_claimed_bank_transaction_ids_for_month(normalized_scope))
        relations = self._active_relations_for_scope(month=normalized_scope, row_ids=affected_row_ids)
        relation_row_ids = _dedupe_preserve_order(row_id for relation in relations for row_id in text_list(relation.get("row_ids")))
        object_row_ids = _dedupe_preserve_order([*affected_row_ids, *relation_row_ids])
        objects = self._source_objects_for_month(
            normalized_scope,
            relation_row_ids=object_row_ids,
            excluded_bank_transaction_ids=pending_claimed_bank_ids,
            include_month_scope=False,
            source_kinds=_source_kinds_for_relation_row_ids(relations, object_row_ids),
        )
        if pending_claimed_bank_ids:
            active_relation_row_ids = set(relation_row_ids)
            objects = {
                row_id: object_payload
                for row_id, object_payload in objects.items()
                if not (
                    row_id in pending_claimed_bank_ids
                    and text(object_payload.get("row_type")) == "bank_transaction"
                    and row_id not in active_relation_row_ids
                )
            }

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
            for row_id in sorted(object_row_ids)
            if row_id in objects
        ]
        save_rows(
            scope_key=normalized_scope,
            affected_row_ids=affected_row_ids,
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
            "partial": True,
            "affected_row_count": len(affected_row_ids),
        }

    def _unchanged_scope_result(self, *, scope_key: str, source_versions: dict[str, Any]) -> dict[str, Any] | None:
        scope_summary_loader = getattr(self._read_model_repository, "workbench_relation_scope_summary", None)
        if not callable(scope_summary_loader):
            return None
        payload = scope_summary_loader(scope_key=scope_key, tenant_id=self._tenant_id)
        if not isinstance(payload, dict):
            return None
        existing_source_versions = payload.get("source_versions")
        if not isinstance(existing_source_versions, dict) or existing_source_versions != source_versions:
            return None
        return {
            "scope_key": scope_key,
            "row_count": int_value(payload.get("row_count"), 0),
            "group_count": int_value(payload.get("group_count"), 0),
            "source_versions": source_versions,
            "skipped": True,
            "skip_reason": "source_versions_unchanged",
        }

    def mark_workbench_relation_scope_empty(self, scope_key: str) -> dict[str, Any]:
        normalized_scope = text(scope_key) or ""
        if not normalized_scope:
            raise ValueError("workbench relation scope_key is required.")
        source_versions = self._source_versions(normalized_scope)
        mark_empty = getattr(self._read_model_repository, "mark_workbench_relation_scope_empty", None)
        if callable(mark_empty):
            mark_empty(scope_key=normalized_scope, source_versions=source_versions, tenant_id=self._tenant_id)
        return {"scope_key": normalized_scope, "row_count": 0, "group_count": 0, "source_versions": source_versions}

    def _source_objects_for_month(
        self,
        month: str,
        *,
        relation_row_ids: list[str],
        excluded_bank_transaction_ids: set[str] | None = None,
        include_month_scope: bool = True,
        source_kinds: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        ids = _dedupe_preserve_order(text(row_id) for row_id in list(relation_row_ids or []))
        excluded_bank_ids = {text(row_id) for row_id in (excluded_bank_transaction_ids or set()) if text(row_id)}
        selected_source_kinds = source_kinds or {"bank_transaction", "oa", "invoice"}
        objects: dict[str, dict[str, Any]] = {}
        if "bank_transaction" in selected_source_kinds:
            for row in self._bank_transaction_rows(
                month,
                ids,
                excluded_bank_transaction_ids=excluded_bank_ids,
                include_month_scope=include_month_scope,
            ):
                _put_object(objects, _bank_transaction_object(row, month=month))
        if "oa" in selected_source_kinds:
            for row in self._oa_rows(month, ids, include_month_scope=include_month_scope):
                _put_object(objects, _oa_object(row, month=month))
        if "invoice" in selected_source_kinds:
            for row in self._formal_invoice_rows(month, ids, include_month_scope=include_month_scope):
                _put_object(objects, _formal_invoice_object(row, month=month))
        return objects

    def _bank_transaction_rows(
        self,
        month: str,
        row_ids: list[str],
        *,
        excluded_bank_transaction_ids: set[str] | None = None,
        include_month_scope: bool = True,
    ) -> list[dict[str, Any]]:
        explicit_ids = set(row_ids)
        excluded_ids = {text(row_id) for row_id in (excluded_bank_transaction_ids or set()) if text(row_id)}
        if not include_month_scope:
            if not row_ids:
                return []
            return self._connection.fetch_all(
                """
                select coalesce(legacy_mongo_id, id::text) as row_id, counterparty_name_raw, trade_time, txn_date,
                       amount, txn_direction, summary, remark, bank_serial_no, account_name, account_no, txn_month,
                       raw_payload
                from app.bank_transactions
                where status <> 'deleted'
                  and coalesce(legacy_mongo_id, id::text) = any(%s::text[])
                """,
                (row_ids,),
            )
        rows = self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, counterparty_name_raw, trade_time, txn_date,
                   amount, txn_direction, summary, remark, bank_serial_no, account_name, account_no, txn_month,
                   raw_payload
            from app.bank_transactions
            where status <> 'deleted'
              and (
                  coalesce(legacy_mongo_id, id::text) = any(%s::text[])
                  or (
                      txn_month = %s::date
                      and not (coalesce(legacy_mongo_id, id::text) = any(%s::text[]))
                  )
              )
            """,
            (row_ids, month_start(month), sorted(excluded_ids)),
        )
        if not excluded_ids:
            return rows
        return [row for row in rows if text(row.get("row_id")) in explicit_ids or text(row.get("row_id")) not in excluded_ids]

    def _oa_rows(self, month: str, row_ids: list[str], *, include_month_scope: bool = True) -> list[dict[str, Any]]:
        if not include_month_scope:
            if not row_ids:
                return []
            return self._connection.fetch_all(
                """
                select row_id, form_id, form_type, status, applicant, application_date, project_name, amount, raw_payload
                from app.oa_applications
                where row_id = any(%s)
                  and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
                """,
                (row_ids,),
            )
        return self._connection.fetch_all(
            """
            select row_id, form_id, form_type, status, applicant, application_date, project_name, amount, raw_payload
            from app.oa_applications
            where (
                (application_date >= %s::date and application_date < (%s::date + interval '1 month'))
                or row_id = any(%s)
            )
              and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
            """,
            (month_start(month), month_start(month), row_ids),
        )

    def _formal_invoice_rows(self, month: str, row_ids: list[str], *, include_month_scope: bool = True) -> list[dict[str, Any]]:
        if not include_month_scope:
            if not row_ids:
                return []
            return self._connection.fetch_all(
                """
                select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_code, invoice_no, digital_invoice_no,
                       invoice_date, invoice_month, seller_name, seller_tax_no, buyer_name, buyer_tax_no,
                       amount, total_with_tax, raw_payload
                from app.invoices
                where status <> 'deleted'
                  and coalesce(legacy_mongo_id, id::text) = any(%s)
                """,
                (row_ids,),
            )
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

    def _pending_claimed_bank_transaction_ids_for_month(self, month: str) -> list[str]:
        rows = self._connection.fetch_all(
            """
            select bank_transaction_id
            from app.bank_transaction_relation_claims
            where status = 'active'
              and owner_type = 'oa_pending_payment_relation'
              and scope_month = %s::date
            order by bank_transaction_id
            """,
            (month_start(month),),
        )
        return _dedupe_preserve_order(row.get("bank_transaction_id") for row in rows)

    def _source_versions(self, scope_key: str | None = None) -> dict[str, Any]:
        scope_month = month_start(scope_key)
        if scope_month is None:
            row = self._connection.fetch_one(
                """
                select
                  (select max(updated_at)::text from app.workbench_pair_relations) as pair_relations_updated_at,
                  (select max(updated_at)::text from app.bank_transaction_relation_claims where status = 'active') as oa_pending_payment_bank_claims_updated_at,
                  (select max(updated_at)::text from app.bank_transactions) as bank_transactions_updated_at,
                  (select max(updated_at)::text from app.invoices) as invoices_updated_at,
                  (select max(updated_at)::text from app.oa_applications) as oa_projection_updated_at
                """
            )
        else:
            row = self._connection.fetch_one(
                """
                with scope as (select %s::date as scope_month),
                month_objects as (
                    select coalesce(legacy_mongo_id, id::text) as row_id
                    from app.bank_transactions, scope
                    where status <> 'deleted'
                      and txn_month = scope.scope_month
                    union
                    select row_id
                    from app.oa_applications, scope
                    where application_date is not null
                      and application_date >= scope.scope_month
                      and application_date < scope.scope_month + interval '1 month'
                      and """
                + COMPLETED_WORKFLOW_STATUS_SQL
                + """
                    union
                    select coalesce(legacy_mongo_id, id::text) as row_id
                    from app.invoices, scope
                    where status <> 'deleted'
                      and invoice_month = scope.scope_month
                ),
                month_object_array as (
                    select coalesce(array_agg(row_id), array[]::text[]) as row_ids
                    from month_objects
                ),
                scoped_relations as (
                    select relation.status, relation.updated_at, relation.row_ids
                    from app.workbench_pair_relations relation, scope, month_object_array objects
                    where relation.month_scope = scope.scope_month
                       or relation.row_ids && objects.row_ids
                ),
                active_relation_row_ids as (
                    select distinct unnest(row_ids) as row_id
                    from scoped_relations
                    where status = 'active'
                ),
                scope_row_ids as (
                    select row_id from month_objects
                    union
                    select row_id from active_relation_row_ids
                ),
                scope_row_id_array as (
                    select coalesce(array_agg(row_id), array[]::text[]) as row_ids
                    from scope_row_ids
                )
                select
                  (select max(updated_at)::text from scoped_relations) as pair_relations_updated_at,
                  (
                    select max(updated_at)::text
                    from app.bank_transaction_relation_claims claims, scope
                    where claims.status = 'active'
                      and claims.scope_month = scope.scope_month
                  ) as oa_pending_payment_bank_claims_updated_at,
                  (
                    select max(bank.updated_at)::text
                    from app.bank_transactions bank, scope, scope_row_id_array ids
                    where bank.status <> 'deleted'
                      and (
                        bank.txn_month = scope.scope_month
                        or coalesce(bank.legacy_mongo_id, bank.id::text) = any(ids.row_ids)
                      )
                  ) as bank_transactions_updated_at,
                  (
                    select max(invoice.updated_at)::text
                    from app.invoices invoice, scope, scope_row_id_array ids
                    where invoice.status <> 'deleted'
                      and (
                        invoice.invoice_month = scope.scope_month
                        or coalesce(invoice.legacy_mongo_id, invoice.id::text) = any(ids.row_ids)
                      )
                  ) as invoices_updated_at,
                  (
                    select max(oa.updated_at)::text
                    from app.oa_applications oa, scope, scope_row_id_array ids
                    where (
                        (
                          oa.application_date >= scope.scope_month
                          and oa.application_date < scope.scope_month + interval '1 month'
                        )
                        or oa.row_id = any(ids.row_ids)
                      )
                      and """
                + COMPLETED_WORKFLOW_STATUS_SQL
                + """
                  ) as oa_projection_updated_at
                """,
                (scope_month,),
            )
        payload = row if isinstance(row, dict) else {}
        return {
            "workbench_relation_schema_version": WORKBENCH_RELATION_SQL_PROJECTION_SCHEMA_VERSION,
            "workbench_pair_relations_updated_at": text(payload.get("pair_relations_updated_at")),
            "oa_pending_payment_bank_claims_updated_at": text(payload.get("oa_pending_payment_bank_claims_updated_at")),
            "bank_transactions_updated_at": text(payload.get("bank_transactions_updated_at")),
            "invoices_updated_at": text(payload.get("invoices_updated_at")),
            "oa_projection_updated_at": text(payload.get("oa_projection_updated_at")),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
            "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
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


def _relation_group_payload(relation: dict[str, Any], *, objects: dict[str, dict[str, Any]], month: str) -> dict[str, Any]:
    group_id = text(relation.get("case_id")) or ""
    typed_ids = _relation_typed_row_ids(relation, objects=objects)
    relation_kind = _relation_kind(typed_ids)
    relation_status = text(relation.get("relation_status")) or "linked"
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
        "relation_status": relation_status,
        "oa_row_ids": typed_ids["oa"],
        "bank_transaction_ids": typed_ids["bank_transaction"],
        "input_invoice_ids": typed_ids["input_invoice"],
        "output_invoice_ids": typed_ids["output_invoice"],
        "_summaries_by_id": summaries_by_id,
        "payload": {
            "group_id": group_id,
            "relation_mode": text(relation.get("relation_mode")),
            "relation_kind": relation_kind,
            "relation_status": relation_status,
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
    relation_status = _row_relation_status(groups)
    return {
        "row_id": row_id,
        "row_type": row_type,
        "scope_key": month,
        "scope_month": month,
        "relation_status": relation_status,
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
            item["relation_status"] = text(group.get("relation_status")) or "linked"
            item["relation_source"] = text(group.get("relation_source")) or "manual"
            summaries.append(item)
            seen.add(row_id)
    return summaries


def _row_relation_status(groups: list[dict[str, Any]]) -> str:
    statuses = {text(group.get("relation_status")) or "linked" for group in groups}
    if "linked" in statuses:
        return "linked"
    if "candidate" in statuses:
        return "candidate"
    return "unlinked"


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


def _source_kinds_for_relation_row_ids(relations: list[dict[str, Any]], row_ids: list[str]) -> set[str]:
    target_row_ids = set(text_list(row_ids))
    if not target_row_ids:
        return {"bank_transaction", "oa", "invoice"}
    source_kinds: set[str] = set()
    for relation in relations:
        relation_row_ids = text_list(relation.get("row_ids"))
        relation_row_types = text_list(relation.get("row_types"))
        for index, row_id in enumerate(relation_row_ids):
            if row_id not in target_row_ids:
                continue
            row_type = text(relation_row_types[index] if index < len(relation_row_types) else "")
            if row_type in {"bank", "bank_transaction"}:
                source_kinds.add("bank_transaction")
            elif row_type == "oa":
                source_kinds.add("oa")
            elif row_type in {"invoice", "input_invoice", "output_invoice"}:
                source_kinds.add("invoice")
            else:
                return {"bank_transaction", "oa", "invoice"}
    return source_kinds or {"bank_transaction", "oa", "invoice"}


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
    return "manual"


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
