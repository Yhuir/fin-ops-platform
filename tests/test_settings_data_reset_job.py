from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tests.app_test_support import (
    build_local_state_application,
    configure_access_control,
    install_durable_import_queue,
)
from fin_ops_platform.services.background_job_service import BackgroundJobService
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.runtime_worker_handlers import SettingsDataResetRuntimeFactory
from fin_ops_platform.services.settings_data_reset_job import (
    SETTINGS_DATA_RESET_REQUESTED_EVENT,
    SettingsDataResetJobHandler,
)
from fin_ops_platform.services.settings_data_reset_service import (
    RESET_BANK_TRANSACTIONS_ACTION,
    SettingsDataResetResult,
)
from fin_ops_platform.services.state_store import ApplicationStateStore


class SettingsDataResetJobTests(unittest.TestCase):
    def test_runtime_factory_reloads_durable_state_for_each_reset(self) -> None:
        stores = [
            SimpleNamespace(
                name=name,
                load_workbench_overrides=lambda: {},
                load_workbench_pair_relations=lambda: {},
            )
            for name in ("first", "second")
        ]
        factory = SettingsDataResetRuntimeFactory(data_dir=".", connection=object(), queue_repository=object())
        factory._state_store = lambda: stores.pop(0)  # type: ignore[method-assign]
        constructed_with: list[str] = []

        class FakeResetService:
            def __init__(self, **kwargs):
                constructed_with.append(kwargs["state_store"].name)

            def execute(self, action: str, **_kwargs):
                return action

        with patch(
            "fin_ops_platform.services.runtime_worker_handlers.ImportNormalizationService.from_snapshot",
            return_value=SimpleNamespace(),
        ), patch(
            "fin_ops_platform.services.runtime_worker_handlers.SettingsDataResetService",
            FakeResetService,
        ):
            self.assertEqual(factory._execute_reset(RESET_BANK_TRANSACTIONS_ACTION), RESET_BANK_TRANSACTIONS_ACTION)
            self.assertEqual(factory._execute_reset(RESET_BANK_TRANSACTIONS_ACTION), RESET_BANK_TRANSACTIONS_ACTION)

        self.assertEqual(constructed_with, ["first", "second"])

    def test_api_enqueues_durable_reset_without_persisting_password(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_local_state_application(data_dir=Path(temp_dir))
            queue = install_durable_import_queue(app)
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="admin-id",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                roles=["finance"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = (
                lambda token, password: token == "admin-token" and password == "secret-password"
            )

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset/jobs",
                body=json.dumps({
                    "action": RESET_BANK_TRANSACTIONS_ACTION,
                    "oa_password": "secret-password",
                    "idempotency_key": "reset-request-1",
                }),
                headers={"Authorization": "Bearer admin-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["job"]["status"], "queued")
        self.assertEqual(queue.events[0].event_type, SETTINGS_DATA_RESET_REQUESTED_EVENT)
        encoded = json.dumps({"job": payload["job"], "event": vars(queue.events[0])})
        self.assertNotIn("secret-password", encoded)
        self.assertNotIn("oa_password", encoded)

    def test_api_rejects_non_admin_without_enqueuing_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_local_state_application(data_dir=Path(temp_dir))
            queue = install_durable_import_queue(app)
            configure_access_control(app, full_access=["YNSYLP006"])
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="finance-id",
                username="YNSYLP006",
                nickname="财务用户",
                display_name="财务用户",
                roles=["finance"],
                permissions=["finops:app:view"],
            )

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset/jobs",
                body=json.dumps({
                    "action": RESET_BANK_TRANSACTIONS_ACTION,
                    "oa_password": "secret-password",
                    "idempotency_key": "reset-request-1",
                }),
                headers={"Authorization": "Bearer finance-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "admin_only")
        self.assertEqual(queue.events, [])

    def test_api_rejects_wrong_password_without_enqueuing_or_echoing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_local_state_application(data_dir=Path(temp_dir))
            queue = install_durable_import_queue(app)
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="admin-id",
                username="YNSYLP005",
                nickname="管理员",
                display_name="管理员",
                roles=["finance"],
                permissions=[],
            )
            app._oa_identity_service.verify_current_user_password = lambda _token, _password: False

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset/jobs",
                body=json.dumps({
                    "action": RESET_BANK_TRANSACTIONS_ACTION,
                    "oa_password": "wrong-secret",
                    "idempotency_key": "reset-request-1",
                }),
                headers={"Authorization": "Bearer admin-token"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(queue.events, [])
        self.assertNotIn("wrong-secret", response.body)

    def test_api_rejects_a_second_active_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_local_state_application(data_dir=Path(temp_dir))
            queue = install_durable_import_queue(app)
            app._resolve_admin_session = lambda _headers: (
                SimpleNamespace(identity=SimpleNamespace(user_id="admin-id", username="YNSYLP005")),
                None,
            )
            app._verify_reset_oa_password = lambda _session, _password: None
            first_request = json.dumps({
                "action": RESET_BANK_TRANSACTIONS_ACTION,
                "oa_password": "secret-password",
                "idempotency_key": "reset-request-1",
            })
            second_request = json.dumps({
                "action": RESET_BANK_TRANSACTIONS_ACTION,
                "oa_password": "secret-password",
                "idempotency_key": "reset-request-2",
            })

            headers = {"X-User": "YNSYLP005"}
            first = app.handle_request("POST", "/api/workbench/settings/data-reset/jobs", body=first_request, headers=headers)
            second = app.handle_request("POST", "/api/workbench/settings/data-reset/jobs", body=second_request, headers=headers)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(len(queue.events), 1)
        self.assertNotIn("secret-password", str(second.body))

    def test_api_replays_same_reset_request_without_duplicate_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_local_state_application(data_dir=Path(temp_dir))
            queue = install_durable_import_queue(app)
            app._resolve_admin_session = lambda _headers: (
                SimpleNamespace(identity=SimpleNamespace(user_id="admin-id", username="YNSYLP005")),
                None,
            )
            app._verify_reset_oa_password = lambda _session, _password: None
            request = json.dumps({
                "action": RESET_BANK_TRANSACTIONS_ACTION,
                "oa_password": "secret-password",
                "idempotency_key": "reset-request-1",
            })

            first = app.handle_request("POST", "/api/workbench/settings/data-reset/jobs", body=request)
            second = app.handle_request("POST", "/api/workbench/settings/data-reset/jobs", body=request)
            first_payload = json.loads(first.body)
            second_payload = json.loads(second.body)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first_payload["job"]["job_id"], second_payload["job"]["job_id"])
        self.assertEqual(len(queue.events), 1)

    def test_api_fails_closed_when_durable_queue_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_local_state_application(data_dir=Path(temp_dir))
            queue = install_durable_import_queue(app)
            queue.fail_next_enqueue = True
            app._resolve_admin_session = lambda _headers: (
                SimpleNamespace(identity=SimpleNamespace(user_id="admin-id", username="YNSYLP005")),
                None,
            )
            app._verify_reset_oa_password = lambda _session, _password: None

            response = app.handle_request(
                "POST",
                "/api/workbench/settings/data-reset/jobs",
                body=json.dumps({
                    "action": RESET_BANK_TRANSACTIONS_ACTION,
                    "oa_password": "secret-password",
                    "idempotency_key": "reset-request-1",
                }),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "settings_data_reset_enqueue_failed")
        self.assertEqual(payload["job"]["status"], "failed")
        self.assertEqual(queue.events, [])
        self.assertNotIn("secret-password", response.body)

    def test_worker_executes_reset_and_completes_durable_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            jobs = BackgroundJobService(store)
            job = jobs.create_job(
                job_type="settings_data_reset",
                label="重置银行流水",
                owner_user_id="admin",
                result_summary={"action": RESET_BANK_TRANSACTIONS_ACTION},
            )
            lifecycle_calls: list[tuple[list[str], str]] = []
            runtime_reload_calls: list[str] = []

            def reset_executor(action: str, *, progress_callback):
                progress_callback("reset", "正在重置。", 1, 1)
                return SettingsDataResetResult(
                    action=action,
                    status="completed",
                    cleared_collections=["bank_transactions"],
                    deleted_counts={"bank_transactions": 2},
                    protected_targets=["form_data_db.form_data"],
                    rebuild_status="not_required",
                    message="银行流水已重置。",
                )

            handler = SettingsDataResetJobHandler(
                reset_executor=reset_executor,
                supported_actions={RESET_BANK_TRANSACTIONS_ACTION},
                background_jobs=jobs,
                scope_months_provider=lambda: ["2026-05"],
                lifecycle_executor=lambda months, action: lifecycle_calls.append((months, action)) or {
                    "errors": [],
                    "invalidated_scopes": ["workbench:all"],
                },
                runtime_reload_request=lambda: runtime_reload_calls.append("reload"),
            )
            event = SimpleNamespace(
                payload={
                    "job_id": job.job_id,
                    "owner_user_id": "admin",
                    "action": RESET_BANK_TRANSACTIONS_ACTION,
                }
            )

            result = handler.handle_runtime_event(event)
            completed = jobs.get_job(job.job_id, "admin")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(completed.status, "succeeded")
        self.assertEqual(lifecycle_calls, [(["2026-05"], RESET_BANK_TRANSACTIONS_ACTION)])
        self.assertEqual(runtime_reload_calls, ["reload"])

    def test_worker_marks_completed_reset_partial_when_api_reload_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = BackgroundJobService(ApplicationStateStore(Path(temp_dir)))
            job = jobs.create_job(
                job_type="settings_data_reset",
                label="重置银行流水",
                owner_user_id="admin",
            )
            handler = SettingsDataResetJobHandler(
                reset_executor=lambda action, **_kwargs: SettingsDataResetResult(
                    action=action,
                    status="completed",
                    cleared_collections=["bank_transactions"],
                    deleted_counts={"bank_transactions": 2},
                    protected_targets=["form_data_db.form_data"],
                    rebuild_status="not_required",
                    message="银行流水已重置。",
                ),
                supported_actions={RESET_BANK_TRANSACTIONS_ACTION},
                background_jobs=jobs,
                scope_months_provider=lambda: [],
                lifecycle_executor=lambda _months, _action: {"errors": []},
                runtime_reload_request=lambda: (_ for _ in ()).throw(RuntimeError("pidfile unavailable")),
            )

            result = handler.handle_runtime_event(
                SimpleNamespace(
                    payload={
                        "job_id": job.job_id,
                        "owner_user_id": "admin",
                        "action": RESET_BANK_TRANSACTIONS_ACTION,
                    }
                )
            )
            failed = jobs.get_job(job.job_id, "admin")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(failed.status, "failed")
        self.assertIn("API 运行时刷新失败", failed.message)
        self.assertEqual(result["derived_data_lifecycle"]["errors"][0]["domain"], "api_runtime_reload")

    def test_worker_never_replays_an_unknown_interrupted_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = BackgroundJobService(ApplicationStateStore(Path(temp_dir)))
            job = jobs.create_job(
                job_type="settings_data_reset",
                label="重置银行流水",
                owner_user_id="admin",
            )
            jobs.start_job(job.job_id)
            reset_calls: list[str] = []
            handler = SettingsDataResetJobHandler(
                reset_executor=lambda action, **_kwargs: reset_calls.append(action),
                supported_actions={RESET_BANK_TRANSACTIONS_ACTION},
                background_jobs=jobs,
                scope_months_provider=lambda: [],
                lifecycle_executor=lambda _months, _action: {},
            )

            result = handler.handle_runtime_event(
                SimpleNamespace(
                    payload={
                        "job_id": job.job_id,
                        "owner_user_id": "admin",
                        "action": RESET_BANK_TRANSACTIONS_ACTION,
                    }
                )
            )
            failed = jobs.get_job(job.job_id, "admin")

        self.assertEqual(reset_calls, [])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(failed.error, "interrupted_data_reset_requires_manual_retry")


if __name__ == "__main__":
    unittest.main()
