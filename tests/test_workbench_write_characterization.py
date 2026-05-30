from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fin_ops_platform.app.server import Application, build_application
from fin_ops_platform.app.worker import _run_workbench_matching_dirty_queue_loop


def _flatten_groups(groups: list[dict[str, object]], record_type: str) -> list[dict[str, object]]:
    key = f"{record_type}_rows"
    rows: list[dict[str, object]] = []
    for group in groups:
        rows.extend(group[key])
    return rows


def _json_response(response) -> dict[str, object]:
    return json.loads(response.body)


class WorkbenchWriteCharacterizationTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()

    def _build_app(self) -> Application:
        app = build_application()
        app._emit_workbench_action_timing = lambda **kwargs: None
        return app

    def _workbench_payload(self, app: Application, month: str = "2026-03") -> dict[str, object]:
        response = app.handle_request("GET", f"/api/workbench?month={month}")
        self.assertEqual(response.status_code, 200, response.body)
        return _json_response(response)

    def _default_open_row_ids(self, app: Application) -> list[str]:
        payload = self._workbench_payload(app)
        return [
            _flatten_groups(payload["open"]["groups"], "oa")[0]["id"],
            _flatten_groups(payload["open"]["groups"], "bank")[0]["id"],
            _flatten_groups(payload["open"]["groups"], "invoice")[0]["id"],
        ]

    def _default_invoice_row_id(self, app: Application) -> str:
        payload = self._workbench_payload(app)
        return str(_flatten_groups(payload["open"]["groups"], "invoice")[0]["id"])

    def _post(self, app: Application, path: str, payload: dict[str, object]):
        return app.handle_request("POST", path, json.dumps(payload))

    @contextmanager
    def _suppress_background_persistence(self, app: Application):
        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist") as pair_relation_persist,
            patch.object(app, "_schedule_workbench_read_model_persist") as read_model_persist,
        ):
            yield pair_relation_persist, read_model_persist

    def test_duplicate_confirm_link_with_same_case_id_replays_success_and_reschedules(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            first_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-DUP-SAME"},
            )
            second_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-DUP-SAME"},
            )

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        first_payload = _json_response(first_response)
        second_payload = _json_response(second_response)
        self.assertEqual(first_payload["case_id"], "CASE-DUP-SAME")
        self.assertEqual(second_payload["case_id"], "CASE-DUP-SAME")
        self.assertCountEqual(first_payload["affected_row_ids"], row_ids)
        self.assertCountEqual(second_payload["affected_row_ids"], row_ids)

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-DUP-SAME")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertCountEqual(relation["row_ids"], row_ids)
        self.assertEqual(
            [entry["operation_type"] for entry in app._workbench_pair_relation_service.list_history()],
            ["confirm_link", "confirm_link"],
        )
        self.assertEqual(pair_relation_persist.call_count, 2)
        self.assertEqual(read_model_persist.call_count, 2)

    def test_duplicate_confirm_link_without_case_id_allocates_new_case_and_replaces_active_relation(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            first_response = self._post(app, "/api/workbench/actions/confirm-link", {"month": "2026-03", "row_ids": row_ids})
            second_response = self._post(app, "/api/workbench/actions/confirm-link", {"month": "2026-03", "row_ids": row_ids})

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        first_payload = _json_response(first_response)
        second_payload = _json_response(second_response)
        self.assertEqual(first_payload["case_id"], "CASE-AUTO-0001")
        self.assertEqual(second_payload["case_id"], "CASE-AUTO-0002")
        active_relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_ids[0])
        self.assertIsNotNone(active_relation)
        assert active_relation is not None
        self.assertEqual(active_relation["case_id"], "CASE-AUTO-0002")
        self.assertEqual(
            [entry["operation_type"] for entry in app._workbench_pair_relation_service.list_history()],
            ["confirm_link", "confirm_link"],
        )

    def test_duplicate_cancel_link_returns_not_found_after_first_cancel(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-DUP"},
            )
            first_cancel = self._post(app, "/api/workbench/actions/cancel-link", {"month": "2026-03", "row_id": row_ids[1]})
            second_cancel = self._post(app, "/api/workbench/actions/cancel-link", {"month": "2026-03", "row_id": row_ids[1]})

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(first_cancel.status_code, 200, first_cancel.body)
        self.assertEqual(second_cancel.status_code, 404, second_cancel.body)
        self.assertEqual(_json_response(second_cancel)["error"], "workbench_pair_relation_not_found")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CANCEL-DUP"))

    def test_duplicate_ignore_and_unignore_current_behavior(self) -> None:
        app = self._build_app()
        invoice_row_id = self._default_invoice_row_id(app)

        with self._suppress_background_persistence(app):
            first_ignore = self._post(
                app,
                "/api/workbench/actions/ignore-row",
                {"month": "2026-03", "row_id": invoice_row_id, "comment": "ignore once"},
            )
            second_ignore = self._post(
                app,
                "/api/workbench/actions/ignore-row",
                {"month": "2026-03", "row_id": invoice_row_id, "comment": "ignore twice"},
            )
            first_unignore = self._post(app, "/api/workbench/actions/unignore-row", {"month": "2026-03", "row_id": invoice_row_id})
            second_unignore = self._post(app, "/api/workbench/actions/unignore-row", {"month": "2026-03", "row_id": invoice_row_id})

        self.assertEqual(first_ignore.status_code, 200, first_ignore.body)
        self.assertEqual(second_ignore.status_code, 200, second_ignore.body)
        first_ignore_payload = _json_response(first_ignore)
        second_ignore_payload = _json_response(second_ignore)
        self.assertEqual(first_ignore_payload["exception_case_id"], second_ignore_payload["exception_case_id"])
        self.assertEqual(first_unignore.status_code, 200, first_unignore.body)
        self.assertEqual(second_unignore.status_code, 404, second_unignore.body)
        self.assertEqual(_json_response(second_unignore)["error"], "workbench_row_not_found")
        case = app._workbench_exception_case_service.snapshot()["cases"][first_ignore_payload["exception_case_id"]]
        self.assertEqual(case["status"], "cancelled")

    def test_duplicate_mark_exception_reuses_existing_case_and_replays_success(self) -> None:
        app = self._build_app()
        invoice_row_id = self._default_invoice_row_id(app)

        with self._suppress_background_persistence(app):
            first_response = self._post(
                app,
                "/api/workbench/actions/mark-exception",
                {
                    "month": "2026-03",
                    "row_id": invoice_row_id,
                    "exception_code": "pending_collection",
                    "comment": "pending once",
                },
            )
            second_response = self._post(
                app,
                "/api/workbench/actions/mark-exception",
                {
                    "month": "2026-03",
                    "row_id": invoice_row_id,
                    "exception_code": "pending_collection",
                    "comment": "pending twice",
                },
            )

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        first_payload = _json_response(first_response)
        second_payload = _json_response(second_response)
        self.assertEqual(first_payload["exception_case_id"], second_payload["exception_case_id"])
        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)
        case = app._workbench_exception_case_service.snapshot()["cases"][first_payload["exception_case_id"]]
        self.assertEqual(case["status"], "open")

    def test_duplicate_exception_apply_is_service_idempotent_at_http_boundary(self) -> None:
        app = self._build_app()
        rows = [
            {"id": "oa-exc-api-001", "type": "oa", "month": "2026-05", "apply_type": "付款申请", "amount": "100.00"},
            {
                "id": "bank-exc-api-001",
                "type": "bank",
                "month": "2026-05",
                "debit_amount": "100.00",
                "credit_amount": "",
                "summary": "支付供应商",
            },
            {
                "id": "invoice-exc-api-001",
                "type": "invoice",
                "month": "2026-05",
                "issue_date": "2026-05-10",
                "total_with_tax": "100.00",
                "invoice_type": "进项发票",
            },
        ]
        request_payload = {
            "month": "2026-05",
            "row_ids": ["oa-exc-api-001", "bank-exc-api-001", "invoice-exc-api-001"],
            "scenario_code": "expense_all_equal",
            "action_code": "confirm_closed",
            "payload": {},
        }

        with patch.object(app, "_resolve_live_rows_direct", return_value=rows), self._suppress_background_persistence(app):
            first_response = self._post(app, "/api/workbench/exception/apply", request_payload)
            second_response = self._post(app, "/api/workbench/exception/apply", request_payload)

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        first_payload = _json_response(first_response)
        second_payload = _json_response(second_response)
        self.assertFalse(first_payload["idempotent"])
        self.assertTrue(second_payload["idempotent"])
        self.assertEqual(first_payload["case"]["id"], second_payload["case"]["id"])
        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)

    def test_stale_confirm_after_ignore_creates_pair_relation_and_leaves_ignored_case_active(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            ignore_response = self._post(app, "/api/workbench/actions/ignore-row", {"month": "2026-03", "row_id": row_ids[2]})
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-STALE-CONFIRM"},
            )

        self.assertEqual(ignore_response.status_code, 200, ignore_response.body)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-STALE-CONFIRM")
        self.assertIsNotNone(relation)
        ignored_case_id = _json_response(ignore_response)["exception_case_id"]
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"][ignored_case_id]["status"], "ignored")

    def test_stale_ignore_after_confirm_keeps_active_relation_and_creates_ignored_case(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-STALE-IGNORE"},
            )
            ignore_response = self._post(app, "/api/workbench/actions/ignore-row", {"month": "2026-03", "row_id": row_ids[2]})

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(ignore_response.status_code, 200, ignore_response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-STALE-IGNORE")
        self.assertIsNotNone(relation)
        ignored_case_id = _json_response(ignore_response)["exception_case_id"]
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"][ignored_case_id]["status"], "ignored")

    def test_stale_cancel_after_replaced_cancels_current_relation_by_row_id(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            old_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-OLD"},
            )
            replacement_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-NEW"},
            )
            cancel_response = self._post(app, "/api/workbench/actions/cancel-link", {"month": "2026-03", "row_id": row_ids[1]})

        self.assertEqual(old_response.status_code, 200, old_response.body)
        self.assertEqual(replacement_response.status_code, 200, replacement_response.body)
        self.assertEqual(cancel_response.status_code, 200, cancel_response.body)
        self.assertEqual(_json_response(cancel_response)["case_id"], "CASE-NEW")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-OLD"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-NEW"))

    def test_stale_exception_after_relation_returns_conflict_and_preserves_relation(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-STALE-EXCEPTION"},
            )
            exception_response = self._post(
                app,
                "/api/workbench/actions/mark-exception",
                {"month": "2026-03", "row_id": row_ids[2], "exception_code": "pending_collection"},
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(exception_response.status_code, 409, exception_response.body)
        self.assertEqual(_json_response(exception_response)["error"], "active_pair_relation_conflict")
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-STALE-EXCEPTION"))
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"], {})

    def test_read_model_scheduling_failure_propagates_after_pair_relation_fact_is_mutated(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist", side_effect=RuntimeError("mock read model scheduling failure")),
        ):
            with self.assertRaisesRegex(RuntimeError, "mock read model scheduling failure"):
                self._post(
                    app,
                    "/api/workbench/actions/confirm-link",
                    {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-SCHEDULING-FAIL"},
                )

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-SCHEDULING-FAIL")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertCountEqual(relation["row_ids"], row_ids)


class WorkbenchWriteWorkerTriggerCharacterizationTests(unittest.TestCase):
    def test_http_process_dirty_worker_uses_opt_in_interval_and_starts_once(self) -> None:
        app = build_application()

        with patch("fin_ops_platform.app.server.Thread") as thread_class:
            self.assertFalse(app.start_workbench_matching_dirty_scope_worker(interval_seconds=0))
            self.assertFalse(thread_class.called)

            self.assertTrue(app.start_workbench_matching_dirty_scope_worker(interval_seconds=1))
            self.assertTrue(app.start_workbench_matching_dirty_scope_worker(interval_seconds=1))

        thread_class.assert_called_once()
        self.assertEqual(thread_class.call_args.kwargs["target"], app._run_workbench_matching_dirty_scope_worker)
        self.assertEqual(thread_class.call_args.kwargs["kwargs"], {"interval_seconds": 60.0})
        self.assertTrue(thread_class.call_args.kwargs["daemon"])
        thread_class.return_value.start.assert_called_once()

    def test_standalone_matching_loop_honors_max_iterations_without_sleeping_after_final_iteration(self) -> None:
        class FakeApplication:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def _rebuild_workbench_matching_dirty_scopes_once(self, **kwargs) -> None:
                self.calls.append(dict(kwargs))

        application = FakeApplication()

        with patch("fin_ops_platform.app.worker.sleep") as sleep:
            _run_workbench_matching_dirty_queue_loop(
                application,
                worker_id="worker-test",
                poll_interval_seconds=0,
                batch_size=3,
                lease_seconds=120,
                retry_delay_seconds=15,
                max_iterations=1,
            )

        self.assertEqual(
            application.calls,
            [
                {
                    "worker_id": "worker-test",
                    "limit": 3,
                    "lease_seconds": 120,
                    "retry_delay_seconds": 15,
                }
            ],
        )
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
