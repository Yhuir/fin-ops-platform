from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fin_ops_platform.app.server as server_module
from fin_ops_platform.app.server import build_application
from fin_ops_platform.app.worker import build_parser
from fin_ops_platform.services.workbench_matching_dirty_scope_worker import (
    WorkbenchMatchingDirtyScopeWorker,
    WorkbenchMatchingDirtyScopeWorkerConfig,
)
from fin_ops_platform.services.workbench_reconciliation_models import expand_scope_month_window


class RecordingDirtyQueue:
    def __init__(self, *, claim_months: list[str] | None = None) -> None:
        self.mark_calls: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.complete_calls: list[dict[str, object]] = []
        self.fail_calls: list[dict[str, object]] = []
        self.claim_months = list(claim_months or [])

    def mark_dirty_expanded(
        self,
        months: list[str],
        *,
        reason: str,
        source_versions: dict[str, object] | None = None,
    ) -> list[str]:
        self.mark_calls.append(
            {
                "months": list(months),
                "reason": reason,
                "source_versions": dict(source_versions or {}),
            }
        )
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


class FailingClaimDirtyQueue(RecordingDirtyQueue):
    def claim_due_scopes(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int | None = None,
        request_id: str | None = None,
    ) -> list[str]:
        raise RuntimeError("db queue unavailable")


class FailingMarkDirtyQueue(RecordingDirtyQueue):
    def mark_dirty_expanded(
        self,
        months: list[str],
        *,
        reason: str,
        source_versions: dict[str, object] | None = None,
    ) -> list[str]:
        raise RuntimeError("db queue unavailable")


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
    def test_import_and_oa_lifecycle_events_mark_expanded_db_dirty_scopes(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue()
        app._workbench_reconciliation_dirty_queue = queue

        summary = app._execute_derived_data_lifecycle_event(
            "invoice_import_confirmed",
            months=["2026-05"],
            include_all=False,
            metadata={"reason": "invoice_import_confirm"},
            schedule_cost_warmup=False,
        )

        self.assertEqual(
            queue.mark_calls,
            [
                {
                    "months": ["2026-05"],
                    "reason": "invoice_import_confirm",
                    "source_versions": app._workbench_matching_source_versions(),
                }
            ],
        )
        self.assertEqual(
            summary["invalidated_scopes"],
            ["2026-05", "2026-03", "2026-04", "2026-06", "2026-07"],
        )

    def test_manual_and_exception_lifecycle_events_mark_expanded_db_dirty_scopes(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue()
        app._workbench_reconciliation_dirty_queue = queue

        app._execute_derived_data_lifecycle_event(
            "pair_relation_changed",
            scope_keys=["2026-05"],
            include_all=False,
            metadata={"reason": "confirm_link"},
            schedule_cost_warmup=False,
        )
        app._execute_derived_data_lifecycle_event(
            "exception_case_changed",
            scope_keys=["2026-04"],
            include_all=False,
            metadata={"reason": "cancel_exception"},
            schedule_cost_warmup=False,
        )

        self.assertEqual(
            [(call["months"], call["reason"]) for call in queue.mark_calls],
            [(["2026-05"], "confirm_link"), (["2026-04"], "cancel_exception")],
        )

    def test_dirty_scope_worker_claims_db_queue_and_completes_with_lease_identity(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue(claim_months=["2026-05"])
        app._workbench_reconciliation_dirty_queue = queue

        with patch.object(
            app,
            "_run_workbench_auto_matching_for_scopes",
            return_value={"processed_months": ["2026-05"], "candidate_count": 2},
        ) as run_matching:
            result = app._rebuild_workbench_matching_dirty_scopes_once(
                worker_id="worker-a",
                request_id="request-1",
                limit=10,
                lease_seconds=300,
            )

        run_matching.assert_called_once_with(
            ["2026-05"],
            reason="dirty_scope_retry",
            request_id="request-1:2026-05",
            requeue_on_error=False,
            raise_on_error=True,
        )
        self.assertEqual(queue.claim_calls[0]["worker_id"], "worker-a")
        self.assertEqual(queue.claim_calls[0]["request_id"], "request-1")
        self.assertEqual(
            queue.complete_calls,
            [
                {
                    "scope_month": "2026-05",
                    "source_versions": app._workbench_matching_source_versions(),
                    "worker_id": "worker-a",
                    "request_id": "request-1:2026-05",
                }
            ],
        )
        self.assertEqual(result["processed_months"], ["2026-05"])
        self.assertEqual(result["failed_months"], [])

    def test_dirty_scope_worker_fails_db_queue_scope_when_matching_raises(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue(claim_months=["2026-05"])
        app._workbench_reconciliation_dirty_queue = queue

        with patch.object(
            app,
            "_run_workbench_auto_matching_for_scopes",
            side_effect=RuntimeError("matching unavailable"),
        ):
            result = app._rebuild_workbench_matching_dirty_scopes_once(
                worker_id="worker-a",
                request_id="request-1",
                limit=10,
                retry_delay_seconds=45,
            )

        self.assertEqual(queue.complete_calls, [])
        self.assertEqual(
            queue.fail_calls,
            [
                {
                    "scope_month": "2026-05",
                    "error": "matching unavailable",
                    "retry_delay_seconds": 45,
                    "worker_id": "worker-a",
                    "request_id": "request-1:2026-05",
                }
            ],
        )
        self.assertEqual(result["processed_months"], [])
        self.assertEqual(result["failed_months"], ["2026-05"])

    def test_db_dirty_queue_empty_claim_does_not_drain_legacy_dirty_scopes(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue(claim_months=[])
        app._workbench_reconciliation_dirty_queue = queue
        app._workbench_matching_dirty_scope_service.mark_dirty(["2026-05"], reason="legacy")

        with patch.object(app, "_run_workbench_auto_matching_for_scopes") as run_matching:
            result = app._rebuild_workbench_matching_dirty_scopes_once(
                worker_id="worker-a",
                request_id="request-1",
                limit=10,
            )

        self.assertIsNone(result)
        run_matching.assert_not_called()
        self.assertEqual(
            [entry["scope_month"] for entry in app._workbench_matching_dirty_scope_service.list_dirty_scopes()],
            ["2026-05"],
        )

    def test_db_dirty_queue_claim_failure_does_not_run_legacy_dirty_scopes(self) -> None:
        app = build_application()
        app._workbench_reconciliation_dirty_queue = FailingClaimDirtyQueue()
        app._workbench_matching_dirty_scope_service.mark_dirty(["2026-05"], reason="legacy")

        with patch.object(app, "_run_workbench_auto_matching_for_scopes") as run_matching:
            with self.assertRaisesRegex(RuntimeError, "db queue unavailable"):
                app._rebuild_workbench_matching_dirty_scopes_once(
                    worker_id="worker-a",
                    request_id="request-1",
                    limit=10,
                )

        run_matching.assert_not_called()
        self.assertEqual(
            [entry["scope_month"] for entry in app._workbench_matching_dirty_scope_service.list_dirty_scopes()],
            ["2026-05"],
        )

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

    def test_db_dirty_queue_mark_failure_does_not_fall_back_to_legacy_dirty_scopes(self) -> None:
        app = build_application()
        app._workbench_reconciliation_dirty_queue = FailingMarkDirtyQueue()

        with self.assertRaisesRegex(RuntimeError, "db queue unavailable"):
            app._schedule_or_run_workbench_auto_matching_for_scopes(["2026-05"], reason="import_confirm")

        self.assertEqual(app._workbench_matching_dirty_scope_service.list_dirty_scopes(), [])

    def test_exception_apply_api_marks_db_dirty_queue(self) -> None:
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

        with patch.object(app, "_resolve_live_rows_direct", return_value=rows):
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
        self.assertEqual(
            [(call["months"], call["reason"]) for call in queue.mark_calls],
            [(["2026-05"], "exception_apply")],
        )

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
                self.oa_started = False
                self.workbench_dirty_started = False

            def start_oa_sync_polling_worker(self) -> bool:
                self.oa_started = True
                return True

            def start_workbench_matching_dirty_scope_worker(self) -> bool:
                self.workbench_dirty_started = True
                return True

        app = FakeApplication()
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "FIN_OPS_OA_POLLING_ENABLED",
                "FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED",
            }
        }
        with patch.dict(os.environ, env, clear=True), patch.object(server_module, "ThreadingHTTPServer", FakeServer):
            server_module.run_http_server("127.0.0.1", 0, app)

        self.assertFalse(app.oa_started)
        self.assertFalse(app.workbench_dirty_started)

    def test_matching_row_provider_does_not_supplement_historical_pair_relation_rows(self) -> None:
        app = build_application()
        raw_payload = {
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [{"id": "oa-match-provider-001", "type": "oa", "amount": "100.00", "month": "2026-03"}],
                "bank": [
                    {
                        "id": "bank-match-provider-001",
                        "type": "bank",
                        "amount": "100.00",
                        "month": "2026-03",
                        "trade_time": "2026-03-10",
                    }
                ],
                "invoice": [
                    {
                        "id": "invoice-match-provider-001",
                        "type": "invoice",
                        "total_with_tax": "100.00",
                        "issue_date": "2026-03-10",
                    }
                ],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload) as build_payload:
            rows = app._workbench_matching_rows_for_scope("2026-03")

        build_payload.assert_called_once_with("2026-03", supplement_missing_pair_relation_rows=False)
        self.assertEqual([row["id"] for row in rows["oa_rows"]], ["oa-match-provider-001"])

    def test_oa_invoice_offset_settings_change_marks_all_available_months_dirty(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue()
        app._workbench_reconciliation_dirty_queue = queue
        payload = {
            **app._app_settings_service.get_settings_payload(),
            "oa_invoice_offset": {"applicant_names": ["李四"]},
        }
        session = SimpleNamespace(
            can_mutate_data=True,
            identity=SimpleNamespace(username="finance-admin"),
        )

        with (
            patch.object(app._workbench_query_service, "list_available_months", return_value=["2026-05"]),
            patch("fin_ops_platform.app.server.resolve_oa_request_session", return_value=session),
        ):
            response = app._handle_api_workbench_settings_update(json.dumps(payload), headers={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(call["months"], call["reason"]) for call in queue.mark_calls],
            [(["2026-05"], "oa_invoice_offset_settings_changed")],
        )

    def test_startup_stale_scan_is_called_during_application_startup(self) -> None:
        with patch.object(
            server_module.Application,
            "_schedule_startup_workbench_matching_stale_scan",
            autospec=True,
        ) as scan:
            build_application()

        scan.assert_called_once()

    def test_startup_stale_scan_marks_available_months_dirty_when_db_queue_exists(self) -> None:
        app = build_application()
        queue = RecordingDirtyQueue()
        app._workbench_reconciliation_dirty_queue = queue

        with patch.object(app._workbench_query_service, "list_available_months", return_value=["2026-05"]):
            summary = app._schedule_startup_workbench_matching_stale_scan()

        self.assertEqual(
            [(call["months"], call["reason"]) for call in queue.mark_calls],
            [(["2026-05"], "startup_stale_scan")],
        )
        self.assertEqual(
            summary["invalidated_scopes"],
            ["2026-05", "2026-03", "2026-04", "2026-06", "2026-07"],
        )

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
