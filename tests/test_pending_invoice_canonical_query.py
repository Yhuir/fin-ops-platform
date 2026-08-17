from __future__ import annotations

import json
import unittest

from fin_ops_platform.services.pending_invoice_canonical_query import (
    BANK_DETAIL_SQL,
    CANDIDATE_QUERY_SQL,
    INVOICE_DETAIL_SQL,
    OA_DETAIL_SQL,
    PAGE_QUERY_SQL,
    RELATION_DETAIL_SQL,
    PendingInvoiceCanonicalQueryService,
    PostgresPendingInvoiceCanonicalRepository,
    _rule_required_fields,
)
from fin_ops_platform.services.pending_invoice_service import PendingInvoiceError


class _RecordingTransaction:
    def __init__(self, result: dict[str, object] | None = None) -> None:
        self.commands: list[tuple[str, tuple[object, ...]]] = []
        self.result = result or {
            "rows": [],
            "total": 0,
            "missing_invoice_rows": 0,
            "create_invoice_available_rows": 0,
            "statistics": {},
            "source_summary": {},
            "options": [],
        }

    def __enter__(self) -> "_RecordingTransaction":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.commands.append((sql, params))

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        self.commands.append((sql, params))
        if "from app.app_settings" in sql:
            return {"settings_payload": {}}
        return dict(self.result)


class _RecordingConnection:
    def __init__(self, result: dict[str, object] | None = None) -> None:
        self.transaction_state = _RecordingTransaction(result)

    def transaction(self) -> _RecordingTransaction:
        return self.transaction_state


class _PageRepository:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or {
            "rows": [],
            "total": 0,
            "missing_invoice_rows": 0,
            "create_invoice_available_rows": 0,
            "statistics": {},
            "source_summary": {},
            "options": [],
            "settings": {},
        }
        self.calls: list[tuple[dict[str, object], int, int]] = []
        self.candidate_payload: dict[str, object] = {
            "rows": [],
            "total": 0,
            "selected_total": "0.00",
        }
        self.candidate_request: dict[str, object] = {}
        self.relation_payload: dict[str, object] = {
            "bank_rows": [],
            "invoice_rows": [],
            "oa_rows": [],
        }
        self.bank_detail_payload: dict[str, object] | None = None
        self.invoice_detail_payload: dict[str, object] | None = None
        self.oa_detail_payload: dict[str, object] | None = None

    def query(
        self,
        request: dict[str, object],
        *,
        page_size: int,
        page: int,
    ) -> dict[str, object]:
        self.calls.append((dict(request), page_size, page))
        return dict(self.payload)

    def invoice_candidates(self, request: dict[str, object]) -> dict[str, object]:
        self.candidate_request = dict(request)
        return dict(self.candidate_payload)

    def bank_transaction_detail(self, _object_id: str) -> dict[str, object] | None:
        return dict(self.bank_detail_payload) if self.bank_detail_payload is not None else None

    def invoice_detail(self, _object_id: str) -> dict[str, object] | None:
        return dict(self.invoice_detail_payload) if self.invoice_detail_payload is not None else None

    def oa_detail(self, _object_id: str) -> dict[str, object] | None:
        return dict(self.oa_detail_payload) if self.oa_detail_payload is not None else None

    def relation_detail(self, _object_id: str, *, direction: str, kind: str) -> dict[str, object]:
        del direction, kind
        return dict(self.relation_payload)


class PendingInvoiceCanonicalRepositoryTests(unittest.TestCase):
    def test_relation_detail_uses_one_bounded_snapshot_query_without_technical_oa_number_fallback(self) -> None:
        connection = _RecordingConnection({"bank_rows": [], "invoice_rows": [], "oa_rows": []})
        repository = PostgresPendingInvoiceCanonicalRepository(connection)

        payload = repository.relation_detail("bank-1", direction="expense", kind="oa")

        commands = connection.transaction_state.commands
        self.assertEqual(commands[0][0], "set transaction isolation level repeatable read read only")
        selects = [sql for sql, _params in commands if sql.lstrip().lower().startswith(("select", "with"))]
        self.assertEqual(len(selects), 1)
        self.assertIsNotNone(payload)
        self.assertIn("join app.bank_transactions", RELATION_DETAIL_SQL)
        self.assertIn("join app.invoices", RELATION_DETAIL_SQL)
        self.assertIn("join app.oa_applications", RELATION_DETAIL_SQL)
        self.assertIn("join app.oa_pending_payment_admissions", RELATION_DETAIL_SQL)
        self.assertNotIn("coalesce(oa.workflow_no, oa.form_id", PAGE_QUERY_SQL)

    def test_uses_one_read_only_repeatable_read_snapshot_and_fixed_query_count(self) -> None:
        connection = _RecordingConnection()
        service = PendingInvoiceCanonicalQueryService(
            repository=PostgresPendingInvoiceCanonicalRepository(connection)
        )

        payload = service.rows(
            {
                "direction": ["expense"],
                "filter": ["all"],
                "page": ["2"],
                "page_size": ["50"],
            }
        )

        commands = connection.transaction_state.commands
        self.assertEqual(
            commands[0][0],
            "set transaction isolation level repeatable read read only",
        )
        self.assertEqual(commands[1][0], "set local jit = off")
        self.assertEqual(commands[2][0], "set local max_parallel_workers_per_gather = 0")
        self.assertEqual(len([sql for sql, _params in commands if sql.lstrip().lower().startswith(("select", "with"))]), 2)
        page_sql, page_params = commands[4]
        self.assertIn("from app.bank_transactions", page_sql)
        self.assertIn("from app.bank_transaction_categories", page_sql)
        self.assertIn("bank_legacy_identities as materialized", page_sql)
        self.assertIn("manual_category_candidates as materialized", page_sql)
        self.assertIn("confirmed_category_candidates as materialized", page_sql)
        self.assertNotIn("category.bank_transaction_id = bank.canonical_id\n      or", page_sql)
        self.assertNotIn("confirmation.bank_transaction_id = bank.canonical_id\n      or", page_sql)
        self.assertIn("app.invoices", page_sql)
        rule_source_sql = page_sql.split("rule_banks as materialized", 1)[1].split(
            "compiled_rule_matches as materialized", 1
        )[0]
        self.assertNotIn("bank.*", rule_source_sql)
        self.assertIn("app.oa_applications", page_sql)
        self.assertIn("from app.workbench_pair_relations", page_sql)
        self.assertIn("relation_case_bank_facts as materialized", page_sql)
        self.assertIn("jsonb_path_query_array", page_sql)
        self.assertNotIn("from bank_case_members member", page_sql)
        self.assertIn("r.status = 'active'", page_sql)
        self.assertIn("r.relation_mode <> 'turnover_manual_closure'", page_sql)
        self.assertIn("as rule_counterparty_name", page_sql)
        self.assertIn("as rule_account_type", page_sql)
        self.assertIn("compiled_rule_matches as materialized", page_sql)
        self.assertIn("page_keys as materialized", page_sql)
        self.assertIn("join classified row on row.row_id = page.row_id", page_sql)
        self.assertNotIn("select *\n    from classified\n    where", page_sql)
        self.assertIn("effective_categories as (", page_sql)
        effective_sql = page_sql.split("effective_categories as (", 1)[1].split("enriched as (", 1)[0]
        self.assertNotIn("and internal.row_id is null", effective_sql)
        self.assertNotIn("and auto.definition is null", effective_sql)
        self.assertIn("auto.definition->>'code' = 'external_turnover'", effective_sql)
        self.assertIn("enriched as (", page_sql)
        self.assertIn("classified_source as (", page_sql)
        self.assertNotIn("effective_categories as materialized", page_sql)
        self.assertNotIn("enriched as materialized", page_sql)
        self.assertNotIn("classified_source as materialized", page_sql)
        self.assertNotIn("__RULE_MATCH_SQL__", page_sql)
        self.assertNotIn("raw_rule_definitions as materialized", page_sql)
        self.assertNotIn("rule_definitions as materialized", page_sql)
        self.assertNotIn("read_model.", page_sql)
        self.assertEqual(json.loads(str(page_params[0]))["scan_direction"], "all")
        self.assertEqual(page_params[-8:-6], (50, 50))
        self.assertIs(page_params[-6], True)
        self.assertIs(page_params[-5], False)
        self.assertEqual(payload["pagination"], {"page": 2, "page_size": 50, "total": 0})
        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("source_versions", payload)

    def test_without_statistics_scans_only_the_requested_direction(self) -> None:
        connection = _RecordingConnection()
        service = PendingInvoiceCanonicalQueryService(
            repository=PostgresPendingInvoiceCanonicalRepository(connection)
        )

        service.rows(
            {
                "direction": ["expense"],
                "filter": ["all"],
                "include_statistics": ["false"],
            }
        )

        _page_sql, page_params = connection.transaction_state.commands[4]
        self.assertEqual(json.loads(str(page_params[0]))["scan_direction"], "expense")
        self.assertIs(page_params[-6], False)

    def test_compacts_common_transaction_text_rule_scans_without_cross_field_matches(self) -> None:
        class RuleTransaction(_RecordingTransaction):
            def fetch_one(
                self,
                sql: str,
                params: tuple[object, ...] = (),
            ) -> dict[str, object]:
                self.commands.append((sql, params))
                if "from app.app_settings" in sql:
                    return {
                        "settings_payload": {
                            "bank_transaction_tags": {
                                "definitions": [
                                    {
                                        "code": "expense-fee",
                                        "direction": "expense",
                                        "status": "active",
                                        "rules": {
                                            "match_fields": [
                                                "detail_text",
                                                "note_text",
                                                "purpose_text",
                                                "summary_text",
                                            ],
                                            "contains_any": ["服务费", "\u0001"],
                                        },
                                    }
                                ]
                            }
                        }
                    }
                return dict(self.result)

        connection = _RecordingConnection()
        connection.transaction_state = RuleTransaction()
        service = PendingInvoiceCanonicalQueryService(
            repository=PostgresPendingInvoiceCanonicalRepository(connection)
        )

        service.rows(
            {
                "direction": ["expense"],
                "filter": ["all"],
                "include_statistics": ["false"],
            }
        )

        page_sql, _page_params = connection.transaction_state.commands[4]
        self.assertIn("as norm_transaction_text", page_sql)
        self.assertIn("strpos(base.norm_transaction_text, %s) > 0", page_sql)
        self.assertIn("strpos(base.norm_detail_text, %s) > 0", page_sql)
        self.assertIn("strpos(base.norm_note_text, %s) > 0", page_sql)
        self.assertIn("strpos(base.norm_purpose_text, %s) > 0", page_sql)
        self.assertIn("strpos(base.norm_summary_text, %s) > 0", page_sql)

    def test_candidate_repository_uses_one_snapshot_and_two_bounded_selects(self) -> None:
        class CandidateTransaction(_RecordingTransaction):
            def fetch_one(
                self,
                sql: str,
                params: tuple[object, ...] = (),
            ) -> dict[str, object]:
                self.commands.append((sql, params))
                if "found_count" in sql:
                    return {
                        "found_count": 1,
                        "expense_count": 1,
                        "selected_total": "118.00",
                    }
                return {"rows": [], "total": 0}

        connection = _RecordingConnection()
        connection.transaction_state = CandidateTransaction()
        repository = PostgresPendingInvoiceCanonicalRepository(connection)

        payload = repository.invoice_candidates(
            {
                "transaction_ids": ["bank-1"],
                "keyword": "",
                "seller_name": "",
                "issue_date_from": None,
                "issue_date_to": None,
                "amount_min": None,
                "amount_max": None,
                "sort_field": "",
                "sort_direction": "asc",
                "page": 1,
                "page_size": 50,
            }
        )

        commands = connection.transaction_state.commands
        self.assertEqual(commands[0][0], "set transaction isolation level repeatable read read only")
        self.assertEqual(
            len(
                [
                    sql
                    for sql, _params in commands
                    if sql.lstrip().lower().startswith(("select", "with"))
                ]
            ),
            2,
        )
        self.assertIn("limit %s offset %s", commands[2][0].lower())
        self.assertNotIn("read_model.", commands[2][0])
        self.assertEqual(payload, {"rows": [], "total": 0, "selected_total": "118.00"})

    def test_query_template_is_bounded_and_has_no_forbidden_page_fact_sources(self) -> None:
        self.assertIn("limit %s offset %s", PAGE_QUERY_SQL.lower())
        self.assertIn("scope_summary as (", PAGE_QUERY_SQL.lower())
        self.assertIn("from bank_source\n    where __source_where_sql__", PAGE_QUERY_SQL.lower())
        self.assertNotIn("select count(*)::integer from scope_rows", PAGE_QUERY_SQL.lower())
        self.assertNotIn("read_model.pending_invoice", PAGE_QUERY_SQL)
        self.assertNotIn("read_model.bank_detail", PAGE_QUERY_SQL)
        self.assertNotIn("read_model.workbench_relation", PAGE_QUERY_SQL)
        self.assertNotIn("read_model.search", PAGE_QUERY_SQL)
        self.assertIn("source.amount::text", PAGE_QUERY_SQL)
        self.assertIn("source.balance::text", PAGE_QUERY_SQL)
        self.assertIn("coalesce(invoice.total_with_tax, invoice.amount)::text", CANDIDATE_QUERY_SQL)
        self.assertIn("limit %s offset %s", CANDIDATE_QUERY_SQL.lower())
        self.assertIn("from app.invoices", CANDIDATE_QUERY_SQL)
        self.assertIn("from app.workbench_pair_relations", CANDIDATE_QUERY_SQL)
        self.assertIn("status = 'active'", CANDIDATE_QUERY_SQL)
        self.assertIn("relation_mode <> 'turnover_manual_closure'", CANDIDATE_QUERY_SQL)
        for sql in (CANDIDATE_QUERY_SQL, BANK_DETAIL_SQL, INVOICE_DETAIL_SQL, OA_DETAIL_SQL):
            self.assertNotIn("read_model.", sql)

    def test_rule_match_hot_path_reuses_precomputed_normalized_arrays(self) -> None:
        banks_sql = PAGE_QUERY_SQL.split(
            "banks as materialized (",
            maxsplit=1,
        )[1].split(
            "active_relations as materialized (",
            maxsplit=1,
        )[0]
        rule_banks_sql = PAGE_QUERY_SQL.split(
            "rule_banks as materialized (",
            maxsplit=1,
        )[1].split(
            "rule_matches as materialized (",
            maxsplit=1,
        )[0]
        rule_match_sql = PAGE_QUERY_SQL.split(
            "compiled_rule_matches as materialized (",
            maxsplit=1,
        )[1].split(
            "winning_rule_priority as materialized (",
            maxsplit=1,
        )[0]

        self.assertNotIn("normalize(", banks_sql)
        self.assertIn("normalize(", rule_banks_sql)
        self.assertIn("scan_direction", rule_banks_sql)
        self.assertIn("config.payload->'rule_fields'", rule_banks_sql)
        self.assertNotIn("bank.*", rule_banks_sql)
        self.assertIn("bank.row_id", rule_banks_sql)
        self.assertIn("__RULE_MATCH_SQL__", rule_match_sql)
        self.assertNotIn("cross join lateral", rule_match_sql)
        self.assertNotIn("jsonb_array_elements_text", rule_match_sql)
        self.assertNotIn("normalize(", rule_match_sql)
        self.assertNotIn("regexp_replace(", rule_match_sql)

    def test_rule_field_plan_only_normalizes_fields_used_by_active_rules(self) -> None:
        fields = _rule_required_fields(
            [
                {
                    "status": "active",
                    "rules": {"match_fields": ["summary_text", "counterparty_name"]},
                    "account_scope": {"type": "bank", "values": ["建设银行"]},
                },
                {
                    "status": "archived",
                    "rules": {"match_fields": ["all_text"]},
                },
            ]
        )

        self.assertEqual(fields, ["bank", "counterparty_name", "summary_text"])


class PendingInvoiceCanonicalQueryServiceTests(unittest.TestCase):
    def test_empty_set_keeps_summary_statistics_facets_and_canonical_contract(self) -> None:
        repository = _PageRepository(
            {
                "rows": [],
                "total": 0,
                "missing_invoice_rows": 0,
                "create_invoice_available_rows": 0,
                "statistics": {"bank_transaction_count": 0},
                "source_summary": {
                    "bank_transaction_rows": 0,
                    "expense_rows": 0,
                    "income_rows": 0,
                    "current_direction_rows": 0,
                    "excluded_direction_rows": 0,
                },
                "options": [
                    {"field": "counterparty_name", "value": "云南供应商", "count": 2}
                ],
                "settings": {},
            }
        )
        service = PendingInvoiceCanonicalQueryService(repository=repository)

        payload = service.rows({"direction": ["all"], "filter": ["all"]})

        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["summary"]["total_rows"], 0)
        self.assertEqual(payload["statistics"], {"bank_transaction_count": 0})
        self.assertEqual(
            payload["filter_options"]["options"]["counterparty_name"],
            [{"value": "云南供应商", "label": "云南供应商", "count": 2}],
        )
        self.assertEqual(len(repository.calls), 1)
        self.assertNotIn("read_model_status", payload)

    def test_rejects_invalid_direction_filter_sort_dates_filters_and_pagination(self) -> None:
        service = PendingInvoiceCanonicalQueryService(repository=_PageRepository())
        invalid_queries = (
            {"direction": ["sideways"]},
            {"direction": ["all"], "filter": ["requires_invoice"]},
            {"direction": ["expense"], "sort_field": ["created_at"]},
            {"direction": ["expense"], "sort_direction": ["sideways"]},
            {"direction": ["expense"], "date_from": ["2026-13-40"]},
            {"direction": ["expense"], "date_from": ["2026-05-02"], "date_to": ["2026-05-01"]},
            {"direction": ["expense"], "filters": ['{"field":"amount"}']},
            {"direction": ["expense"], "filters": ['[{"field":"unknown","operator":"in","values":[]}]']},
            {"direction": ["expense"], "include_statistics": ["sometimes"]},
            {"direction": ["expense"], "page": ["0"]},
            {"direction": ["expense"], "page_size": ["201"]},
        )

        for query in invalid_queries:
            with self.subTest(query=query), self.assertRaises(PendingInvoiceError):
                service.rows(query)

    def test_forwards_server_pagination_filter_sort_and_export_limit(self) -> None:
        repository = _PageRepository()
        service = PendingInvoiceCanonicalQueryService(repository=repository)
        service.rows(
            {
                "direction": ["income"],
                "filter": ["cash_income"],
                "filters": ['[{"field":"status_code","operator":"in","values":["cash_income"]}]'],
                "sort_field": ["amount"],
                "sort_direction": ["asc"],
                "page": ["3"],
                "page_size": ["25"],
            }
        )

        request, page_size, page = repository.calls[0]
        self.assertEqual((page, page_size), (3, 25))
        self.assertIs(request["_include_statistics"], True)
        self.assertIs(request["_include_filter_options"], False)
        self.assertEqual(request["sort_field"], "amount")
        self.assertEqual(request["sort_direction"], "asc")
        self.assertEqual(request["filters"], [{"field": "status_code", "operator": "in", "values": ["cash_income"]}])

        repository.payload["total"] = 20_001
        with self.assertRaises(PendingInvoiceError) as raised:
            service.all_rows({"direction": ["expense"], "filter": ["all"]})
        self.assertIs(repository.calls[-1][0]["_include_statistics"], False)
        self.assertEqual(
            raised.exception.error_code,
            "pending_invoice_export_row_limit_exceeded",
        )

    def test_filter_options_are_loaded_only_by_the_dedicated_query(self) -> None:
        repository = _PageRepository()
        service = PendingInvoiceCanonicalQueryService(repository=repository)

        service.filter_options({"direction": ["expense"], "filter": ["all"]})

        request, page_size, page = repository.calls[0]
        self.assertIs(request["_include_statistics"], False)
        self.assertIs(request["_include_filter_options"], True)
        self.assertEqual((page, page_size), (1, 1))

    def test_rows_can_skip_global_statistics_without_changing_page_contract(self) -> None:
        repository = _PageRepository()
        service = PendingInvoiceCanonicalQueryService(repository=repository)

        payload = service.rows(
            {
                "direction": ["expense"],
                "filter": ["all"],
                "include_statistics": ["false"],
            }
        )

        self.assertIs(repository.calls[0][0]["_include_statistics"], False)
        self.assertIsNone(payload["statistics"])
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 50, "total": 0})

    def test_candidate_query_is_validated_paginated_and_keeps_money_contract(self) -> None:
        repository = _PageRepository()
        repository.candidate_payload = {
            "rows": [
                {
                    "invoice_id": "invoice-1",
                    "total_with_tax": "118.000000",
                    "paid_total": "18",
                    "related_paid_total": "18",
                    "remaining_amount": "100",
                    "amount_difference_abs": "82",
                }
            ],
            "total": 1,
            "selected_total": "200",
        }
        service = PendingInvoiceCanonicalQueryService(repository=repository)

        payload = service.invoice_candidates_batch(
            {
                "transaction_ids": ["bank-1", "bank-1", "bank-2"],
                "sort_field": "total_with_tax",
                "sort_direction": "desc",
                "page": 2,
                "page_size": 25,
            }
        )

        self.assertEqual(repository.candidate_request["transaction_ids"], ["bank-1", "bank-2"])
        self.assertEqual(payload["selection_summary"], {"transaction_count": 2, "bank_total": "200.00"})
        self.assertEqual(payload["pagination"], {"page": 2, "page_size": 25, "total": 1})
        self.assertEqual(payload["rows"][0]["remaining_amount"], "100.00")
        with self.assertRaises(PendingInvoiceError):
            service.invoice_candidates({"transaction_id": [""], "page_size": ["201"]})

    def test_missing_canonical_details_keep_existing_error_contract(self) -> None:
        service = PendingInvoiceCanonicalQueryService(repository=_PageRepository())

        for action, error_code in (
            (lambda: service.bank_transaction_detail("missing-bank"), "bank_transaction_not_found"),
            (lambda: service.invoice_detail("missing-invoice"), "invoice_not_found"),
        ):
            with self.subTest(error_code=error_code), self.assertRaises(PendingInvoiceError) as raised:
                action()
            self.assertEqual(raised.exception.error_code, error_code)
        with self.assertRaises(PendingInvoiceError) as raised:
            service.oa_detail("candidate:123")
        self.assertEqual(raised.exception.error_code, "invalid_oa_detail_id")

    def test_relation_detail_uses_public_sections_and_never_exposes_form_type_as_oa_number(self) -> None:
        repository = _PageRepository()
        repository.relation_payload = {
            "bank_rows": [
                {
                    "id": "bank-1",
                    "txn_direction": "outflow",
                    "amount": "332",
                    "trade_time": "2026-08-03T11:19:55+08:00",
                    "counterparty_name": "供应商",
                }
            ],
            "invoice_rows": [],
            "oa_rows": [
                {
                    "row_id": "oa-exp-2047",
                    "workflow_no": "2047",
                    "form_type": "expense_claim",
                    "applicant": "樊祖芳",
                    "workflow_status": "completed",
                    "project_name": "大理余热项目",
                    "amount": "332",
                    "detail_fields": {"费用类型": "交通费"},
                },
                {
                    "row_id": "oa-exp-broken",
                    "workflow_no": "expense_claim",
                    "form_type": "expense_claim",
                    "applicant": "樊祖芳",
                    "workflow_status": "completed",
                },
            ],
        }
        service = PendingInvoiceCanonicalQueryService(repository=repository)

        payload = service.relation_detail("bank-1", direction="expense", kind="all")

        self.assertEqual([section["title"] for section in payload["sections"]], ["银行流水", "OA 1", "OA 2"])
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertIn('"OA单号", "value": "2047"', serialized)
        self.assertIn('"OA类型", "value": "日常报销"', serialized)
        self.assertNotIn('"OA单号", "value": "expense_claim"', serialized)
        self.assertNotIn("relation_case", serialized)

    def test_object_details_publish_only_named_business_fields(self) -> None:
        repository = _PageRepository()
        repository.bank_detail_payload = {
            "id": "bank-1",
            "txn_direction": "outflow",
            "amount": "332",
            "trade_time": "2026-08-03T11:19:55+08:00",
            "counterparty_name": "供应商",
            "account_no": "8106",
        }
        repository.invoice_detail_payload = {
            "id": "invoice-1",
            "invoice_type": "input",
            "digital_invoice_no": "26534000000097888906",
            "issue_date": "2026-07-15",
            "seller_name": "供应商",
            "total_with_tax": "332",
        }
        repository.oa_detail_payload = {
            "oa_id": "oa-exp-2047",
            "workflow_no": "2047",
            "application_type": "expense_claim",
            "applicant": "樊祖芳",
            "status": "completed",
            "project_name": "大理余热项目",
            "amount": "332",
            "detail_fields": {"费用类型": "交通费", "OA单号": "2047"},
        }
        service = PendingInvoiceCanonicalQueryService(repository=repository)

        bank = service.bank_transaction_detail("bank-1")
        invoice = service.invoice_detail("invoice-1")
        oa = service.oa_detail("oa-exp-2047")

        self.assertEqual(bank["sections"][0]["title"], "支出流水")
        self.assertIn({"label": "账号", "value": "8106"}, bank["sections"][0]["fields"])
        self.assertEqual(invoice["sections"][0]["title"], "进项发票")
        self.assertIn(
            {"label": "数电发票号码", "value": "26534000000097888906"},
            invoice["sections"][0]["fields"],
        )
        self.assertIn({"label": "OA单号", "value": "2047"}, oa["sections"][0]["fields"])
        self.assertIn({"label": "OA类型", "value": "日常报销"}, oa["sections"][0]["fields"])
        for payload in (bank, invoice, oa):
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn('"id"', serialized)
            self.assertNotIn("raw_payload", serialized)
            self.assertNotIn("relation_case", serialized)


if __name__ == "__main__":
    unittest.main()
