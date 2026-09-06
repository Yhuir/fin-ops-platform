"""Real PostgreSQL cash queries; explicit disposable DSN, never fake/skip success."""

from __future__ import annotations

import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fin_ops_platform.services.cash_domain import CashError
from fin_ops_platform.services.cash_queries import CashQueryService
from fin_ops_platform.services.cash_service import CashService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.cash import CashRepository
from fin_ops_platform.services.postgres_repositories.cash_queries import CashQueryRepository

from tests.postgres_test_utils import assert_safe_test_database_url


class CashPostgresCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["FIN_OPS_TEST_DATABASE_URL"]
        assert_safe_test_database_url(cls.dsn)
        cls.connection = PostgresConnection(PostgresSettings(database_url=cls.dsn, pool_enabled=False))
        if cls.connection.fetch_one("select to_regclass('cash.flows') as name")["name"] is None:
            migration = Path("backend/src/fin_ops_platform/postgres/migrations/0166_cash_ledger.sql")
            cls.connection.execute(migration.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def setUp(self):
        self.connection.execute("truncate cash.settlements,cash.items,cash.flows,cash.task_occurrences,cash.task_templates,cash.accounts,cash.categories,cash.bill_labels,cash.deleted_submission_ids")
        self.connection.execute("update cash.settings set personal_opening_date=null,allowed_project_stage_codes='{}',project_selection_configured=false,version=1 where id=1")
        self.now = date(2026, 12, 31)
        self.repo = CashRepository(self.connection)
        self.cash = CashService(self.repo, today=lambda: self.now)
        self.query = CashQueryService(CashQueryRepository(self.connection))
        self.actor = {"account": "cash-test", "name": "Synthetic actor"}
        self.account = self.cash.create_account({"id": self.uid(), "name": "Synthetic cash", "kind": "cash", "opening_date": "2026-01-01", "opening_amount": "1000.00"})["account"]
        self.category = self.cash.create_category({"id": self.uid(), "name": "Synthetic turnover", "group": "turnover"})["category"]

    @staticmethod
    def uid():
        return str(uuid4())

    def flow_payload(self, amount="100.00", kind="payment", **changes):
        result = {"id": self.uid(), "occurred_on": "2026-09-03", "kind": kind, "amount": amount,
                  "from_account_id" if kind == "payment" else "to_account_id": self.account["id"],
                  "category_id": self.category["id"], "project_mode": "selection", "content": "Synthetic cash"}
        result.update(changes)
        return result

    def flow(self, amount="100.00", kind="payment", **changes):
        return self.cash.create_flow(self.flow_payload(amount, kind, **changes), self.actor)["flow"]

    def item(self, kind="loan", amount="100.00", **changes):
        payload = {"id": self.uid(), "type": kind, "origin_date": "2026-09-01", "original_amount": amount, "content": "Synthetic item"}
        if kind in {"loan", "company_receivable"}:
            payload.update(obligation_direction="receivable", ledger_group="company", counterparty="Synthetic party")
        if kind == "ticket_source":
            payload.update(ticket_provider="Synthetic provider", ticket_provided_on="2026-09-01", ticket_description="Synthetic ticket")
        payload.update(changes)
        return self.cash.create_item(payload, self.actor)["item"]

    def settlement(self, kind, amount, item=None, source=None, flow=None, **changes):
        payload = {"id": self.uid(), "kind": kind, "amount": amount, "occurred_on": flow["occurred_on"] if flow else "2026-09-03"}
        for prefix, value in (("item", item), ("source_item", source), ("flow", flow)):
            if value is not None:
                payload[prefix + "_id"] = value["id"]
                payload["expected_" + prefix + "_version"] = value["version"]
        payload.update(changes)
        return self.cash.create_settlement(payload, self.actor)["settlement"]


class CashQueryPostgresTests(CashPostgresCase):
    period = {"date_from": "2026-09-01", "date_to": "2026-09-30"}

    def test_empty_reports_keep_unknown_personal_coverage(self):
        for method in (self.query.list_flows, self.query.query_turnover, self.query.query_tickets, self.query.project_options):
            result = method(self.period)
            self.assertEqual(result["rows"], [])
            self.assertEqual(result["pagination"]["total"], 0)
        self.assertIsNone(self.query.query_personal({"year": "2026"})["summary"]["remaining_obligation_amount"])

    def test_cash_filter_does_not_rebase_running_balance_or_summary(self):
        self.flow("100.00", content="not matched", occurred_on="2026-09-01")
        expected = self.flow("20.00", content="matched only", occurred_on="2026-09-02")
        self.flow("50.00", "receipt", occurred_on="2026-09-03")
        result = self.query.list_flows({**self.period, "account_id": self.account["id"], "keyword": "matched only", "sort": "amount"})
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["rows"][0]["id"], expected["id"])
        self.assertEqual(result["rows"][0]["account_running_balance"], "880.00")
        self.assertEqual(result["summary"]["filtered_totals"]["expense_amount"], "20.00")
        self.assertEqual(result["summary"]["account_balances"][0]["ending_balance"], "930.00")

    def test_transfer_single_cash_row_and_two_account_contributions(self):
        other = self.cash.create_account({"id": self.uid(), "name": "Other", "kind": "savings", "opening_date": "2026-01-01", "opening_amount": "0.00"})["account"]
        self.cash.create_flow({"id": self.uid(), "occurred_on": "2026-09-03", "kind": "transfer", "amount": "75.00", "from_account_id": self.account["id"], "to_account_id": other["id"], "project_mode": "selection", "content": "Internal"}, self.actor)
        result = self.query.list_flows(self.period)
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["summary"]["filtered_totals"], {"flow_count": 1, "income_amount": "0.00", "expense_amount": "0.00", "transfer_amount": "75.00"})
        self.assertCountEqual([a["ending_balance"] for a in result["summary"]["account_balances"]], ["925.00", "75.00"])

    def test_account_coverage_does_not_invent_prior_balance(self):
        with self.repo.transaction() as tx:
            tx.update("accounts", self.account["id"], {"opening_date": date(2026, 9, 15)})
        result = self.query.list_flows(self.period)["summary"]["account_balances"][0]
        self.assertEqual(result["coverage_state"], "starts_during_period")
        self.assertIsNone(result["opening_balance"])
        self.assertEqual(result["ending_balance"], "1000.00")
        earlier = self.query.list_flows({"date_from": "2026-08-01", "date_to": "2026-08-31"})["summary"]["account_balances"][0]
        self.assertEqual(earlier["coverage_state"], "not_started")
        self.assertIsNone(earlier["ending_balance"])

    def test_split_principal_counts_cash_once_and_obligations_by_identity(self):
        children = [{"id": self.uid(), "type": "loan", "origin_date": "2026-09-03", "original_amount": amount, "obligation_direction": "receivable", "ledger_group": "external_person", "counterparty": "Synthetic", "content": "Split loan"} for amount in ("40.00", "60.00")]
        flow = self.flow("100.00", related_items=children)
        report = self.query.query_turnover(self.period)
        self.assertEqual(report["summary"]["cash_paid_amount"], "100.00")
        self.assertEqual(report["summary"]["principal_amount"], "100.00")
        self.assertEqual(report["summary"]["remaining_obligation_amount"]["receivable"], "100.00")
        self.assertEqual(self.query.get_flow(flow["id"])["delete_impact"]["source_owned_item_count"], 2)

    def test_expense_payment_is_not_second_expense_or_turnover_cash(self):
        loan = self.item()
        expense = self.item("expense", "100.00", related_obligation_id=loan["id"], expected_related_versions={"items": [{"id": loan["id"], "version": loan["version"]}]})
        payment = self.flow()
        self.settlement("expense_payment", "100.00", item=expense, flow=payment)
        report = self.query.query_turnover(self.period)
        self.assertEqual(report["summary"]["real_expense_amount"], "100.00")
        self.assertEqual(report["summary"]["cash_paid_amount"], "0.00")
        detail = self.query.get_item(expense["id"])
        self.assertEqual(detail["amounts"]["paid_amount"], "100.00")
        self.assertEqual(detail["amounts"]["net_expense_amount"], "100.00")

    def test_ticket_offset_is_used_once_and_cutoff_excludes_future_usage(self):
        ticket = self.item("ticket_source", "100.00")
        loan = self.item()
        self.settlement("ticket_offset", "40.00", item=loan, source=ticket)
        result = self.query.query_tickets(self.period)
        self.assertEqual(result["rows"][0]["used_amount"], "40.00")
        self.assertEqual(result["rows"][0]["offset_amount"], "40.00")
        self.assertEqual(result["rows"][0]["available_source_amount"], "60.00")
        before = self.query.query_tickets({"date_from": "2026-09-01", "date_to": "2026-09-02"})
        self.assertEqual(before["rows"][0]["used_amount"], "0.00")

    def test_personal_matrix_uses_actual_month_and_opening_not_principal(self):
        self.cash.update_personal_opening({"expected_version": 1, "opening_date": "2026-07-15"})
        label = self.cash.create_bill_label({"id": self.uid(), "bank_name": "Synthetic bank", "label": "A"})["bill_label"]
        self.item(amount="200.00", ledger_group="personal", is_opening=True, origin_date="2026-07-15")
        loan = self.item(amount="100.00", ledger_group="personal", origin_date="2026-11-03", bill_label_id=label["id"], bill_month="2026-12")
        report = self.query.query_personal({"year": "2026"})
        self.assertEqual(report["summary"]["opening_adjustment_amount"], "200.00")
        self.assertEqual(report["summary"]["new_principal_amount"], "100.00")
        row = next(r for r in report["rows"] if r["row_key"] == label["id"])
        self.assertIsNone(row["months"][0]["principal_amount"])
        self.assertEqual(Decimal(row["months"][10]["principal_amount"]), Decimal("100.00"))
        self.assertEqual(Decimal(row["months"][11]["principal_amount"]), Decimal("0.00"))
        self.assertEqual(self.query.list_items({"bill_label_id": label["id"], "origin_date_from": "2026-11-01", "origin_date_to": "2026-11-30"})["rows"][0]["id"], loan["id"])

    def test_selectors_use_specific_budget_and_return_versions(self):
        expense = self.item("expense")
        payment = self.flow()
        self.settlement("expense_payment", "100.00", item=expense, flow=payment)
        result = self.query.list_flows({**self.period, "purpose": "settlement", "item_id": expense["id"], "settlement_kind": "expense_payment"})
        self.assertEqual(result["rows"][0]["available_amount"], "0.00")
        self.assertFalse(result["rows"][0]["selectable"])
        self.assertEqual(result["selection_context"]["item_version"], 2)
        target = self.query.list_items({"purpose": "settlement_target", "settlement_kind": "expense_refund"})
        self.assertTrue(target["rows"][0]["selectable"])

    def test_pagination_summary_not_page_and_unknown_input_rejected(self):
        self.flow("100.00")
        self.flow("100.00")
        result = self.query.list_flows({**self.period, "page_size": "1", "page": "3"})
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["pagination"]["total"], 2)
        self.assertEqual(result["summary"]["filtered_totals"]["expense_amount"], "200.00")
        for raw in ({}, {**self.period, "sort": "id;drop"}, {**self.period, "page_size": 201}, {**self.period, "kind": "bank"}, {**self.period, "unexpected": 1}):
            with self.assertRaises(CashError):
                self.query.list_flows(raw)

    def test_settlement_parents_and_detail_versions(self):
        loan = self.item()
        flow = self.flow("20.00", "receipt")
        self.settlement("cash_repayment", "20.00", item=loan, flow=flow)
        result = self.query.list_settlements({"item_id": loan["id"]})
        self.assertEqual(result["rows"][0]["flow_version"], 2)
        self.assertEqual(result["rows"][0]["item_version"], 2)
        self.assertEqual(self.query.list_flows({"item_id": loan["id"]})["pagination"]["total"], 1)
        with self.assertRaises(CashError):
            self.query.list_settlements({})
        with self.assertRaises(CashError) as missing:
            self.query.get_item(self.uid())
        self.assertEqual(missing.exception.status, 404)

    def test_personal_january_first_opening_is_year_opening_not_new_principal(self):
        self.cash.update_personal_opening({"expected_version": 1, "opening_date": "2026-01-01"})
        self.item(amount="250.00", ledger_group="personal", is_opening=True, origin_date="2026-01-01")
        report = self.query.query_personal({"year": "2026"})
        self.assertEqual(report["summary"]["opening_obligation_amount"], "250.00")
        self.assertEqual(report["summary"]["opening_adjustment_amount"], "0.00")
        self.assertEqual(report["summary"]["new_principal_amount"], "0.00")
        self.assertEqual(report["summary"]["remaining_obligation_amount"], "250.00")

    def test_ticket_company_collection_requires_explicit_receivable(self):
        ticket = self.item("ticket_source", "100.00")
        self.assertEqual(self.query.query_tickets(self.period)["rows"][0]["cash_received_amount"], "0.00")
        receivable = self.item("company_receivable", "70.00", ticket_source_id=ticket["id"], expected_related_versions={"items": [{"id": ticket["id"], "version": ticket["version"]}]})
        cash = self.flow("30.00", "receipt")
        self.settlement("company_collection", "30.00", item=receivable, flow=cash)
        row = self.query.query_tickets(self.period)["rows"][0]
        self.assertEqual(row["receivable_amount"], "70.00")
        self.assertEqual(row["cash_received_amount"], "30.00")
        self.assertEqual(row["available_source_amount"], "100.00")

    def test_personal_three_subtables_use_settlement_amounts(self):
        self.cash.update_personal_opening({"expected_version": 1, "opening_date": "2026-01-01"})
        item = self.item(ledger_group="personal")
        cash = self.flow("20.00", "receipt")
        self.settlement("cash_repayment", "20.00", item=item, flow=cash)
        item = self.query.get_item(item["id"])["item"]
        ticket = self.item("ticket_source")
        self.settlement("ticket_offset", "10.00", item=item, source=ticket)
        item = self.query.get_item(item["id"])["item"]
        self.settlement("non_ticket_offset", "5.00", item=item, remark="Explicit synthetic adjustment")
        for view, expected in (("cash_repayments", "20.00"), ("ticket_offsets", "10.00"), ("non_ticket_offsets", "5.00")):
            result = self.query.query_personal({"year": "2026", "view": view})
            self.assertEqual(result["rows"][0]["amount"], expected)
            self.assertEqual(result["summary"]["remaining_obligation_amount"], "65.00")

    def test_cash_rows_totals_and_balances_share_repeatable_read_snapshot(self):
        from contextlib import contextmanager
        self.flow("100.00")
        original = self.connection
        case = self
        class InterleavedTransaction:
            def __init__(self, raw):
                self.raw = raw
                self.inserted = False
            def execute(self, *args):
                return self.raw.execute(*args)
            def fetch_one(self, *args):
                return self.raw.fetch_one(*args)
            def fetch_all(self, *args):
                result = self.raw.fetch_all(*args)
                if not self.inserted:
                    self.inserted = True
                    case.flow("200.00")
                return result
        class InterleavedConnection:
            @contextmanager
            def transaction(self):
                with original.transaction() as tx:
                    yield InterleavedTransaction(tx)
        query = CashQueryService(CashQueryRepository(InterleavedConnection()))
        result = query.list_flows(self.period)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["summary"]["filtered_totals"]["expense_amount"], "100.00")
        self.assertEqual(result["summary"]["account_balances"][0]["ending_balance"], "900.00")
        self.assertEqual(self.query.list_flows(self.period)["pagination"]["total"], 2)

    def test_historical_project_options_include_current_non_cash_settlement(self):
        self.cash.project_resolver = lambda project_id, **_: {"id": project_id, "name": "Historical synthetic project", "selection_settings_version": 1}
        item = self.item(origin_date="2026-08-01", oa_project_id="historical-project")
        self.settlement("non_ticket_offset", "10.00", item=item, remark="Synthetic historical settlement")
        rows = self.query.project_options(self.period)["rows"]
        self.assertEqual(rows, [{"id": "historical-project", "name": "Historical synthetic project"}])

    def test_turnover_category_filter_remains_attached_to_real_cash(self):
        child = {"id": self.uid(), "type": "loan", "origin_date": "2026-09-03", "original_amount": "100.00", "obligation_direction": "receivable", "ledger_group": "company", "counterparty": "Synthetic", "content": "Actual category"}
        self.flow(related_items=[child])
        result = self.query.query_turnover({**self.period, "category_id": self.category["id"]})
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["summary"]["cash_paid_amount"], "100.00")
        empty = self.query.query_turnover({**self.period, "category_id": self.uid()})
        self.assertEqual(empty["pagination"]["total"], 0)
