"""Real PostgreSQL cash queries; explicit disposable DSN, never fake/skip success."""

from __future__ import annotations

import json
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

    def test_multi_flow_columns_filter_whole_result_preserve_balances_and_delete(self):
        self.cash.project_resolver = lambda project_id, **_: {"id": project_id, "name": project_id, "selection_settings_version": 1}
        other = self.cash.create_account({"id": self.uid(), "name": "Other", "kind": "cash", "opening_date": "2026-01-01", "opening_amount": "200.00"})["account"]
        category = self.cash.create_category({"id": self.uid(), "name": "Payment", "group": "payment"})["category"]
        self.flow("100.00", oa_project_id="A", occurred_on="2026-09-01", content="Earlier")
        matched = self.flow("20.00", oa_project_id="B", category_id=category["id"], occurred_on="2026-09-02", content="Matched")
        self.flow("50.00", "receipt", occurred_on="2026-09-03")
        self.cash.create_flow({"id": self.uid(), "occurred_on": "2026-09-04", "kind": "transfer", "amount": "75.00",
            "from_account_id": self.account["id"], "to_account_id": other["id"], "project_mode": "selection", "content": "Transfer"}, self.actor)
        selected = {**self.period, "account_ids": json.dumps([self.account["id"], other["id"]]),
            "project_ids": '[null,"B"]', "category_ids": json.dumps([None, category["id"], self.category["id"]]),
            "kinds": '["receipt","payment","transfer"]', "sources": '["manual"]', "page_size": 1, "page": 2,
            "sort": "occurred_on", "order": "asc"}
        result = self.query.list_flows(selected)
        self.assertEqual(result["pagination"], {"page": 2, "page_size": 1, "total": 3})
        self.assertEqual(result["summary"]["filtered_totals"], {"flow_count": 3, "income_amount": "50.00", "expense_amount": "20.00", "transfer_amount": "75.00"})
        self.assertTrue(all(row["account_running_balance"] is None for row in result["rows"]))
        balances = {row["account_id"]: row["ending_balance"] for row in result["summary"]["account_balances"]}
        self.assertEqual(balances, {self.account["id"]: "855.00", other["id"]: "275.00"})
        single = self.query.list_flows({**self.period, "account_ids": json.dumps([self.account["id"]]), "keyword": "Matched"})
        self.assertEqual(single["rows"][0]["id"], matched["id"])
        self.assertEqual(single["rows"][0]["account_running_balance"], "880.00")
        self.assertEqual(single["summary"]["account_balances"][0]["ending_balance"], "855.00")
        scalar = self.query.list_flows({**self.period, "account_id": self.account["id"], "keyword": "Matched"})
        self.assertEqual(single, scalar)
        self.cash.delete_flow(matched["id"], {"expected_version": 1})
        after = self.query.list_flows(selected)
        self.assertEqual(after["pagination"]["total"], 2)
        self.assertEqual(after["summary"]["filtered_totals"]["expense_amount"], "0.00")
        with self.assertRaises(CashError) as missing:
            self.query.list_flows({**self.period, "account_ids": json.dumps([self.account["id"], self.uid()])})
        self.assertEqual(missing.exception.status, 404)

    def test_category_groups_filter_before_paging_including_disabled_history(self):
        self.cash.create_category({"id": self.uid(), "name": "A receipt", "group": "receipt"})
        first = self.cash.create_category({"id": self.uid(), "name": "B payment", "group": "payment"})["category"]
        second = self.cash.create_category({"id": self.uid(), "name": "C payment", "group": "payment"})["category"]
        with self.repo.transaction() as tx:
            tx.update("categories", second["id"], {"enabled": False})
        query = {"groups": '["payment","turnover"]', "page_size": 1, "page": 2, "order": "asc"}
        result = self.query.list_configuration("categories", query)
        self.assertEqual(result["pagination"]["total"], 3)
        self.assertEqual(result["rows"][0]["id"], second["id"])
        entry = self.query.list_configuration("categories", {**query, "enabled": "true", "page": 1})
        self.assertEqual(entry["pagination"]["total"], 2)
        self.assertEqual(entry["rows"][0]["id"], first["id"])

    def test_multi_report_states_null_categories_and_project_sets_before_paging(self):
        self.cash.project_resolver = lambda project_id, **_: {"id": project_id, "name": project_id, "selection_settings_version": 1}
        self.item(oa_project_id="A")
        partial = self.item(oa_project_id="B")
        settled = self.item()
        self.settlement("non_ticket_offset", "10.00", item=partial, remark="Partial")
        self.settlement("non_ticket_offset", "100.00", item=settled, remark="Settled")
        result = self.query.query_turnover({**self.period, "project_ids": '["A","B",null]',
            "category_ids": '[null]', "states": '["open","partial"]', "page_size": 1, "page": 2})
        self.assertEqual(result["pagination"]["total"], 3)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["summary"]["remaining_obligation_amount"]["receivable"], "190.00")
        self.assertEqual(result["summary"]["principal_amount"], "200.00")
        self.assertEqual(result["summary"]["non_ticket_offset_amount"], "10.00")
        self.assertNotEqual(result["rows"][0]["state"], "settled")

    def test_multi_tickets_state_filter_and_summary_do_not_use_only_page(self):
        self.item("ticket_source", "200.00")
        partial = self.item("ticket_source", "100.00")
        used = self.item("ticket_source", "50.00")
        loan = self.item(amount="500.00")
        self.settlement("ticket_offset", "10.00", item=loan, source=partial)
        loan = self.query.get_item(loan["id"])["item"]
        self.settlement("ticket_offset", "50.00", item=loan, source=used)
        result = self.query.query_tickets({**self.period, "project_ids": '[null]', "states": '["unused","partial"]', "page_size": 1, "page": 2})
        self.assertEqual(result["pagination"]["total"], 2)
        self.assertEqual(result["summary"]["provided_amount"], "300.00")
        self.assertEqual(result["summary"]["used_amount"], "10.00")
        self.assertEqual(result["summary"]["available_source_amount"], "290.00")

    def test_multi_personal_labels_with_null_cover_matrix_and_settlement_views(self):
        self.cash.update_personal_opening({"expected_version": 1, "opening_date": "2026-01-01"})
        label = self.cash.create_bill_label({"id": self.uid(), "bank_name": "A bank", "label": "A"})["bill_label"]
        excluded = self.cash.create_bill_label({"id": self.uid(), "bank_name": "B bank", "label": "B"})["bill_label"]
        self.item(ledger_group="personal", bill_label_id=label["id"], bill_month="2026-09")
        unlabeled = self.item(ledger_group="personal")
        self.item(amount="900.00", ledger_group="personal", bill_label_id=excluded["id"], bill_month="2026-09")
        receipt = self.flow("20.00", "receipt")
        self.settlement("cash_repayment", "20.00", item=unlabeled, flow=receipt)
        selected = {"year": "2026", "project_ids": '[null]', "bill_label_ids": json.dumps([None, label["id"]])}
        result = self.query.query_personal({**selected, "page_size": 1, "page": 2})
        self.assertEqual(result["pagination"]["total"], 2)
        self.assertEqual(result["summary"]["new_principal_amount"], "200.00")
        self.assertEqual(result["summary"]["remaining_obligation_amount"], "180.00")
        detail = self.query.query_personal({**selected, "view": "cash_repayments"})
        self.assertEqual(detail["pagination"]["total"], 1)
        self.assertEqual(detail["rows"][0]["amount"], "20.00")
        self.assertIsNone(detail["rows"][0]["bill_label"])
        self.assertEqual(detail["summary"], result["summary"])

    def test_personal_month_drilldown_preserves_project_multi_scope(self):
        self.cash.project_resolver = lambda project_id, **_: {"id": project_id, "name": project_id, "selection_settings_version": 2}
        self.cash.update_personal_opening({"expected_version": 1, "opening_date": "2026-01-01"})
        label = self.cash.create_bill_label({"id": self.uid(), "bank_name": "Bank", "label": "Month"})["bill_label"]
        common = {"ledger_group": "personal", "bill_label_id": label["id"], "bill_month": "2026-09"}
        expected = [self.item(amount="100.00", oa_project_id="A", **common), self.item(amount="200.00", **common)]
        self.item(amount="900.00", oa_project_id="excluded", **common)
        projects = '["A",null]'
        matrix = self.query.query_personal({"year": "2026", "project_ids": projects, "bill_label_ids": json.dumps([label["id"]])})
        cell = matrix["rows"][0]["months"][8]
        detail = self.query.list_items({"type": "loan", "ledger_group": "personal", "bill_label_id": label["id"],
            "project_ids": projects, "is_opening": "false", "origin_date_from": "2026-09-01", "origin_date_to": "2026-09-30"})
        self.assertEqual(cell["item_count"], detail["pagination"]["total"])
        self.assertEqual({item["id"] for item in detail["rows"]}, {item["id"] for item in expected})
        self.assertEqual(Decimal(cell["principal_amount"]), sum(Decimal(item["original_amount"]) for item in detail["rows"]))

    def test_historical_candidates_include_prior_year_and_parent_intersection(self):
        self.cash.project_resolver = lambda project_id, **_: {"id": project_id, "name": project_id, "selection_settings_version": 1}
        old = self.item(origin_date="2025-11-01", oa_project_id="prior-year")
        current = self.item(oa_project_id="current")
        self.item(origin_date="2026-10-01", oa_project_id="future")
        result = self.query.project_options(self.period)
        self.assertEqual({row["id"] for row in result["rows"]}, {"prior-year", "current"})
        parent = self.query.project_options({"item_id": old["id"]})
        self.assertEqual(parent["rows"], [{"id": "prior-year", "name": "prior-year"}])
        self.assertEqual(self.query.project_options({**self.period, "item_id": old["id"]})["rows"], [])
        self.settlement("non_ticket_offset", "10.00", item=old, remark="Prior year handling")
        self.assertEqual(self.query.project_options({**self.period, "item_id": old["id"]})["rows"], parent["rows"])
        current_result = self.query.project_options({"item_id": current["id"]})
        self.assertEqual(current_result["pagination"]["total"], 1)
        for raw in ({"item_id": self.uid()}, {"task_occurrence_id": self.uid()}):
            with self.subTest(raw=raw), self.assertRaises(CashError) as missing:
                self.query.project_options(raw)
            self.assertEqual(missing.exception.status, 404)
        with self.assertRaises(CashError):
            self.query.project_options({})

    def test_historical_project_candidates_keep_latest_name_ties_and_keyword_scope(self):
        self.cash.project_resolver = lambda project_id, **_: {"id": project_id, "name": project_id, "selection_settings_version": 1}
        older = self.flow(oa_project_id="renamed")
        current = self.flow(oa_project_id="renamed")
        duplicate = self.item(oa_project_id="renamed")
        tied = self.item(oa_project_id="renamed")
        another = self.flow(oa_project_id="another")
        self.connection.execute("update cash.flows set project_name_snapshot=%s,updated_at=%s::timestamptz where id=%s",
                                ("Retired name", "2026-09-01T00:00:00Z", older["id"]))
        self.connection.execute("update cash.flows set project_name_snapshot=%s,updated_at=%s::timestamptz where id=%s",
                                ("A current", "2026-09-05T00:00:00Z", current["id"]))
        self.connection.execute("update cash.items set project_name_snapshot=%s,updated_at=%s::timestamptz where id=%s",
                                ("A current", "2026-09-02T00:00:00Z", duplicate["id"]))
        self.connection.execute("update cash.items set project_name_snapshot=%s,updated_at=%s::timestamptz where id=%s",
                                ("Z tied", "2026-09-05T00:00:00Z", tied["id"]))
        self.connection.execute("update cash.flows set project_name_snapshot=%s,updated_at=%s::timestamptz where id=%s",
                                ("B other", "2026-09-04T00:00:00Z", another["id"]))
        result = self.query.project_options({**self.period, "order": "asc", "page_size": 1})
        self.assertEqual(result["rows"], [{"id": "renamed", "name": "A current"}])
        self.assertEqual(result["pagination"]["total"], 2)
        page = self.query.project_options({**self.period, "order": "asc", "page_size": 1, "page": 2})
        self.assertEqual(page["rows"], [{"id": "another", "name": "B other"}])
        for keyword in ("Retired", "Z tied"):
            self.assertEqual(self.query.project_options({**self.period, "keyword": keyword})["pagination"]["total"], 0)
        current_name = self.query.project_options({**self.period, "keyword": "A current"})
        self.assertEqual(current_name["rows"], [{"id": "renamed", "name": "A current"}])
        # Parent-scoped candidates choose the latest name only within that parent.
        scoped = self.query.project_options({"item_id": tied["id"]})
        self.assertEqual(scoped["rows"], [{"id": "renamed", "name": "Z tied"}])

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

    def test_turnover_projects_category_and_each_event_remark_without_inheriting(self):
        child = {"id": self.uid(), "type": "loan", "origin_date": "2026-09-03", "original_amount": "100.00",
                 "obligation_direction": "receivable", "ledger_group": "company", "counterparty": "Synthetic",
                 "content": "Principal content", "remark": "Principal remark"}
        payment = self.flow(related_items=[child], remark="Not the item remark")
        loan = self.query.get_item(child["id"])["item"]
        receipt_category = self.cash.create_category({"id": self.uid(), "name": "Receipt type", "group": "receipt"})["category"]
        receipt = self.flow("20.00", "receipt", category_id=receipt_category["id"], remark="Not the settlement remark")
        repaid = self.settlement("cash_repayment", "20.00", item=loan, flow=receipt)
        loan = self.query.get_item(loan["id"])["item"]
        offset = self.settlement("non_ticket_offset", "10.00", item=loan, occurred_on="2026-09-04", remark="This adjustment")
        report = self.query.query_turnover({**self.period, "order": "asc"})
        rows = {row["row_id"]: row for row in report["rows"]}
        principal = rows["item:" + loan["id"]]
        self.assertEqual(principal["category"], {key: self.category[key] for key in ("id", "name", "group")})
        self.assertEqual(principal["remark"], "Principal remark")
        self.assertEqual(principal["flow_id"], payment["id"])
        self.assertEqual(principal["remaining_after_event"], "100.00")
        repayment = rows["settlement:" + repaid["id"]]
        self.assertEqual(repayment["category"], {key: receipt_category[key] for key in ("id", "name", "group")})
        self.assertIsNone(repayment["remark"])
        self.assertEqual(repayment["remaining_after_event"], "80.00")
        adjustment = rows["settlement:" + offset["id"]]
        self.assertIsNone(adjustment["category"])
        self.assertEqual(adjustment["remark"], "This adjustment")
        self.assertEqual(adjustment["remaining_after_event"], "70.00")
        self.assertTrue(all(row["ticket_collection_state"] is None for row in rows.values()))
        page = self.query.query_turnover({**self.period, "page_size": 1, "page": 2, "order": "asc"})
        self.assertEqual(page["rows"], [repayment])
        self.assertEqual(page["summary"], report["summary"])
        self.cash.delete_flow(receipt["id"], {"expected_version": 2})
        after = self.query.query_turnover(self.period)
        self.assertNotIn(repayment["row_id"], {row["row_id"] for row in after["rows"]})
        self.assertEqual(after["summary"]["remaining_obligation_amount"]["receivable"], "90.00")

    def test_turnover_opening_expense_and_expense_settlement_remark_sources(self):
        loan = self.item(is_opening=True, remark="Opening remark")
        expense = self.item("expense", related_obligation_id=loan["id"], remark="Expense remark",
                            expected_related_versions={"items": [{"id": loan["id"], "version": loan["version"]}]})
        payment = self.flow()
        paid = self.settlement("expense_payment", "100.00", item=expense, flow=payment, remark="Payment remark")
        rows = {row["row_id"]: row for row in self.query.query_turnover(self.period)["rows"]}
        opening = rows["item:" + loan["id"]]
        self.assertEqual(opening["row_kind"], "opening")
        self.assertEqual(opening["remark"], "Opening remark")
        self.assertIsNone(opening["category"])
        self.assertEqual(rows["expense:" + expense["id"]]["remark"], "Expense remark")
        self.assertIsNone(rows["expense:" + expense["id"]]["category"])
        event = rows["expense_settlement:" + paid["id"]]
        self.assertEqual(event["remark"], "Payment remark")
        self.assertEqual(event["category"]["id"], self.category["id"])
        self.assertIsNone(event["remaining_after_event"])

    def test_turnover_ticket_collection_state_uses_cutoff_and_actual_cash_only(self):
        ticket = self.item("ticket_source")
        receivable = self.item("company_receivable", ticket_source_id=ticket["id"],
                               expected_related_versions={"items": [{"id": ticket["id"], "version": ticket["version"]}]})
        self.item("company_receivable", content="No explicit ticket")
        collection = self.flow("30.00", "receipt", occurred_on="2026-09-05")
        self.settlement("company_collection", "30.00", item=receivable, flow=collection)
        receivable = self.query.get_item(receivable["id"])["item"]
        remaining = self.flow("70.00", "receipt", occurred_on="2026-09-10")
        self.settlement("company_collection", "70.00", item=receivable, flow=remaining)
        for cutoff, expected in (("2026-09-04", "open"), ("2026-09-05", "partial"), ("2026-09-10", "settled")):
            with self.subTest(cutoff=cutoff):
                rows = self.query.query_turnover({**self.period, "date_to": cutoff})["rows"]
                self.assertTrue(all(row["ticket_collection_state"] == expected for row in rows if row["item_id"] == receivable["id"]))
                self.assertIsNone(next(row for row in rows if row["content"] == "No explicit ticket")["ticket_collection_state"])
        self.cash.delete_flow(remaining["id"], {"expected_version": 2})
        receivable = self.query.get_item(receivable["id"])["item"]
        self.settlement("non_ticket_offset", "70.00", item=receivable, occurred_on="2026-09-10", remark="Not cash collection")
        rows = [row for row in self.query.query_turnover(self.period)["rows"] if row["item_id"] == receivable["id"]]
        self.assertTrue(all(row["state"] == "settled" and row["ticket_collection_state"] == "partial" for row in rows))
        self.cash.delete_flow(collection["id"], {"expected_version": 2})
        rows = [row for row in self.query.query_turnover(self.period)["rows"] if row["item_id"] == receivable["id"]]
        self.assertTrue(all(row["state"] == "partial" and row["ticket_collection_state"] == "open" for row in rows))

    def test_turnover_personal_variant_filters_before_pagination_and_summary(self):
        self.cash.update_personal_opening({"expected_version": 1, "opening_date": "2026-09-01"})
        loan = self.item(ledger_group="personal")
        self.item(amount="200.00", ledger_group="personal")
        self.item(amount="50.00", ledger_group="personal", is_opening=True)
        self.item(amount="999.00")
        receipt = self.flow("40.00", "receipt")
        self.settlement("cash_repayment", "40.00", item=loan, flow=receipt)
        loan = self.query.get_item(loan["id"])["item"]
        self.settlement("non_ticket_offset", "10.00", item=loan, remark="Synthetic offset")
        loan = self.query.get_item(loan["id"])["item"]
        self.item("expense", "20.00", related_obligation_id=loan["id"],
                  expected_related_versions={"items": [{"id": loan["id"], "version": loan["version"]}]})
        query = {**self.period, "ledger_group": "personal", "page_size": 1, "page": 2}
        principal = self.query.query_turnover({**query, "personal_variant": "principal"})
        self.assertEqual(principal["pagination"], {"page": 2, "page_size": 1, "total": 3})
        self.assertEqual(len(principal["rows"]), 1)
        self.assertEqual(principal["rows"][0]["personal_variant"], "principal")
        self.assertEqual(principal["summary"]["principal_amount"], "300.00")
        self.assertEqual(principal["summary"]["opening_adjustment_amount"], "50.00")
        self.assertEqual(principal["summary"]["remaining_obligation_amount"]["receivable"], "300.00")
        processed = self.query.query_turnover({**query, "personal_variant": "settlement"})
        self.assertEqual(processed["pagination"]["total"], 3)
        self.assertEqual(processed["rows"][0]["personal_variant"], "settlement")
        self.assertEqual(processed["summary"]["principal_amount"], "0.00")
        self.assertEqual(processed["summary"]["repayment_amount"], "40.00")
        self.assertEqual(processed["summary"]["non_ticket_offset_amount"], "10.00")
        self.assertEqual(processed["summary"]["real_expense_amount"], "20.00")
        self.assertEqual(processed["summary"]["remaining_obligation_amount"]["receivable"], "50.00")
        beyond = self.query.query_turnover({**query, "personal_variant": "settlement", "page": 4})
        self.assertEqual(beyond["rows"], [])
        self.assertEqual(beyond["summary"], processed["summary"])

    def test_item_relationship_lists_are_bounded_complete_and_list_only(self):
        children = [{"id": self.uid(), "type": "loan", "origin_date": "2026-09-03", "original_amount": "1.00",
                     "obligation_direction": "receivable", "ledger_group": "company", "counterparty": "Synthetic",
                     "content": f"Owned {index}"} for index in range(25)]
        flow = self.flow("25.00", related_items=children)
        self.item(content="Unrelated")
        first = self.query.list_items({"origin_flow_id": flow["id"], "page_size": 20})
        second = self.query.list_items({"origin_flow_id": flow["id"], "page_size": 20, "page": 2})
        self.assertEqual(first["pagination"]["total"], 25)
        self.assertEqual(len(first["rows"]), 20)
        self.assertEqual(len(second["rows"]), 5)
        self.assertEqual({row["id"] for row in first["rows"] + second["rows"]}, {row["id"] for row in children})
        parent = self.query.get_item(children[0]["id"])["item"]
        expense = self.item("expense", "1.00", related_obligation_id=parent["id"],
                            expected_related_versions={"items": [{"id": parent["id"], "version": parent["version"]}]})
        self.assertEqual([row["id"] for row in self.query.list_items({"related_obligation_id": parent["id"]})["rows"]], [expense["id"]])
        ticket = self.item("ticket_source")
        receivable = self.item("company_receivable", ticket_source_id=ticket["id"],
                               expected_related_versions={"items": [{"id": ticket["id"], "version": ticket["version"]}]})
        self.assertEqual([row["id"] for row in self.query.list_items({"ticket_source_id": ticket["id"]})["rows"]], [receivable["id"]])
        for field, identity in (("origin_flow_id", flow["id"]), ("related_obligation_id", parent["id"]), ("ticket_source_id", ticket["id"])):
            with self.subTest(field=field):
                with self.assertRaises(CashError) as invalid_selector:
                    self.query.list_items({field: identity, "purpose": "settlement_target", "settlement_kind": "cash_repayment"})
                self.assertEqual(invalid_selector.exception.status, 400)
                with self.assertRaises(CashError) as missing:
                    self.query.list_items({field: self.uid()})
                self.assertEqual(missing.exception.status, 404)
