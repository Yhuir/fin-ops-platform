from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fin_ops_platform.services.operations_audit_service import OperationsAuditService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class OperationHistoryPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.addCleanup(truncate_test_database, self.database_url)
        self.repository = PostgresOperationsAuditRepository(self.connection)
        self.service = OperationsAuditService(self.repository)
        self.time = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)

    def event(self, *, request_id="request-1", event_type="operation.requested", action="settings.oa_credential.save",
              actor_id="admin", page_key="settings", outcome="pending", occurred_at=None, metadata=None, operation_location=None):
        return self.repository.append_operation_event({
            "event_type": event_type, "object_type": "oa_credential", "object_id": "credential-1",
            "actor_id": actor_id, "actor_name": actor_id, "actor_account": actor_id,
            "page_key": page_key, "request_id": request_id, "outcome": outcome,
            "action": action, "occurred_at": occurred_at or self.time, "operation_location": operation_location,
            "payload": {"metadata": metadata or {}, "summary": action},
        })

    def test_list_detail_and_result_filter_use_same_origin_and_terminal_evidence(self):
        self.event()
        self.event(event_type="operation.completed", outcome="failed", occurred_at=self.time + timedelta(seconds=1), metadata={
            "api_call": {"method": "POST", "path": "/api/workbench/settings/oa-applicant-credentials",
                         "status_code": 400, "request_id": "request-1", "duration_ms": 3.2,
                         "parameters": {"oaUserId": "7", "password": "must-not-escape", "cookie": "private"}},
            "evidence": {"target": {"kind": "oa_credential", "title": "陈秀云"},
                         "failure": {"code": "verification_failed", "message": "身份验证失败"}},
        })
        self.event(event_type="operation.action", action="import_job.completed", actor_id="worker", page_key="system",
                   outcome="success", occurred_at=self.time + timedelta(seconds=3), metadata={"status_code": 200},
                   operation_location="/api/workbench/settings/oa-applicant-credentials")
        self.event(event_type="operation.action", action="import_job.completed", actor_id="worker", page_key="system",
                   outcome="success", occurred_at=self.time + timedelta(seconds=4), metadata={
                       "api_call": {"method": "POST", "path": "/api/workbench/settings/oa-applicant-credentials",
                                    "status_code": 200, "request_id": "request-1"},
                   })
        rows = self.service.list_operation_history(category="oa", outcome="failed", actor_id="admin", page_key="settings")["rows"]
        self.assertEqual(len(rows), 1)
        detail = self.service.get_operation_history("request:request-1")
        self.assertEqual(rows[0], {key: value for key, value in detail.items() if key not in {"detail", "reason"}})
        self.assertEqual(detail["actor_id"], "admin")
        self.assertEqual(detail["action_label"], "保存 OA 申请人凭据")
        self.assertEqual(detail["object_title"], "陈秀云")
        self.assertEqual(detail["detail"]["api_calls"][0]["status_code"], 400)
        self.assertEqual(detail["detail"]["api_calls"][0]["method"], "POST")
        self.assertEqual(detail["detail"]["api_calls"][0]["duration_ms"], 3.2)
        self.assertEqual(len(detail["detail"]["api_calls"]), 1)
        self.assertEqual(detail["detail"]["api_calls"][0]["parameters"], [{"label": "OA 用户", "value": "7"}])
        self.assertEqual(detail["detail"]["activities"][0]["title"], "导入任务执行结果")
        self.assertNotIn("must-not-escape", str(detail))
        self.assertEqual(self.service.list_operation_history(outcome="success")["rows"], [])

    def test_accepted_request_waits_for_exact_correlated_job_and_preserves_http_receipt(self):
        self.event(action="imports.files.confirm")
        self.event(event_type="operation.completed", action="imports.files.confirm", outcome="pending", metadata={
            "api_call": {"method": "POST", "path": "/imports/files/confirm", "status_code": 202, "request_id": "request-1"},
        })
        self.event(request_id="different-request", event_type="operation.action", action="import_job.completed", outcome="success")
        detail = self.service.get_operation_history("request:request-1")
        self.assertEqual(detail["outcome"], "pending")
        self.assertIsNone(detail["completed_at"])
        self.assertEqual(detail["detail"]["activities"][0]["fields"],
                         [{"label": "后续处理", "value": "请求已接收；后续结果未记录"}])
        self.event(event_type="operation.action", action="import_job.completed", actor_id="worker", outcome="failed",
                   occurred_at=self.time + timedelta(seconds=10), metadata={"stage": "commit", "status": "failed"})
        detail = self.service.get_operation_history("request:request-1")
        self.assertEqual(detail["outcome"], "failed")
        self.assertEqual(detail["detail"]["api_calls"][0]["status_code"], 202)
        self.assertEqual(detail["detail"]["activities"][0]["outcome"], "failed")
        self.assertEqual(detail["actor_id"], "admin")
        self.assertEqual(self.service.list_operation_history(outcome="failed")["rows"][0]["outcome"], "failed")

    def test_registered_reset_partial_result_is_incomplete_without_overriding_http_receipt(self):
        self.event(action="settings.data_reset.create")
        self.event(event_type="operation.completed", action="settings.data_reset.create", outcome="pending",
                   metadata={"api_call": {"method": "POST", "path": "/api/workbench/settings/data-reset/jobs", "status_code": 202, "request_id": "request-1"}})
        self.event(event_type="settings.data_reset.partial", action="reset_bank_transactions", outcome="partial",
                   occurred_at=self.time + timedelta(seconds=10), metadata={"outcome": "partial"})
        operation = self.service.get_operation_history("request:request-1")
        self.assertEqual(operation["outcome"], "incomplete")
        self.assertEqual(operation["detail"]["api_calls"][0]["status_code"], 202)
        self.assertEqual(operation["detail"]["activities"][0]["title"], "重置银行流水")
        self.assertEqual(operation["detail"]["activities"][0]["outcome"], "incomplete")

    def test_unknown_action_remains_unclassified_in_display_and_query(self):
        self.event(request_id=None, event_type="operation.action", action="not_registered", outcome="success")
        rows = self.service.list_operation_history(category="unclassified")["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category_label"], "未分类")
        self.assertEqual(rows[0]["action_label"], "未登记操作")
        self.assertEqual(self.service.list_operation_history(category="business")["rows"], [])

    def test_old_export_has_no_guessed_completion_or_method(self):
        self.event(event_type="operation.action", action="input_invoice_usage_export_downloaded", outcome="success")
        detail = self.service.get_operation_history("request:request-1")
        self.assertEqual(detail["outcome"], "unknown")
        self.assertEqual(detail["action_label"], "导出进项发票使用情况")
        self.assertEqual(detail["category"], "transfer")
        self.assertEqual(detail["detail"]["api_calls"], [])
        self.assertTrue(detail["detail"]["legacy_evidence_missing"])
        self.assertEqual(len(self.service.list_operation_history(search="进项发票清单", category="transfer", outcome="unknown")["rows"]), 1)
        self.assertEqual(self.service.list_operation_history(search="进项发票清单", category="oa")["rows"], [])

    def test_unfinished_requests_use_same_expiry_rule_and_system_event_requires_recorded_result(self):
        self.event(occurred_at=datetime.now(UTC) - timedelta(minutes=10))
        self.event(request_id="live", occurred_at=datetime.now(UTC))
        self.event(request_id=None, event_type="operation.action", action="import_job.completed", outcome="failed")
        self.assertEqual(self.service.get_operation_history("request:request-1")["outcome"], "incomplete")
        self.assertEqual(self.service.get_operation_history("request:live")["outcome"], "pending")
        self.assertEqual(len(self.service.list_operation_history(outcome="incomplete")["rows"]), 1)
        self.assertEqual(len(self.service.list_operation_history(outcome="failed")["rows"]), 1)

    def test_beijing_day_boundaries_and_literal_search(self):
        self.event(request_id="before", occurred_at=datetime(2026, 10, 9, 15, 59, 59, tzinfo=UTC))
        self.event(request_id="first", occurred_at=datetime(2026, 10, 9, 16, 0, tzinfo=UTC))
        self.event(request_id="last", occurred_at=datetime(2026, 10, 10, 15, 59, 59, tzinfo=UTC))
        self.event(request_id="after", occurred_at=datetime(2026, 10, 10, 16, 0, tzinfo=UTC))
        rows = self.service.list_operation_history(date_from="2026-10-10", date_to="2026-10-10")["rows"]
        self.assertEqual({row["operation_key"] for row in rows}, {"request:first", "request:last"})
        self.assertEqual(self.service.list_operation_history(search="%_")["rows"], [])

    def test_cursor_pages_whole_operations_and_later_activities_do_not_move_origin(self):
        for index in range(5):
            request = f"request-{index}"
            self.event(request_id=request)
            for offset in range(4):
                self.event(request_id=request, event_type="operation.action", occurred_at=self.time + timedelta(seconds=offset))
            self.event(request_id=request, event_type="operation.completed", outcome="success")
        first = self.service.list_operation_history(limit=2)
        self.event(request_id="request-4", event_type="operation.action", occurred_at=self.time + timedelta(days=1), actor_id="worker")
        second = self.service.list_operation_history(limit=2, cursor=first["next_cursor"])
        third = self.service.list_operation_history(limit=2, cursor=second["next_cursor"])
        keys = [row["operation_key"] for page in (first, second, third) for row in page["rows"]]
        self.assertEqual(len(keys), 5)
        self.assertEqual(len(set(keys)), 5)
        self.assertIsNone(third["next_cursor"])
        self.assertEqual(self.service.get_operation_history("request:request-4")["actor_id"], "admin")

    def test_failed_transaction_does_not_leave_half_written_audit(self):
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.connection.transaction() as transaction:
                PostgresOperationsAuditRepository(transaction).append_operation_event({
                    "event_type": "operation.action", "object_type": "business_record", "object_id": str(uuid4()),
                    "actor_id": "admin", "action": "import_job.completed", "outcome": "success", "payload": {},
                })
                raise RuntimeError("rollback")
        self.assertEqual(self.service.list_operation_history()["rows"], [])
