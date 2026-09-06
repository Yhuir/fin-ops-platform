from __future__ import annotations

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from threading import Event
from uuid import uuid4

import psycopg
from fin_ops_platform.services.cash_domain import CashError, normalize_money
from fin_ops_platform.services.cash_service import CashService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.cash import CashRepository


def uid():
    return str(uuid4())


class CashMoneyTests(unittest.TestCase):
    def test_strict_money(self):
        for value in (1, True, None, "NaN", "Infinity", "1e2", "1,000", "1.001", "10000000000000000.00", "", "+1", "01"):
            with self.subTest(value=value), self.assertRaises(CashError):
                normalize_money(value)
        self.assertEqual(normalize_money("9999999999999999.99"), Decimal("9999999999999999.99"))
        self.assertEqual(normalize_money("-2", signed=True), Decimal("-2.00"))
        with self.assertRaises(CashError):
            normalize_money("0")


@unittest.skipUnless(os.environ.get("FIN_OPS_CASH_TEST_DATABASE_URL"), "requires explicitly isolated cash PostgreSQL test database")
class CashCorePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["FIN_OPS_CASH_TEST_DATABASE_URL"]
        cls.connection = PostgresConnection(PostgresSettings(cls.dsn, pool_enabled=False))
        db = cls.connection.fetch_one("SELECT current_database() AS name")["name"]
        if not db.startswith("fin_ops_cash_test_"):
            raise RuntimeError("Cash destructive fixtures require a dedicated fin_ops_cash_test_* database")
        # This schema belongs solely to this explicit disposable test database.
        cls.connection.execute("DROP SCHEMA IF EXISTS cash CASCADE")
        cls.connection.execute(Path("backend/src/fin_ops_platform/postgres/migrations/0166_cash_ledger.sql").read_text())

    def setUp(self):
        self.connection.execute("TRUNCATE cash.settlements,cash.items,cash.flows,cash.task_occurrences,cash.task_templates,cash.accounts,cash.categories,cash.bill_labels,cash.deleted_submission_ids")
        self.connection.execute("UPDATE cash.settings SET allowed_project_stage_codes='{}',project_selection_configured=false,personal_opening_date=NULL,version=1")
        self.repo = CashRepository(self.connection)
        self.oa_calls = []

        def resolve(project_id, *, allow_historical=False):
            self.oa_calls.append((project_id, allow_historical))
            if project_id == "ended" and not allow_historical:
                raise CashError("cash_project_selection_changed", "Ended", 409)
            return {"id": project_id, "name": "Synthetic project", "selection_settings_version": self.service.get_project_selection()["version"]}

        self.service = CashService(self.repo, resolve, stage_validator=lambda codes: None, today=lambda: date(2026, 9, 7))
        self.actor = {"account": "test-account", "name": "Synthetic operator"}
        self.account = self.service.create_account({"id": uid(), "name": "Synthetic account", "kind": "cash", "opening_date": "2026-01-01", "opening_amount": "1000"})["account"]
        self.category = self.service.create_category({"id": uid(), "name": "Synthetic turnover", "group": "turnover"})["category"]

    def flow(self, kind="payment", amount="100", **extra):
        payload = {"id": uid(), "kind": kind, "amount": amount, "occurred_on": "2026-09-01", "content": "Synthetic flow", "category_id": self.category["id"], "project_mode": "selection"}
        payload["from_account_id" if kind == "payment" else "to_account_id"] = self.account["id"]
        payload.update(extra)
        return payload

    def item(self, kind="loan", amount="100", **extra):
        payload = {"id": uid(), "type": kind, "origin_date": "2026-09-01", "original_amount": amount, "content": "Synthetic item"}
        if kind in {"loan", "company_receivable"}:
            payload.update(obligation_direction="receivable", ledger_group="company", counterparty="Synthetic company")
        if kind == "ticket_source":
            payload.update(ticket_provider="Synthetic provider", ticket_provided_on="2026-09-01", ticket_description="Synthetic tickets")
        payload.update(extra)
        return payload

    def row(self, table, entity_id):
        with self.repo.transaction(readonly=True) as tx:
            return tx.get(table, entity_id)

    def allocation(self, item, kind="cash_repayment", amount="100"):
        return {"id": uid(), "item_id": item["id"], "expected_item_version": item["version"], "target_is_new": False, "kind": kind, "amount": amount}

    def test_plain_create_retry_delete_no_resurrection(self):
        payload = self.flow()
        first = self.service.create_flow(payload, self.actor)
        self.assertTrue(first["created"])
        self.assertEqual(first["flow"]["amount"], "100.00")
        self.assertFalse(self.service.create_flow(payload, self.actor)["created"])
        self.assertEqual(self.service.update_flow(payload["id"], {"expected_version": 1, "remark": None})["changed"], False)
        result = self.service.delete_flow(payload["id"], {"expected_version": 1})
        self.assertTrue(result["deleted"])
        self.assertTrue(self.service.delete_flow(payload["id"], {"expected_version": 1})["already_deleted"])
        with self.assertRaises(CashError) as error:
            self.service.create_flow(payload, self.actor)
        self.assertEqual(error.exception.code, "cash_submission_deleted")
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 0)

    def test_composite_retry_checks_children(self):
        item = self.item()
        payload = self.flow(related_items=[item])
        self.service.create_flow(payload, self.actor)
        self.assertFalse(self.service.create_flow(payload, self.actor)["created"])
        payload["related_items"][0]["original_amount"] = "90"
        with self.assertRaises(CashError) as error:
            self.service.create_flow(payload, self.actor)
        self.assertEqual(error.exception.code, "cash_submission_conflict")
        self.assertEqual(self.row("items", item["id"])["original_amount"], Decimal("100.00"))

    def test_invalid_composite_rolls_back(self):
        payload = self.flow(related_items=[self.item(amount="101")])
        with self.assertRaises(CashError):
            self.service.create_flow(payload, self.actor)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 0)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.items")["n"], 0)

    def test_two_fixed_amount_dimensions(self):
        expense = self.service.create_item(self.item("expense"))["item"]
        loan = self.item()
        payment = self.service.create_flow(self.flow(related_items=[loan], allocations=[self.allocation(expense, "expense_payment")]), self.actor)["flow"]
        loan = self.row("items", loan["id"])
        expense = self.row("items", expense["id"])
        receipt = self.service.create_flow(self.flow("receipt", allocations=[self.allocation(loan), self.allocation(expense, "expense_refund")]), self.actor)["flow"]
        self.assertEqual(payment["amount"], "100.00")
        self.assertEqual(receipt["amount"], "100.00")
        self.assertEqual(self.connection.fetch_one("SELECT sum(amount) AS n FROM cash.flows")["n"], Decimal("200.00"))
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.items WHERE type='expense'")["n"], 1)

    def test_refund_cannot_exceed_paid(self):
        expense = self.service.create_item(self.item("expense"))["item"]
        self.service.create_flow(self.flow(amount="50", allocations=[self.allocation(expense, "expense_payment", "50")]), self.actor)
        expense = self.row("items", expense["id"])
        self.service.create_flow(self.flow("receipt", "40", allocations=[self.allocation(expense, "expense_refund", "40")]), self.actor)
        expense = self.row("items", expense["id"])
        with self.assertRaises(CashError):
            self.service.create_flow(self.flow("receipt", "40", allocations=[self.allocation(expense, "expense_refund", "40")]), self.actor)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 2)

    def test_late_origin_binding_keeps_real_item(self):
        loan = self.service.create_item(self.item())["item"]
        payload = self.flow(origin_items=[{"item_id": loan["id"], "expected_item_version": 1}])
        self.service.create_flow(payload, self.actor)
        self.assertEqual(self.row("items", loan["id"])["origin_mode"], "linked")
        self.service.delete_flow(payload["id"], {"expected_version": 1})
        remaining = self.row("items", loan["id"])
        self.assertIsNone(remaining["origin_flow_id"])
        self.assertEqual(remaining["original_amount"], Decimal("100.00"))

    def test_source_amount_correction_and_false_source_delete(self):
        loan_input = self.item(amount="1000")
        source = self.service.create_flow(self.flow(amount="1000", related_items=[loan_input]), self.actor)["flow"]
        loan = self.row("items", loan_input["id"])
        repayment = self.service.create_flow(self.flow("receipt", "200", allocations=[self.allocation(loan, amount="200")]), self.actor)["flow"]
        loan = self.row("items", loan["id"])
        changed = self.service.update_flow(source["id"], {"expected_version": 1, "amount": "800", "source_corrections": [{"action": "correct_amount", "item_id": loan["id"], "expected_version": loan["version"], "original_amount": "800"}]})
        self.assertEqual(changed["flow"]["amount"], "800.00")
        loan = self.row("items", loan["id"])
        self.service.delete_flow(source["id"], {"expected_version": changed["version"], "source_corrections": [{"action": "delete_false_item", "item_id": loan["id"], "expected_version": loan["version"]}]})
        self.assertEqual(self.row("flows", repayment["id"])["amount"], Decimal("200.00"))
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.settlements")["n"], 0)

    def test_historical_opening_and_r7_no_oa_on_settlement(self):
        loan = self.service.create_item(self.item(is_opening=True, oa_project_id="ended"))["item"]
        self.assertEqual(self.oa_calls, [("ended", True)])
        payload = self.flow("receipt", project_mode="existing_item", project_item_id=loan["id"], expected_project_item_version=1, allocations=[self.allocation(loan)])
        self.service.create_flow(payload, self.actor)
        self.assertEqual(len(self.oa_calls), 1)
        self.assertFalse(self.service.create_flow(payload, self.actor)["created"])
        self.assertEqual(len(self.oa_calls), 1)
        with self.assertRaises(CashError):
            self.service.create_flow(self.flow(oa_project_id="ended"), self.actor)

    def test_r7_rejects_false_anchor_and_new_items(self):
        loan = self.service.create_item(self.item())["item"]
        payload = self.flow("receipt", project_mode="existing_item", project_item_id=loan["id"], expected_project_item_version=1, allocations=[])
        with self.assertRaises(CashError):
            self.service.create_flow(payload, self.actor)
        payload["allocations"] = [self.allocation(loan)]
        payload["related_items"] = []
        with self.assertRaises(CashError):
            self.service.create_flow(payload, self.actor)

    def test_ticket_use_to_offset_once_and_removed_retry_rejected(self):
        ticket = self.service.create_item(self.item("ticket_source"))["item"]
        loan = self.service.create_item(self.item())["item"]
        payload = {"id": uid(), "kind": "ticket_use", "amount": "60", "occurred_on": "2026-09-01", "source_item_id": ticket["id"], "expected_source_item_version": 1, "remark": "Synthetic use"}
        entry = self.service.create_settlement(payload)["settlement"]
        versions = {"items": [{"id": ticket["id"], "version": 2}, {"id": loan["id"], "version": 1}]}
        updated = self.service.update_settlement(entry["id"], {"expected_version": 1, "kind": "ticket_offset", "item_id": loan["id"], "expected_related_versions": versions})
        self.assertEqual(updated["settlement"]["amount"], "60.00")
        self.assertEqual(self.connection.fetch_one("SELECT sum(amount) AS n FROM cash.settlements")["n"], Decimal("60.00"))
        versions = {"items": [{"id": ticket["id"], "version": 3}, {"id": loan["id"], "version": 2}]}
        self.service.delete_settlement(entry["id"], {"expected_version": 2, "expected_related_versions": versions})
        with self.assertRaises(CashError):
            self.service.create_settlement(payload)

    def test_personal_start_does_not_configure_oa(self):
        self.service.update_personal_opening({"expected_version": 1, "opening_date": "2026-01-01"})
        self.assertFalse(self.service.get_project_selection()["configured"])
        first = self.service.update_project_selection({"expected_version": 2, "allowed_stage_codes": []})
        self.assertTrue(first["configured"])
        self.assertEqual(first["version"], 3)
        self.assertFalse(self.service.update_project_selection({"expected_version": 3, "allowed_stage_codes": []})["changed"])

    def test_account_start_cannot_hide_flow(self):
        self.service.create_flow(self.flow(), self.actor)
        with self.assertRaises(CashError):
            self.service.update_account(self.account["id"], {"expected_version": 1, "opening_date": "2026-09-02"})
        self.assertEqual(self.row("accounts", self.account["id"])["opening_date"], date(2026, 1, 1))

    def test_concurrent_double_allocation_is_atomic(self):
        loan = self.service.create_item(self.item())["item"]
        payloads = [self.flow("receipt", "80", allocations=[self.allocation(loan, amount="80")]) for _ in range(2)]
        def run(payload):
            try:
                self.service.create_flow(payload, self.actor)
                return "created"
            except CashError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, payloads))
        self.assertEqual(results.count("created"), 1)
        self.assertEqual(self.connection.fetch_one("SELECT sum(amount) AS n FROM cash.flows")["n"], Decimal("80.00"))

    def test_delete_insert_waiting_race_cannot_resurrect(self):
        payload = self.flow()
        self.service.create_flow(payload, self.actor)
        normalized = self.service.prepare_flow(self.service.normalize_flow(payload, self.actor))
        deleted, attempted = Event(), Event()
        def deleting():
            with self.repo.transaction() as tx:
                tx.delete("flows", payload["id"])
                tx.remember_deleted("flow", payload["id"])
                deleted.set()
                self.assertTrue(attempted.wait(3))
                # Inspect native lock wait rather than guessing scheduling from sleep.
                for _ in range(1000):
                    rows = self.connection.fetch_all("SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE %s", ("INSERT INTO cash.%",))
                    if rows:
                        return
                self.fail("retry INSERT did not wait on uncommitted DELETE")
        def creating():
            self.assertTrue(deleted.wait(3))
            with self.repo.transaction() as tx:
                attempted.set()
                inserted = tx.insert("flows", normalized["flow"])
                self.assertIsNotNone(inserted)
                if tx.was_deleted("flow", payload["id"]):
                    raise CashError("cash_submission_deleted", "deleted", 409)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(deleting)
            second = pool.submit(creating)
            first.result(timeout=10)
            with self.assertRaises(CashError):
                second.result(timeout=10)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 0)

    def test_raw_database_conditional_nulls_rejected(self):
        sql = "INSERT INTO cash.items(id,type,origin_date,original_amount,counterparty,content) VALUES (%s,'loan','2026-09-01',1,'Synthetic','Synthetic')"
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.connection.execute(sql, (uid(),))

    def test_reference_clear_preserves_real_expense(self):
        loan = self.service.create_item(self.item())["item"]
        expense = self.service.create_item(self.item("expense", related_obligation_id=loan["id"], expected_related_versions={"items": [{"id": loan["id"], "version": 1}]}))["item"]
        with self.assertRaises(CashError):
            self.service.delete_item(loan["id"], {"expected_version": 1})
        self.service.delete_item(loan["id"], {"expected_version": 1, "item_reference_changes": [{"item_id": expense["id"], "expected_version": 1, "related_obligation_id": None}]})
        self.assertIsNone(self.row("items", expense["id"])["related_obligation_id"])
        self.assertEqual(self.row("items", expense["id"])["original_amount"], Decimal("100.00"))

    def test_two_explicit_removals_share_original_versions(self):
        loan = self.service.create_item(self.item())["item"]
        first = self.service.create_flow(self.flow("receipt", "20", allocations=[self.allocation(loan, amount="20")]), self.actor)
        loan = self.row("items", loan["id"])
        second = self.service.create_flow(self.flow("receipt", "30", allocations=[self.allocation(loan, amount="30")]), self.actor)
        loan = self.row("items", loan["id"])
        versions = {"items": [{"id": loan["id"], "version": loan["version"]}], "flows": [{"id": first["flow"]["id"], "version": 1}, {"id": second["flow"]["id"], "version": 1}]}
        changes = [{"id": row["allocations"][0]["id"], "expected_version": 1, "action": "remove"} for row in (first, second)]
        self.service.update_item(loan["id"], {"expected_version": loan["version"], "original_amount": "10", "expected_related_versions": versions, "settlement_changes": changes})
        self.assertEqual(self.row("items", loan["id"])["version"], loan["version"] + 1)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 2)

    def test_flow_date_updates_allocations_but_not_independent_item(self):
        loan = self.service.create_item(self.item())["item"]
        result = self.service.create_flow(self.flow("receipt", allocations=[self.allocation(loan)]), self.actor)
        self.service.update_flow(result["flow"]["id"], {"expected_version": 1, "occurred_on": "2026-09-02"})
        self.assertEqual(self.row("settlements", result["allocations"][0]["id"])["occurred_on"], date(2026, 9, 2))
        self.assertEqual(self.row("items", loan["id"])["origin_date"], date(2026, 9, 1))

    def test_edit_deleted_or_old_version_does_not_overwrite(self):
        payload = self.flow()
        self.service.create_flow(payload, self.actor)
        updated = self.service.update_flow(payload["id"], {"expected_version": 1, "content": "Corrected"})
        self.assertEqual(updated["version"], 2)
        with self.assertRaises(CashError):
            self.service.update_flow(payload["id"], {"expected_version": 1, "amount": "5"})
        self.assertEqual(self.row("flows", payload["id"])["amount"], Decimal("100.00"))

    def test_negative_balance_allowed_transfer_one_flow(self):
        second = self.service.create_account({"id": uid(), "name": "Second", "kind": "savings", "opening_date": "2026-01-01", "opening_amount": "0"})["account"]
        result = self.service.create_flow({"id": uid(), "kind": "transfer", "occurred_on": "2026-09-01", "amount": "9999", "from_account_id": self.account["id"], "to_account_id": second["id"], "content": "Synthetic transfer", "project_mode": "selection"}, self.actor)
        self.assertEqual(result["flow"]["amount"], "9999.00")
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 1)

    def test_inactive_account_history_can_edit_note_and_delete(self):
        result = self.service.create_flow(self.flow(), self.actor)
        self.service.update_account(self.account["id"], {"expected_version": 1, "enabled": False})
        updated = self.service.update_flow(result["flow"]["id"], {"expected_version": 1, "remark": "Correction note"})
        self.service.delete_flow(result["flow"]["id"], {"expected_version": updated["version"]})

    def test_new_loan_and_related_expense_are_order_independent(self):
        loan = self.item()
        expense = self.item("expense", related_obligation_id=loan["id"])
        result = self.service.create_flow(self.flow(related_items=[expense, loan]), self.actor)
        self.assertEqual(len(result["related_items"]), 2)

    def test_personal_start_rejects_hiding_real_principal(self):
        self.service.update_personal_opening({"expected_version": 1, "opening_date": "2026-01-01"})
        loan = self.service.create_item(self.item(ledger_group="personal"))["item"]
        with self.assertRaises(CashError):
            self.service.update_personal_opening({"expected_version": 2, "opening_date": "2026-09-02"})
        self.assertEqual(self.row("items", loan["id"])["origin_date"], date(2026, 9, 1))

    def test_future_date_unknown_fields_and_wrong_types_fail(self):
        for changes in ({"occurred_on": "2026-09-08"}, {"source_kind": "monthly_task"}, {"created_by_account": "forged"}, {"amount": 5}, {"project_mode": None}):
            with self.subTest(changes=changes), self.assertRaises(CashError):
                self.service.create_flow(self.flow(**changes), self.actor)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 0)

    def test_cash_and_ticket_different_projects_rejected(self):
        loan = self.service.create_item(self.item(oa_project_id="one"))["item"]
        with self.assertRaises(CashError):
            self.service.create_flow(self.flow("receipt", oa_project_id="two", allocations=[self.allocation(loan)]), self.actor)
        ticket = self.service.create_item(self.item("ticket_source", oa_project_id="two"))["item"]
        with self.assertRaises(CashError):
            self.service.create_settlement({"id": uid(), "kind": "ticket_offset", "amount": "10", "occurred_on": "2026-09-01", "item_id": loan["id"], "expected_item_version": 1, "source_item_id": ticket["id"], "expected_source_item_version": 1})

    def test_cash_allocation_sum_cannot_exceed_flow(self):
        loan1 = self.service.create_item(self.item())["item"]
        loan2 = self.service.create_item(self.item())["item"]
        with self.assertRaises(CashError):
            self.service.create_flow(self.flow("receipt", allocations=[self.allocation(loan1, amount="60"), self.allocation(loan2, amount="60")]), self.actor)
        valid = self.service.create_flow(self.flow("receipt", allocations=[self.allocation(loan1, amount="40"), self.allocation(loan2, amount="60")]), self.actor)
        self.assertEqual(valid["flow"]["amount"], "100.00")

    def test_database_ticket_null_remark_and_missing_snapshot_rejected(self):
        ticket = self.service.create_item(self.item("ticket_source"))["item"]
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.connection.execute("INSERT INTO cash.settlements(id,kind,amount,occurred_on,source_item_id) VALUES (%s,'ticket_use',1,'2026-09-01',%s)", (uid(), ticket["id"]))

    def test_explicit_expense_rebind_preserves_fact_on_new_source_delete(self):
        expense_input = self.item("expense")
        incorrect = self.service.create_flow(self.flow(related_items=[expense_input]), self.actor)["flow"]
        correct = self.service.create_flow(self.flow(), self.actor)["flow"]
        self.service.delete_flow(incorrect["id"], {"expected_version": 1, "source_corrections": [{"action": "rebind_flow", "item_id": expense_input["id"], "expected_version": 1, "new_flow_id": correct["id"], "expected_new_flow_version": 1}]})
        expense = self.row("items", expense_input["id"])
        self.assertEqual(expense["origin_mode"], "linked")
        self.assertEqual(expense["origin_flow_id"], correct["id"])
        self.service.delete_flow(correct["id"], {"expected_version": 2})
        self.assertIsNone(self.row("items", expense["id"])["origin_flow_id"])
        self.assertEqual(self.row("items", expense["id"])["original_amount"], Decimal("100.00"))

    def test_delete_linked_expense_source_rejects_unfunded_real_refund(self):
        expense_input = self.item("expense")
        incorrect = self.service.create_flow(self.flow(related_items=[expense_input]), self.actor)["flow"]
        correct = self.service.create_flow(self.flow(), self.actor)["flow"]
        self.service.delete_flow(incorrect["id"], {"expected_version": 1, "source_corrections": [{"action": "rebind_flow", "item_id": expense_input["id"], "expected_version": 1, "new_flow_id": correct["id"], "expected_new_flow_version": 1}]})
        expense = self.row("items", expense_input["id"])
        self.service.create_flow(self.flow("receipt", "10", allocations=[self.allocation(expense, "expense_refund", "10")]), self.actor)
        with self.assertRaises(CashError):
            self.service.delete_flow(correct["id"], {"expected_version": 2})
        self.assertEqual(self.row("items", expense["id"])["origin_flow_id"], correct["id"])

    def test_concurrent_identical_composite_returns_original_before_old_cas(self):
        loan = self.service.create_item(self.item())["item"]
        payload = self.flow("receipt", allocations=[self.allocation(loan)])
        commands = [self.service.prepare_flow(self.service.normalize_flow(payload, self.actor)) for _ in range(2)]
        def run(command):
            with self.repo.transaction() as tx:
                return self.service.create_flow_in_transaction(tx, command)
        with ThreadPoolExecutor(max_workers=2) as pool:
            with self.repo.transaction() as locked:
                locked.get("items", loan["id"], "update")
                jobs = [pool.submit(run, command) for command in commands]
                for _ in range(1000):
                    waiting = self.connection.fetch_one("SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'")["n"]
                    if waiting >= 2:
                        break
                else:
                    self.fail("concurrent creators did not reach identity/target locks")
            results = [job.result(timeout=5) for job in jobs]
        self.assertEqual(sorted(row["created"] for row in results), [False, True])
        self.assertEqual(self.row("items", loan["id"])["version"], 2)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 1)

    def test_concurrent_identical_settlement_replays_after_graph_lock(self):
        loan = self.service.create_item(self.item())["item"]
        flow = self.service.create_flow(self.flow("receipt"), self.actor)["flow"]
        payload = {"id": uid(), "kind": "cash_repayment", "amount": "100", "occurred_on": "2026-09-01", "item_id": loan["id"], "expected_item_version": 1, "flow_id": flow["id"], "expected_flow_version": 1}
        with ThreadPoolExecutor(max_workers=2) as pool:
            with self.repo.transaction() as locked:
                locked.get("items", loan["id"], "update")
                jobs = [pool.submit(self.service.create_settlement, payload) for _ in range(2)]
                for _ in range(1000):
                    waiting = self.connection.fetch_one("SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'")["n"]
                    if waiting >= 2:
                        break
                else:
                    self.fail("concurrent settlement creators did not reach graph locks")
            results = [job.result(timeout=5) for job in jobs]
        self.assertEqual(sorted(row["created"] for row in results), [False, True])
        self.assertEqual(self.row("items", loan["id"])["version"], 2)

    def test_duplicate_cash_allocation_pair_is_explicit_input_error(self):
        loan = self.service.create_item(self.item())["item"]
        with self.assertRaises(CashError) as error:
            self.service.create_flow(self.flow("receipt", allocations=[self.allocation(loan, amount="40"), self.allocation(loan, amount="60")]), self.actor)
        self.assertEqual(error.exception.code, "cash_invalid_input")

    def test_real_composite_create_delete_retry_interleave_rolls_back_everything(self):
        payload = self.flow(related_items=[self.item()])
        prepared = self.service.prepare_flow(self.service.normalize_flow(payload, self.actor))
        initial_absence, continue_retry, delete_ready, allow_delete_commit = Event(), Event(), Event(), Event()
        retry_service = CashService(self.repo, today=lambda: date(2026, 9, 7))
        original_replay = retry_service.replay_flow
        first_lookup = True

        def delayed_replay(command, tx=None):
            nonlocal first_lookup
            result = original_replay(command, tx)
            if first_lookup:
                first_lookup = False
                self.assertIsNone(result)
                initial_absence.set()
                self.assertTrue(continue_retry.wait(5))
            return result

        retry_service.replay_flow = delayed_replay

        class PausedDeleteRepository(CashRepository):
            @contextmanager
            def transaction(inner, readonly=False):
                with super().transaction(readonly) as tx:
                    yield tx
                    delete_ready.set()
                    if not allow_delete_commit.wait(5):
                        raise AssertionError("delete commit was not released")

        deleting_service = CashService(PausedDeleteRepository(self.connection), today=lambda: date(2026, 9, 7))

        def retry():
            with self.repo.transaction() as tx:
                return retry_service.create_flow_in_transaction(tx, prepared)

        with ThreadPoolExecutor(max_workers=2) as pool:
            retry_job = pool.submit(retry)
            self.assertTrue(initial_absence.wait(3))
            self.service.create_flow(payload, self.actor)
            delete_job = pool.submit(deleting_service.delete_flow, payload["id"], {"expected_version": 1})
            self.assertTrue(delete_ready.wait(3))
            continue_retry.set()
            try:
                for _ in range(1000):
                    rows = self.connection.fetch_all("SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE %s", ('INSERT INTO cash."flows"%',))
                    if rows:
                        break
                else:
                    self.fail("real composite retry did not wait for physical delete")
            finally:
                allow_delete_commit.set()
            self.assertTrue(delete_job.result(timeout=5)["deleted"])
            with self.assertRaises(CashError) as error:
                retry_job.result(timeout=5)
            self.assertEqual(error.exception.code, "cash_submission_deleted")
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 0)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.items")["n"], 0)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.deleted_submission_ids")["n"], 2)


if __name__ == "__main__":
    unittest.main()
