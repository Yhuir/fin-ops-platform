from __future__ import annotations

import unittest

from fin_ops_platform.services.pending_invoice_canonical_query import (
    BANK_DETAIL_SQL,
    CANDIDATE_QUERY_SQL,
    INVOICE_DETAIL_SQL,
    OA_DETAIL_SQL,
    PAGE_QUERY_SQL,
    PendingInvoiceCanonicalQueryService,
    PostgresPendingInvoiceCanonicalRepository,
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

    def bank_transaction_detail(self, _object_id: str) -> None:
        return None

    def invoice_detail(self, _object_id: str) -> None:
        return None

    def oa_detail(self, _object_id: str) -> None:
        return None


class PendingInvoiceCanonicalRepositoryTests(unittest.TestCase):
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
        self.assertEqual(len([sql for sql, _params in commands if sql.lstrip().lower().startswith(("select", "with"))]), 2)
        page_sql, page_params = commands[2]
        self.assertIn("from app.bank_transactions", page_sql)
        self.assertIn("from app.bank_transaction_categories", page_sql)
        self.assertIn("app.invoices", page_sql)
        self.assertIn("app.oa_applications", page_sql)
        self.assertIn("from app.workbench_pair_relations", page_sql)
        self.assertIn("r.status = 'active'", page_sql)
        self.assertIn("r.relation_mode <> 'turnover_manual_closure'", page_sql)
        self.assertNotIn("read_model.", page_sql)
        self.assertEqual(page_params[-6:-4], (50, 50))
        self.assertEqual(payload["pagination"], {"page": 2, "page_size": 50, "total": 0})
        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("source_versions", payload)

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
        self.assertNotIn("read_model.pending_invoice", PAGE_QUERY_SQL)
        self.assertNotIn("read_model.bank_detail", PAGE_QUERY_SQL)
        self.assertNotIn("read_model.workbench_relation", PAGE_QUERY_SQL)
        self.assertNotIn("read_model.search", PAGE_QUERY_SQL)
        self.assertIn("limit %s offset %s", CANDIDATE_QUERY_SQL.lower())
        self.assertIn("from app.invoices", CANDIDATE_QUERY_SQL)
        self.assertIn("from app.workbench_pair_relations", CANDIDATE_QUERY_SQL)
        self.assertIn("status = 'active'", CANDIDATE_QUERY_SQL)
        self.assertIn("relation_mode <> 'turnover_manual_closure'", CANDIDATE_QUERY_SQL)
        for sql in (CANDIDATE_QUERY_SQL, BANK_DETAIL_SQL, INVOICE_DETAIL_SQL, OA_DETAIL_SQL):
            self.assertNotIn("read_model.", sql)


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
                "options": [],
                "settings": {},
            }
        )
        service = PendingInvoiceCanonicalQueryService(repository=repository)

        payload = service.rows({"direction": ["all"], "filter": ["all"]})

        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["summary"]["total_rows"], 0)
        self.assertEqual(payload["statistics"], {"bank_transaction_count": 0})
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
        self.assertEqual(request["sort_field"], "amount")
        self.assertEqual(request["sort_direction"], "asc")
        self.assertEqual(request["filters"], [{"field": "status_code", "operator": "in", "values": ["cash_income"]}])

        repository.payload["total"] = 20_001
        with self.assertRaises(PendingInvoiceError) as raised:
            service.all_rows({"direction": ["expense"], "filter": ["all"]})
        self.assertEqual(
            raised.exception.error_code,
            "pending_invoice_export_row_limit_exceeded",
        )

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


if __name__ == "__main__":
    unittest.main()
