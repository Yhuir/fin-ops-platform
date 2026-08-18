from __future__ import annotations

import unittest
from datetime import UTC, datetime

from fin_ops_platform.services.operations_audit_service import OperationsAuditService, PageAuditUnavailableError


class FakeOperationsAuditRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.history_rows: list[dict[str, object]] = []
        self.events_by_key: dict[str, list[dict[str, object]]] = {}
        self.relation_history: list[dict[str, object]] = []

    def list_logical_operations(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(("history", kwargs))
        return list(self.history_rows)

    def list_operation_actors(self) -> list[dict[str, object]]:
        return [{"actor_id": "6", "actor_name": "刘汉金", "actor_account": "YNSYLP006"}]

    def list_operation_events_for_key(self, operation_key: str) -> list[dict[str, object]]:
        self.calls.append(("detail", {"operation_key": operation_key}))
        return list(self.events_by_key.get(operation_key) or [])

    def list_workbench_relation_history_for_request(self, request_id: str) -> list[dict[str, object]]:
        self.calls.append(("relation_history", {"request_id": request_id}))
        return list(self.relation_history)

    def audit_page(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("page", kwargs))
        return {"kind": "page"}

    def audit_system(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("system", kwargs))
        return {"kind": "system"}


class OperationsAuditServiceTests(unittest.TestCase):
    def test_delegates_page_audit_through_explicit_repository_contract(self) -> None:
        repository = FakeOperationsAuditRepository()
        service = OperationsAuditService(repository)

        self.assertEqual(
            service.audit_page(page_key="bank-details", tenant_id="tenant-a", sample_limit=30),
            {"kind": "page"},
        )
        self.assertEqual(
            repository.calls,
            [
                ("page", {"page_key": "bank-details", "tenant_id": "tenant-a", "sample_limit": 30}),
            ],
        )

    def test_system_page_uses_explicit_dashboard_projection_boundary(self) -> None:
        repository = FakeOperationsAuditRepository()
        dashboard_builder = lambda _connection: {"kind": "dashboard"}
        service = OperationsAuditService(repository, dashboard_payload_builder=dashboard_builder)

        self.assertEqual(
            service.audit_page(page_key="app-health-operations", tenant_id="tenant-a"),
            {"kind": "system"},
        )
        self.assertEqual(repository.calls[0][0], "system")
        self.assertEqual(repository.calls[0][1]["tenant_id"], "tenant-a")
        self.assertIs(repository.calls[0][1]["dashboard_payload_builder"], dashboard_builder)

    def test_system_page_without_dashboard_projection_fails_closed(self) -> None:
        repository = FakeOperationsAuditRepository()
        service = OperationsAuditService(repository)

        with self.assertRaisesRegex(PageAuditUnavailableError, "dashboard projection is unavailable"):
            service.audit_page(page_key="app-health-operations", tenant_id="tenant-a")

        self.assertEqual(repository.calls, [])

    def test_lists_operation_history_with_bounded_stable_cursor(self) -> None:
        repository = FakeOperationsAuditRepository()
        occurred_at = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        repository.history_rows = [
            {"operation_key": f"request:request-{index}", "occurred_at": occurred_at} for index in range(1, 4)
        ]
        service = OperationsAuditService(repository)

        payload = service.list_operation_history(limit=2, actor_id=" YNSYLP005 ", search=" 关联 ")

        self.assertEqual(len(payload["rows"]), 2)
        self.assertEqual(payload["limit"], 2)
        self.assertEqual(
            payload["next_cursor"],
            "2026-08-09T12:00:00+00:00|request:request-2",
        )
        self.assertEqual(repository.calls[0][1]["limit"], 3)
        self.assertEqual(repository.calls[0][1]["actor_id"], "YNSYLP005")
        self.assertEqual(repository.calls[0][1]["search"], "关联")

    def test_rejects_invalid_history_cursor_date_and_event_id(self) -> None:
        service = OperationsAuditService(FakeOperationsAuditRepository())

        with self.assertRaisesRegex(ValueError, "cursor"):
            service.list_operation_history(cursor="not-a-cursor")
        with self.assertRaisesRegex(ValueError, "date"):
            service.list_operation_history(date_from="not-a-date")
        with self.assertRaises(ValueError):
            service.get_operation_history("not-an-id")

    def test_returns_actor_facets_with_name_and_account(self) -> None:
        service = OperationsAuditService(FakeOperationsAuditRepository())

        self.assertEqual(
            service.list_operation_history_actors(),
            {"rows": [{"actor_id": "6", "actor_name": "刘汉金", "actor_account": "YNSYLP006"}]},
        )

    def test_enriches_only_matching_legacy_actor_from_authenticated_identity(self) -> None:
        repository = FakeOperationsAuditRepository()
        occurred_at = datetime(2026, 8, 9, 10, 6, tzinfo=UTC)
        repository.history_rows = [
            {
                "operation_key": "request:request-1",
                "actor_id": "6",
                "actor_name": None,
                "actor_account": None,
                "occurred_at": occurred_at,
            }
        ]

        payload = OperationsAuditService(repository).list_operation_history(
            known_actor={"actor_id": "6", "actor_name": "刘涵静", "actor_account": "YNSYLP005"},
        )

        self.assertEqual(payload["rows"][0]["actor_name"], "刘涵静")
        self.assertEqual(payload["rows"][0]["actor_account"], "YNSYLP005")

    def test_returns_sanitized_workbench_selection_and_status_change(self) -> None:
        repository = FakeOperationsAuditRepository()
        occurred_at = datetime(2026, 8, 9, 10, 6, tzinfo=UTC)
        repository.events_by_key["request:request-1"] = [
            {
                "event_type": "operation.requested",
                "request_id": "request-1",
                "actor_id": "6",
                "actor_name": "刘汉金",
                "actor_account": "YNSYLP006",
                "action": "POST /api/workbench/actions/confirm-link",
                "page_key": "reconciliation-workbench",
                "object_type": "http_request",
                "occurred_at": occurred_at,
                "outcome": "pending",
                "payload": {},
            },
            {
                "event_type": "operation.completed",
                "request_id": "request-1",
                "actor_id": "6",
                "actor_name": "刘汉金",
                "actor_account": "YNSYLP006",
                "action": "POST /api/workbench/actions/confirm-link",
                "page_key": "reconciliation-workbench",
                "object_type": "http_request",
                "occurred_at": occurred_at,
                "outcome": "success",
                "payload": {},
            },
        ]
        repository.relation_history = [
            {
                "raw_payload": {
                    "normalized_payload": {
                        "affected_row_ids": ["oa-internal"],
                        "affected_row_types": ["oa"],
                    }
                }
            }
        ]

        operation = OperationsAuditService(repository).get_operation_history("request:request-1")

        self.assertIsNotNone(operation)
        assert operation is not None
        self.assertEqual(operation["action_label"], "确认关联")
        self.assertEqual(operation["action_code"], "workbench.relation.confirm")
        self.assertEqual(operation["object_label"], "关联关系")
        self.assertEqual(operation["actor_name"], "刘汉金")
        self.assertEqual(operation["detail"]["records"][0]["title"], "1 条OA")
        self.assertEqual(
            operation["detail"]["changes"],
            [{"label": "关联状态", "before": "未配对", "after": "已配对"}],
        )
        self.assertFalse(operation["detail"]["legacy_evidence_missing"])
        for internal_field in ("event_id", "request_id", "trace_id", "object_id"):
            self.assertNotIn(internal_field, operation)
        self.assertNotIn("oa-internal", str(operation))
        self.assertNotIn("operation_projection", str(operation))
        self.assertEqual([name for name, _kwargs in repository.calls], ["detail", "relation_history"])

    def test_derives_typed_items_from_real_relation_history_shape(self) -> None:
        repository = FakeOperationsAuditRepository()
        occurred_at = datetime(2026, 8, 9, 10, 6, tzinfo=UTC)
        repository.events_by_key["request:request-typed"] = [
            {
                "event_type": "operation.completed",
                "request_id": "request-typed",
                "action": "POST /api/workbench/actions/withdraw-link",
                "page_key": "reconciliation-workbench",
                "occurred_at": occurred_at,
                "outcome": "success",
                "payload": {},
            }
        ]
        relation = {
            "case_id": "CASE-1",
            "row_ids": ["same-id", "same-id"],
            "row_types": ["bank", "invoice"],
        }
        repository.relation_history = [
            {
                "before_payload": [relation],
                "after_payload": [],
                "raw_payload": {
                    "normalized_payload": {
                        "affected_row_ids": ["same-id", "same-id"],
                        "before_relations": [relation],
                        "after_relations": [],
                    }
                },
            }
        ]

        operation = OperationsAuditService(repository).get_operation_history("request:request-typed")

        assert operation is not None
        self.assertEqual(
            [(item["kind"], item["title"]) for item in operation["detail"]["records"]],
            [("bank", "1 条银行流水"), ("invoice", "1 条发票")],
        )
        self.assertNotIn("same-id", str(operation))

    def test_returns_stored_file_evidence_without_requerying_mutable_business_rows(self) -> None:
        repository = FakeOperationsAuditRepository()
        occurred_at = datetime(2026, 8, 19, 1, 0, tzinfo=UTC)
        repository.events_by_key["request:upload-1"] = [
            {
                "event_type": "operation.completed",
                "request_id": "upload-1",
                "action": "workbench.oa_invoice.document_upload",
                "page_key": "reconciliation-workbench",
                "occurred_at": occurred_at,
                "outcome": "success",
                "payload": {
                    "metadata": {
                        "action_code": "workbench.oa_invoice.document_upload",
                        "action_label": "上传 OA 补充凭证",
                        "object_label": "OA 补充凭证",
                        "description": "上传并关联补充凭证。",
                        "evidence": {
                            "schema_version": 1,
                            "target": {
                                "kind": "oa_expense_item_relation",
                                "title": "关联关系 CASE-1",
                                "fields": [{"label": "OA 子付款项", "value": "oa-1:item:0"}],
                            },
                            "artifacts": [{
                                "artifact_key": "document-1",
                                "kind": "file",
                                "title": "凭证.png",
                                "media_type": "image/png",
                                "size_bytes": 128,
                                "preview_url": "/api/workbench/oa-invoice-supplements/documents/document-1/content",
                                "availability": "available",
                            }],
                            "records": [],
                            "changes": [{"label": "补充凭证", "before": "未上传", "after": "已关联 1 个文件"}],
                            "failure": None,
                        },
                    }
                },
            }
        ]

        operation = OperationsAuditService(repository).get_operation_history("request:upload-1")

        assert operation is not None
        self.assertEqual(operation["detail"]["target"]["title"], "关联关系 CASE-1")
        self.assertEqual(operation["detail"]["artifacts"][0]["title"], "凭证.png")
        self.assertFalse(operation["detail"]["legacy_evidence_missing"])
        self.assertEqual([name for name, _kwargs in repository.calls], ["detail"])

    def test_projects_legacy_http_action_to_stable_user_semantics(self) -> None:
        repository = FakeOperationsAuditRepository()
        repository.history_rows = [
            {
                "operation_key": "request:legacy",
                "action": "POST /imports/files/confirm",
                "page_key": "imports.bank-transactions",
                "object_type": "http_request",
                "occurred_at": datetime(2026, 8, 9, 10, 6, tzinfo=UTC),
                "payload": {"summary": "POST /imports/files/confirm · HTTP 202"},
            }
        ]

        operation = OperationsAuditService(repository).list_operation_history()["rows"][0]

        self.assertEqual(operation["action_code"], "imports.files.confirm")
        self.assertEqual(operation["action_label"], "确认文件导入")
        self.assertEqual(operation["object_label"], "文件导入")
        self.assertNotIn("/imports/", str(operation))


if __name__ == "__main__":
    unittest.main()
