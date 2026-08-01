from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
import json
from typing import Any, Callable, Iterator, Mapping

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.services.bank_details_canonical_query import (
    compile_bank_category_rule_sql,
)
from fin_ops_platform.services.pending_invoice_rules import (
    pending_invoice_effective_category_payload,
    pending_invoice_group_for_category,
    pending_invoice_tag_group_sets,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    bank_transaction_tag_dictionary_display_payload,
)
from fin_ops_platform.services.pending_invoice_relation_identity import (
    is_valid_pending_invoice_oa_row_id,
)
from fin_ops_platform.services.pending_invoice_service import (
    INVOICE_CANDIDATE_SORT_FIELDS,
    PENDING_INVOICE_EXPORT_ROW_LIMIT,
    PENDING_INVOICE_FILTER_FIELDS,
    PendingInvoiceError,
    PendingInvoiceQueryService,
)
from fin_ops_platform.services.pending_invoice_status import (
    pending_invoice_available_actions,
    pending_invoice_filter_status_codes,
    pending_invoice_status_payload,
)


PAGE_SIZE_LIMIT = 200
FILTER_OPTION_LIMIT = 50
SORT_EXPRESSIONS = {
    "trade_date": "trade_date",
    "amount": "amount",
    "counterparty_name": "counterparty_name",
    "status_code": "status_code",
    "seller_name": "seller_name",
    "invoice_total": "invoice_total",
    "oa_applicant": "oa_applicant",
    "project_name": "project_name",
}
FILTER_EXPRESSIONS = {
    "trade_date": "trade_date",
    "bank_name": "bank_name",
    "account_name": "account_name",
    "bank_account": "bank_account",
    "counterparty_name": "counterparty_name",
    "transaction_tag": "transaction_tag",
    "direction": "direction",
    "amount": "amount",
    "summary_remark": "summary_remark",
    "status_code": "status_code",
    "rule_group": "filter_group",
    "seller_name": "seller_name",
    "invoice_total": "invoice_total",
    "oa_applicant": "oa_applicant",
    "oa_application_type": "oa_application_type",
    "project_name": "project_name",
}
FILTER_FIELDS = [
    {"field": "trade_date", "label": "交易日期", "operators": ["between"]},
    {"field": "bank_name", "label": "银行", "operators": ["in", "contains"]},
    {"field": "account_name", "label": "账户", "operators": ["in", "contains"]},
    {"field": "bank_account", "label": "银行账户", "operators": ["in", "contains"]},
    {"field": "counterparty_name", "label": "对方户名", "operators": ["contains", "in"]},
    {"field": "transaction_tag", "label": "流水标签", "operators": ["contains", "in"]},
    {"field": "direction", "label": "收支", "operators": ["in"]},
    {"field": "amount", "label": "金额", "operators": ["between", "eq"]},
    {"field": "summary_remark", "label": "摘要/备注", "operators": ["contains"]},
    {"field": "status_code", "label": "发票获取状态", "operators": ["in"]},
    {"field": "rule_group", "label": "规则组", "operators": ["in"]},
    {"field": "seller_name", "label": "销方", "operators": ["contains", "in"]},
    {"field": "invoice_total", "label": "发票金额", "operators": ["between", "eq"]},
    {"field": "oa_applicant", "label": "OA申请人", "operators": ["contains", "in"]},
    {"field": "oa_application_type", "label": "OA类型", "operators": ["contains", "in"]},
    {"field": "project_name", "label": "项目", "operators": ["contains", "in"]},
]

_RULE_TEXT_FIELDS = {
    "counterparty_name",
    "counterparty_account",
    "counterparty_bank",
    "purpose_text",
    "summary_text",
    "note_text",
    "detail_text",
}


def _rule_required_fields(definitions: list[dict[str, Any]]) -> list[str]:
    fields: set[str] = set()
    for definition in definitions:
        if not isinstance(definition, dict) or str(definition.get("status") or "active") != "active":
            continue
        rules = definition.get("rules")
        if not isinstance(rules, dict):
            continue
        match_fields = {str(field) for field in list(rules.get("match_fields") or [])}
        fields.update(_RULE_TEXT_FIELDS if "all_text" in match_fields else match_fields & _RULE_TEXT_FIELDS)
        scope = definition.get("account_scope")
        if not isinstance(scope, dict) or not list(scope.get("values") or []):
            continue
        scope_field = {
            "bank_account": "account",
            "account_type": "account_type",
            "bank": "bank",
        }.get(str(scope.get("type") or ""))
        if scope_field:
            fields.add(scope_field)
    return sorted(fields)


def _normalize_sql_text(expression: str) -> str:
    return (
        "lower(regexp_replace("
        f"replace(normalize(coalesce({expression}, ''), NFKC), '帐户', '账户'), "
        "'\\s+', '', 'g'))"
    )


PAGE_QUERY_SQL = f"""
with recursive
request_config as materialized (
    select %s::jsonb as payload
),
bank_source as materialized (
    select
        b.id as canonical_id,
        coalesce(b.legacy_mongo_id, b.id::text) as row_id,
        case when b.txn_direction = 'outflow' then 'expense' else 'income' end as direction,
        b.account_no,
        coalesce(b.account_name, '') as account_name,
        coalesce(b.counterparty_name_raw, '') as counterparty_name,
        coalesce(
            b.raw_payload->'normalized_payload'->>'counterparty_account_no',
            b.raw_payload->>'counterparty_account_no',
            ''
        ) as counterparty_account_no,
        coalesce(
            b.raw_payload->'normalized_payload'->>'counterparty_bank_name',
            b.raw_payload->>'counterparty_bank_name',
            ''
        ) as counterparty_bank_name,
        abs(b.amount) as amount,
        b.txn_date as trade_date,
        coalesce(b.trade_time, b.pay_receive_time, b.txn_date::timestamptz) as trade_time,
        coalesce(b.balance, 0) as balance,
        coalesce(b.currency, 'CNY') as currency,
        coalesce(b.summary, '') as summary,
        coalesce(b.remark, '') as remark,
        coalesce(b.bank_serial_no, '') as bank_serial_no,
        b.bank_text_fields,
        b.raw_payload
    from app.bank_transactions b
    where b.status <> 'deleted'
      and b.txn_direction in ('outflow', 'inflow')
),
manual_categories as materialized (
    select distinct on (bank.row_id)
        bank.row_id,
        coalesce(
            category.raw_payload->'normalized_payload'->>'category_code',
            category.raw_payload->>'category_code',
            category.category
        ) as category_code,
        coalesce(
            category.raw_payload->'normalized_payload'->>'source',
            category.raw_payload->>'source',
            category.source
        ) as category_source,
        coalesce(category.raw_payload->'normalized_payload', category.raw_payload) as category_payload
    from app.bank_transaction_categories category
    join bank_source bank
      on category.bank_transaction_id = bank.canonical_id
      or category.legacy_transaction_id in (bank.row_id, bank.canonical_id::text)
    where category.status = 'active'
    order by bank.row_id, category.updated_at desc, category.id desc
),
confirmed_categories as materialized (
    select distinct on (bank.row_id)
        bank.row_id,
        confirmation.category_code
    from app.bank_transaction_category_confirmations confirmation
    join bank_source bank
      on confirmation.bank_transaction_id = bank.canonical_id
      or confirmation.legacy_transaction_id in (bank.row_id, bank.canonical_id::text)
    where confirmation.tenant_id = 'default'
      and confirmation.status = 'active'
    order by bank.row_id, confirmation.confirmed_at desc, confirmation.id desc
),
income_override_rows as materialized (
    select command.updated_at, command.command_payload->'income_status_override' as payload
    from app.pending_invoice_manual_invoice_commands command
    where command.status = 'completed'
      and command.command_payload->>'operation' = 'income_status_override'
      and jsonb_typeof(command.command_payload->'income_status_override') = 'object'
    union all
    select command.updated_at, item.payload
    from app.pending_invoice_manual_invoice_commands command
    cross join lateral jsonb_array_elements(
        case
            when jsonb_typeof(command.command_payload->'income_status_overrides') = 'array'
            then command.command_payload->'income_status_overrides'
            else '[]'::jsonb
        end
    ) item(payload)
    where command.status = 'completed'
      and command.command_payload->>'operation' = 'income_status_override'
),
income_overrides as materialized (
    select distinct on (payload->>'transaction_id')
        payload->>'transaction_id' as row_id,
        payload->>'status_code' as status_code
    from income_override_rows
    where nullif(payload->>'transaction_id', '') is not null
    order by payload->>'transaction_id', updated_at desc
),
banks as materialized (
    select
        bank.*,
        manual.category_code as manual_category_code,
        manual.category_source as manual_category_source,
        manual.category_payload as manual_category_payload,
        confirmation.category_code as confirmed_category_code,
        income_override.status_code as income_override_status
    from bank_source bank
    left join manual_categories manual on manual.row_id = bank.row_id
    left join confirmed_categories confirmation on confirmation.row_id = bank.row_id
    left join income_overrides income_override on income_override.row_id = bank.row_id
),
active_relations as materialized (
    select r.case_id, r.relation_mode, r.row_ids, r.row_types
    from app.workbench_pair_relations r
    where r.status = 'active'
      and r.relation_mode <> 'turnover_manual_closure'
),
relation_members as materialized (
    select
        relation.case_id,
        relation.relation_mode,
        relation.row_ids[member_index] as row_id,
        case
            when relation.row_types[member_index] = 'bank_transaction' then 'bank'
            when relation.row_types[member_index] in ('input_invoice', 'output_invoice') then 'invoice'
            else relation.row_types[member_index]
        end as row_type
    from active_relations relation
    cross join lateral generate_subscripts(relation.row_ids, 1) member(member_index)
),
bank_cases as materialized (
    select distinct member.row_id as bank_id, member.case_id
    from relation_members member
    join bank_source owner_bank on owner_bank.row_id = member.row_id
    cross join request_config config
    where member.row_type = 'bank'
      and (
          coalesce(config.payload->>'scan_direction', 'all') = 'all'
          or owner_bank.direction = config.payload->>'scan_direction'
      )
),
bank_case_members as materialized (
    select distinct owner.bank_id, member.row_id as member_bank_id
    from bank_cases owner
    join relation_members member on member.case_id = owner.case_id and member.row_type = 'bank'
),
relation_bank_facts as materialized (
    select
        member.bank_id,
        coalesce(sum(bank.amount), 0) as paid_total,
        count(*)::integer as payment_transaction_count,
        jsonb_agg(
            jsonb_build_object(
                'id', bank.row_id,
                'trade_time', coalesce(bank.trade_time::text, ''),
                'counterparty_name', bank.counterparty_name,
                'amount', bank.amount::text,
                'debit_amount', case when bank.direction = 'expense' then bank.amount::text else '0.00' end,
                'credit_amount', case when bank.direction = 'income' then bank.amount::text else '0.00' end,
                'summary', bank.summary,
                'remark', bank.remark,
                'statement_serial_no', bank.bank_serial_no,
                'account_name', bank.account_name,
                'account_last4', right(regexp_replace(bank.account_no, '\\D', '', 'g'), 4),
                'relation_status', 'linked'
            )
            order by bank.trade_time desc nulls last, bank.row_id
        ) as bank_summaries
    from bank_case_members member
    join banks bank on bank.row_id = member.member_bank_id
    group by member.bank_id
),
case_invoice_members as materialized (
    select distinct owner.bank_id, member.row_id as invoice_id
    from bank_cases owner
    join relation_members member on member.case_id = owner.case_id and member.row_type = 'invoice'
),
relation_invoice_facts as materialized (
    select
        member.bank_id,
        coalesce(sum(coalesce(invoice.total_with_tax, invoice.amount)), 0) as invoice_total,
        count(*) filter (where invoice.invoice_type = 'input')::integer as input_invoice_count,
        count(*) filter (where invoice.invoice_type = 'output')::integer as output_invoice_count,
        coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'id', coalesce(invoice.legacy_mongo_id, invoice.id::text),
                    'invoice_no', coalesce(invoice.invoice_no, ''),
                    'digital_invoice_no', coalesce(invoice.digital_invoice_no, ''),
                    'invoice_code', coalesce(invoice.invoice_code, ''),
                    'issue_date', coalesce(invoice.invoice_date::text, ''),
                    'total_with_tax', coalesce(invoice.total_with_tax, invoice.amount)::text,
                    'seller_name', coalesce(invoice.seller_name, ''),
                    'seller_tax_no', coalesce(invoice.seller_tax_no, ''),
                    'buyer_name', coalesce(invoice.buyer_name, ''),
                    'buyer_tax_no', coalesce(invoice.buyer_tax_no, ''),
                    'invoice_type', invoice.invoice_type,
                    'counterparty_display_name',
                        case when invoice.invoice_type = 'input'
                             then coalesce(invoice.seller_name, '')
                             else coalesce(invoice.buyer_name, '') end,
                    'relation_status', 'linked',
                    'relation_source', 'workbench_pair_relations'
                )
                order by invoice.invoice_date desc nulls last, invoice.id
            ),
            '[]'::jsonb
        ) as invoice_summaries
    from case_invoice_members member
    join app.invoices invoice
      on coalesce(invoice.legacy_mongo_id, invoice.id::text) = member.invoice_id
      or invoice.id::text = member.invoice_id
    where invoice.status <> 'deleted'
    group by member.bank_id
),
case_oa_members as materialized (
    select distinct owner.bank_id, member.row_id as oa_id
    from bank_cases owner
    join relation_members member on member.case_id = owner.case_id and member.row_type = 'oa'
),
relation_oa_facts as materialized (
    select
        member.bank_id,
        count(*)::integer as oa_count,
        coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'id', oa.row_id,
                    'applicant', coalesce(oa.applicant, ''),
                    'application_type', coalesce(oa.form_type, ''),
                    'project_name', coalesce(oa.project_name, ''),
                    'status', coalesce(oa.status, ''),
                    'form_no', coalesce(oa.workflow_no, oa.form_id, ''),
                    'amount', coalesce(oa.amount, 0)::text,
                    'detail_available', true,
                    'relation_status', 'linked',
                    'relation_source', 'workbench_pair_relations'
                )
                order by oa.application_date desc nulls last, oa.row_id
            ),
            '[]'::jsonb
        ) as oa_summaries
    from case_oa_members member
    join app.oa_applications oa on oa.row_id = member.oa_id
    group by member.bank_id
),
relation_case_facts as materialized (
    select bank_id, array_agg(case_id order by case_id) as relation_case_ids
    from bank_cases
    group by bank_id
),
internal_edges as materialized (
    select
        outgoing.row_id as outgoing_id,
        incoming.row_id as incoming_id,
        outgoing.amount,
        abs(extract(epoch from incoming.trade_time - outgoing.trade_time))::integer as delta_seconds,
        (
            outgoing.summary || ' ' || outgoing.remark || ' ' ||
            coalesce(outgoing.raw_payload->'normalized_payload'->>'purpose', '') || ' ' ||
            coalesce(outgoing.raw_payload->>'purpose', '')
        ) ~ '(本公司帐户|本公司账户|本公司税户)' as outgoing_explicit,
        (
            incoming.summary || ' ' || incoming.remark || ' ' ||
            coalesce(incoming.raw_payload->'normalized_payload'->>'purpose', '') || ' ' ||
            coalesce(incoming.raw_payload->>'purpose', '')
        ) ~ '(本公司帐户|本公司账户|本公司税户)' as incoming_explicit
    from banks outgoing
    join banks incoming
      on outgoing.direction = 'expense'
     and incoming.direction = 'income'
     and outgoing.amount = incoming.amount
     and outgoing.account_no <> incoming.account_no
     and abs(extract(epoch from incoming.trade_time - outgoing.trade_time)) <= 172800
    where (
        outgoing.counterparty_name like '%%云南溯源科技有限公司%%'
        or outgoing.counterparty_name like '%%溯源科技有限公司%%'
    )
      and (
        incoming.counterparty_name like '%%云南溯源科技有限公司%%'
        or incoming.counterparty_name like '%%溯源科技有限公司%%'
    )
),
internal_degrees as materialized (
    select row_id, count(*)::integer as degree
    from (
        select outgoing_id as row_id from internal_edges
        union all
        select incoming_id as row_id from internal_edges
    ) ids
    group by row_id
),
internal_unambiguous as materialized (
    select edge.outgoing_id, edge.incoming_id
    from internal_edges edge
    join internal_degrees outgoing_degree on outgoing_degree.row_id = edge.outgoing_id
    join internal_degrees incoming_degree on incoming_degree.row_id = edge.incoming_id
    where outgoing_degree.degree = 1 and incoming_degree.degree = 1
),
explicit_edges as materialized (
    select
        row_number() over (
            order by edge.amount, edge.delta_seconds, edge.outgoing_id, edge.incoming_id
        )::integer as edge_no,
        edge.outgoing_id,
        edge.incoming_id
    from internal_edges edge
    where edge.outgoing_explicit and edge.incoming_explicit
      and (
          (select degree from internal_degrees where row_id = edge.outgoing_id) > 1
          or (select degree from internal_degrees where row_id = edge.incoming_id) > 1
      )
),
explicit_greedy(step, edge_no, used_outgoing, used_incoming, outgoing_id, incoming_id) as (
    select 0, 0, array[]::text[], array[]::text[], null::text, null::text
    union all
    select
        state.step + 1,
        next_edge.edge_no,
        state.used_outgoing || next_edge.outgoing_id,
        state.used_incoming || next_edge.incoming_id,
        next_edge.outgoing_id,
        next_edge.incoming_id
    from explicit_greedy state
    cross join lateral (
        select edge.*
        from explicit_edges edge
        where edge.edge_no > state.edge_no
          and not edge.outgoing_id = any(state.used_outgoing)
          and not edge.incoming_id = any(state.used_incoming)
        order by edge.edge_no
        limit 1
    ) next_edge
),
internal_matches as materialized (
    select outgoing_id as row_id from internal_unambiguous
    union
    select incoming_id from internal_unambiguous
    union
    select outgoing_id from explicit_greedy where step > 0
    union
    select incoming_id from explicit_greedy where step > 0
),
rule_banks as materialized (
    select
        bank.*,
        case when config.payload->'rule_fields' ? 'counterparty_name'
            then {_normalize_sql_text("bank.counterparty_name")} else '' end as rule_counterparty_name,
        case when config.payload->'rule_fields' ? 'counterparty_account'
            then {_normalize_sql_text("bank.counterparty_account_no")} else '' end as rule_counterparty_account,
        case when config.payload->'rule_fields' ? 'counterparty_bank'
            then {_normalize_sql_text("bank.counterparty_bank_name")} else '' end as rule_counterparty_bank,
        case when config.payload->'rule_fields' ? 'purpose_text'
            then {_normalize_sql_text("coalesce(bank.raw_payload->'normalized_payload'->>'purpose', bank.raw_payload->>'purpose', '')")}
            else '' end as rule_purpose_text,
        case when config.payload->'rule_fields' ? 'summary_text'
            then {_normalize_sql_text("bank.summary")} else '' end as rule_summary_text,
        case when config.payload->'rule_fields' ? 'note_text'
            then {_normalize_sql_text("bank.remark")} else '' end as rule_note_text,
        case when config.payload->'rule_fields' ? 'detail_text'
            then {_normalize_sql_text("concat_ws(' ', coalesce(bank.raw_payload->'normalized_payload'->>'detail_text', bank.raw_payload->>'detail_text', ''), (select string_agg(text_field->>'value', ' ' order by position) from jsonb_array_elements(case when jsonb_typeof(bank.bank_text_fields) = 'array' then bank.bank_text_fields else '[]'::jsonb end) with ordinality fields(text_field, position) where nullif(text_field->>'value', '') is not null))")}
            else '' end as rule_detail_text,
        case when config.payload->'rule_fields' ? 'account'
            then {_normalize_sql_text("bank.account_no")} else '' end as rule_account,
        case when config.payload->'rule_fields' ? 'account_type'
            then {_normalize_sql_text("coalesce(bank.raw_payload->'normalized_payload'->>'account_type', bank.raw_payload->>'account_type')")}
            else '' end as rule_account_type,
        case when config.payload->'rule_fields' ? 'bank'
            then {_normalize_sql_text("coalesce(bank.raw_payload->'normalized_payload'->>'bank_name', bank.raw_payload->>'bank_name')")}
            else '' end as rule_bank
    from banks bank
    cross join request_config config
    where coalesce(config.payload->>'scan_direction', 'all') = 'all'
       or bank.direction = config.payload->>'scan_direction'
),
canonical_rule_banks as materialized (
    select
        bank.*,
        bank.rule_counterparty_name as norm_counterparty_name,
        bank.rule_counterparty_account as norm_counterparty_account,
        bank.rule_counterparty_bank as norm_counterparty_bank,
        bank.rule_purpose_text as norm_purpose_text,
        bank.rule_summary_text as norm_summary_text,
        bank.rule_note_text as norm_note_text,
        bank.rule_detail_text as norm_detail_text,
        bank.rule_account as norm_account_no,
        bank.rule_account_type as norm_account_type,
        bank.rule_bank as norm_bank_name,
        bank.rule_counterparty_name as regex_counterparty_name,
        bank.rule_counterparty_account as regex_counterparty_account,
        bank.rule_counterparty_bank as regex_counterparty_bank,
        bank.rule_purpose_text as regex_purpose_text,
        bank.rule_summary_text as regex_summary_text,
        bank.rule_note_text as regex_note_text,
        bank.rule_detail_text as regex_detail_text,
        bank.rule_account as account_key
    from rule_banks bank
),
compiled_rule_matches as materialized (
    select
        rule_match.row_id,
        rule_match.definition,
        rule_match.priority
    from (
        __RULE_MATCH_SQL__
    ) rule_match
    where not exists (
        select 1 from internal_matches match where match.row_id = rule_match.row_id
    )
),
winning_rule_priority as materialized (
    select row_id, min(priority) as priority
    from compiled_rule_matches
    group by row_id
),
auto_rules as materialized (
    select
        match.row_id,
        case when count(*) = 1 then (jsonb_agg(match.definition order by match.definition->>'code')->0) end as definition
    from compiled_rule_matches match
    join winning_rule_priority winner
      on winner.row_id = match.row_id and winner.priority = match.priority
    group by match.row_id
),
effective_categories as materialized (
    select
        b.*,
        case
            when b.confirmed_category_code is not null then b.confirmed_category_code
            when b.manual_category_code is not null
                 and b.manual_category_source = 'manual'
                 and coalesce((b.manual_category_payload->>'manual_assignment')::boolean, false)
                 and internal.row_id is null
                 and auto.definition is null
                then b.manual_category_code
            when b.manual_category_code is not null
                 and (
                     b.manual_category_source = 'turnover_ledger'
                     or auto.definition->>'code' = 'external_turnover'
                 )
                then b.manual_category_code
            when internal.row_id is not null then 'internal_transfer'
            when auto.definition->>'code' = 'external_turnover' then null
            else auto.definition->>'code'
        end as category_code,
        case
            when b.confirmed_category_code is not null then 'manual_confirmation'
            when b.manual_category_code is not null
                 and b.manual_category_source = 'manual'
                 and coalesce((b.manual_category_payload->>'manual_assignment')::boolean, false)
                 and internal.row_id is null
                 and auto.definition is null
                then 'manual'
            when b.manual_category_code is not null
                 and (
                     b.manual_category_source = 'turnover_ledger'
                     or auto.definition->>'code' = 'external_turnover'
                 )
                then b.manual_category_source
            when internal.row_id is not null or auto.definition is not null then 'auto'
            else ''
        end as category_source,
        auto.definition as auto_definition
    from banks b
    cross join request_config config
    left join internal_matches internal on internal.row_id = b.row_id
    left join auto_rules auto on auto.row_id = b.row_id
    where coalesce(config.payload->>'scan_direction', 'all') = 'all'
       or b.direction = config.payload->>'scan_direction'
),
enriched as materialized (
    select
        category.*,
        case
            when category.direction = 'expense'
                 and category.category_code in (
                     select jsonb_array_elements_text(config.payload#>'{{groups,expense,no_invoice_required}}')
                     from request_config config
                 ) then 'no_invoice_required'
            when category.direction = 'expense'
                 and category.category_code in (
                     select jsonb_array_elements_text(config.payload#>'{{groups,expense,bank_statement_as_invoice}}')
                     from request_config config
                 ) then 'bank_statement_as_invoice'
            when category.direction = 'income'
                 and category.category_code in (
                     select jsonb_array_elements_text(config.payload#>'{{groups,income,no_invoice_required}}')
                     from request_config config
                 ) then 'no_invoice_required'
            when category.direction = 'income'
                 and category.category_code in (
                     select jsonb_array_elements_text(config.payload#>'{{groups,income,cash_income}}')
                     from request_config config
                 ) then 'cash_income'
            when category.direction = 'expense'
                 and category.category_code in (
                     select jsonb_array_elements_text(config.payload#>'{{groups,expense,active}}')
                     from request_config config
                 ) then 'requires_invoice'
            when category.direction = 'income'
                 and category.category_code in (
                     select jsonb_array_elements_text(config.payload#>'{{groups,income,active}}')
                     from request_config config
                 ) then 'requires_invoice'
            else 'all'
        end as filter_group,
        coalesce(invoice.input_invoice_count, 0) as input_invoice_count,
        coalesce(invoice.output_invoice_count, 0) as output_invoice_count,
        coalesce(invoice.invoice_total, 0) as invoice_total,
        coalesce(invoice.invoice_summaries, '[]'::jsonb) as invoice_summaries,
        coalesce(bank.paid_total, category.amount) as paid_total,
        coalesce(bank.payment_transaction_count, 1) as payment_transaction_count,
        coalesce(bank.bank_summaries, '[]'::jsonb) as bank_summaries,
        coalesce(oa.oa_count, 0) as oa_count,
        coalesce(oa.oa_summaries, '[]'::jsonb) as oa_summaries,
        coalesce(cases.relation_case_ids, array[]::text[]) as relation_case_ids
    from effective_categories category
    left join relation_invoice_facts invoice on invoice.bank_id = category.row_id
    left join relation_bank_facts bank on bank.bank_id = category.row_id
    left join relation_oa_facts oa on oa.bank_id = category.row_id
    left join relation_case_facts cases on cases.bank_id = category.row_id
),
classified_source as materialized (
    select
        enriched.*,
        case
            when enriched.direction = 'income' and enriched.output_invoice_count > 0 then 'income_invoiced'
            when enriched.direction = 'income' and enriched.income_override_status = 'income_no_invoice_required'
                then 'income_no_invoice_required'
            when enriched.direction = 'income' and enriched.income_override_status = 'cash_income'
                then 'cash_income'
            when enriched.direction = 'income' and enriched.filter_group = 'no_invoice_required'
                then 'income_no_invoice_required'
            when enriched.direction = 'income' and enriched.filter_group = 'cash_income' then 'cash_income'
            when enriched.direction = 'income' then 'income_pending_invoice'
            when enriched.input_invoice_count > 0 and enriched.invoice_total > enriched.paid_total
                then 'invoice_not_fully_paid'
            when enriched.input_invoice_count > 0 then 'paid_invoiced'
            when enriched.filter_group = 'no_invoice_required' then 'no_invoice_required'
            when enriched.filter_group = 'bank_statement_as_invoice' then 'bank_statement_as_invoice'
            else 'paid_pending_invoice'
        end as status_code
    from enriched
),
classified as materialized (
    select
        source.row_id,
        source.direction,
        source.account_no,
        source.account_name,
        source.counterparty_name,
        source.counterparty_account_no,
        source.counterparty_bank_name,
        source.amount,
        source.trade_date,
        source.trade_time,
        source.balance,
        source.currency,
        source.summary,
        source.remark,
        source.bank_serial_no,
        source.income_override_status,
        source.category_code,
        source.category_source,
        source.filter_group,
        source.input_invoice_count,
        source.output_invoice_count,
        source.invoice_total,
        source.invoice_summaries,
        source.paid_total,
        source.payment_transaction_count,
        source.bank_summaries,
        source.oa_count,
        source.oa_summaries,
        source.relation_case_ids,
        source.status_code,
        coalesce(
            definition.definition->>'label',
            source.manual_category_payload->>'category_label',
            source.manual_category_payload->>'label',
            source.category_code,
            ''
        ) as category_label,
        coalesce(
            definition.definition->>'output_primary_label',
            source.manual_category_payload->>'category_primary_label',
            ''
        ) as category_primary_label,
        coalesce(
            definition.definition->>'output_sub_label',
            source.manual_category_payload->>'category_sub_label',
            ''
        ) as category_sub_label,
        trim(concat_ws(' ', nullif(
            coalesce(
                mapping.account->>'short_name',
                mapping.account->>'bank_name',
                source.raw_payload->'normalized_payload'->>'bank_short_name',
                source.raw_payload->'normalized_payload'->>'bank_name',
                source.raw_payload->>'bank_name',
                ''
            ),
            ''
        ), nullif(right(regexp_replace(source.account_no, '\\D', '', 'g'), 4), ''))) as bank_account,
        coalesce(
            mapping.account->>'bank_name',
            source.raw_payload->'normalized_payload'->>'bank_name',
            source.raw_payload->>'bank_name',
            ''
        ) as bank_name,
        coalesce(
            mapping.account->>'short_name',
            mapping.account->>'bank_name',
            source.raw_payload->'normalized_payload'->>'bank_short_name',
            source.raw_payload->'normalized_payload'->>'bank_name',
            source.raw_payload->>'bank_name',
            ''
        ) as bank_short_name,
        trim(concat_ws(' / ',
            nullif(coalesce(definition.definition->>'output_primary_label', source.manual_category_payload->>'category_primary_label', ''), ''),
            nullif(coalesce(definition.definition->>'output_sub_label', source.manual_category_payload->>'category_sub_label', ''), '')
        )) as transaction_tag,
        source.summary || ' ' || source.remark as summary_remark,
        coalesce(source.invoice_summaries->0->>'seller_name', '') as seller_name,
        coalesce(source.oa_summaries->0->>'applicant', '') as oa_applicant,
        coalesce(source.oa_summaries->0->>'application_type', '') as oa_application_type,
        coalesce(source.oa_summaries->0->>'project_name', '') as project_name,
        concat_ws(' ',
            source.row_id,
            source.counterparty_name,
            source.summary,
            source.remark,
            source.category_code,
            source.invoice_summaries::text,
            source.oa_summaries::text
        ) as searchable_text,
        case
            when jsonb_array_length(source.bank_summaries) > 1 and cardinality(source.relation_case_ids) > 0
            then source.relation_case_ids[1]
            else source.row_id
        end as visible_group_key
    from classified_source source
    left join lateral (
        select definition
        from request_config config
        cross join lateral jsonb_array_elements(
            case
                when jsonb_typeof(config.payload#>'{{settings,bank_transaction_tags,definitions}}') = 'array'
                then config.payload#>'{{settings,bank_transaction_tags,definitions}}'
                else '[]'::jsonb
            end
        ) definitions(definition)
        where definition->>'code' = source.category_code
        limit 1
    ) definition on true
    left join lateral (
        select account
        from request_config config
        cross join lateral jsonb_array_elements(
            case
                when jsonb_typeof(config.payload#>'{{settings,bank_account_mappings}}') = 'array'
                then config.payload#>'{{settings,bank_account_mappings}}'
                else '[]'::jsonb
            end
        ) accounts(account)
        where regexp_replace(account->>'last4', '\\D', '', 'g')
            = right(regexp_replace(source.account_no, '\\D', '', 'g'), 4)
        limit 1
    ) mapping on true
),
scope_candidates as materialized (
    select *
    from classified
    where __WHERE_SQL__
),
scope_ranked as materialized (
    select
        candidate.*,
        row_number() over (
            partition by candidate.visible_group_key
            order by candidate.trade_time desc nulls last, candidate.row_id
        ) as visible_group_rank
    from scope_candidates candidate
),
scope_rows as materialized (
    select *
    from scope_ranked
    where visible_group_rank = 1
),
scope_summary as (
    select
        count(*)::integer as total,
        count(*) filter (where status_code in (
            'paid_pending_invoice', 'paid_pending_future_invoice', 'income_pending_invoice'
        ))::integer as missing_invoice_rows,
        count(*) filter (
            where direction = 'expense'
              and input_invoice_count = 0
              and filter_group <> 'no_invoice_required'
        )::integer as create_invoice_available_rows
    from scope_rows
),
ordered_rows as materialized (
    select
        scope.*,
        row_number() over (order by __ORDER_SQL__) as page_index
    from scope_rows scope
),
page_rows as materialized (
    select *
    from ordered_rows
    order by page_index
    limit %s offset %s
),
statistics as (
    select
        count(*)::integer as bank_transaction_count,
        count(*) filter (where direction = 'expense')::integer as expense_transaction_count,
        count(*) filter (where direction = 'income')::integer as income_transaction_count,
        count(*) filter (
            where (direction = 'expense' and input_invoice_count > 0)
               or (direction = 'income' and output_invoice_count > 0)
        )::integer as found_invoice_transaction_count,
        count(*) filter (
            where status_code in ('paid_pending_invoice', 'paid_pending_future_invoice', 'income_pending_invoice')
        )::integer as pending_invoice_transaction_count,
        count(*) filter (
            where status_code in ('no_invoice_required', 'income_no_invoice_required')
        )::integer as no_invoice_required_transaction_count,
        count(*) filter (where status_code = 'cash_income')::integer as cash_income_transaction_count,
        count(*) filter (where oa_count > 0)::integer as linked_oa_transaction_count,
        count(*) filter (where direction = 'expense' and input_invoice_count > 0)::integer
            as linked_input_invoice_transaction_count,
        count(*) filter (where direction = 'income' and output_invoice_count > 0)::integer
            as linked_output_invoice_transaction_count
    from classified
    where %s::boolean
),
source_summary as (
    select
        count(*)::integer as bank_transaction_rows,
        count(*) filter (where direction = 'expense')::integer as expense_rows,
        count(*) filter (where direction = 'income')::integer as income_rows
    from bank_source
    where __SOURCE_WHERE_SQL__
),
option_values as (
    select option.field, nullif(btrim(option.value), '') as value
    from scope_rows row
    cross join lateral (
        values
            ('trade_date', coalesce(row.trade_date::text, '')),
            ('bank_name', row.bank_name),
            ('account_name', row.account_name),
            ('bank_account', row.bank_account),
            ('counterparty_name', row.counterparty_name),
            ('transaction_tag', coalesce(nullif(row.transaction_tag, ''), row.category_label, row.category_code, '')),
            ('direction', row.direction),
            ('amount', row.amount::text),
            ('summary_remark', row.summary_remark),
            ('status_code', row.status_code),
            ('rule_group', row.filter_group),
            ('seller_name', row.seller_name),
            ('invoice_total', row.invoice_total::text),
            ('oa_applicant', row.oa_applicant),
            ('oa_application_type', row.oa_application_type),
            ('project_name', row.project_name)
    ) option(field, value)
),
ranked_options as (
    select
        field,
        value,
        count(*)::integer as option_count,
        row_number() over (partition by field order by count(*) desc, value) as option_rank
    from option_values
    where %s::boolean and value is not null
    group by field, value
)
select
    coalesce(
        (
            select jsonb_agg(to_jsonb(page_row) - 'page_index' - 'visible_group_rank' order by page_index)
            from page_rows page_row
        ),
        '[]'::jsonb
    ) as rows,
    (select total from scope_summary) as total,
    (select missing_invoice_rows from scope_summary) as missing_invoice_rows,
    (select create_invoice_available_rows from scope_summary) as create_invoice_available_rows,
    (select to_jsonb(statistics) from statistics) as statistics,
    (
        select jsonb_build_object(
            'bank_transaction_rows', source_summary.bank_transaction_rows,
            'expense_rows', source_summary.expense_rows,
            'income_rows', source_summary.income_rows,
            'current_direction_rows',
                case
                    when %s = 'all' then source_summary.bank_transaction_rows
                    when %s = 'expense' then source_summary.expense_rows
                    else source_summary.income_rows
                end,
            'excluded_direction_rows',
                source_summary.bank_transaction_rows - case
                    when %s = 'all' then source_summary.bank_transaction_rows
                    when %s = 'expense' then source_summary.expense_rows
                    else source_summary.income_rows
                end
        )
        from source_summary
    ) as source_summary,
    coalesce(
        (
            select jsonb_agg(
                jsonb_build_object(
                    'field', field,
                    'value', value,
                    'count', option_count
                )
                order by field, option_rank
            )
            from ranked_options
            where option_rank <= {FILTER_OPTION_LIMIT}
        ),
        '[]'::jsonb
    ) as options
"""

CANDIDATE_SORT_EXPRESSIONS = {
    "issue_date": "issue_date",
    "total_with_tax": "total_with_tax",
    "seller_name": "seller_name",
    "amount_difference_abs": "amount_difference_abs",
}

CANDIDATE_QUERY_SQL = """
with
active_relations as materialized (
    select case_id, row_ids, row_types
    from app.workbench_pair_relations
    where status = 'active'
      and relation_mode <> 'turnover_manual_closure'
),
relation_members as materialized (
    select
        relation.case_id,
        relation.row_ids[member_index] as row_id,
        case
            when relation.row_types[member_index] = 'bank_transaction' then 'bank'
            when relation.row_types[member_index] in ('input_invoice', 'output_invoice') then 'invoice'
            else relation.row_types[member_index]
        end as row_type
    from active_relations relation
    cross join lateral generate_subscripts(relation.row_ids, 1) member(member_index)
),
invoice_cases as materialized (
    select
        invoice_member.row_id as invoice_id,
        invoice_member.case_id,
        bool_and(member.row_type in ('bank', 'invoice', 'oa')) as attach_existing_compatible
    from relation_members invoice_member
    join relation_members member on member.case_id = invoice_member.case_id
    where invoice_member.row_type = 'invoice'
    group by invoice_member.row_id, invoice_member.case_id
),
invoice_bank_members as materialized (
    select distinct invoice_case.invoice_id, bank_member.row_id as bank_id
    from invoice_cases invoice_case
    join relation_members bank_member
      on bank_member.case_id = invoice_case.case_id
     and bank_member.row_type = 'bank'
),
invoice_case_facts as materialized (
    select
        invoice_case.invoice_id,
        count(*)::integer as relation_count,
        bool_or(invoice_case.attach_existing_compatible) as has_attach_existing_compatible_relation
    from invoice_cases invoice_case
    group by invoice_case.invoice_id
),
invoice_bank_facts as materialized (
    select
        bank_member.invoice_id,
        coalesce(
            array_agg(distinct bank_member.bank_id)
                filter (where bank_member.bank_id is not null),
            array[]::text[]
        ) as linked_bank_ids,
        coalesce(sum(abs(bank.amount)), 0) as paid_total
    from invoice_bank_members bank_member
    left join app.bank_transactions bank
      on coalesce(bank.legacy_mongo_id, bank.id::text) = bank_member.bank_id
     and bank.status <> 'deleted'
    group by bank_member.invoice_id
),
candidate_source as materialized (
    select
        coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_id,
        coalesce(invoice.invoice_no, '') as invoice_no,
        coalesce(invoice.digital_invoice_no, '') as digital_invoice_no,
        invoice.invoice_date as issue_date,
        coalesce(invoice.seller_name, '') as seller_name,
        coalesce(invoice.seller_tax_no, '') as seller_tax_no,
        coalesce(invoice.buyer_name, '') as buyer_name,
        coalesce(invoice.total_with_tax, invoice.amount) as total_with_tax,
        coalesce(bank_relation.paid_total, 0) as paid_total,
        coalesce(bank_relation.linked_bank_ids, array[]::text[]) as linked_bank_ids,
        coalesce(case_relation.relation_count, 0) as relation_count,
        coalesce(case_relation.has_attach_existing_compatible_relation, false)
            as has_attach_existing_compatible_relation,
        lower(concat_ws(
            ' ',
            invoice.invoice_no,
            invoice.digital_invoice_no,
            invoice.seller_name,
            invoice.raw_payload->>'remark'
        )) as searchable_text
    from app.invoices invoice
    left join invoice_case_facts case_relation
      on case_relation.invoice_id in (coalesce(invoice.legacy_mongo_id, invoice.id::text), invoice.id::text)
    left join invoice_bank_facts bank_relation
      on bank_relation.invoice_id in (coalesce(invoice.legacy_mongo_id, invoice.id::text), invoice.id::text)
    where invoice.invoice_type = 'input'
      and invoice.status <> 'deleted'
),
filtered as materialized (
    select source.*
    from candidate_source source
    where (%s = '' or source.searchable_text like %s)
      and (%s = '' or lower(source.seller_name) like %s)
      and (%s::date is null or source.issue_date >= %s::date)
      and (%s::date is null or source.issue_date <= %s::date)
      and (%s::numeric is null or source.total_with_tax >= %s::numeric)
      and (%s::numeric is null or source.total_with_tax <= %s::numeric)
),
classified as materialized (
    select
        filtered.*,
        case
            when %s::text[] <@ filtered.linked_bank_ids then 'already_related'
            when cardinality(filtered.linked_bank_ids) = 0
                 and filtered.relation_count > 0
                 and not filtered.has_attach_existing_compatible_relation then 'conflict'
            else 'available'
        end as candidate_status,
        case
            when cardinality(filtered.linked_bank_ids) = 0
                 and filtered.relation_count > 0
                 and not filtered.has_attach_existing_compatible_relation then 'conflict'
            when %s::text[] <@ filtered.linked_bank_ids then 'already_selected'
            when cardinality(filtered.linked_bank_ids) > 0 then 'linked'
            else 'unlinked'
        end as bank_relation_status,
        abs(filtered.total_with_tax - %s::numeric) as amount_difference_abs
    from filtered
),
paged as materialized (
    select *
    from classified
    order by __CANDIDATE_ORDER_SQL__
    limit %s offset %s
)
select
    (select count(*)::integer from classified) as total,
    coalesce(
        jsonb_agg(
            jsonb_build_object(
                'invoice_id', paged.invoice_id,
                'invoice_no', paged.invoice_no,
                'digital_invoice_no', paged.digital_invoice_no,
                'issue_date', coalesce(paged.issue_date::text, ''),
                'seller_name', paged.seller_name,
                'seller_tax_no', paged.seller_tax_no,
                'buyer_name', paged.buyer_name,
                'total_with_tax', paged.total_with_tax::text,
                'paid_total', paged.paid_total::text,
                'related_paid_total', paged.paid_total::text,
                'remaining_amount', greatest(paged.total_with_tax - paged.paid_total, 0)::text,
                'candidate_status', paged.candidate_status,
                'bank_relation_status', paged.bank_relation_status,
                'linked_bank_transaction_count', cardinality(paged.linked_bank_ids),
                'conflict_reason',
                    case when paged.candidate_status = 'conflict' then '已有不兼容关系' else '' end,
                'amount_difference_abs', paged.amount_difference_abs::text
            )
            order by __CANDIDATE_ORDER_SQL__
        ),
        '[]'::jsonb
    ) as rows
from paged
"""

SELECTED_BANKS_SQL = """
select
    count(*)::integer as found_count,
    count(*) filter (where txn_direction = 'outflow')::integer as expense_count,
    coalesce(sum(abs(amount)), 0) as selected_total
from app.bank_transactions
where status <> 'deleted'
  and coalesce(legacy_mongo_id, id::text) = any(%s::text[])
"""

BANK_DETAIL_SQL = """
select
    coalesce(legacy_mongo_id, id::text) as id,
    account_no,
    coalesce(account_name, '') as account_name,
    txn_direction,
    counterparty_name_raw as counterparty_name,
    coalesce(
        raw_payload->'normalized_payload'->>'counterparty_account_no',
        raw_payload->>'counterparty_account_no',
        ''
    ) as counterparty_account_no,
    coalesce(
        raw_payload->'normalized_payload'->>'counterparty_bank_name',
        raw_payload->>'counterparty_bank_name',
        ''
    ) as counterparty_bank_name,
    abs(amount) as amount,
    coalesce(trade_time, pay_receive_time, txn_date::timestamptz)::text as trade_time,
    coalesce(txn_date::text, '') as booked_date,
    balance,
    coalesce(currency, 'CNY') as currency,
    coalesce(
        raw_payload->'normalized_payload'->>'bank_name',
        raw_payload->>'bank_name',
        ''
    ) as bank_name,
    coalesce(summary, '') as summary,
    coalesce(remark, '') as remark,
    coalesce(bank_serial_no, '') as statement_serial_no,
    coalesce(
        raw_payload->'normalized_payload'->>'enterprise_serial_no',
        raw_payload->>'enterprise_serial_no',
        ''
    ) as enterprise_serial_no,
    coalesce(
        raw_payload->'normalized_payload'->>'voucher_type',
        raw_payload->>'voucher_type',
        ''
    ) as voucher_type,
    coalesce(
        raw_payload->'normalized_payload'->>'voucher_no',
        raw_payload->>'voucher_no',
        ''
    ) as voucher_no
from app.bank_transactions
where status <> 'deleted'
  and coalesce(legacy_mongo_id, id::text) = %s
limit 1
"""

INVOICE_DETAIL_SQL = """
select
    coalesce(legacy_mongo_id, id::text) as id,
    coalesce(invoice_no, '') as invoice_no,
    coalesce(digital_invoice_no, '') as digital_invoice_no,
    coalesce(invoice_code, '') as invoice_code,
    coalesce(invoice_date::text, '') as issue_date,
    coalesce(total_with_tax, amount) as total_with_tax,
    coalesce(seller_name, '') as seller_name,
    coalesce(seller_tax_no, '') as seller_tax_no,
    coalesce(buyer_name, '') as buyer_name,
    coalesce(buyer_tax_no, '') as buyer_tax_no,
    coalesce(tax_amount, 0) as tax_amount,
    coalesce(raw_payload->>'remark', '') as remark,
    invoice_type
from app.invoices
where status <> 'deleted'
  and coalesce(legacy_mongo_id, id::text) = %s
limit 1
"""

OA_DETAIL_SQL = """
select
    oa.row_id as oa_id,
    coalesce(oa.applicant, '') as applicant,
    coalesce(oa.form_type, '') as application_type,
    coalesce(oa.project_name, '') as project_name,
    coalesce(oa.workflow_no, '') as workflow_no,
    coalesce(oa.workflow_status, oa.status, '') as status,
    coalesce(oa.amount, 0) as amount,
    coalesce(oa.scope_month::text, '') as month,
    coalesce(
        oa.normalized_payload->>'counterparty_name',
        oa.raw_payload->>'counterparty_name',
        ''
    ) as counterparty_name,
    coalesce(
        oa.normalized_payload->>'reason',
        oa.raw_payload->>'reason',
        ''
    ) as reason,
    coalesce(
        (
            select relation.case_id
            from app.workbench_pair_relations relation
            where relation.status = 'active'
              and relation.relation_mode <> 'turnover_manual_closure'
              and oa.row_id = any(relation.row_ids)
            order by relation.updated_at desc, relation.case_id
            limit 1
        ),
        ''
    ) as relation_case_id
from app.oa_applications oa
where oa.status <> 'deleted'
  and oa.row_id = %s
limit 1
"""


class PostgresPendingInvoiceCanonicalRepository:
    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Pending invoice canonical repository requires a PostgreSQL connection.")
        self._connection = connection

    def query(
        self,
        request: dict[str, Any],
        *,
        page_size: int,
        page: int,
    ) -> dict[str, Any]:
        with self._snapshot_transaction() as transaction:
            transaction.execute("set local jit = off")
            settings = self._settings(transaction)
            scan_direction = (
                "all"
                if request.get("_include_statistics")
                else str(request["direction"])
            )
            tags = settings.get("bank_transaction_tags")
            tag_definitions = (
                list(tags.get("definitions") or [])
                if isinstance(tags, dict)
                else []
            )
            definitions = [
                dict(item)
                for item in tag_definitions
                if isinstance(item, dict)
                and (
                    scan_direction == "all"
                    or str(item.get("direction") or "any") in {"", "any", scan_direction}
                )
            ]
            _normalization_sql, rule_match_sql, rule_match_params = (
                compile_bank_category_rule_sql(
                    definitions,
                    source_relation="canonical_rule_banks",
                )
            )
            config = {
                "scan_direction": scan_direction,
                "settings": settings,
                "rule_fields": _rule_required_fields(definitions),
                "groups": {
                    direction: {
                        **{
                            group: sorted(values)
                            for group, values in pending_invoice_tag_group_sets(
                                settings,
                                direction=direction,
                            ).items()
                            if group != "active_tag_codes"
                        },
                        "active": sorted(
                            pending_invoice_tag_group_sets(
                                settings,
                                direction=direction,
                            ).get("active_tag_codes", set())
                        ),
                    }
                    for direction in ("expense", "income")
                },
            }
            where_sql, where_params = _where_sql(request)
            source_where_sql, source_params = _source_where_sql(request)
            order_sql = _order_sql(request)
            sql = (
                PAGE_QUERY_SQL
                .replace("__WHERE_SQL__", where_sql)
                .replace("__ORDER_SQL__", order_sql)
                .replace("__SOURCE_WHERE_SQL__", source_where_sql)
                .replace("__RULE_MATCH_SQL__", rule_match_sql)
            )
            direction = str(request["direction"])
            row = transaction.fetch_one(
                sql,
                tuple(
                    [
                        json.dumps(config, ensure_ascii=False),
                        *rule_match_params,
                        *where_params,
                        page_size,
                        (page - 1) * page_size,
                        *source_params,
                        bool(request.get("_include_statistics")),
                        bool(request.get("_include_filter_options")),
                        direction,
                        direction,
                        direction,
                        direction,
                    ]
                ),
            )
        payload = dict(row) if isinstance(row, dict) else {}
        payload["settings"] = settings
        return payload

    def invoice_candidates(self, request: dict[str, Any]) -> dict[str, Any]:
        transaction_ids = list(request["transaction_ids"])
        with self._snapshot_transaction() as transaction:
            selected = transaction.fetch_one(SELECTED_BANKS_SQL, (transaction_ids,))
            selected_payload = dict(selected) if isinstance(selected, dict) else {}
            if int(selected_payload.get("found_count") or 0) != len(transaction_ids):
                raise PendingInvoiceError(
                    "bank_transaction_not_found",
                    "One or more selected bank transactions were not found.",
                    status_code=HTTPStatus.NOT_FOUND,
                )
            if int(selected_payload.get("expense_count") or 0) != len(transaction_ids):
                raise PendingInvoiceError(
                    "invalid_direction",
                    "invoice candidates are only supported for expense rows.",
                )
            keyword = str(request.get("keyword") or "").lower()
            seller_name = str(request.get("seller_name") or "").lower()
            date_from = request.get("issue_date_from")
            date_to = request.get("issue_date_to")
            amount_min = request.get("amount_min")
            amount_max = request.get("amount_max")
            order_sql = _candidate_order_sql(
                str(request.get("sort_field") or ""),
                str(request.get("sort_direction") or "asc"),
            )
            sql = CANDIDATE_QUERY_SQL.replace("__CANDIDATE_ORDER_SQL__", order_sql)
            row = transaction.fetch_one(
                sql,
                (
                    keyword,
                    f"%{keyword}%",
                    seller_name,
                    f"%{seller_name}%",
                    date_from,
                    date_from,
                    date_to,
                    date_to,
                    amount_min,
                    amount_min,
                    amount_max,
                    amount_max,
                    transaction_ids,
                    transaction_ids,
                    selected_payload.get("selected_total") or Decimal("0"),
                    request["page_size"],
                    (request["page"] - 1) * request["page_size"],
                ),
            )
        payload = dict(row) if isinstance(row, dict) else {}
        return {
            "rows": list(payload.get("rows") or []),
            "total": int(payload.get("total") or 0),
            "selected_total": _money(selected_payload.get("selected_total")),
        }

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any] | None:
        return self._detail(BANK_DETAIL_SQL, bank_transaction_id)

    def invoice_detail(self, invoice_id: str) -> dict[str, Any] | None:
        return self._detail(INVOICE_DETAIL_SQL, invoice_id)

    def oa_detail(self, oa_id: str) -> dict[str, Any] | None:
        return self._detail(OA_DETAIL_SQL, oa_id)

    def _detail(self, sql: str, object_id: str) -> dict[str, Any] | None:
        with self._snapshot_transaction() as transaction:
            row = transaction.fetch_one(sql, (object_id,))
        return dict(row) if isinstance(row, dict) else None

    @contextmanager
    def _snapshot_transaction(self) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield transaction

    @staticmethod
    def _settings(transaction: Any) -> dict[str, Any]:
        row = transaction.fetch_one(
            """
            select settings_payload
            from app.app_settings
            where settings_key = 'app_settings'
            limit 1
            """
        )
        payload = row.get("settings_payload") if isinstance(row, dict) else None
        return dict(payload) if isinstance(payload, dict) else {}


class LocalPendingInvoiceCanonicalRepository:
    """Canonical local-state adapter; production PostgreSQL never uses this path."""

    def __init__(
        self,
        *,
        import_service: Any,
        query_service: PendingInvoiceQueryService,
        settings_provider: Callable[[], dict[str, Any]],
    ) -> None:
        self._import_service = import_service
        self._query_service = query_service
        self._settings_provider = settings_provider

    def query(
        self,
        request: dict[str, Any],
        *,
        page_size: int,
        page: int,
    ) -> dict[str, Any]:
        settings = dict(self._settings_provider() or {})
        rows: list[dict[str, Any]] = []
        statistics_rows: list[dict[str, Any]] = []
        transactions = list(self._import_service.list_transactions())
        for transaction in transactions:
            if getattr(transaction, "txn_direction", None) not in {
                TransactionDirection.OUTFLOW,
                TransactionDirection.INFLOW,
            }:
                continue
            direction = (
                "expense"
                if getattr(transaction, "txn_direction", None) == TransactionDirection.OUTFLOW
                else "income"
            )
            row = self._query_service.row_for_transaction(transaction.id, direction=direction)
            row["_direction"] = direction
            statistics_rows.append(row)
            if _local_row_matches(row, request):
                rows.append(row)
        rows.sort(
            key=lambda item: _local_sort_value(item, str(request.get("sort_field") or "trade_date")),
            reverse=str(request.get("sort_direction") or "desc") == "desc",
        )
        start = (page - 1) * page_size
        selected = rows[start : start + page_size]
        source_expense = sum(
            getattr(transaction, "txn_direction", None) == TransactionDirection.OUTFLOW
            for transaction in transactions
        )
        source_income = sum(
            getattr(transaction, "txn_direction", None) == TransactionDirection.INFLOW
            for transaction in transactions
        )
        options: list[dict[str, Any]] = []
        if request.get("_include_filter_options"):
            for field in FILTER_EXPRESSIONS:
                counts: dict[str, int] = {}
                for row in rows:
                    value = str(PendingInvoiceQueryService._row_field_value(row, field) or "").strip()
                    if value:
                        counts[value] = counts.get(value, 0) + 1
                options.extend(
                    {"field": field, "value": value, "count": count}
                    for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:FILTER_OPTION_LIMIT]
                )
        return {
            "rows": selected,
            "total": len(rows),
            "missing_invoice_rows": sum(
                _status_code(row)
                in {"paid_pending_invoice", "paid_pending_future_invoice", "income_pending_invoice"}
                for row in rows
            ),
            "create_invoice_available_rows": sum(bool(row.get("can_create_invoice")) for row in rows),
            "statistics": _local_statistics(statistics_rows),
            "source_summary": {
                "bank_transaction_rows": source_expense + source_income,
                "expense_rows": source_expense,
                "income_rows": source_income,
                "current_direction_rows": (
                    source_expense + source_income
                    if request["direction"] == "all"
                    else source_expense
                    if request["direction"] == "expense"
                    else source_income
                ),
                "excluded_direction_rows": (
                    0
                    if request["direction"] == "all"
                    else source_income
                    if request["direction"] == "expense"
                    else source_expense
                ),
            },
            "options": options,
            "settings": settings,
        }

    def invoice_candidates(self, request: dict[str, Any]) -> dict[str, Any]:
        kwargs = {
            key: request.get(key)
            for key in (
                "keyword",
                "seller_name",
                "issue_date_from",
                "issue_date_to",
                "amount_min",
                "amount_max",
                "sort_field",
                "sort_direction",
                "page",
                "page_size",
            )
        }
        transaction_ids = list(request["transaction_ids"])
        if len(transaction_ids) == 1:
            payload = self._query_service.invoice_candidates(
                transaction_id=transaction_ids[0],
                **kwargs,
            )
        else:
            payload = self._query_service.invoice_candidates_batch(
                transaction_ids=transaction_ids,
                **kwargs,
            )
        pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
        selection = (
            payload.get("selection_summary")
            if isinstance(payload.get("selection_summary"), dict)
            else {}
        )
        return {
            "rows": list(payload.get("rows") or []),
            "total": int(pagination.get("total") or 0),
            "selected_total": selection.get("bank_total"),
        }

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        return self._query_service.bank_transaction_detail(bank_transaction_id)

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        return self._query_service.invoice_detail(invoice_id)

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        return self._query_service.oa_detail(oa_id)


def _filter_options_payload(
    request: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    options: dict[str, list[dict[str, Any]]] = {field["field"]: [] for field in FILTER_FIELDS}
    for item in list(payload.get("options") or []):
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "")
        value = str(item.get("value") or "")
        if field in options and value:
            options[field].append(
                {"value": value, "label": value, "count": int(item.get("count") or 0)}
            )
    return {
        "direction": request["direction"],
        "filter": request["filter"],
        "fields": [{**field, "options": options[field["field"]]} for field in FILTER_FIELDS],
        "options": options,
    }


class PendingInvoiceCanonicalQueryService:
    def __init__(
        self,
        *,
        repository: Any,
        row_normalizer: Callable[..., list[dict[str, Any]]] | None = None,
    ) -> None:
        self._repository = repository
        self._row_normalizer = row_normalizer

    def rows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        request = _request(query)
        request["_include_statistics"] = bool(request["include_statistics"])
        request["_include_filter_options"] = False
        page = _positive_int(query.get("page", [1])[0], field="page")
        page_size = _positive_int(query.get("page_size", [50])[0], field="page_size")
        if page_size > PAGE_SIZE_LIMIT:
            raise PendingInvoiceError(
                "invalid_pending_invoice_query",
                f"page_size must be between 1 and {PAGE_SIZE_LIMIT}.",
            )
        payload = self._repository.query(request, page=page, page_size=page_size)
        rows = [_compact_page_row(_row_payload(row)) for row in list(payload.get("rows") or [])]
        if callable(self._row_normalizer):
            rows = self._row_normalizer(rows, settings_payload=payload.get("settings"))
        return {
            "direction": request["direction"],
            "filter": request["filter"],
            "rows": rows,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": int(payload.get("total") or 0),
            },
            "summary": {
                "total_rows": int(payload.get("total") or 0),
                "missing_invoice_rows": int(payload.get("missing_invoice_rows") or 0),
                "create_invoice_available_rows": int(payload.get("create_invoice_available_rows") or 0),
                "source_summary": dict(payload.get("source_summary") or {}),
            },
            "statistics": (
                dict(payload.get("statistics") or {})
                if request["_include_statistics"]
                else None
            ),
            "tag_dictionary": bank_transaction_tag_dictionary_display_payload(
                (payload.get("settings") or {}).get("bank_transaction_tags")
            ),
            "filter_options": _filter_options_payload(request, payload),
        }

    def filter_options(self, query: dict[str, list[str]]) -> dict[str, Any]:
        request = _request(query)
        request["_include_statistics"] = False
        request["_include_filter_options"] = True
        payload = self._repository.query(request, page=1, page_size=1)
        return _filter_options_payload(request, payload)

    def all_rows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        request = _request(query)
        request["_include_statistics"] = False
        request["_include_filter_options"] = False
        payload = self._repository.query(
            request,
            page=1,
            page_size=PENDING_INVOICE_EXPORT_ROW_LIMIT + 1,
        )
        total = int(payload.get("total") or 0)
        if total > PENDING_INVOICE_EXPORT_ROW_LIMIT:
            raise PendingInvoiceError(
                "pending_invoice_export_row_limit_exceeded",
                f"导出结果超过 {PENDING_INVOICE_EXPORT_ROW_LIMIT} 行，请缩小筛选范围后重试。",
                details={"total": total, "limit": PENDING_INVOICE_EXPORT_ROW_LIMIT},
            )
        rows = [_compact_page_row(_row_payload(row)) for row in list(payload.get("rows") or [])]
        if callable(self._row_normalizer):
            rows = self._row_normalizer(rows, settings_payload=payload.get("settings"))
        return {"rows": rows, "total": total}

    def invoice_candidates(self, query: dict[str, list[str]]) -> dict[str, Any]:
        transaction_id = str(query.get("transaction_id", [""])[0] or "").strip()
        request = _candidate_request([transaction_id], query)
        payload = self._repository.invoice_candidates(request)
        return {
            "transaction_id": transaction_id,
            "rows": _candidate_rows(payload.get("rows")),
            "pagination": {
                "page": request["page"],
                "page_size": request["page_size"],
                "total": int(payload.get("total") or 0),
            },
        }

    def invoice_candidates_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        transaction_ids = _candidate_transaction_ids(payload.get("transaction_ids"))
        query = {
            key: [value]
            for key, value in payload.items()
            if key != "transaction_ids" and value is not None
        }
        request = _candidate_request(transaction_ids, query)
        result = self._repository.invoice_candidates(request)
        return {
            "transaction_ids": transaction_ids,
            "selection_summary": {
                "transaction_count": len(transaction_ids),
                "bank_total": _money(result.get("selected_total")),
            },
            "rows": _candidate_rows(result.get("rows")),
            "pagination": {
                "page": request["page"],
                "page_size": request["page_size"],
                "total": int(result.get("total") or 0),
            },
        }

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        row = self._repository.bank_transaction_detail(str(bank_transaction_id or "").strip())
        if isinstance(row, dict) and "bank_transaction" in row:
            return row
        if not isinstance(row, dict):
            raise PendingInvoiceError(
                "bank_transaction_not_found",
                f"Bank transaction not found: {bank_transaction_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        amount = _money(row.get("amount"))
        detail = {
            "id": str(row.get("id") or ""),
            "account_no": str(row.get("account_no") or ""),
            "counterparty_name": str(row.get("counterparty_name") or ""),
            "counterparty_account_no": str(row.get("counterparty_account_no") or ""),
            "counterparty_bank_name": str(row.get("counterparty_bank_name") or ""),
            "trade_time": str(row.get("trade_time") or ""),
            "booked_date": str(row.get("booked_date") or ""),
            "debit_amount": amount if row.get("txn_direction") == "outflow" else "0.00",
            "credit_amount": amount if row.get("txn_direction") == "inflow" else "0.00",
            "balance": _money(row.get("balance")) if row.get("balance") is not None else "",
            "currency": str(row.get("currency") or "CNY"),
            "bank_name": str(row.get("bank_name") or ""),
            "account_name": str(row.get("account_name") or ""),
            "summary": str(row.get("summary") or ""),
            "remark": str(row.get("remark") or ""),
            "statement_serial_no": str(row.get("statement_serial_no") or ""),
            "enterprise_serial_no": str(row.get("enterprise_serial_no") or ""),
            "voucher_type": str(row.get("voucher_type") or ""),
            "voucher_no": str(row.get("voucher_no") or ""),
        }
        return {
            "title": detail["counterparty_name"] or detail["id"],
            "subtitle": detail["trade_time"] or detail["booked_date"],
            "detail_available": True,
            "sections": [{"title": "支出流水", "fields": _detail_fields(detail)}],
            "bank_transaction": detail,
        }

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        row = self._repository.invoice_detail(str(invoice_id or "").strip())
        if isinstance(row, dict) and "invoice" in row:
            return row
        if not isinstance(row, dict):
            raise PendingInvoiceError(
                "invoice_not_found",
                f"Invoice detail not found: {invoice_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        detail = {
            "id": str(row.get("id") or ""),
            "invoice_no": str(row.get("invoice_no") or ""),
            "digital_invoice_no": str(row.get("digital_invoice_no") or ""),
            "invoice_code": str(row.get("invoice_code") or ""),
            "issue_date": str(row.get("issue_date") or ""),
            "total_with_tax": _money(row.get("total_with_tax")),
            "seller_name": str(row.get("seller_name") or ""),
            "seller_tax_no": str(row.get("seller_tax_no") or ""),
            "buyer_name": str(row.get("buyer_name") or ""),
            "buyer_tax_no": str(row.get("buyer_tax_no") or ""),
            "tax_amount": _money(row.get("tax_amount")),
            "remark": str(row.get("remark") or ""),
            "invoice_type": str(row.get("invoice_type") or ""),
        }
        return {
            "title": detail["invoice_no"] or detail["digital_invoice_no"] or detail["id"],
            "subtitle": detail["seller_name"],
            "detail_available": True,
            "sections": [{"title": "进项发票", "fields": _detail_fields(detail)}],
            "invoice": detail,
        }

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        normalized_oa_id = str(oa_id or "").strip()
        if not is_valid_pending_invoice_oa_row_id(normalized_oa_id):
            raise PendingInvoiceError(
                "invalid_oa_detail_id",
                "OA detail requires a real OA row id.",
                status_code=HTTPStatus.BAD_REQUEST,
                details={"oa_id": normalized_oa_id},
            )
        row = self._repository.oa_detail(normalized_oa_id)
        if isinstance(row, dict) and "detail_available" in row:
            return row
        if not isinstance(row, dict):
            return {
                "title": normalized_oa_id,
                "oa_id": normalized_oa_id,
                "detail_available": False,
                "unavailable_reason": "OA 投影尚未同步，不能展示完整支付申请。",
                "reason": "OA detail projection is unavailable.",
            }
        detail = {
            "oa_id": normalized_oa_id,
            "applicant": str(row.get("applicant") or ""),
            "application_type": str(row.get("application_type") or ""),
            "project_name": str(row.get("project_name") or ""),
            "workflow_no": str(row.get("workflow_no") or ""),
            "status": str(row.get("status") or ""),
            "amount": _money(row.get("amount")),
            "month": str(row.get("month") or ""),
            "counterparty_name": str(row.get("counterparty_name") or ""),
            "reason": str(row.get("reason") or ""),
        }
        return {
            "title": detail["workflow_no"] or normalized_oa_id,
            "subtitle": detail["project_name"],
            "oa_id": normalized_oa_id,
            "detail_available": True,
            "relation_case_id": str(row.get("relation_case_id") or ""),
            "detail_fields": detail,
            "sections": [{"title": "OA支付申请", "fields": _detail_fields(detail)}],
        }

    def relation_detail(
        self,
        transaction_id: str,
        *,
        direction: str,
        kind: str,
    ) -> dict[str, Any]:
        query = {
            "direction": [direction],
            "filter": ["all"],
            "transaction_id": [transaction_id],
            "page": ["1"],
            "page_size": ["1"],
        }
        payload = self.rows(query)
        rows = list(payload.get("rows") or [])
        if not rows:
            raise PendingInvoiceError(
                "bank_transaction_not_found",
                f"Bank transaction not found: {transaction_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        row = rows[0]
        invoice_payload = row.get("input_invoices") if isinstance(row.get("input_invoices"), dict) else {}
        oa_payload = row.get("oa") if isinstance(row.get("oa"), dict) else {}
        bank_payload = row.get("bank_transactions") if isinstance(row.get("bank_transactions"), dict) else {}
        result = {
            "transaction_summary": dict(bank_payload.get("primary") or {}),
            "related_invoices": list(invoice_payload.get("summaries") or []),
            "invoice_summaries": list(invoice_payload.get("summaries") or []),
            "payment_rows": list(bank_payload.get("summaries") or []),
            "oa_summaries": list(oa_payload.get("summaries") or []),
            "related_oa": list(oa_payload.get("summaries") or []),
            "payment_summary": dict(invoice_payload.get("payment_summary") or {}),
            "relation_case_ids": list(row.get("relation_case_ids") or []),
        }
        normalized_kind = str(kind or "all").strip()
        if normalized_kind == "invoice":
            result["payment_rows"] = []
            result["oa_summaries"] = []
            result["related_oa"] = []
        elif normalized_kind == "oa":
            result["related_invoices"] = []
            result["invoice_summaries"] = []
            result["payment_rows"] = []
        return result


def _candidate_transaction_ids(value: Any) -> list[str]:
    try:
        raw_values = [value] if isinstance(value, str) else list(value or [])
    except TypeError as exc:
        raise PendingInvoiceError("invalid_id_list", "transaction_ids must be a list of ids.") from exc
    result: list[str] = []
    for raw_value in raw_values:
        item = str(raw_value or "").strip()
        if item and item not in result:
            result.append(item)
    if not result:
        raise PendingInvoiceError(
            "invalid_id_list",
            "transaction_ids must include at least one id.",
        )
    return result


def _candidate_request(
    transaction_ids: list[str],
    query: dict[str, list[Any]],
) -> dict[str, Any]:
    normalized_ids = _candidate_transaction_ids(transaction_ids)
    sort_field = str(query.get("sort_field", [""])[0] or "").strip()
    if sort_field and sort_field not in INVOICE_CANDIDATE_SORT_FIELDS:
        raise PendingInvoiceError(
            "invalid_sort_field",
            f"Unsupported candidate sort field: {sort_field}",
            details={"field": sort_field},
        )
    sort_direction = str(query.get("sort_direction", ["asc"])[0] or "asc").strip().lower()
    if sort_direction not in {"asc", "desc"}:
        raise PendingInvoiceError(
            "invalid_sort_direction",
            "sort_direction must be asc or desc.",
        )
    amount_min = _optional_decimal(query.get("amount_min", [None])[0])
    amount_max = _optional_decimal(query.get("amount_max", [None])[0])
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise PendingInvoiceError(
            "invalid_amount",
            "amount_min must not be greater than amount_max.",
        )
    page = _positive_int(query.get("page", [1])[0], field="page")
    page_size = _positive_int(query.get("page_size", [50])[0], field="page_size")
    if page_size > PAGE_SIZE_LIMIT:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            f"page_size must be between 1 and {PAGE_SIZE_LIMIT}.",
        )
    issue_date_from = _date_value(
        query.get("issue_date_from", [None])[0],
        field="issue_date_from",
    )
    issue_date_to = _date_value(
        query.get("issue_date_to", [None])[0],
        field="issue_date_to",
    )
    if issue_date_from and issue_date_to and issue_date_from > issue_date_to:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            "issue_date_from must not be after issue_date_to.",
        )
    return {
        "transaction_ids": normalized_ids,
        "keyword": str(query.get("keyword", [""])[0] or "").strip(),
        "seller_name": str(query.get("seller_name", [""])[0] or "").strip(),
        "issue_date_from": issue_date_from,
        "issue_date_to": issue_date_to,
        "amount_min": amount_min,
        "amount_max": amount_max,
        "sort_field": sort_field,
        "sort_direction": sort_direction,
        "page": page,
        "page_size": page_size,
    }


def _candidate_order_sql(sort_field: str, sort_direction: str) -> str:
    if sort_field:
        return (
            f"{CANDIDATE_SORT_EXPRESSIONS[sort_field]} {sort_direction}, "
            "invoice_id asc"
        )
    return (
        "case candidate_status "
        "when 'available' then 0 when 'already_related' then 1 else 2 end asc, "
        "amount_difference_abs asc, issue_date desc nulls last, invoice_id asc"
    )


def _candidate_rows(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw_row in list(value or []):
        if not isinstance(raw_row, dict):
            continue
        row = dict(raw_row)
        for field in (
            "total_with_tax",
            "paid_total",
            "related_paid_total",
            "remaining_amount",
            "amount_difference_abs",
        ):
            row[field] = _money(row.get(field))
        result.append(row)
    return result


def _optional_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise PendingInvoiceError(
            "invalid_amount",
            "amount filters must be valid decimal values.",
        ) from exc


def _detail_fields(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": str(key), "value": "" if value is None else str(value)}
        for key, value in payload.items()
        if str(value or "").strip()
    ]


def _request(query: dict[str, list[str]]) -> dict[str, Any]:
    direction = str(query.get("direction", ["expense"])[0] or "expense").strip()
    filter_name = str(query.get("filter", ["all"])[0] or "all").strip()
    if direction not in {"all", "expense", "income"}:
        raise PendingInvoiceError(
            "invalid_direction",
            "direction must be expense, income or all.",
        )
    if direction == "all" and filter_name != "all":
        raise PendingInvoiceError(
            "invalid_filter",
            "all direction only supports filter=all.",
        )
    if filter_name != "all" and not pending_invoice_filter_status_codes(
        direction=direction,
        filter_name=filter_name,
    ):
        raise PendingInvoiceError(
            "invalid_filter",
            "filter must be all or a supported pending invoice group.",
        )
    date_from = _date_value(query.get("date_from", [None])[0], field="date_from")
    date_to = _date_value(query.get("date_to", [None])[0], field="date_to")
    if date_from and date_to and date_from > date_to:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            "date_from must not be after date_to.",
        )
    sort_field = str(query.get("sort_field", ["trade_date"])[0] or "trade_date").strip()
    if sort_field not in SORT_EXPRESSIONS:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            f"unsupported pending invoice sort field: {sort_field}",
        )
    sort_direction = str(query.get("sort_direction", ["desc"])[0] or "desc").strip().lower()
    if sort_direction not in {"asc", "desc"}:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            "sort_direction must be asc or desc.",
        )
    filters = _filters(query.get("filters", [None])[0])
    include_statistics = str(
        query.get("include_statistics", ["true"])[0] or "true"
    ).strip().lower()
    if include_statistics not in {"true", "false"}:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            "include_statistics must be true or false.",
        )
    return {
        "direction": direction,
        "filter": filter_name,
        "date_from": date_from,
        "date_to": date_to,
        "keyword": str(query.get("keyword", [""])[0] or "").strip(),
        "filters": filters,
        "sort_field": sort_field,
        "sort_direction": sort_direction,
        "transaction_id": str(query.get("transaction_id", [""])[0] or "").strip(),
        "include_statistics": include_statistics == "true",
    }


def _where_sql(request: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    direction = str(request["direction"])
    filter_name = str(request["filter"])
    if direction != "all":
        clauses.append("direction = %s")
        params.append(direction)
    if filter_name != "all":
        clauses.append("status_code = any(%s::text[])")
        params.append(list(pending_invoice_filter_status_codes(direction=direction, filter_name=filter_name)))
    if request.get("date_from"):
        clauses.append("trade_date >= %s::date")
        params.append(request["date_from"])
    if request.get("date_to"):
        clauses.append("trade_date <= %s::date")
        params.append(request["date_to"])
    if request.get("keyword"):
        clauses.append("searchable_text ilike %s")
        params.append(f"%{request['keyword']}%")
    if request.get("transaction_id"):
        clauses.append("row_id = %s")
        params.append(request["transaction_id"])
    for item in list(request.get("filters") or []):
        field = str(item["field"])
        operator = str(item["operator"])
        expression = FILTER_EXPRESSIONS[field]
        if operator == "contains":
            clauses.append(f"{expression} ilike %s")
            params.append(f"%{item.get('value') or ''}%")
        elif operator == "in":
            values = [str(value).strip() for value in list(item.get("values") or []) if str(value).strip()]
            if values:
                clauses.append(f"{expression} = any(%s::text[])")
                params.append(values)
        elif operator == "between":
            bounds = item.get("value") if isinstance(item.get("value"), dict) else {}
            if field in {"amount", "invoice_total"}:
                if bounds.get("min") not in (None, ""):
                    clauses.append(f"{expression} >= %s::numeric")
                    params.append(str(bounds["min"]).replace(",", ""))
                if bounds.get("max") not in (None, ""):
                    clauses.append(f"{expression} <= %s::numeric")
                    params.append(str(bounds["max"]).replace(",", ""))
            else:
                if bounds.get("from"):
                    clauses.append(f"{expression} >= %s::date")
                    params.append(bounds["from"])
                if bounds.get("to"):
                    clauses.append(f"{expression} <= %s::date")
                    params.append(bounds["to"])
        elif operator == "eq":
            clauses.append(f"{expression} = %s::numeric")
            params.append(str(item.get("value") or "0").replace(",", ""))
    return " and ".join(clauses) if clauses else "true", params


def _source_where_sql(request: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if request.get("date_from"):
        clauses.append("trade_date >= %s::date")
        params.append(request["date_from"])
    if request.get("date_to"):
        clauses.append("trade_date <= %s::date")
        params.append(request["date_to"])
    return " and ".join(clauses) if clauses else "true", params


def _order_sql(request: dict[str, Any]) -> str:
    expression = SORT_EXPRESSIONS[str(request["sort_field"])]
    direction = str(request["sort_direction"]).upper()
    return f"{expression} {direction} nulls last, row_id ASC"


def _filters(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            "pending invoice filters must be valid JSON.",
        ) from exc
    if not isinstance(parsed, list):
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            "pending invoice filters must be a list.",
        )
    result: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise PendingInvoiceError(
                "invalid_pending_invoice_query",
                "pending invoice filter must be an object.",
            )
        field = str(item.get("field") or "")
        operator = str(item.get("operator") or "")
        if field not in PENDING_INVOICE_FILTER_FIELDS or operator not in PENDING_INVOICE_FILTER_FIELDS[field]:
            raise PendingInvoiceError(
                "invalid_pending_invoice_query",
                f"unsupported pending invoice filter: {field}/{operator}",
            )
        result.append(dict(item))
    return result


def _positive_int(value: Any, *, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            f"{field} must be a positive integer.",
        ) from exc
    if parsed < 1:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            f"{field} must be a positive integer.",
        )
    return parsed


def _date_value(value: Any, *, field: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise PendingInvoiceError(
            "invalid_pending_invoice_query",
            f"{field} must be YYYY-MM-DD.",
        ) from exc


def _row_payload(row: dict[str, Any]) -> dict[str, Any]:
    if "bank_transaction" in row:
        return dict(row)
    direction = str(row.get("direction") or "expense")
    invoice_summaries = [
        dict(item)
        for item in list(row.get("invoice_summaries") or [])
        if isinstance(item, dict)
        and str(item.get("invoice_type") or "") == ("input" if direction == "expense" else "output")
    ]
    oa_summaries = [dict(item) for item in list(row.get("oa_summaries") or []) if isinstance(item, dict)]
    bank_summaries = [dict(item) for item in list(row.get("bank_summaries") or []) if isinstance(item, dict)]
    amount = _money(row.get("amount"))
    invoice_total = _money(sum((_decimal(item.get("total_with_tax")) for item in invoice_summaries), Decimal("0")))
    paid_total = _money(row.get("paid_total"))
    difference = _decimal(invoice_total) - _decimal(paid_total)
    payment_summary = {
        "invoice_total": invoice_total,
        "paid_total": paid_total,
        "remaining_amount": _money(max(difference, Decimal("0"))),
        "difference_amount": _money(difference),
        "payment_transaction_count": int(row.get("payment_transaction_count") or len(bank_summaries) or 1),
    }
    category = {
        "category_code": row.get("category_code"),
        "category_label": row.get("category_label"),
        "category_primary_label": row.get("category_primary_label"),
        "category_sub_label": row.get("category_sub_label"),
        "category_label_path": [
            value
            for value in [row.get("category_primary_label"), row.get("category_sub_label")]
            if str(value or "").strip()
        ],
    }
    category = pending_invoice_effective_category_payload(category)
    group = str(row.get("filter_group") or "all")
    matched_rule = (
        {
            "group": group,
            "tag_code": category.get("category_code"),
            "tag_label": category.get("category_label"),
            "tag_primary_label": category.get("category_primary_label"),
            "tag_sub_label": category.get("category_sub_label"),
            "tag_label_path": list(category.get("category_label_path") or []),
        }
        if group != "all"
        else None
    )
    status_override = (
        {"status_code": row.get("income_override_status")}
        if row.get("income_override_status")
        else None
    )
    status = pending_invoice_status_payload(
        direction=direction,
        group=None if group == "all" else group,
        has_invoices=bool(invoice_summaries),
        payment_summary=payment_summary,
        matched_rule=matched_rule,
        status_override=status_override,
    )
    if str(status.get("code") or "") != str(row.get("status_code") or ""):
        raise RuntimeError("pending invoice SQL status classification diverged from domain policy")
    can_create_invoice = (
        direction == "expense"
        and not invoice_summaries
        and group != "no_invoice_required"
    )
    account_no = str(row.get("account_no") or "")
    bank_transaction = {
        "id": str(row.get("row_id") or ""),
        "account_no": account_no,
        "counterparty_name": str(row.get("counterparty_name") or ""),
        "counterparty_account_no": str(row.get("counterparty_account_no") or ""),
        "counterparty_bank_name": str(row.get("counterparty_bank_name") or ""),
        "trade_time": str(row.get("trade_time") or ""),
        "booked_date": str(row.get("trade_date") or ""),
        "trade_date": str(row.get("trade_date") or ""),
        "amount": amount,
        "debit_amount": amount if direction == "expense" else "0.00",
        "credit_amount": amount if direction == "income" else "0.00",
        "balance": _money(row.get("balance")),
        "currency": str(row.get("currency") or "CNY"),
        "bank_name": str(row.get("bank_name") or ""),
        "bank_short_name": str(row.get("bank_short_name") or ""),
        "account_name": str(row.get("account_name") or ""),
        "account_last4": "".join(character for character in account_no if character.isdigit())[-4:],
        "summary": str(row.get("summary") or ""),
        "remark": str(row.get("remark") or ""),
        "statement_serial_no": str(row.get("bank_serial_no") or ""),
        "enterprise_serial_no": "",
        "voucher_type": "",
        "voucher_no": "",
        "effective_tag_code": category.get("category_code"),
        "effective_tag_label": category.get("category_label"),
        "effective_tag_primary_label": category.get("category_primary_label"),
        "effective_tag_sub_label": category.get("category_sub_label"),
        "effective_tag_label_path": list(category.get("category_label_path") or []),
    }
    if not bank_summaries:
        bank_summaries = [
            {
                "id": bank_transaction["id"],
                "trade_time": bank_transaction["trade_time"],
                "counterparty_name": bank_transaction["counterparty_name"],
                "amount": amount,
                "debit_amount": bank_transaction["debit_amount"],
                "credit_amount": bank_transaction["credit_amount"],
                "summary": bank_transaction["summary"],
                "remark": bank_transaction["remark"],
                "statement_serial_no": bank_transaction["statement_serial_no"],
                "account_name": bank_transaction["account_name"],
                "account_last4": bank_transaction["account_last4"],
                "relation_status": "unlinked",
            }
        ]
    return {
        "id": bank_transaction["id"],
        "bank_transactions": {
            "primary": bank_transaction,
            "relation_count": len(bank_summaries),
            "has_multiple": len(bank_summaries) > 1,
            "summaries": bank_summaries if len(bank_summaries) > 1 else [],
            "payment_summary": {"paid_total": paid_total},
        },
        "invoice_acquisition_status": status,
        "input_invoices": {
            "primary": invoice_summaries[0] if invoice_summaries else None,
            "relation_count": len(invoice_summaries),
            "linked_relation_count": len(invoice_summaries),
            "has_multiple": len(invoice_summaries) > 1,
            "summaries": invoice_summaries if len(invoice_summaries) > 1 else [],
            "payment_summary": payment_summary,
        },
        "oa": {
            "primary": oa_summaries[0] if oa_summaries else None,
            "relation_count": len(oa_summaries),
            "has_multiple": len(oa_summaries) > 1,
            "detail_available": any(bool(item.get("detail_available")) for item in oa_summaries),
            "summaries": oa_summaries if len(oa_summaries) > 1 else [],
        },
        "can_create_invoice": can_create_invoice,
        "available_actions": pending_invoice_available_actions(
            status,
            can_create_invoice=can_create_invoice,
        ),
        "relation_case_ids": list(row.get("relation_case_ids") or []),
    }


def _compact_page_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    legacy_bank = payload.get("bank_transaction")
    bank_group = payload.get("bank_transactions")
    if not isinstance(bank_group, dict):
        bank_group = {}
    if not isinstance(bank_group.get("primary"), dict) and isinstance(legacy_bank, dict):
        bank_group["primary"] = dict(legacy_bank)
    legacy_invoices = [
        dict(item)
        for item in list(payload.get("invoices") or [])
        if isinstance(item, dict)
    ]
    invoice_group = payload.get("input_invoices")
    if not isinstance(invoice_group, dict):
        invoice_group = {}
    if not isinstance(invoice_group.get("primary"), dict) and legacy_invoices:
        invoice_group["primary"] = legacy_invoices[0]
    if not list(invoice_group.get("summaries") or []) and len(legacy_invoices) > 1:
        invoice_group["summaries"] = legacy_invoices
    payload["bank_transactions"] = bank_group
    payload["input_invoices"] = invoice_group
    for legacy_field in ("bank_transaction", "invoices", "oa_applicant"):
        payload.pop(legacy_field, None)
    return payload


def _local_row_matches(row: dict[str, Any], request: dict[str, Any]) -> bool:
    direction = str(row.get("_direction") or "")
    if request["direction"] != "all" and request["direction"] != direction:
        return False
    if request["filter"] != "all" and _status_code(row) not in pending_invoice_filter_status_codes(
        direction=direction,
        filter_name=str(request["filter"]),
    ):
        return False
    trade_date = str(PendingInvoiceQueryService._row_field_value(row, "trade_date") or "")[:10]
    if request.get("date_from") and trade_date < request["date_from"]:
        return False
    if request.get("date_to") and trade_date > request["date_to"]:
        return False
    keyword = str(request.get("keyword") or "").casefold()
    if keyword and keyword not in json.dumps(row, ensure_ascii=False).casefold():
        return False
    if request.get("transaction_id") and row.get("id") != request["transaction_id"]:
        return False
    for item in list(request.get("filters") or []):
        value = PendingInvoiceQueryService._row_field_value(row, str(item["field"]))
        operator = str(item["operator"])
        if operator == "contains" and str(item.get("value") or "").casefold() not in str(value or "").casefold():
            return False
        if operator == "in" and str(value or "") not in {str(option) for option in list(item.get("values") or [])}:
            return False
        if operator == "between":
            bounds = item.get("value") if isinstance(item.get("value"), dict) else {}
            if item["field"] in {"amount", "invoice_total"}:
                number = _decimal(value)
                if bounds.get("min") not in (None, "") and number < _decimal(bounds["min"]):
                    return False
                if bounds.get("max") not in (None, "") and number > _decimal(bounds["max"]):
                    return False
            elif bounds.get("from") and str(value or "") < str(bounds["from"]):
                return False
            elif bounds.get("to") and str(value or "") > str(bounds["to"]):
                return False
    return True


def _local_sort_value(row: dict[str, Any], field: str) -> tuple[int, Any]:
    value = PendingInvoiceQueryService._row_field_value(row, field)
    if field in {"amount", "invoice_total"}:
        return 0, _decimal(value)
    return 0, str(value or "")


def _status_code(row: dict[str, Any]) -> str:
    status = row.get("invoice_acquisition_status")
    return str(status.get("code") or "") if isinstance(status, dict) else ""


def _local_statistics(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "bank_transaction_count": len(rows),
        "expense_transaction_count": sum(row.get("_direction") == "expense" for row in rows),
        "income_transaction_count": sum(row.get("_direction") == "income" for row in rows),
        "found_invoice_transaction_count": sum(
            bool((row.get("input_invoices") or {}).get("summaries"))
            for row in rows
            if isinstance(row.get("input_invoices"), dict)
        ),
        "pending_invoice_transaction_count": sum(
            _status_code(row)
            in {"paid_pending_invoice", "paid_pending_future_invoice", "income_pending_invoice"}
            for row in rows
        ),
        "no_invoice_required_transaction_count": sum(
            _status_code(row) in {"no_invoice_required", "income_no_invoice_required"}
            for row in rows
        ),
        "cash_income_transaction_count": sum(_status_code(row) == "cash_income" for row in rows),
        "linked_oa_transaction_count": sum(
            bool((row.get("oa") or {}).get("summaries"))
            for row in rows
            if isinstance(row.get("oa"), dict)
        ),
        "linked_input_invoice_transaction_count": sum(
            row.get("_direction") == "expense"
            and isinstance(row.get("input_invoices"), dict)
            and bool((row.get("input_invoices") or {}).get("summaries"))
            for row in rows
        ),
        "linked_output_invoice_transaction_count": sum(
            row.get("_direction") == "income"
            and isinstance(row.get("input_invoices"), dict)
            and bool((row.get("input_invoices") or {}).get("summaries"))
            for row in rows
        ),
    }


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _money(value: Any) -> str:
    return f"{_decimal(value):.2f}"
