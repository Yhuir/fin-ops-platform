from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Literal

from fin_ops_platform.services.postgres_repositories.common import row_payload, text
from fin_ops_platform.services.postgres_repositories.oa_projection import COMPLETED_WORKFLOW_STATUS_SQL
from fin_ops_platform.services.oa_attachment_invoice_linking import (
    OA_SOURCE_ALIAS_FIELD_NAMES,
    oa_row_source_alias_map,
)
from fin_ops_platform.services.workbench_free_matching_engine import (
    ActiveFormalRelationAnchor,
    FormalRelationFact,
    FormalRelationFactBatch,
    FormalRelationReference,
    canonical_member_key,
    relation_fingerprint,
)
from fin_ops_platform.services.workbench_etc_batch_link import relation_external_etc_batch_ids
from fin_ops_platform.services.workbench_invoice_direction import invoice_workbench_direction_from_row
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id
from fin_ops_platform.services.workbench_text_normalization import normalize_match_text


_MATCHABLE_DIRECTIONS = {"expenditure", "income"}
_WEAK_SUBJECT_VALUES = frozenset(
    {
        normalize_match_text("云南溯源科技"),
        normalize_match_text("云南溯源科技有限公司"),
        normalize_match_text("供应商"),
        normalize_match_text("客户"),
        normalize_match_text("科技"),
        normalize_match_text("有限公司"),
    }
)
_WITHDRAW_EVENTS = frozenset(
    {
        "cancel_active_relation",
        "cancel_link",
        "cancel_relation",
        "withdraw_link",
        "withdraw_relation",
    }
)
_SINGLE_MEMBER_CLAIM_RELATION_MODES = frozenset({"bank_flow_rule_batch", "no_oa_bank_batch"})
_OA_OWNED_SOURCE_ALIASES_SQL = """
array(
    select distinct source_alias.parent_oa_id
    from (
        select split_part(nullif(item.normalized_payload->>'source_expense_item_id', ''), ':item:', 1)
                   as parent_oa_id
        from app.oa_application_items item
        where item.oa_application_id = oa.id
        union all
        select split_part(nullif(attachment.normalized_payload->>'source_expense_item_id', ''), ':item:', 1)
        from app.oa_attachments attachment
        where attachment.oa_application_id = oa.id
        union all
        select split_part(nullif(attachment.normalized_payload->>'derived_from_oa_id', ''), ':item:', 1)
        from app.oa_attachments attachment
        where attachment.oa_application_id = oa.id
        union all
        select split_part(nullif(attachment.normalized_payload->>'source_oa_id', ''), ':item:', 1)
        from app.oa_attachments attachment
        where attachment.oa_application_id = oa.id
    ) source_alias
    where nullif(source_alias.parent_oa_id, '') is not null
)
"""


class PostgresWorkbenchFormalRelationFactRepository:
    """The only SQL owner for deterministic Workbench matching inputs."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_batch(
        self,
        scope_months: list[str],
        *,
        source_versions: dict[str, object] | None = None,
    ) -> FormalRelationFactBatch:
        normalized_scopes = _normalize_scope_months(scope_months)
        start_date, end_date = _composite_window(normalized_scopes)
        oa_rows = self._connection.fetch_all(
            f"""
            select
                oa.row_id as canonical_object_identity,
                oa.row_id,
                oa.amount,
                oa.currency,
                oa.application_date as fact_date,
                oa.workflow_no,
                oa.project_id,
                oa.project_name,
                oa.applicant,
                oa.status,
                oa.workflow_status,
                oa.normalized_payload,
                {_OA_OWNED_SOURCE_ALIASES_SQL} as source_aliases,
                greatest(oa.updated_at, oa.synced_at) as source_version
            from app.oa_applications oa
            where coalesce(oa.application_date, oa.scope_month) between %s::date and %s::date
              and oa.status <> 'deleted'
              and """
            + COMPLETED_WORKFLOW_STATUS_SQL
            + """
            order by oa.row_id
            """,
            (start_date, end_date),
        )
        bank_rows = self._connection.fetch_all(
            """
            select
                coalesce(legacy_mongo_id, id::text) as canonical_object_identity,
                coalesce(legacy_mongo_id, id::text) as row_id,
                amount,
                signed_amount,
                coalesce(currency, 'CNY') as currency,
                coalesce(txn_date, trade_time::date, pay_receive_time::date) as fact_date,
                txn_direction,
                counterparty_name_raw,
                normalized_counterparty_name,
                project_id,
                bank_serial_no,
                source_unique_key,
                summary,
                remark,
                bank_text_fields,
                raw_payload,
                updated_at as source_version
            from app.bank_transactions
            where coalesce(txn_date, trade_time::date, pay_receive_time::date) between %s::date and %s::date
              and status <> 'deleted'
            order by coalesce(legacy_mongo_id, id::text)
            """,
            (start_date, end_date),
        )
        invoice_rows = self._connection.fetch_all(
            """
            select
                coalesce(legacy_mongo_id, id::text) as canonical_object_identity,
                coalesce(legacy_mongo_id, id::text) as row_id,
                invoice_type,
                invoice_no,
                invoice_code,
                digital_invoice_no,
                invoice_date as fact_date,
                amount,
                signed_amount,
                tax_rate,
                tax_amount,
                total_with_tax,
                currency,
                counterparty_name,
                seller_name,
                seller_tax_no,
                buyer_name,
                buyer_tax_no,
                oa_form_id,
                source_unique_key,
                source_links,
                raw_payload,
                updated_at as source_version
            from app.invoices
            where invoice_date between %s::date and %s::date
              and status <> 'deleted'
              and coalesce(workbench_visibility, 'visible') <> 'hidden_after_etc_submission'
              and coalesce(raw_payload->'normalized_payload'->>'workbench_visibility', 'visible')
                    <> 'hidden_after_etc_submission'
              and coalesce(raw_payload->'normalized_payload'->>'etc_submission_status', '') <> 'submitted'
            order by coalesce(legacy_mongo_id, id::text)
            """,
            (start_date, end_date),
        )

        current_oa_aliases = oa_row_source_alias_map(oa_rows)
        initial_facts = _facts_from_rows(
            oa_rows=oa_rows,
            bank_rows=bank_rows,
            invoice_rows=invoice_rows,
            oa_aliases=current_oa_aliases,
        )
        target_ids = _explicit_target_ids(initial_facts)
        historical_rows = self._load_historical_targets(target_ids)
        all_oa_aliases = oa_row_source_alias_map([*oa_rows, *historical_rows["oa"]])
        facts = _merge_facts(
            _facts_from_rows(
                oa_rows=oa_rows,
                bank_rows=bank_rows,
                invoice_rows=invoice_rows,
                oa_aliases=all_oa_aliases,
            ),
            _facts_from_rows(
                oa_rows=historical_rows["oa"],
                bank_rows=historical_rows["bank"],
                invoice_rows=historical_rows["invoice"],
                oa_aliases=all_oa_aliases,
            ),
        )

        active_rows = self._connection.fetch_all(
            """
            select case_id, relation_mode, row_ids, row_types
            from app.workbench_pair_relations
            where status = 'active'
            order by case_id
            """
        )
        history_rows = self._connection.fetch_all(
            """
            select event_type, actor_id, before_payload
            from app.workbench_pair_relation_history
            where event_type = any(%s::text[])
              and nullif(actor_id, '') is not null
              and actor_id not like 'system:%%'
              and actor_id not like 'migration:%%'
            order by occurred_at, case_id
            """,
            (sorted(_WITHDRAW_EVENTS),),
        )
        single_member_claims = {
            claim
            for row in active_rows
            if (claim := _single_member_claim(row)) is not None
        }
        facts = tuple(fact for fact in facts if fact.member_key not in single_member_claims)
        active_relations = tuple(
            _active_anchor(row)
            for row in active_rows
            if _single_member_claim(row) is None
        )
        withdrawals = frozenset(
            fingerprint
            for row in history_rows
            for fingerprint in _withdrawal_fingerprints(row)
        )
        versions = tuple(
            sorted(
                (str(key).strip(), str(value).strip())
                for key, value in dict(source_versions or {}).items()
                if str(key).strip()
            )
        )
        return FormalRelationFactBatch(
            facts=facts,
            active_relations=active_relations,
            withdrawal_fingerprints=withdrawals,
            affected_scopes=tuple(sorted({*normalized_scopes, "all"})),
            source_versions=versions,
        )

    def load_bank_rows_by_ids(self, transaction_ids: list[str]) -> list[dict[str, Any]]:
        normalized_ids = sorted(
            {
                str(transaction_id or "").strip()
                for transaction_id in list(transaction_ids or [])
                if str(transaction_id or "").strip()
            }
        )
        if not normalized_ids:
            return []
        return self._connection.fetch_all(
            """
            select
                coalesce(legacy_mongo_id, id::text) as id,
                amount,
                signed_amount,
                txn_direction,
                counterparty_name_raw,
                normalized_counterparty_name,
                summary,
                remark,
                bank_text_fields,
                raw_payload
            from app.bank_transactions
            where status <> 'deleted'
              and coalesce(legacy_mongo_id, id::text) = any(%s::text[])
            order by coalesce(legacy_mongo_id, id::text)
            """,
            (normalized_ids,),
        )

    def load_etc_batch_link_candidates(self, scope_months: list[str]) -> list[dict[str, Any]]:
        """Load exact OA -> submitted ETC batch references with one bounded query."""
        normalized_scopes = _normalize_scope_months(scope_months)
        start_date, end_date = _composite_window(normalized_scopes)
        rows = self._connection.fetch_all(
            """
            with submitted_batches as (
                select
                    batch.business_batch_id,
                    batch.scope_month,
                    batch.invoice_count,
                    batch.total_amount,
                    coalesce(
                        nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                        nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                        nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                        nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                        batch.business_batch_id
                    ) as external_etc_batch_id,
                    coalesce(
                        nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                        nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', '')
                    ) as submission_batch_id,
                    count(*) over (
                        partition by coalesce(
                            nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                            nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                            nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                            nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                            batch.business_batch_id
                        )
                    ) as external_batch_owner_count
                from app.etc_business_batches batch
                where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                  and batch.scope_month between %s::date and %s::date
            )
            select
                oa.row_id as oa_row_id,
                submitted.business_batch_id,
                submitted.external_etc_batch_id,
                submitted.submission_batch_id,
                submitted.invoice_count,
                submitted.total_amount,
                submitted.external_batch_owner_count,
                to_char(coalesce(oa.scope_month, date_trunc('month', oa.application_date)::date), 'YYYY-MM') as oa_scope_month,
                to_char(submitted.scope_month, 'YYYY-MM') as batch_scope_month
            from app.oa_applications oa
            join submitted_batches submitted
              on submitted.external_etc_batch_id = nullif(oa.normalized_payload->>'etc_batch_id', '')
            where coalesce(oa.application_date, oa.scope_month) between %s::date and %s::date
              and oa.status <> 'deleted'
              and """
            + COMPLETED_WORKFLOW_STATUS_SQL
            + """
            order by submitted.external_etc_batch_id, oa.row_id
            """,
            (start_date, end_date, start_date, end_date),
        )
        return [
            {
                "oa_row_id": text(row.get("oa_row_id")) or "",
                "business_batch_id": text(row.get("business_batch_id")) or "",
                "external_etc_batch_id": text(row.get("external_etc_batch_id")) or "",
                "submission_batch_id": text(row.get("submission_batch_id")) or "",
                "invoice_count": int(row.get("invoice_count") or 0),
                "total_amount": str(row.get("total_amount") or "0"),
                "external_batch_owner_count": int(row.get("external_batch_owner_count") or 0),
                "scope_keys": sorted(
                    {
                        *(
                            value
                            for value in (
                                text(row.get("oa_scope_month")),
                                text(row.get("batch_scope_month")),
                            )
                            if value
                        ),
                    }
                ),
            }
            for row in rows
            if text(row.get("oa_row_id"))
            and text(row.get("business_batch_id"))
            and text(row.get("external_etc_batch_id"))
        ]

    def validate_etc_batch_links(self, links: list[dict[str, Any]]) -> dict[str, Any]:
        """Revalidate and lock exact canonical ETC ownership inside the write UoW."""
        candidates = [dict(link) for link in list(links or []) if isinstance(link, dict)]
        external_ids = sorted(
            {
                external_id
                for link in candidates
                if (external_id := text(link.get("external_etc_batch_id")))
            }
        )
        if not candidates or len(external_ids) != len(candidates):
            return {"valid": False, "issues": [{"code": "invalid_candidate_set"}]}

        self._connection.fetch_all(
            """
            select pg_advisory_xact_lock(
                hashtextextended('workbench_etc_batch_owner:' || item.external_batch_id, 0)
            )
            from unnest(%s::text[]) item(external_batch_id)
            order by item.external_batch_id
            """,
            (external_ids,),
        )
        canonical_rows = self._connection.fetch_all(
            """
            select
                oa.row_id as oa_row_id,
                batch.business_batch_id,
                batch.invoice_count,
                batch.total_amount,
                coalesce(
                    nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                    batch.business_batch_id
                ) as external_etc_batch_id
            from app.etc_business_batches batch
            join app.oa_applications oa
              on oa.normalized_payload->>'etc_batch_id' = coalesce(
                    nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                    batch.business_batch_id
                 )
            where coalesce(
                    nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                    batch.business_batch_id
                  ) = any(%s::text[])
              and batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
              and oa.status <> 'deleted'
              and """
            + COMPLETED_WORKFLOW_STATUS_SQL
            + """
            order by external_etc_batch_id, batch.business_batch_id, oa.row_id
            for update of batch, oa
            """,
            (external_ids,),
        )
        active_rows = self._connection.fetch_all(
            """
            select case_id, amount_check, special_metadata
            from app.workbench_pair_relations
            where status = 'active'
              and (
                    nullif(amount_check->>'external_etc_batch_id', '') = any(%s::text[])
                 or nullif(amount_check->>'etc_batch_id', '') = any(%s::text[])
                 or nullif(special_metadata->>'external_etc_batch_id', '') = any(%s::text[])
                 or nullif(special_metadata->>'etc_batch_id', '') = any(%s::text[])
                 or nullif(special_metadata->'etc_batch_link'->>'external_etc_batch_id', '') = any(%s::text[])
                 or nullif(special_metadata->'etc_batch_link'->>'etc_batch_id', '') = any(%s::text[])
                 or nullif(special_metadata->'historical_etc_business_batch_migration'->>'external_etc_batch_id', '') = any(%s::text[])
                 or nullif(special_metadata->'historical_etc_business_batch_migration'->>'etc_batch_id', '') = any(%s::text[])
              )
            order by case_id
            for update
            """,
            tuple(external_ids for _ in range(8)),
        )

        rows_by_external: dict[str, list[dict[str, Any]]] = {}
        for row in canonical_rows:
            rows_by_external.setdefault(text(row.get("external_etc_batch_id")) or "", []).append(row)
        owners_by_external: dict[str, set[str]] = {}
        for relation in active_rows:
            for external_id in relation_external_etc_batch_ids(dict(relation)):
                owners_by_external.setdefault(external_id, set()).add(text(relation.get("case_id")) or "")

        issues: list[dict[str, Any]] = []
        for candidate in candidates:
            external_id = text(candidate.get("external_etc_batch_id")) or ""
            matching_rows = rows_by_external.get(external_id, [])
            batch_owners = {text(row.get("business_batch_id")) or "" for row in matching_rows}
            exact_rows = [
                row
                for row in matching_rows
                if text(row.get("business_batch_id")) == text(candidate.get("business_batch_id"))
                and text(row.get("oa_row_id")) == text(candidate.get("oa_row_id"))
            ]
            if len(batch_owners) != 1 or len(matching_rows) != 1 or len(exact_rows) != 1:
                issues.append({"code": "canonical_owner_changed", "external_etc_batch_id": external_id})
                continue
            row = exact_rows[0]
            if (
                int(row.get("invoice_count") or 0) != int(candidate.get("invoice_count") or 0)
                or _decimal_value(row.get("total_amount")) != _decimal_value(candidate.get("total_amount"))
            ):
                issues.append({"code": "canonical_batch_totals_changed", "external_etc_batch_id": external_id})
            relation_owners = owners_by_external.get(external_id, set())
            expected_case_id = text(candidate.get("case_id")) or ""
            if relation_owners - {expected_case_id}:
                issues.append(
                    {
                        "code": "active_relation_owner_conflict",
                        "external_etc_batch_id": external_id,
                        "case_ids": sorted(relation_owners),
                    }
                )
        return {"valid": not issues, "issues": issues}

    def _load_historical_targets(self, target_ids: dict[str, set[str]]) -> dict[str, list[dict[str, Any]]]:
        oa_ids = sorted(target_ids["oa"])
        oa_alias_values = _oa_alias_lookup_values(oa_ids)
        bank_ids = sorted(target_ids["bank"])
        invoice_ids = sorted(target_ids["invoice"])
        oa_rows = self._connection.fetch_all(
            f"""
            select
                oa.row_id as canonical_object_identity,
                oa.row_id,
                oa.amount,
                oa.currency,
                oa.application_date as fact_date,
                oa.workflow_no,
                oa.project_id,
                oa.project_name,
                oa.applicant,
                oa.status,
                oa.workflow_status,
                oa.normalized_payload,
                {_OA_OWNED_SOURCE_ALIASES_SQL} as source_aliases,
                greatest(oa.updated_at, oa.synced_at) as source_version
            from app.oa_applications oa
            where (
                    oa.row_id = any(%s::text[])
                    or exists (
                        select 1
                        from (
                            values
                                (case when jsonb_typeof(oa.normalized_payload) = 'object'
                                      then oa.normalized_payload else '{{}}'::jsonb end),
                                (case when jsonb_typeof(oa.normalized_payload->'detail_fields') = 'object'
                                      then oa.normalized_payload->'detail_fields' else '{{}}'::jsonb end),
                                (case when jsonb_typeof(oa.normalized_payload->'summary_fields') = 'object'
                                      then oa.normalized_payload->'summary_fields' else '{{}}'::jsonb end),
                                (case when jsonb_typeof(oa.normalized_payload->'metadata') = 'object'
                                      then oa.normalized_payload->'metadata' else '{{}}'::jsonb end)
                        ) as source_containers(payload)
                        cross join lateral jsonb_each_text(source_containers.payload) as source_alias(field_name, field_value)
                        where source_alias.field_name = any(%s::text[])
                          and source_alias.field_value = any(%s::text[])
                    )
                    or {_OA_OWNED_SOURCE_ALIASES_SQL} && %s::text[]
              )
              and oa.status <> 'deleted'
              and """
            + COMPLETED_WORKFLOW_STATUS_SQL
            + """
            order by oa.row_id
            """,
            (oa_ids, list(OA_SOURCE_ALIAS_FIELD_NAMES), oa_alias_values, oa_alias_values),
        ) if oa_ids else []
        bank_rows = self._connection.fetch_all(
            """
            select
                coalesce(legacy_mongo_id, id::text) as canonical_object_identity,
                coalesce(legacy_mongo_id, id::text) as row_id,
                amount,
                signed_amount,
                coalesce(currency, 'CNY') as currency,
                coalesce(txn_date, trade_time::date, pay_receive_time::date) as fact_date,
                txn_direction,
                counterparty_name_raw,
                normalized_counterparty_name,
                project_id,
                bank_serial_no,
                source_unique_key,
                summary,
                remark,
                bank_text_fields,
                raw_payload,
                updated_at as source_version
            from app.bank_transactions
            where coalesce(legacy_mongo_id, id::text) = any(%s::text[])
              and status <> 'deleted'
            order by coalesce(legacy_mongo_id, id::text)
            """,
            (bank_ids,),
        ) if bank_ids else []
        invoice_rows = self._connection.fetch_all(
            """
            select
                coalesce(legacy_mongo_id, id::text) as canonical_object_identity,
                coalesce(legacy_mongo_id, id::text) as row_id,
                invoice_type,
                invoice_no,
                invoice_code,
                digital_invoice_no,
                invoice_date as fact_date,
                amount,
                signed_amount,
                tax_rate,
                tax_amount,
                total_with_tax,
                currency,
                counterparty_name,
                seller_name,
                seller_tax_no,
                buyer_name,
                buyer_tax_no,
                oa_form_id,
                source_unique_key,
                source_links,
                raw_payload,
                updated_at as source_version
            from app.invoices
            where coalesce(legacy_mongo_id, id::text) = any(%s::text[])
              and status <> 'deleted'
              and coalesce(workbench_visibility, 'visible') <> 'hidden_after_etc_submission'
            order by coalesce(legacy_mongo_id, id::text)
            """,
            (invoice_ids,),
        ) if invoice_ids else []
        return {"oa": oa_rows, "bank": bank_rows, "invoice": invoice_rows}


def _facts_from_rows(
    *,
    oa_rows: Iterable[dict[str, Any]],
    bank_rows: Iterable[dict[str, Any]],
    invoice_rows: Iterable[dict[str, Any]],
    oa_aliases: dict[str, str] | None = None,
) -> tuple[FormalRelationFact, ...]:
    facts: list[FormalRelationFact] = []
    for row in oa_rows:
        facts.append(_oa_fact(row, oa_aliases=oa_aliases))
    for row in bank_rows:
        facts.append(_bank_fact(row, oa_aliases=oa_aliases))
    for row in invoice_rows:
        facts.append(_invoice_fact(row, oa_aliases=oa_aliases))
    return tuple(facts)


def _oa_fact(
    row: dict[str, Any],
    *,
    oa_aliases: dict[str, str] | None = None,
) -> FormalRelationFact:
    payload = row_payload(row, "normalized_payload")
    payload = payload if isinstance(payload, dict) else {}
    detail = payload.get("detail_fields") if isinstance(payload.get("detail_fields"), dict) else {}
    apply_type = text(payload.get("apply_type") or payload.get("application_type") or detail.get("报销/支付")) or ""
    direction = "income" if "收" in apply_type and "付" not in apply_type else "expenditure"
    evidence = _evidence_keys(
        counterparty=payload.get("counterparty_name") or payload.get("counterparty"),
        tax_no=payload.get("counterparty_tax_no"),
        business_references=(
            row.get("workflow_no"),
            payload.get("contract_no"),
            payload.get("order_no"),
        ),
        project_references=(row.get("project_id"), payload.get("project_no")),
    )
    return FormalRelationFact(
        row_type="oa",
        canonical_object_identity=_required_identity(row),
        row_id=_required_row_id(row),
        amount_minor=_minor_units(row.get("amount")),
        currency=text(row.get("currency")) or "CNY",
        direction=direction,
        fact_date=_date_value(row.get("fact_date")),
        evidence_keys=evidence,
        references=_references_from_payload(payload, oa_aliases=oa_aliases),
        source_version=_source_version(row),
    )


def _bank_fact(
    row: dict[str, Any],
    *,
    oa_aliases: dict[str, str] | None = None,
) -> FormalRelationFact:
    direction = _bank_direction(row.get("txn_direction"), row.get("signed_amount"))
    if direction not in _MATCHABLE_DIRECTIONS:
        raise ValueError(f"Unsupported bank transaction direction for {_required_row_id(row)}.")
    payload = row_payload(row, "raw_payload")
    payload = payload if isinstance(payload, dict) else {}
    evidence = _evidence_keys(
        counterparty=row.get("normalized_counterparty_name") or row.get("counterparty_name_raw"),
        tax_no=payload.get("counterparty_tax_no"),
        business_references=(row.get("bank_serial_no"), row.get("source_unique_key")),
        project_references=(row.get("project_id"),),
        invoice_numbers=_invoice_numbers_in_bank_payload(row, payload),
    )
    return FormalRelationFact(
        row_type="bank",
        canonical_object_identity=_required_identity(row),
        row_id=_required_row_id(row),
        amount_minor=_minor_units(row.get("amount")),
        currency=text(row.get("currency")) or "CNY",
        direction=direction,
        fact_date=_date_value(row.get("fact_date")),
        evidence_keys=evidence,
        references=_references_from_payload(payload, oa_aliases=oa_aliases),
        source_version=_source_version(row),
    )


def _invoice_fact(
    row: dict[str, Any],
    *,
    oa_aliases: dict[str, str] | None = None,
) -> FormalRelationFact:
    direction = invoice_workbench_direction_from_row(row)
    if direction not in _MATCHABLE_DIRECTIONS:
        raise ValueError(f"Unsupported invoice direction for {_required_row_id(row)}.")
    payload = row_payload(row, "raw_payload")
    payload = payload if isinstance(payload, dict) else {}
    normalized = payload.get("normalized_payload") if isinstance(payload.get("normalized_payload"), dict) else payload
    amount = row.get("total_with_tax") if row.get("total_with_tax") is not None else row.get("amount")
    signed_amount = _decimal_value(row.get("signed_amount"))
    if signed_amount is not None and signed_amount < 0:
        amount = signed_amount
    if direction == "income":
        counterparty = row.get("buyer_name") or row.get("counterparty_name")
        tax_no = row.get("buyer_tax_no")
    else:
        counterparty = row.get("seller_name") or row.get("counterparty_name")
        tax_no = row.get("seller_tax_no")
    evidence = _evidence_keys(
        counterparty=counterparty,
        tax_no=tax_no,
        business_references=(row.get("source_unique_key"), normalized.get("contract_no"), normalized.get("order_no")),
        project_references=(normalized.get("project_no"), normalized.get("project_id")),
        invoice_numbers=(row.get("invoice_no"), row.get("digital_invoice_no")),
    )
    references = [
        *_references_from_payload(normalized, oa_aliases=oa_aliases),
        *_references_from_source_links(row.get("source_links"), oa_aliases=oa_aliases),
    ]
    reversal_key, reversal_polarity = _output_invoice_reversal_identity(row)
    return FormalRelationFact(
        row_type="invoice",
        canonical_object_identity=_required_identity(row),
        row_id=_required_row_id(row),
        amount_minor=abs(_minor_units(amount)),
        currency=text(row.get("currency")) or "CNY",
        direction=direction,
        fact_date=_date_value(row.get("fact_date")),
        evidence_keys=evidence,
        references=tuple(sorted(set(references))),
        source_version=_source_version(row),
        reversal_key=reversal_key,
        reversal_polarity=reversal_polarity,
    )


def _output_invoice_reversal_identity(
    row: dict[str, Any],
) -> tuple[tuple[str, ...] | None, Literal["blue", "red"] | None]:
    if str(row.get("invoice_type") or "").strip().lower() != "output":
        return None, None
    seller_tax_no = _normalized_identifier(row.get("seller_tax_no"))
    buyer_tax_no = _normalized_identifier(row.get("buyer_tax_no"))
    currency = str(row.get("currency") or "CNY").strip().upper()
    tax_rate = _decimal_value(row.get("tax_rate"))
    gross = _decimal_value(row.get("total_with_tax"))
    net = _decimal_value(row.get("amount"))
    tax = _decimal_value(row.get("tax_amount"))
    if not seller_tax_no or not buyer_tax_no or tax_rate is None or gross is None or net is None or tax is None:
        return None, None
    if (
        gross == 0
        or net == 0
        or (gross > 0) != (net > 0)
        or (tax != 0 and (gross > 0) != (tax > 0))
    ):
        return None, None
    key = (
        seller_tax_no,
        buyer_tax_no,
        currency,
        str(abs(_minor_units(gross))),
        str(abs(_minor_units(net))),
        str(abs(_minor_units(tax))),
        format(abs(tax_rate).normalize(), "f"),
    )
    return key, "blue" if gross > 0 else "red"


def _normalized_identifier(value: Any) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _references_from_payload(
    payload: dict[str, Any],
    *,
    oa_aliases: dict[str, str] | None = None,
) -> tuple[FormalRelationReference, ...]:
    references: list[FormalRelationReference] = []
    for field, kind, target_type in (
        ("source_oa_row_id", "oa_source", "oa"),
        ("oa_row_id", "oa_source", "oa"),
        ("derived_from_oa_id", "attachment_source", "oa"),
        ("source_workbench_row_id", "canonical_source", "oa"),
        ("original_invoice_row_id", "original_reference", "invoice"),
        ("original_bank_row_id", "original_reference", "bank"),
    ):
        target = _canonical_target_identity(
            target_type,
            payload.get(field),
            oa_aliases=oa_aliases,
        )
        if target:
            references.append(
                FormalRelationReference(
                    kind=kind,
                    value=f"{field}:{target}",
                    target_row_type=target_type,
                    target_identity=target,
                    original=kind == "original_reference",
                )
            )
    return tuple(sorted(set(references)))


def _references_from_source_links(
    value: Any,
    *,
    oa_aliases: dict[str, str] | None = None,
) -> tuple[FormalRelationReference, ...]:
    if not isinstance(value, list):
        return ()
    references: list[FormalRelationReference] = []
    for link in value:
        if not isinstance(link, dict):
            continue
        metadata = link.get("metadata") if isinstance(link.get("metadata"), dict) else {}
        combined = {**link, **metadata}
        references.extend(_references_from_payload(combined, oa_aliases=oa_aliases))
    return tuple(sorted(set(references)))


def _evidence_keys(
    *,
    counterparty: Any = None,
    tax_no: Any = None,
    business_references: Iterable[Any] = (),
    project_references: Iterable[Any] = (),
    invoice_numbers: Iterable[Any] = (),
) -> tuple[tuple[str, str], ...]:
    evidence: set[tuple[str, str]] = set()
    normalized_counterparty = normalize_match_text(counterparty)
    if len(normalized_counterparty) >= 4 and normalized_counterparty not in _WEAK_SUBJECT_VALUES:
        evidence.add(("counterparty", normalized_counterparty))
    normalized_tax_no = normalize_match_text(tax_no)
    if len(normalized_tax_no) >= 8:
        evidence.add(("tax_no", normalized_tax_no))
    for raw_value in business_references:
        normalized = normalize_match_text(raw_value)
        if len(normalized) >= 6:
            evidence.add(("business_reference", normalized))
    for raw_value in project_references:
        normalized = normalize_match_text(raw_value)
        if len(normalized) >= 4:
            evidence.add(("project_reference", normalized))
    for raw_value in invoice_numbers:
        normalized = normalize_match_text(raw_value)
        if len(normalized) >= 8:
            evidence.add(("invoice_number", normalized))
    return tuple(sorted(evidence))


def _invoice_numbers_in_bank_payload(row: dict[str, Any], payload: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for field in ("invoice_no", "invoice_number", "digital_invoice_no"):
        value = text(payload.get(field))
        if value:
            values.append(value)
    bank_text_fields = row.get("bank_text_fields")
    if isinstance(bank_text_fields, list):
        for item in bank_text_fields:
            if isinstance(item, dict) and str(item.get("label") or "").strip() in {"发票号码", "数电发票号码"}:
                value = text(item.get("value"))
                if value:
                    values.append(value)
    return tuple(values)


def _active_anchor(row: dict[str, Any]) -> ActiveFormalRelationAnchor:
    case_id = text(row.get("case_id"))
    row_ids = [str(item).strip() for item in list(row.get("row_ids") or []) if str(item).strip()]
    row_types = [str(item).strip().lower() for item in list(row.get("row_types") or [])]
    if not case_id or len(row_ids) < 2:
        raise ValueError("Active Workbench relation requires case_id and at least two row_ids.")
    members = []
    for index, row_id in enumerate(row_ids):
        row_type = row_types[index] if index < len(row_types) and row_types[index] else row_type_for_workbench_row_id(row_id)
        members.append(canonical_member_key(row_type, row_id))
    return ActiveFormalRelationAnchor(case_id=case_id, member_keys=tuple(members))


def _single_member_claim(row: dict[str, Any]) -> tuple[str, str] | None:
    relation_mode = text(row.get("relation_mode"))
    case_id = text(row.get("case_id"))
    row_ids = [str(item).strip() for item in list(row.get("row_ids") or []) if str(item).strip()]
    if relation_mode not in _SINGLE_MEMBER_CLAIM_RELATION_MODES or not case_id or len(row_ids) != 1:
        return None
    row_types = [str(item).strip().lower() for item in list(row.get("row_types") or [])]
    row_type = row_types[0] if row_types and row_types[0] else row_type_for_workbench_row_id(row_ids[0])
    return canonical_member_key(row_type, row_ids[0])


def _withdrawal_fingerprints(row: dict[str, Any]) -> tuple[str, ...]:
    if str(row.get("event_type") or "").strip() not in _WITHDRAW_EVENTS:
        return ()
    actor_id = str(row.get("actor_id") or "").strip()
    if not actor_id or actor_id.startswith(("system:", "migration:")):
        return ()
    fingerprints: set[str] = set()
    for relation in _relation_payloads(row.get("before_payload")):
        try:
            anchor = _active_anchor(relation)
            fingerprints.add(relation_fingerprint(anchor.member_keys))
        except (TypeError, ValueError):
            continue
    return tuple(sorted(fingerprints))


def _relation_payloads(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("before_relations", "relations"):
        nested = value.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    normalized = value.get("normalized_payload")
    if isinstance(normalized, dict):
        return _relation_payloads(normalized)
    return [value] if value.get("row_ids") else []


def _explicit_target_ids(facts: Iterable[FormalRelationFact]) -> dict[str, set[str]]:
    targets = {"oa": set(), "bank": set(), "invoice": set()}
    for fact in facts:
        for reference in fact.references:
            target = reference.target_member_key
            if target is not None:
                targets[target[0]].add(target[1])
    return targets


def _merge_facts(*collections: Iterable[FormalRelationFact]) -> tuple[FormalRelationFact, ...]:
    facts_by_key: dict[tuple[str, str], FormalRelationFact] = {}
    for collection in collections:
        for fact in collection:
            existing = facts_by_key.get(fact.member_key)
            if existing is not None and existing != fact:
                raise ValueError(f"Conflicting canonical fact rows for {fact.member_key}.")
            facts_by_key[fact.member_key] = fact
    return tuple(facts_by_key.values())


def _normalize_scope_months(scope_months: list[str]) -> tuple[str, ...]:
    if not isinstance(scope_months, list):
        raise TypeError("scope_months must be a list.")
    normalized: set[str] = set()
    for raw_scope in scope_months:
        scope = str(raw_scope or "").strip()
        try:
            parsed = date.fromisoformat(f"{scope}-01")
        except ValueError as exc:
            raise ValueError("scope_months values must be YYYY-MM.") from exc
        if parsed.strftime("%Y-%m") != scope:
            raise ValueError("scope_months values must be YYYY-MM.")
        normalized.add(scope)
    if not normalized:
        raise ValueError("scope_months must include at least one month.")
    return tuple(sorted(normalized))


def _composite_window(scope_months: tuple[str, ...]) -> tuple[date, date]:
    first = date.fromisoformat(f"{scope_months[0]}-01")
    last_month = date.fromisoformat(f"{scope_months[-1]}-01")
    last = last_month.replace(day=monthrange(last_month.year, last_month.month)[1])
    return first - timedelta(days=365), last + timedelta(days=365)


def _minor_units(value: Any) -> int:
    decimal = _decimal_value(value)
    if decimal is None:
        raise ValueError("Formal relation fact amount is required and must be numeric.")
    cents = decimal * Decimal("100")
    integral = cents.to_integral_value()
    if cents != integral:
        raise ValueError("Formal relation fact amount must be exact to the currency minor unit.")
    return int(integral)


def _decimal_value(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _date_value(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError(f"Invalid canonical fact date: {value}.") from exc


def _bank_direction(value: Any, signed_amount: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"outflow", "expenditure", "debit", "支出", "付款"}:
        return "expenditure"
    if normalized in {"inflow", "income", "credit", "收入", "收款"}:
        return "income"
    signed = _decimal_value(signed_amount)
    if signed is not None:
        return "expenditure" if signed < 0 else "income"
    return ""


def _canonical_target_identity(
    row_type: str,
    value: Any,
    *,
    oa_aliases: dict[str, str] | None = None,
) -> str:
    target = str(value or "").strip()
    if not target:
        return ""
    if row_type == "oa" and ":item:" in target:
        target = target.split(":item:", 1)[0]
    if row_type == "oa" and oa_aliases:
        target = str(oa_aliases.get(target) or target).strip()
    return target


def _oa_alias_lookup_values(target_ids: Iterable[str]) -> list[str]:
    values: set[str] = set()
    for target_id in target_ids:
        value = str(target_id or "").strip()
        if not value:
            continue
        values.add(value)
        for prefix in ("oa-exp-", "oa-pay-"):
            if value.startswith(prefix) and len(value) > len(prefix):
                values.add(value[len(prefix):])
    return sorted(values)


def _required_identity(row: dict[str, Any]) -> str:
    identity = str(row.get("canonical_object_identity") or "").strip()
    if not identity:
        raise ValueError("Canonical fact identity is required.")
    return identity


def _required_row_id(row: dict[str, Any]) -> str:
    row_id = str(row.get("row_id") or "").strip()
    if not row_id:
        raise ValueError("Canonical fact row_id is required.")
    return row_id


def _source_version(row: dict[str, Any]) -> str:
    value = row.get("source_version")
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "").strip()
