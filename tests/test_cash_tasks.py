"""Cash task rules and transactions against explicit disposable PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fin_ops_platform.services.cash_domain import CashError
from fin_ops_platform.services.cash_tasks import CashTaskService
from fin_ops_platform.services.postgres_repositories.cash_tasks import CashTaskRepository

from tests.test_cash_queries import CashPostgresCase


class CashTaskPostgresTests(CashPostgresCase):
    def setUp(self):
        super().setUp()
        self.now = date(2026, 9, 7)
        self.tasks = CashTaskService(CashTaskRepository(self.connection), self.cash, today=lambda: self.now)

    def template(self, kind="payment", **changes):
        payload = {"id": self.uid(), "title": "Synthetic monthly task", "kind": kind, "execution_day": 5, "remind_days": 2,
                   "effective_from_month": self.now.strftime("%Y-%m")}
        if kind != "check":
            payload.update(default_amount="100.00", default_account_id=self.account["id"], default_category_id=self.category["id"])
        payload.update(changes)
        return self.tasks.create_template(payload)["template"]

    @staticmethod
    def identity(template, month="2026-09", version=None):
        result = {"template_id": template["id"], "month": month, "expected_version": version}
        if version is None:
            result["expected_template_version"] = template["version"]
        return result

    def confirm_new(self, template, amount="30.00", version=None, **changes):
        payload = {**self.identity(template, version=version), "mode": "new_flow", "new_flow": self.flow_payload(amount)}
        payload.update(changes)
        return self.tasks.confirm(payload, self.actor)

    def test_virtual_month_is_read_only_short_month_and_reminder(self):
        self.now = date(2026, 1, 1)
        template = self.template(execution_day=31, remind_days=31)
        result = self.tasks.list_occurrences({"month": "2026-02"})
        row = result["rows"][0]
        self.assertEqual(row["due_on"], "2026-02-28")
        self.assertEqual(row["remind_on"], "2026-01-28")
        self.assertIsNone(row["occurrence_id"])
        self.assertEqual(row["planned_amount"], "100.00")
        self.assertEqual(self.connection.fetch_one("select count(*) as n from cash.task_occurrences")["n"], 0)
        self.assertEqual(self.tasks.list_occurrences({"reminder_from": "2026-01-28", "reminder_to": "2026-01-28"})["rows"][0]["template_id"], template["id"])

    def test_task_multi_kind_state_paging_summary_and_source_queries(self):
        pending = self.template("receipt", title="A pending")
        partial = self.template("payment", title="B partial")
        completed = self.template("payment", title="C completed")
        self.template("check", title="D check")
        partial_flow = self.confirm_new(partial, "30.00")
        self.confirm_new(completed, "100.00")
        query = {"month": "2026-09", "kinds": '["receipt","payment"]', "states": '["pending","partial"]',
                 "sort": "title", "order": "asc", "page": 2, "page_size": 1}
        result = self.tasks.list_occurrences(query)
        self.assertEqual(result["pagination"]["total"], 2)
        self.assertEqual(result["rows"][0]["template_id"], partial["id"])
        self.assertEqual(result["summary"]["counts_by_state"], {"pending": 1, "partial": 1, "completed": 0})
        self.assertEqual(result["summary"]["payment_actual_amount"], "30.00")
        templates = self.tasks.list_templates({"kinds": '["receipt","check"]', "sort": "title", "order": "asc", "page_size": 1})
        self.assertEqual(templates["pagination"]["total"], 2)
        self.assertEqual(templates["rows"][0]["id"], pending["id"])
        flow = self.query.list_flows({"task_occurrence_id": partial_flow["occurrence"]["occurrence_id"],
            "sources": '["monthly_task"]', "kinds": '["payment"]'})
        self.assertEqual(flow["rows"][0]["source_kind"], "monthly_task")
        self.assertEqual(flow["rows"][0]["task"]["template_id"], partial["id"])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from cash.task_occurrences")["n"], 2)
        for raw in ({"kind": "payment", "kinds": '["receipt"]'}, {"kinds": '["transfer"]'},
                    {"states": '[null]'}, {"state": "pending", "states": '["partial"]'}):
            with self.subTest(raw=raw), self.assertRaises(CashError):
                self.tasks.list_occurrences({"month": "2026-09", **raw})

    def test_task_parent_historical_projects_do_not_leak_other_projects(self):
        self.cash.project_resolver = lambda project_id, **_: {"id": project_id, "name": project_id, "selection_settings_version": 1}
        template = self.template()
        result = self.tasks.confirm({**self.identity(template), "mode": "new_flow",
            "new_flow": self.flow_payload("30.00", oa_project_id="parent-project")}, self.actor)
        self.flow(oa_project_id="unrelated-project")
        identity = result["occurrence"]["occurrence_id"]
        projects = self.query.project_options({"task_occurrence_id": identity})
        self.assertEqual(projects["rows"], [{"id": "parent-project", "name": "parent-project"}])
        before = self.query.project_options({"task_occurrence_id": identity, "date_from": "2026-08-01", "date_to": "2026-08-31"})
        self.assertEqual(before["pagination"]["total"], 0)

    def test_partial_confirm_replay_overplan_and_unpaid_rejection(self):
        template = self.template()
        payload = {**self.identity(template), "mode": "new_flow", "new_flow": self.flow_payload("30.00")}
        first = self.tasks.confirm(payload, self.actor)
        self.assertEqual(first["occurrence"]["state"], "partial")
        self.assertEqual(first["flow"]["source_kind"], "monthly_task")
        self.assertEqual(first["version"], 1)
        replay = self.tasks.confirm(payload, self.actor)
        self.assertEqual(replay["flow"]["id"], first["flow"]["id"])
        self.assertEqual(replay["occurrence"]["flow_count"], 1)
        second = self.confirm_new(template, "80.00", version=first["version"])
        self.assertEqual(second["occurrence"]["state"], "completed")
        self.assertTrue(second["occurrence"]["is_over_plan"])
        self.assertEqual(second["occurrence"]["over_plan_amount"], "10.00")
        with self.assertRaises(CashError):
            self.tasks.mark_unpaid(self.identity(template, version=second["version"]))
        with self.assertRaises(CashError):
            self.tasks.adjust({**self.identity(template, version=second["version"]), "planned_amount": None})
        row = self.tasks.list_occurrences({"month": "2026-09"})["rows"][0]
        self.assertEqual(row["actual_amount"], "110.00")

    def test_missing_target_rolls_back_entire_first_month(self):
        template = self.template(default_amount=None)
        with self.assertRaises(CashError):
            self.confirm_new(template)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from cash.task_occurrences")["n"], 0)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from cash.flows")["n"], 0)
        first = self.confirm_new(template, planned_amount="50.00")
        self.assertEqual(first["occurrence"]["state"], "partial")
        with self.assertRaises(CashError):
            self.confirm_new(template, "1.00", version=first["version"], planned_amount="60.00")
        self.assertEqual(self.tasks.list_occurrences({"month": "2026-09"})["rows"][0]["actual_amount"], "30.00")

    def test_direction_and_suballocation_failure_are_atomic(self):
        template = self.template("receipt")
        with self.assertRaises(CashError):
            self.confirm_new(template)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from cash.task_occurrences")["n"], 0)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from cash.flows")["n"], 0)

    def test_existing_manual_flow_claim_preserves_cash_and_settlement(self):
        template = self.template("receipt")
        item = self.item()
        flow = self.flow("25.00", "receipt")
        settlement = self.settlement("cash_repayment", "25.00", item=item, flow=flow)
        payload = {**self.identity(template), "mode": "existing_flow", "existing_flow": {"flow_id": flow["id"], "expected_flow_version": 2}}
        result = self.tasks.confirm(payload, self.actor)
        self.assertEqual(result["flow"]["source_kind"], "manual")
        self.assertEqual(result["flow"]["version"], 3)
        self.assertEqual(result["occurrence"]["actual_amount"], "25.00")
        self.assertEqual(self.query.get_flow(flow["id"])["allocations"][0]["id"], settlement["id"])
        self.assertEqual(self.query.get_item(item["id"])["amounts"]["remaining_obligation_amount"], "75.00")
        self.assertEqual(self.tasks.confirm(payload, self.actor)["flow"]["id"], flow["id"])
        other = self.template("receipt")
        with self.assertRaises(CashError):
            self.tasks.confirm({**self.identity(other), "mode": "existing_flow", "existing_flow": {"flow_id": flow["id"], "expected_flow_version": 3}}, self.actor)

    def test_template_edit_materializes_old_month_and_preserves_snapshots(self):
        self.now = date(2026, 7, 1)
        template = self.template()
        self.now = date(2026, 9, 7)
        updated = self.tasks.update_template(template["id"], {"expected_version": 1, "title": "Future title", "default_amount": "200.00"})
        self.assertEqual(updated["template"]["effective_from_month"], "2026-10")
        old = self.tasks.list_occurrences({"month": "2026-08"})["rows"][0]
        self.assertEqual(old["title"], "Synthetic monthly task")
        self.assertEqual(old["planned_amount"], "100.00")
        self.assertIsNotNone(old["occurrence_id"])
        future = self.tasks.list_occurrences({"month": "2026-10"})["rows"][0]
        self.assertEqual(future["title"], "Future title")
        self.assertEqual(future["planned_amount"], "200.00")
        with self.assertRaises(CashError):
            self.tasks.mark_unpaid(self.identity(template, month="2026-09"))

    def test_occurrence_defaults_and_instructions_keep_month_snapshot_after_template_edit(self):
        template = self.template(instructions="Original monthly instructions")
        keys = ("instructions", "default_account_id", "default_category_id")
        original = {"instructions": "Original monthly instructions", "default_account_id": self.account["id"], "default_category_id": self.category["id"]}
        virtual = self.tasks.list_occurrences({"month": "2026-09"})["rows"][0]
        self.assertIsNone(virtual["occurrence_id"])
        self.assertEqual({key: virtual[key] for key in keys}, original)
        current = self.tasks.mark_unpaid(self.identity(template))["occurrence"]
        explicit_future = self.tasks.adjust({**self.identity(template, month="2026-12"), "note": "Explicit December"})["occurrence"]
        self.assertEqual({key: current[key] for key in keys}, original)
        self.assertEqual({key: explicit_future[key] for key in keys}, original)
        account = self.cash.create_account({"id": self.uid(), "name": "New task account", "kind": "cash", "opening_date": "2026-01-01", "opening_amount": "0.00"})["account"]
        category = self.cash.create_category({"id": self.uid(), "name": "New payment category", "group": "payment"})["category"]
        changed = {"instructions": "Future instructions", "default_account_id": account["id"], "default_category_id": category["id"]}
        self.tasks.update_template(template["id"], {"expected_version": template["version"], **changed})
        for target_month in ("2026-09", "2026-12"):
            row = self.tasks.list_occurrences({"month": target_month})["rows"][0]
            self.assertEqual({key: row[key] for key in keys}, original)
            self.assertEqual(row["template_version"], template["version"])
        updated_current = self.tasks.adjust({**self.identity(template, version=current["version"]), "note": "Current month note"})["occurrence"]
        self.assertEqual({key: updated_current[key] for key in keys}, original)
        future = self.tasks.list_occurrences({"month": "2026-10"})["rows"][0]
        self.assertIsNone(future["occurrence_id"])
        self.assertEqual({key: future[key] for key in keys}, changed)
        self.assertEqual(future["template_version"], template["version"] + 1)

    def test_check_occurrence_keeps_nullable_defaults_in_list_and_command_response(self):
        template = self.template("check")
        listed = self.tasks.list_occurrences({"month": "2026-09"})["rows"][0]
        completed = self.tasks.complete_check(self.identity(template))["occurrence"]
        for row in (listed, completed):
            for key in ("instructions", "default_account_id", "default_category_id"):
                self.assertIn(key, row)
                self.assertIsNone(row[key])

    def test_pause_does_not_erase_explicit_future_or_backfill_paused_months(self):
        template = self.template()
        self.tasks.adjust({**self.identity(template, month="2026-12"), "note": "Explicit future"})
        paused = self.tasks.update_template(template["id"], {"expected_version": 1, "enabled": False})["template"]
        self.assertEqual(self.tasks.list_occurrences({"month": "2026-10"})["rows"], [])
        self.assertEqual(self.tasks.list_occurrences({"month": "2026-12"})["rows"][0]["note"], "Explicit future")
        self.now = date(2026, 11, 1)
        self.tasks.update_template(template["id"], {"expected_version": paused["version"], "enabled": True, "effective_from_month": "2026-11"})
        self.assertEqual(self.tasks.list_occurrences({"month": "2026-10"})["rows"], [])
        self.assertEqual(len(self.tasks.list_occurrences({"month": "2026-11"})["rows"]), 1)

    def test_overdue_includes_never_opened_old_months_and_summary_all_matches(self):
        self.now = date(2026, 7, 1)
        self.template()
        self.now = date(2026, 9, 7)
        result = self.tasks.list_occurrences({"overdue_as_of": "2026-09-07", "page_size": 1})
        self.assertEqual(result["pagination"]["total"], 3)
        self.assertEqual(result["summary"]["task_count"], 3)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["summary"]["counts_by_state"]["pending"], 3)

    def test_check_unpaid_and_reopen_do_not_create_cash(self):
        template = self.template("check")
        complete = self.tasks.complete_check(self.identity(template))
        self.assertEqual(complete["occurrence"]["state"], "completed")
        self.assertIsNone(complete["occurrence"]["actual_amount"])
        reopened = self.tasks.reopen_check(complete["occurrence"]["occurrence_id"], {"expected_version": complete["version"]})
        self.assertEqual(reopened["occurrence"]["state"], "pending")
        with self.assertRaises(CashError):
            self.tasks.mark_unpaid(self.identity(template, version=reopened["version"]))
        money = self.template()
        unpaid = self.tasks.mark_unpaid({**self.identity(money), "note": "Not actually paid"})
        self.assertTrue(unpaid["occurrence"]["marked_unpaid"])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from cash.flows")["n"], 0)

    def test_adjust_dates_keep_attribution_month_and_reminder_selection(self):
        template = self.template()
        result = self.tasks.adjust({**self.identity(template), "due_on": "2026-08-31"})
        self.assertEqual(result["occurrence"]["month"], "2026-09")
        self.assertEqual(result["occurrence"]["due_on"], "2026-08-31")
        reminder = self.tasks.list_occurrences({"reminder_from": "2026-08-29", "reminder_to": "2026-08-29"})
        self.assertEqual(reminder["rows"][0]["month"], "2026-09")
        with self.assertRaises(CashError):
            self.tasks.adjust({**self.identity(template, version=result["version"]), "due_on": "2026-11-02"})

    def test_two_first_confirmations_cannot_bypass_null_month_version(self):
        template = self.template()
        def pay():
            try:
                return self.confirm_new(template)
            except CashError as error:
                return error
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: pay(), range(2)))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, CashError) and result.status == 409 for result in results), 1)
        self.assertEqual(self.tasks.list_occurrences({"month": "2026-09"})["rows"][0]["actual_amount"], "30.00")

    def test_task_link_selector_and_invalid_query(self):
        template = self.template()
        self.flow()
        self.flow("10.00", "receipt")
        result = self.query.list_flows({"date_from": "2026-09-01", "date_to": "2026-09-30", "purpose": "task_link", "template_id": template["id"], "month": "2026-09"})
        self.assertEqual(sum(row["selectable"] for row in result["rows"]), 1)
        for raw in ({}, {"month": "2026-09", "overdue_as_of": "2026-09-01"}, {"reminder_from": "2026-01-01", "reminder_to": "2026-03-10"}, {"overdue_as_of": "2026-09-08"}, {"month": "2026-09", "state": "paid"}):
            with self.assertRaises(CashError):
                self.tasks.list_occurrences(raw)

    def test_concurrent_same_first_cash_id_returns_one_creation(self):
        template = self.template()
        payload = {**self.identity(template), "mode": "new_flow", "new_flow": self.flow_payload("30.00")}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.tasks.confirm(payload, self.actor), range(2)))
        self.assertEqual(results[0]["flow"]["id"], results[1]["flow"]["id"])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from cash.flows")["n"], 1)

    def test_deleted_task_cash_recomputes_all_queries_and_cannot_replay(self):
        template = self.template()
        payload = {**self.identity(template), "mode": "new_flow", "new_flow": self.flow_payload("100.00")}
        confirmed = self.tasks.confirm(payload, self.actor)
        flow = confirmed["flow"]
        self.cash.delete_flow(flow["id"], {"expected_version": flow["version"]}, self.actor)
        current = self.tasks.list_occurrences({"month": "2026-09"})["rows"][0]
        self.assertEqual(current["state"], "pending")
        self.assertEqual(current["actual_amount"], "0.00")
        self.assertEqual(self.query.list_flows({"task_occurrence_id": current["occurrence_id"]})["rows"], [])
        with self.assertRaises(CashError):
            self.tasks.confirm(payload, self.actor)

    def test_invalid_template_types_and_missing_dependency_roll_back(self):
        for fields in ({"execution_day": "5"}, {"remind_days": True}, {"remind_days": 32}, {"default_account_id": self.uid()}):
            with self.assertRaises(CashError):
                self.template(**fields)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from cash.task_templates")["n"], 0)
