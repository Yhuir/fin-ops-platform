from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence, TextIO

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


STRONG_INVOICE_IDENTITY_KINDS = frozenset({"digital_invoice_no", "invoice_code_no"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run audit for financial object identity/dedup rules.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per issue type.")
    parser.add_argument(
        "--workbench-scope",
        default="all",
        help="Workbench active generation scope to audit, for example all or 2026-02.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(list(argv or sys.argv[1:]))
    connection = PostgresConnection(PostgresSettings.from_env())
    policy = FinancialObjectIdentityPolicy()
    report = audit_object_identity(
        connection=connection,
        policy=policy,
        example_limit=max(int(args.limit or 50), 1),
        workbench_scope=str(args.workbench_scope or "all"),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 1 if report["summary"]["blocking_issue_count"] else 0


def audit_object_identity(
    *,
    connection: Any,
    policy: FinancialObjectIdentityPolicy,
    example_limit: int = 50,
    workbench_scope: str = "all",
) -> dict[str, Any]:
    invoice_rows = connection.fetch_all(
        """
        select id::text as id, coalesce(legacy_mongo_id, id::text) as legacy_id,
               invoice_type, invoice_no, invoice_code, digital_invoice_no, source_unique_key,
               data_fingerprint, invoice_date, counterparty_name, seller_name, seller_tax_no,
               buyer_name, buyer_tax_no, amount, signed_amount, total_with_tax, status,
               etc_invoice_id
        from app.invoices
        order by invoice_month nulls last, created_at, id
        """
    )
    bank_rows = connection.fetch_all(
        """
        select id::text as id, coalesce(legacy_mongo_id, id::text) as legacy_id,
               account_no, account_name, txn_direction, counterparty_name_raw,
               amount, signed_amount, txn_date, trade_time, pay_receive_time,
               bank_serial_no, source_unique_key, data_fingerprint, status
        from app.bank_transactions
        order by txn_month nulls last, created_at, id
        """
    )
    etc_scan = _fetch_rows_if_table_exists(
        connection,
        "app.etc_invoices",
        """
        select id::text as id, coalesce(legacy_mongo_id, id::text) as legacy_id,
               etc_invoice_id, invoice_no, invoice_code, invoice_date, seller_name,
               buyer_name, amount, tax_amount, total_with_tax, status
        from app.etc_invoices
        order by scope_month nulls last, created_at, id
        """,
    )
    attachment_cache_scan = _fetch_rows_if_table_exists(
        connection,
        "app.oa_attachment_invoice_cache",
        """
        select source_attachment_key, parser_version, cache_schema_version, parsed_at,
               invoices, evidences, normalized_payload
        from app.oa_attachment_invoice_cache
        order by parsed_at, source_attachment_key
        """,
    )
    attachment_context = _fetch_oa_attachment_invoice_context(connection)
    etc_rows = list(etc_scan["rows"])
    attachment_cache_rows = list(attachment_cache_scan["rows"])
    invoice_identities = [_invoice_identity_payload(policy, row) for row in invoice_rows]
    bank_identities = [_bank_identity_payload(policy, row) for row in bank_rows]
    etc_identities = [_etc_identity_payload(policy, row) for row in etc_rows]
    attachment_invoice_identities = _oa_attachment_invoice_identity_payloads(policy, attachment_cache_rows)
    all_invoice_duplicate_groups = _duplicate_groups(invoice_identities, key_name="policy_canonical_key")
    blocking_invoice_duplicate_groups = _strong_invoice_duplicate_groups(all_invoice_duplicate_groups)
    weak_invoice_duplicate_groups = [
        group
        for group in all_invoice_duplicate_groups
        if group not in blocking_invoice_duplicate_groups
    ]
    all_bank_duplicate_groups = _duplicate_groups(bank_identities, key_name="policy_canonical_key")
    all_etc_duplicate_groups = _duplicate_groups(etc_identities, key_name="policy_canonical_key")
    all_attachment_invoice_classified_duplicate_groups = _classify_oa_attachment_invoice_duplicate_groups(
        _duplicate_groups(attachment_invoice_identities, key_name="policy_canonical_key"),
        attachment_context=attachment_context,
    )
    all_attachment_invoice_cache_alias_groups = [
        group
        for group in all_attachment_invoice_classified_duplicate_groups
        if group.get("classification") != "cross_oa"
    ]
    all_attachment_invoice_duplicate_groups = [
        group
        for group in all_attachment_invoice_classified_duplicate_groups
        if group.get("classification") == "cross_oa"
    ]
    all_attachment_invoice_blocking_duplicate_groups = list(all_attachment_invoice_duplicate_groups)
    all_attachment_invoice_suspected_groups = _duplicate_groups(attachment_invoice_identities, key_name="policy_suspected_key")
    all_invoice_key_mismatches = [
        item
        for item in invoice_identities
        if item.get("stored_source_unique_key") and item.get("policy_canonical_key") and item["stored_source_unique_key"] != item["policy_canonical_key"]
    ]
    blocking_invoice_key_mismatches = [
        item for item in all_invoice_key_mismatches if _is_strong_invoice_identity_kind(item.get("policy_canonical_key_kind"))
    ]
    weak_invoice_key_mismatches = [
        item for item in all_invoice_key_mismatches if not _is_strong_invoice_identity_kind(item.get("policy_canonical_key_kind"))
    ]
    all_bank_key_mismatches = [
        item
        for item in bank_identities
        if item.get("stored_source_unique_key") and item.get("policy_canonical_key") and item["stored_source_unique_key"] != item["policy_canonical_key"]
    ]
    all_missing_canonical_invoices = [item for item in invoice_identities if not item.get("policy_canonical_key")]
    all_missing_canonical_bank_transactions = [item for item in bank_identities if not item.get("policy_canonical_key")]
    all_missing_canonical_etc_invoices = [item for item in etc_identities if not item.get("policy_canonical_key")]
    all_missing_canonical_attachment_invoices = [item for item in attachment_invoice_identities if not item.get("policy_canonical_key")]
    canonical_etc_invoices = [item for item in invoice_identities if item.get("etc_invoice_id")]
    workbench_audit = _audit_workbench_object_identity(
        connection,
        scope_key=workbench_scope,
        example_limit=example_limit,
    )
    workbench_summary = workbench_audit["summary"] if isinstance(workbench_audit.get("summary"), dict) else {}
    blocking_issue_count = (
        len(blocking_invoice_duplicate_groups)
        + len(all_bank_duplicate_groups)
        + len(all_attachment_invoice_blocking_duplicate_groups)
        + len(blocking_invoice_key_mismatches)
        + len(all_bank_key_mismatches)
        + int(workbench_summary.get("cross_zone_identity_duplicate_group_count") or 0)
        + int(workbench_summary.get("open_visible_owner_duplicate_group_count") or 0)
        + int(workbench_summary.get("orphan_relation_group_count") or 0)
    )
    return {
        "summary": {
            "invoice_count": len(invoice_rows),
            "bank_transaction_count": len(bank_rows),
            "etc_invoice_table_status": etc_scan["status"],
            "etc_invoice_count": len(etc_rows),
            "canonical_etc_invoice_count": len(canonical_etc_invoices),
            "oa_attachment_invoice_cache_table_status": attachment_cache_scan["status"],
            "oa_attachment_invoice_cache_source_table_status": attachment_context["source_table_status"],
            "oa_attachment_source_context_status": attachment_context["attachment_table_status"],
            "oa_attachment_invoice_cache_entry_count": len(attachment_cache_rows),
            "oa_attachment_invoice_count": len(attachment_invoice_identities),
            "invoice_duplicate_group_count": len(all_invoice_duplicate_groups),
            "invoice_blocking_duplicate_group_count": len(blocking_invoice_duplicate_groups),
            "invoice_weak_duplicate_group_count": len(weak_invoice_duplicate_groups),
            "bank_duplicate_group_count": len(all_bank_duplicate_groups),
            "etc_duplicate_group_count": len(all_etc_duplicate_groups),
            "etc_duplicate_warning_group_count": len(all_etc_duplicate_groups),
            "etc_blocking_duplicate_group_count": 0,
            "oa_attachment_invoice_duplicate_group_count": len(all_attachment_invoice_duplicate_groups),
            "oa_attachment_invoice_blocking_duplicate_group_count": len(all_attachment_invoice_blocking_duplicate_groups),
            "oa_attachment_invoice_duplicate_classification_counts": _classification_counts(all_attachment_invoice_duplicate_groups),
            "oa_attachment_invoice_cache_alias_group_count": len(all_attachment_invoice_cache_alias_groups),
            "oa_attachment_invoice_cache_alias_classification_counts": _classification_counts(all_attachment_invoice_cache_alias_groups),
            "oa_attachment_invoice_suspected_duplicate_group_count": len(all_attachment_invoice_suspected_groups),
            "invoice_key_mismatch_count": len(all_invoice_key_mismatches),
            "invoice_blocking_key_mismatch_count": len(blocking_invoice_key_mismatches),
            "invoice_weak_key_mismatch_count": len(weak_invoice_key_mismatches),
            "bank_key_mismatch_count": len(all_bank_key_mismatches),
            "missing_canonical_invoice_count": len(all_missing_canonical_invoices),
            "missing_canonical_bank_transaction_count": len(all_missing_canonical_bank_transactions),
            "missing_canonical_etc_invoice_count": len(all_missing_canonical_etc_invoices),
            "missing_canonical_oa_attachment_invoice_count": len(all_missing_canonical_attachment_invoices),
            "missing_canonical_invoice_examples": min(len(all_missing_canonical_invoices), example_limit),
            "missing_canonical_bank_transaction_examples": min(len(all_missing_canonical_bank_transactions), example_limit),
            "missing_canonical_etc_invoice_examples": min(len(all_missing_canonical_etc_invoices), example_limit),
            "missing_canonical_oa_attachment_invoice_examples": min(len(all_missing_canonical_attachment_invoices), example_limit),
            "workbench_scope": workbench_scope,
            "workbench_audit_status": workbench_summary.get("status"),
            "workbench_cross_zone_identity_duplicate_group_count": workbench_summary.get(
                "cross_zone_identity_duplicate_group_count", 0
            ),
            "workbench_open_visible_owner_duplicate_group_count": workbench_summary.get(
                "open_visible_owner_duplicate_group_count", 0
            ),
            "workbench_oa_alias_group_count": workbench_summary.get("oa_alias_group_count", 0),
            "workbench_orphan_relation_group_count": workbench_summary.get("orphan_relation_group_count", 0),
            "blocking_issue_count": blocking_issue_count,
        },
        "invoice_duplicate_groups": _limit_examples(all_invoice_duplicate_groups, example_limit),
        "invoice_blocking_duplicate_groups": _limit_examples(blocking_invoice_duplicate_groups, example_limit),
        "invoice_weak_duplicate_groups": _limit_examples(weak_invoice_duplicate_groups, example_limit),
        "bank_duplicate_groups": _limit_examples(all_bank_duplicate_groups, example_limit),
        "etc_duplicate_groups": _limit_examples(all_etc_duplicate_groups, example_limit),
        "oa_attachment_invoice_duplicate_groups": _limit_examples(all_attachment_invoice_duplicate_groups, example_limit),
        "oa_attachment_invoice_blocking_duplicate_groups": _limit_examples(all_attachment_invoice_blocking_duplicate_groups, example_limit),
        "oa_attachment_invoice_cache_alias_groups": _limit_examples(all_attachment_invoice_cache_alias_groups, example_limit),
        "oa_attachment_invoice_suspected_duplicate_groups": _limit_examples(all_attachment_invoice_suspected_groups, example_limit),
        "invoice_key_mismatches": _limit_examples(all_invoice_key_mismatches, example_limit),
        "invoice_blocking_key_mismatches": _limit_examples(blocking_invoice_key_mismatches, example_limit),
        "invoice_weak_key_mismatches": _limit_examples(weak_invoice_key_mismatches, example_limit),
        "bank_key_mismatches": _limit_examples(all_bank_key_mismatches, example_limit),
        "missing_canonical_invoices": _limit_examples(all_missing_canonical_invoices, example_limit),
        "missing_canonical_bank_transactions": _limit_examples(all_missing_canonical_bank_transactions, example_limit),
        "missing_canonical_etc_invoices": _limit_examples(all_missing_canonical_etc_invoices, example_limit),
        "missing_canonical_oa_attachment_invoices": _limit_examples(all_missing_canonical_attachment_invoices, example_limit),
        "workbench_identity_audit": workbench_audit,
    }


def _audit_workbench_object_identity(connection: Any, *, scope_key: str, example_limit: int) -> dict[str, Any]:
    if not _table_exists(connection, "read_model.workbench_group_rows"):
        return {"summary": {"status": "missing"}}
    normalized_scope = str(scope_key or "all").strip() or "all"
    scope_clause = "" if normalized_scope == "all" else "and gen.scope_key = %s"
    params = () if normalized_scope == "all" else (normalized_scope,)
    try:
        cross_zone_duplicates = connection.fetch_all(
            f"""
            with active_generations as (
                select tenant_id, scope_key, generation_id
                from read_model.workbench_generations gen
                where gen.tenant_id = 'default'
                  and gen.status = 'active'
                  {scope_clause}
            ),
            duplicate_rows as (
                select
                    gr.scope_key,
                    case
                        when gr.pane = 'invoice'
                         and gr.object_identity_kind in ('digital_invoice_no', 'invoice_code_no')
                            then 'invoice'
                        when gr.pane = 'bank'
                         and gr.object_identity_kind = 'business_fields'
                            then 'bank'
                        else null
                    end as object_kind,
                    gr.object_identity_key,
                    gr.object_identity_kind,
                    array_agg(distinct gr.zone order by gr.zone) as zones,
                    array_agg(distinct gr.row_id order by gr.row_id) as row_ids,
                    array_agg(distinct gr.source_kind order by gr.source_kind) as source_kinds
                from read_model.workbench_group_rows gr
                join active_generations gen
                  on gen.generation_id = gr.generation_id
                 and gen.scope_key = gr.scope_key
                where gr.row_role <> 'summary'
                  and gr.object_identity_key is not null
                  and gr.zone in ('paired', 'open')
                group by gr.scope_key, gr.pane, gr.object_identity_key, gr.object_identity_kind
                having bool_or(gr.zone = 'paired') and bool_or(gr.zone = 'open')
            )
            select duplicate_rows.*, count(*) over ()::bigint as total_count
            from duplicate_rows
            where object_kind is not null
            order by scope_key, object_kind, object_identity_key
            limit %s
            """,
            (*params, example_limit),
        )
    except Exception as exc:  # pragma: no cover - depends on pre-migration production databases
        return {"summary": {"status": "unavailable", "error": str(exc)}}

    open_visible_owner_duplicates = connection.fetch_all(
        f"""
        with active_generations as (
            select tenant_id, scope_key, generation_id
            from read_model.workbench_generations gen
            where gen.tenant_id = 'default'
              and gen.status = 'active'
              {scope_clause}
        ),
        visible_owner_claims as (
            select
                gr.scope_key,
                gr.pane as object_kind,
                'row_id' as claim_kind,
                gr.row_id as claim_key,
                gr.zone,
                gr.group_id,
                gr.row_id,
                gr.source_kind
            from read_model.workbench_group_rows gr
            join active_generations gen
              on gen.generation_id = gr.generation_id
             and gen.scope_key = gr.scope_key
            where gr.row_role <> 'summary'
              and gr.zone = 'open'
              and gr.row_id is not null
            union all
            select
                gr.scope_key,
                'invoice' as object_kind,
                gr.object_identity_kind as claim_kind,
                gr.object_identity_key as claim_key,
                gr.zone,
                gr.group_id,
                gr.row_id,
                gr.source_kind
            from read_model.workbench_group_rows gr
            join active_generations gen
              on gen.generation_id = gr.generation_id
             and gen.scope_key = gr.scope_key
            where gr.row_role <> 'summary'
              and gr.zone = 'open'
              and gr.pane = 'invoice'
              and gr.object_identity_kind in ('digital_invoice_no', 'invoice_code_no')
              and gr.object_identity_key is not null
        ),
        duplicate_rows as (
            select
                scope_key,
                object_kind,
                claim_kind,
                claim_key,
                array_agg(distinct zone order by zone) as zones,
                array_agg(distinct group_id order by group_id) as group_ids,
                array_agg(distinct row_id order by row_id) as row_ids,
                array_agg(distinct source_kind order by source_kind) as source_kinds
            from visible_owner_claims
            group by scope_key, object_kind, claim_kind, claim_key
            having count(distinct group_id) > 1
        )
        select duplicate_rows.*, count(*) over ()::bigint as total_count
        from duplicate_rows
        order by scope_key, object_kind, claim_kind, claim_key
        limit %s
        """,
        (*params, example_limit),
    )

    oa_alias_groups = []
    if _table_exists(connection, "app.oa_applications"):
        oa_scope_clause = "" if normalized_scope == "all" else "and date_trunc('month', application_date)::date = %s::date"
        oa_params = () if normalized_scope == "all" else (normalized_scope + "-01",)
        oa_alias_groups = connection.fetch_all(
            f"""
            select form_id, array_agg(distinct row_id order by row_id) as row_ids, count(distinct row_id)::bigint as row_count
            from app.oa_applications
            where coalesce(form_id, '') <> ''
              {oa_scope_clause}
            group by form_id
            having count(distinct row_id) > 1
            order by form_id
            limit %s
            """,
            (*oa_params, example_limit),
        )

    orphan_relation_groups = []
    if _table_exists(connection, "app.workbench_pair_relations"):
        relation_scope_clause = "" if normalized_scope == "all" else "and pr.month_scope = %s::date"
        relation_params = () if normalized_scope == "all" else (normalized_scope + "-01",)
        orphan_relation_groups = connection.fetch_all(
            f"""
            with relation_rows as (
                select pr.case_id, unnest(pr.row_ids) as row_id
                from app.workbench_pair_relations pr
                where pr.status = 'active'
                  {relation_scope_clause}
            ),
            available_objects as (
                select coalesce(legacy_mongo_id, id::text) as row_id from app.bank_transactions where status <> 'deleted'
                union
                select coalesce(legacy_mongo_id, id::text) as row_id from app.invoices where status <> 'deleted'
                union
                select row_id from app.oa_applications
                union
                select r.row_id
                from read_model.workbench_rows r
                join read_model.workbench_generations gen
                  on gen.generation_id = r.generation_id
                 and gen.scope_key = r.scope_key
                 and gen.status = 'active'
                 and gen.tenant_id = 'default'
            )
            select rr.case_id, array_agg(rr.row_id order by rr.row_id) as missing_row_ids
            from relation_rows rr
            left join available_objects obj on obj.row_id = rr.row_id
            where obj.row_id is null
            group by rr.case_id
            order by rr.case_id
            limit %s
            """,
            (*relation_params, example_limit),
        )

    return {
        "summary": {
            "status": "available",
            "scope_key": normalized_scope,
            "cross_zone_identity_duplicate_group_count": _workbench_audit_total_count(cross_zone_duplicates),
            "open_visible_owner_duplicate_group_count": _workbench_audit_total_count(open_visible_owner_duplicates),
            "oa_alias_group_count": len(oa_alias_groups),
            "orphan_relation_group_count": len(orphan_relation_groups),
        },
        "cross_zone_identity_duplicates": cross_zone_duplicates,
        "open_visible_owner_duplicates": open_visible_owner_duplicates,
        "oa_alias_groups": oa_alias_groups,
        "orphan_relation_groups": orphan_relation_groups,
    }


def _workbench_audit_total_count(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    first = rows[0]
    try:
        return int(first.get("total_count") or len(rows))
    except (TypeError, ValueError):
        return len(rows)


def _invoice_identity_payload(policy: FinancialObjectIdentityPolicy, row: dict[str, Any]) -> dict[str, Any]:
    invoice = Invoice(
        id=str(row.get("legacy_id") or row.get("id")),
        invoice_type=InvoiceType(str(row.get("invoice_type") or InvoiceType.INPUT.value)),
        invoice_no=str(row.get("invoice_no") or ""),
        invoice_code=row.get("invoice_code"),
        digital_invoice_no=row.get("digital_invoice_no"),
        counterparty=Counterparty(id="", name=str(row.get("counterparty_name") or ""), normalized_name="", counterparty_type="unknown"),
        amount=row.get("amount") or 0,
        signed_amount=row.get("signed_amount") or row.get("amount") or 0,
        source_unique_key=row.get("source_unique_key"),
        data_fingerprint=row.get("data_fingerprint"),
        invoice_date=str(row.get("invoice_date")) if row.get("invoice_date") is not None else None,
        seller_tax_no=row.get("seller_tax_no"),
        seller_name=row.get("seller_name"),
        buyer_tax_no=row.get("buyer_tax_no"),
        buyer_name=row.get("buyer_name"),
        total_with_tax=row.get("total_with_tax"),
    )
    identity = policy.identify_invoice(invoice)
    return {
        "object_id": invoice.id,
        "object_type": "invoice",
        "stored_source_unique_key": row.get("source_unique_key"),
        "stored_data_fingerprint": row.get("data_fingerprint"),
        "etc_invoice_id": row.get("etc_invoice_id"),
        "policy_canonical_key": identity.canonical_key,
        "policy_canonical_key_kind": identity.canonical_key_kind,
        "policy_suspected_key": identity.suspected_key,
        "missing_fields": list(identity.missing_fields),
    }


def _bank_identity_payload(policy: FinancialObjectIdentityPolicy, row: dict[str, Any]) -> dict[str, Any]:
    transaction = BankTransaction(
        id=str(row.get("legacy_id") or row.get("id")),
        account_no=str(row.get("account_no") or ""),
        txn_direction=TransactionDirection(str(row.get("txn_direction") or TransactionDirection.OUTFLOW.value)),
        counterparty_name_raw=str(row.get("counterparty_name_raw") or ""),
        amount=row.get("amount") or 0,
        signed_amount=row.get("signed_amount") or row.get("amount") or 0,
        bank_serial_no=row.get("bank_serial_no"),
        source_unique_key=row.get("source_unique_key"),
        data_fingerprint=row.get("data_fingerprint"),
        txn_date=str(row.get("txn_date")) if row.get("txn_date") is not None else None,
        trade_time=str(row.get("trade_time"))[:19] if row.get("trade_time") is not None else None,
        pay_receive_time=str(row.get("pay_receive_time"))[:19] if row.get("pay_receive_time") is not None else None,
        account_name=row.get("account_name"),
    )
    identity = policy.identify_bank_transaction(transaction)
    return {
        "object_id": transaction.id,
        "object_type": "bank_transaction",
        "stored_source_unique_key": row.get("source_unique_key"),
        "stored_data_fingerprint": row.get("data_fingerprint"),
        "policy_canonical_key": identity.canonical_key,
        "policy_canonical_key_kind": identity.canonical_key_kind,
        "missing_fields": list(identity.missing_fields),
    }


def _etc_identity_payload(policy: FinancialObjectIdentityPolicy, row: dict[str, Any]) -> dict[str, Any]:
    identity = policy.identify_etc_invoice_mapping(
        {
            "digital_invoice_no": row.get("invoice_no"),
            "invoice_code": row.get("invoice_code"),
            "invoice_no": row.get("invoice_no"),
            "invoice_date": str(row.get("invoice_date")) if row.get("invoice_date") is not None else None,
            "seller_name": row.get("seller_name"),
            "buyer_name": row.get("buyer_name"),
            "amount": row.get("amount"),
            "total_with_tax": row.get("total_with_tax"),
        },
        source_row_id=str(row.get("legacy_id") or row.get("id")),
    )
    return {
        "object_id": str(row.get("legacy_id") or row.get("id")),
        "object_type": "etc_invoice",
        "etc_invoice_id": row.get("etc_invoice_id"),
        "invoice_no": row.get("invoice_no"),
        "policy_canonical_key": identity.canonical_key,
        "policy_canonical_key_kind": identity.canonical_key_kind,
        "policy_suspected_key": identity.suspected_key,
        "missing_fields": list(identity.missing_fields),
    }


def _oa_attachment_invoice_identity_payloads(
    policy: FinancialObjectIdentityPolicy,
    cache_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for row in cache_rows:
        source_attachment_key = str(row.get("source_attachment_key") or "").strip()
        invoices = row.get("invoices") if isinstance(row.get("invoices"), list) else []
        evidences = row.get("evidences") if isinstance(row.get("evidences"), list) else []
        invoice_evidences = [evidence for evidence in evidences if policy.is_oa_attachment_invoice_evidence(evidence)]
        seen_logical_identities: set[str] = set()
        for index, invoice in enumerate([*invoices, *invoice_evidences]):
            if not isinstance(invoice, dict):
                continue
            identity = policy.identify_oa_attachment_invoice(
                {
                    **invoice,
                    "source_attachment_key": invoice.get("source_attachment_key") or source_attachment_key,
                },
                source_row_id=f"{source_attachment_key}:{index}",
            )
            logical_identity = identity.canonical_key or identity.suspected_key or f"{source_attachment_key}:{index}"
            if logical_identity in seen_logical_identities:
                continue
            seen_logical_identities.add(logical_identity)
            payloads.append(
                {
                    "object_id": f"{source_attachment_key}:{index}",
                    "object_type": "oa_attachment_invoice",
                    "source_attachment_key": source_attachment_key,
                    "policy_canonical_key": identity.canonical_key,
                    "policy_canonical_key_kind": identity.canonical_key_kind,
                    "policy_suspected_key": identity.suspected_key,
                    "stable_identity": identity.audit_fields.get("stable_identity"),
                    "candidate_identity": identity.audit_fields.get("candidate_identity"),
                    "missing_fields": list(identity.missing_fields),
                }
            )
    return payloads


def _fetch_oa_attachment_invoice_context(connection: Any) -> dict[str, Any]:
    active_aliases = _fetch_oa_source_aliases(connection)
    sources_scan = _fetch_rows_if_table_exists(
        connection,
        "app.oa_attachment_invoice_cache_sources",
        """
        select source.cache_source_attachment_key, source.source_attachment_key, source.source_kind,
               attachment.oa_application_id::text as oa_application_id,
               attachment.row_id as oa_row_id,
               attachment.oa_source_id as attachment_oa_source_id,
               app.oa_source_id as oa_source_id,
               app.applicant,
               app.application_date,
               app.project_name,
               app.amount
        from app.oa_attachment_invoice_cache_sources source
        left join app.oa_attachments attachment
          on attachment.source_attachment_key = source.source_attachment_key
        left join app.oa_applications app
          on app.id = attachment.oa_application_id
        order by source.cache_source_attachment_key, source.source_attachment_key, source.source_kind
        """,
    )
    attachment_scan = _fetch_rows_if_table_exists(
        connection,
        "app.oa_attachments",
        """
        select attachment.source_attachment_key,
               attachment.source_attachment_key as cache_source_attachment_key,
               'direct_attachment'::text as source_kind,
               attachment.oa_application_id::text as oa_application_id,
               attachment.row_id as oa_row_id,
               attachment.oa_source_id as attachment_oa_source_id,
               app.oa_source_id as oa_source_id,
               app.applicant,
               app.application_date,
               app.project_name,
               app.amount
        from app.oa_attachments attachment
        left join app.oa_applications app
          on app.id = attachment.oa_application_id
        order by attachment.source_attachment_key
        """,
    )
    by_cache_key: dict[str, list[dict[str, Any]]] = {}
    for row in [*sources_scan["rows"], *attachment_scan["rows"]]:
        cache_key = str(row.get("cache_source_attachment_key") or "").strip()
        if not cache_key:
            continue
        row = dict(row)
        row["canonical_oa_row_id"] = _canonical_oa_row_id(row, active_aliases)
        by_cache_key.setdefault(cache_key, []).append(dict(row))
    return {
        "source_table_status": sources_scan["status"],
        "attachment_table_status": attachment_scan["status"],
        "alias_table_status": active_aliases["status"],
        "active_alias_count": len(active_aliases["aliases"]),
        "by_cache_key": by_cache_key,
    }


def _fetch_oa_source_aliases(connection: Any) -> dict[str, Any]:
    scan = _fetch_rows_if_table_exists(
        connection,
        "app.oa_source_aliases",
        """
        select alias_row_id, canonical_row_id
        from app.oa_source_aliases
        where status = 'active'
        order by alias_row_id
        """,
    )
    aliases = {
        str(row.get("alias_row_id") or "").strip(): str(row.get("canonical_row_id") or "").strip()
        for row in scan["rows"]
        if str(row.get("alias_row_id") or "").strip() and str(row.get("canonical_row_id") or "").strip()
    }
    return {"status": scan["status"], "aliases": aliases, "canonical_ids": set(aliases.values())}


def _canonical_oa_row_id(row: dict[str, Any], active_aliases: dict[str, Any]) -> str:
    aliases = active_aliases.get("aliases")
    if not isinstance(aliases, dict):
        aliases = {}
    canonical_ids = active_aliases.get("canonical_ids")
    if not isinstance(canonical_ids, set):
        canonical_ids = set()
    row_id = str(row.get("oa_row_id") or "").strip()
    source_id = str(row.get("oa_source_id") or row.get("attachment_oa_source_id") or "").strip()
    for value in (row_id, source_id):
        canonical = str(aliases.get(value) or "").strip()
        if canonical:
            return canonical
        if value in canonical_ids:
            return value
    return ""


def _classify_oa_attachment_invoice_duplicate_groups(
    groups: list[dict[str, Any]],
    *,
    attachment_context: dict[str, Any],
) -> list[dict[str, Any]]:
    by_cache_key = attachment_context.get("by_cache_key")
    if not isinstance(by_cache_key, dict):
        by_cache_key = {}
    classified: list[dict[str, Any]] = []
    for group in groups:
        oa_by_id: dict[str, dict[str, Any]] = {}
        actual_attachment_keys: set[str] = set()
        cache_keys: set[str] = set()
        for row in group.get("rows", []):
            cache_key = str(row.get("source_attachment_key") or "").strip()
            if not cache_key:
                continue
            cache_keys.add(cache_key)
            for context in by_cache_key.get(cache_key, []):
                source_attachment_key = str(context.get("source_attachment_key") or "").strip()
                if source_attachment_key:
                    actual_attachment_keys.add(source_attachment_key)
                oa_id = str(
                    context.get("canonical_oa_row_id")
                    or context.get("oa_application_id")
                    or context.get("oa_row_id")
                    or context.get("oa_source_id")
                    or ""
                ).strip()
                if oa_id:
                    oa_by_id.setdefault(
                        oa_id,
                        {
                            "oa_application_id": context.get("oa_application_id"),
                            "oa_source_id": context.get("oa_source_id") or context.get("attachment_oa_source_id"),
                            "oa_row_id": context.get("oa_row_id"),
                            "applicant": context.get("applicant"),
                            "application_date": str(context.get("application_date")) if context.get("application_date") is not None else None,
                            "project_name": context.get("project_name"),
                            "amount": str(context.get("amount")) if context.get("amount") is not None else None,
                        },
                    )
        if len(oa_by_id) > 1:
            classification = "cross_oa"
        elif len(actual_attachment_keys) > 1:
            classification = "same_oa_multiple_actual_attachments"
        elif len(actual_attachment_keys) == 1:
            classification = "same_actual_attachment"
        elif len(cache_keys) == 1:
            classification = "same_cache_entry"
        else:
            classification = "unmapped"
        classified.append(
            {
                **group,
                "classification": classification,
                "distinct_cache_key_count": len(cache_keys),
                "distinct_actual_attachment_count": len(actual_attachment_keys),
                "distinct_oa_count": len(oa_by_id),
                "oa_context": list(oa_by_id.values()),
            }
        )
    return classified


def _classification_counts(groups: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for group in groups:
        classification = str(group.get("classification") or "unknown")
        counts[classification] = counts.get(classification, 0) + 1
    return dict(sorted(counts.items()))


def _duplicate_groups(items: list[dict[str, Any]], *, key_name: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        key = str(item.get(key_name) or "").strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(item)
    duplicates = [
        {"identity_key": key, "rows": rows}
        for key, rows in grouped.items()
        if len(rows) > 1
    ]
    duplicates.sort(key=lambda item: (str(item["identity_key"]), len(item["rows"])))
    return duplicates


def _strong_invoice_duplicate_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        group
        for group in groups
        if any(
            _is_strong_invoice_identity_kind(row.get("policy_canonical_key_kind"))
            for row in list(group.get("rows") or [])
        )
    ]


def _is_strong_invoice_identity_kind(value: Any) -> bool:
    return str(value or "").strip() in STRONG_INVOICE_IDENTITY_KINDS


def _limit_examples(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return items[:limit]


def _fetch_rows_if_table_exists(connection: Any, table_name: str, sql: str) -> dict[str, Any]:
    if not _table_exists(connection, table_name):
        return {"status": "missing", "rows": []}
    return {"status": "available", "rows": connection.fetch_all(sql)}


def _table_exists(connection: Any, table_name: str) -> bool:
    row = connection.fetch_one("select to_regclass(%s) as table_name", (table_name,))
    return bool(row and row.get("table_name"))


if __name__ == "__main__":
    raise SystemExit(main())
