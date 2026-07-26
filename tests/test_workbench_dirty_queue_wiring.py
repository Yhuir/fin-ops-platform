from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fin_ops_platform.app.server as server_module
from fin_ops_platform.app import worker as worker_app
from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.app.worker import build_parser
from fin_ops_platform.services.runtime_worker_handlers import _workbench_matching_source_versions
from fin_ops_platform.services.workbench_matching_dirty_scope_worker import (
    WorkbenchMatchingDirtyScopeWorker,
    WorkbenchMatchingDirtyScopeWorkerConfig,
)
from fin_ops_platform.services.workbench_reconciliation_dirty_queue import expand_scope_month_window


class RecordingDirtyQueue:
    def __init__(
        self,
        *,
        claim_months: list[str] | None = None,
        stale_months: list[str] | None = None,
    ) -> None:
        self.mark_calls: list[dict[str, object]] = []
        self.stale_scan_calls: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.complete_calls: list[dict[str, object]] = []
        self.fail_calls: list[dict[str, object]] = []
        self.claim_months = list(claim_months or [])
        self.stale_months = list(stale_months or [])

    def mark_stale_completed_scopes(
        self,
        *,
        source_versions: dict[str, object],
        reason: str,
        debounce_seconds: int = 0,
        limit: int | None = None,
    ) -> list[str]:
        self.stale_scan_calls.append(
            {
                "source_versions": dict(source_versions),
                "reason": reason,
                "debounce_seconds": debounce_seconds,
                "limit": limit,
            }
        )
        return list(self.stale_months)

    def mark_dirty_expanded(
        self,
        months: list[str],
        *,
        reason: str,
        source_versions: dict[str, object] | None = None,
        debounce_seconds: int | None = None,
    ) -> list[str]:
        call: dict[str, object] = {
            "months": list(months),
            "reason": reason,
            "source_versions": dict(source_versions or {}),
        }
        if debounce_seconds is not None:
            call["debounce_seconds"] = debounce_seconds
        self.mark_calls.append(call)
        return sorted({expanded for month in months for expanded in expand_scope_month_window(month)})

    def claim_due_scopes(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int | None = None,
        request_id: str | None = None,
    ) -> list[str]:
        self.claim_calls.append(
            {
                "worker_id": worker_id,
                "limit": limit,
                "lease_seconds": lease_seconds,
                "request_id": request_id,
            }
        )
        return list(self.claim_months)

    def complete(
        self,
        scope_month: str,
        *,
        source_versions: dict[str, object],
        worker_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.complete_calls.append(
            {
                "scope_month": scope_month,
                "source_versions": dict(source_versions),
                "worker_id": worker_id,
                "request_id": request_id,
            }
        )

    def fail(
        self,
        scope_month: str,
        *,
        error: str,
        retry_delay_seconds: int | None = None,
        worker_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.fail_calls.append(
            {
                "scope_month": scope_month,
                "error": error,
                "retry_delay_seconds": retry_delay_seconds,
                "worker_id": worker_id,
                "request_id": request_id,
            }
        )


class FailingMarkDirtyQueue(RecordingDirtyQueue):
    def mark_dirty_expanded(
        self,
        months: list[str],
        *,
        reason: str,
        source_versions: dict[str, object] | None = None,
    ) -> list[str]:
        raise RuntimeError("db queue unavailable")


class RecordingReadModelQueue:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.calls.append(dict(kwargs))


class RecordingHeartbeatRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def record_worker_heartbeat(
        self,
        worker_id: str,
        worker_kind: str,
        status: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.calls.append(
            {
                "worker_id": worker_id,
                "worker_kind": worker_kind,
                "status": status,
                "payload": dict(payload or {}),
            }
        )


class WorkbenchDirtyQueueWiringTests(unittest.TestCase):
    def test_matching_source_versions_exclude_workbench_projection_schema(self) -> None:
        app = build_application()

        application_versions = app._workbench_matching_source_versions()
        worker_versions = _workbench_matching_source_versions(app._app_settings_service)
        bank_batch_versions = app._bank_batch_workbench_source_versions()

        self.assertNotIn("workbench_read_model_schema_version", application_versions)
        self.assertNotIn("workbench_read_model_schema_version", worker_versions)
        self.assertIn("workbench_read_model_schema_version", bank_batch_versions)

    def test_matching_worker_applies_configured_statement_timeout_before_polling(self) -> None:
        class Queue:
            def __init__(self) -> None:
                self.statement_timeouts: list[int | None] = []

            def set_statement_timeout_seconds(self, seconds: int | None) -> None:
                self.statement_timeouts.append(seconds)

        queue = Queue()

        worker_app._apply_statement_timeout(queue, 120)

        self.assertEqual(queue.statement_timeouts, [120])

    def test_historical_etc_repair_marks_only_exact_expanded_matching_scope(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue()
        app._workbench_reconciliation_dirty_queue = queue

        summary = app._execute_explicit_maintenance_lifecycle(
            "etc_business_batch_changed",
            months=["2026-05"],
            include_all=False,
            metadata={"reason": "historical_etc_repair"},
        )

        self.assertEqual(
            queue.mark_calls,
            [
                {
                    "months": ["2026-05"],
                    "reason": "historical_etc_repair",
                    "source_versions": app._workbench_matching_source_versions(),
                }
            ],
        )
        self.assertEqual(
            summary["invalidated_scopes"],
            ["2026-05", "2026-03", "2026-04", "2026-06", "2026-07"],
        )

    def test_explicit_maintenance_refreshes_keep_owner_metadata(self) -> None:
        app = build_application()
        queue = RecordingReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)

        app._execute_explicit_maintenance_lifecycle(
            "etc_business_batch_changed",
            scope_keys=["2026-05"],
            include_all=False,
            metadata={"source": "historical_etc_repair_link"},
        )

        workbench_relation_calls = [
            call
            for call in queue.calls
            if call.get("scope_type") == "workbench_relation" and call.get("scope_key") == "2026-05"
        ]
        self.assertTrue(workbench_relation_calls)
        self.assertEqual(
            workbench_relation_calls[0].get("metadata"),
            {"source": "historical_etc_repair_link"},
        )

    def test_ordinary_write_events_are_not_accepted_by_maintenance_boundary(self) -> None:
        app = build_application()

        with self.assertRaisesRegex(ValueError, "Unsupported"):
            app._execute_explicit_maintenance_lifecycle(
                "pair_relation_changed",
                scope_keys=["2026-05"],
                include_all=False,
            )

    def test_import_state_persistence_does_not_fan_out_page_refreshes(self) -> None:
        app = build_application()
        queue = RecordingReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)

        app._persist_confirmed_import_delta(
            import_state_payload={"imports": {}, "file_imports": {}},
        )

        refreshes = [
            (call.get("scope_type"), call.get("scope_key"), call.get("reason"))
            for call in queue.calls
        ]
        self.assertEqual(refreshes, [])

    def test_db_dirty_queue_write_path_marks_scope_instead_of_inline_matching(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue()
        app._workbench_reconciliation_dirty_queue = queue

        with patch.object(app, "_run_workbench_auto_matching_for_scopes") as run_matching:
            result = app._schedule_or_run_workbench_auto_matching_for_scopes(
                ["2026-05"],
                reason="import_confirm",
            )

        run_matching.assert_not_called()
        self.assertEqual(queue.mark_calls[0]["months"], ["2026-05"])
        self.assertEqual(queue.mark_calls[0]["reason"], "import_confirm")
        self.assertEqual(result["queued_months"], ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07"])

    def test_db_dirty_queue_mark_failure_does_not_fall_back_to_in_memory_state(self) -> None:
        app = build_application()
        app._workbench_reconciliation_dirty_queue = FailingMarkDirtyQueue()

        with self.assertRaisesRegex(RuntimeError, "db queue unavailable"):
            app._schedule_or_run_workbench_auto_matching_for_scopes(["2026-05"], reason="import_confirm")

        self.assertFalse(hasattr(app, "_workbench_matching_dirty_scope_service"))

    def test_exception_apply_api_commits_without_write_time_read_model_fanout(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue()
        app._workbench_reconciliation_dirty_queue = queue
        rows = [
            {
                "id": "oa-exc-api-001",
                "type": "oa",
                "month": "2026-05",
                "apply_type": "付款申请",
                "amount": "100.00",
            },
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

        with (
            patch.object(app, "_resolve_live_rows_direct", return_value=rows),
            patch.object(app, "_workbench_write_freshness_guard", return_value=None),
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/exception/apply",
                json.dumps(
                    {
                        "month": "2026-05",
                        "row_ids": ["oa-exc-api-001", "bank-exc-api-001", "invoice-exc-api-001"],
                        "scenario_code": "expense_all_equal",
                        "action_code": "confirm_closed",
                        "payload": {},
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(queue.mark_calls, [])

    def test_http_server_does_not_start_workbench_dirty_worker_by_default(self) -> None:
        class FakeServer:
            def __init__(self, address, handler_factory) -> None:
                self.address = address
                self.handler_factory = handler_factory

            def serve_forever(self) -> None:
                raise KeyboardInterrupt()

            def server_close(self) -> None:
                pass

        class FakeApplication:
            def __init__(self) -> None:
                self.workbench_dirty_started = False

            def start_workbench_matching_dirty_scope_worker(self) -> bool:
                self.workbench_dirty_started = True
                return True

        app = FakeApplication()
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED",
            }
        }
        env["FIN_OPS_OA_POLLING_ENABLED"] = "1"
        with patch.dict(os.environ, env, clear=True), patch.object(server_module, "ThreadingHTTPServer", FakeServer):
            server_module.run_http_server("127.0.0.1", 0, app)

        self.assertFalse(app.workbench_dirty_started)

    def test_oa_invoice_offset_settings_change_marks_all_available_months_dirty(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue()
        app._workbench_reconciliation_dirty_queue = queue
        current = app._app_settings_service.get_settings_payload()
        access_control = current.get("access_control") or {}
        projects = current.get("projects") or {}
        payload = {
            "completed_project_ids": list(projects.get("completed_project_ids") or []),
            "bank_account_mappings": list(current.get("bank_account_mappings") or []),
            "allowed_usernames": list(access_control.get("allowed_usernames") or []),
            "readonly_export_usernames": list(access_control.get("readonly_export_usernames") or []),
            "admin_usernames": list(access_control.get("admin_usernames") or []),
            "workbench_column_layouts": dict(current.get("workbench_column_layouts") or {}),
            "oa_retention": dict(current.get("oa_retention") or {}),
            "oa_import": dict(current.get("oa_import") or {}),
            "oa_invoice_offset": {"applicant_names": ["李四"]},
            "pending_invoice_tag_groups": dict(current.get("pending_invoice_tag_groups") or {}),
            "pending_output_invoice_tag_groups": dict(current.get("pending_output_invoice_tag_groups") or {}),
        }
        session = SimpleNamespace(
            allowed=True,
            can_access_app=True,
            can_mutate_data=True,
            identity=SimpleNamespace(user_id=None, username="finance-admin"),
        )

        with (
            patch.object(app._workbench_query_service, "list_available_months", return_value=["2026-05"]),
            patch("fin_ops_platform.app.server.resolve_oa_request_session", return_value=session),
        ):
            response = app.handle_request("POST", "/api/workbench/settings", body=json.dumps(payload), headers={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(queue.mark_calls, [])

    def test_startup_stale_scan_is_disabled_during_application_startup_by_default(self) -> None:
        with patch.object(
            server_module.Application,
            "_schedule_startup_workbench_matching_stale_scan",
            autospec=True,
        ) as scan:
            with patch.dict(os.environ, {"FIN_OPS_STARTUP_WORKBENCH_MATCHING_STALE_SCAN_ENABLED": "0"}):
                build_application()

        scan.assert_not_called()

    def test_startup_stale_scan_can_be_enabled_during_application_startup(self) -> None:
        with patch.object(
            server_module.Application,
            "_schedule_startup_workbench_matching_stale_scan",
            autospec=True,
        ) as scan:
            with patch.dict(os.environ, {"FIN_OPS_STARTUP_WORKBENCH_MATCHING_STALE_SCAN_ENABLED": "1"}):
                build_application()

        scan.assert_called_once()

    def test_startup_stale_scan_requeues_only_stale_completed_durable_scopes(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue(stale_months=["2026-05"])
        app._workbench_reconciliation_dirty_queue = queue

        summary = app._schedule_startup_workbench_matching_stale_scan()

        self.assertEqual(
            queue.stale_scan_calls,
            [
                {
                    "source_versions": app._workbench_matching_source_versions(),
                    "reason": "startup_matching_source_versions_changed",
                    "debounce_seconds": 0,
                    "limit": 1000,
                }
            ],
        )
        self.assertEqual(
            summary,
            {"queued_months": ["2026-05"], "reason": "startup_matching_source_versions_changed"},
        )

    def test_startup_stale_scan_is_noop_when_durable_queue_has_no_stale_completed_scope(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue()
        app._workbench_reconciliation_dirty_queue = queue

        self.assertIsNone(app._schedule_startup_workbench_matching_stale_scan())
        self.assertEqual(len(queue.stale_scan_calls), 1)

    def test_worker_cli_exposes_workbench_matching_dirty_queue_options(self) -> None:
        args = build_parser().parse_args(
            [
                "--enable-workbench-matching",
                "--workbench-matching-batch-size",
                "7",
                "--workbench-matching-lease-seconds",
                "300",
                "--workbench-matching-retry-delay-seconds",
                "45",
            ]
        )

        self.assertTrue(args.enable_workbench_matching)
        self.assertEqual(args.workbench_matching_batch_size, 7)
        self.assertEqual(args.workbench_matching_lease_seconds, 300)
        self.assertEqual(args.workbench_matching_retry_delay_seconds, 45)

    def test_worker_wiring_uses_decoupled_dirty_scope_runner(self) -> None:
        queue = RecordingDirtyQueue()
        heartbeat_recorder = RecordingHeartbeatRecorder()
        worker = WorkbenchMatchingDirtyScopeWorker(
            dirty_queue=queue,
            matching_orchestrator=SimpleNamespace(run=lambda **kwargs: {}),
            source_versions_provider=lambda: {"rules": "v1"},
            heartbeat_recorder=heartbeat_recorder,
            config=WorkbenchMatchingDirtyScopeWorkerConfig(
                worker_id="worker-a",
                poll_interval_seconds=0.1,
                batch_size=7,
                lease_seconds=300,
                retry_delay_seconds=45,
                max_iterations=1,
            ),
            sleep=lambda _seconds: None,
        )
        worker.run_once()

        self.assertEqual(queue.claim_calls[0]["worker_id"], "worker-a")
        self.assertEqual(queue.claim_calls[0]["limit"], 7)
        self.assertEqual(queue.claim_calls[0]["lease_seconds"], 300)
        self.assertEqual([call["status"] for call in heartbeat_recorder.calls], ["polling", "idle"])
        self.assertEqual(heartbeat_recorder.calls[-1]["worker_kind"], "workbench-matching")

    def test_deploy_env_includes_dedicated_workbench_matching_worker(self) -> None:
        root_dir = Path(__file__).resolve().parents[1]
        env_path = root_dir / "deploy/oa/env/fin-ops.worker.workbench-matching.env.example"

        content = env_path.read_text(encoding="utf-8")

        self.assertIn("FIN_OPS_APP_STORAGE_BACKEND=postgres", content)
        self.assertIn("FIN_OPS_APP_READ_BACKEND=postgres", content)
        self.assertIn("FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary", content)
        self.assertIn("FIN_OPS_STORAGE_MODE=postgres", content)
        self.assertIn("FIN_OPS_QUEUE_BACKEND=postgres", content)
        self.assertIn("FIN_OPS_WORKER_KIND=workbench-matching", content)
        self.assertIn("--enable-workbench-matching", content)
        self.assertIn("--workbench-matching-batch-size", content)
        self.assertIn("--workbench-matching-lease-seconds", content)


if __name__ == "__main__":
    unittest.main()
