from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_attachment_refresh_request_service import (
    OAAttachmentRefreshRequestError,
    OAAttachmentRefreshRequestService,
    OAAttachmentRefreshRowNotCompletedError,
    OAAttachmentRefreshRowNotFoundError,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class OAAttachmentRefreshRequestServiceTests(unittest.TestCase):
    def test_request_enqueues_exact_row_ids_and_affected_scopes(self) -> None:
        queue = FakeQueueRepository()
        service = OAAttachmentRefreshRequestService(
            queue_repository=queue,
            workflow_reader=FakeWorkflowReader(
                [_record("oa-1", "2026-06"), _record("oa-2", "2026-07")]
            ),
        )

        result = service.request(["oa-2", "oa-1", "oa-2"], actor_id="admin")

        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["row_ids"], ["oa-2", "oa-1"])
        self.assertEqual(result["affected_scope_keys"], ["2026-06", "2026-07"])
        request = queue.enqueued[0]
        self.assertEqual(request["event_type"], "oa.sync")
        self.assertEqual(request["payload"]["operation"], "refresh_attachments")
        self.assertEqual(request["payload"]["row_ids"], ["oa-2", "oa-1"])
        self.assertEqual(request["priority"], "high")

    def test_request_fails_before_enqueue_for_missing_or_in_progress_row(self) -> None:
        queue = FakeQueueRepository()
        service = OAAttachmentRefreshRequestService(
            queue_repository=queue,
            workflow_reader=FakeWorkflowReader([_record("oa-progress", "2026-06", completed=False)]),
        )

        with self.assertRaises(OAAttachmentRefreshRowNotFoundError):
            service.request(["missing"], actor_id="admin")
        with self.assertRaises(OAAttachmentRefreshRowNotCompletedError):
            service.request(["oa-progress"], actor_id="admin")

        self.assertEqual(queue.enqueued, [])

    def test_request_reuses_active_processing_event_without_projection_read(self) -> None:
        queue = FakeQueueRepository()
        queue.active_event = RuntimeQueueEvent(
            event_id="event-active",
            tenant_id="default",
            event_type="oa.sync",
            aggregate_type="oa_attachment_refresh",
            aggregate_id="identity",
            scope_type="oa",
            scope_key="2026-06",
            dedupe_key="dedupe",
            payload={
                "operation": "refresh_attachments",
                "row_ids": ["oa-1"],
                "affected_scope_keys": ["2026-06"],
            },
            attempts=1,
            status="processing",
        )
        workflow_reader = FakeWorkflowReader([])
        service = OAAttachmentRefreshRequestService(
            queue_repository=queue,
            workflow_reader=workflow_reader,
        )

        result = service.request(["oa-1"], actor_id="admin")

        self.assertEqual(
            result,
            {
                "event_id": "event-active",
                "status": "pending",
                "row_ids": ["oa-1"],
                "affected_scope_keys": ["2026-06"],
            },
        )
        self.assertEqual(workflow_reader.calls, [])
        self.assertEqual(queue.enqueued, [])

    def test_request_rejects_active_event_contract_collision(self) -> None:
        queue = FakeQueueRepository()
        queue.active_event = RuntimeQueueEvent(
            event_id="event-active",
            tenant_id="default",
            event_type="oa.sync",
            aggregate_type="oa_attachment_refresh",
            aggregate_id="identity",
            scope_type="oa",
            scope_key="2026-06",
            dedupe_key="dedupe",
            payload={
                "operation": "refresh_attachments",
                "row_ids": ["other-row"],
                "affected_scope_keys": ["2026-06"],
            },
            attempts=1,
            status="processing",
        )
        service = OAAttachmentRefreshRequestService(
            queue_repository=queue,
            workflow_reader=FakeWorkflowReader([]),
        )

        with self.assertRaisesRegex(
            OAAttachmentRefreshRequestError,
            "合同不一致",
        ):
            service.request(["oa-1"], actor_id="admin")

        self.assertEqual(queue.enqueued, [])

    def test_request_rejects_invalid_month_before_enqueue(self) -> None:
        queue = FakeQueueRepository()
        service = OAAttachmentRefreshRequestService(
            queue_repository=queue,
            workflow_reader=FakeWorkflowReader([_record("oa-1", "2026-13")]),
        )

        with self.assertRaisesRegex(OAAttachmentRefreshRequestError, "月份无效"):
            service.request(["oa-1"], actor_id="admin")

        self.assertEqual(queue.enqueued, [])

    def test_done_status_returns_only_controlled_result_fields(self) -> None:
        queue = FakeQueueRepository()
        event_id = "00000000-0000-0000-0000-000000000001"
        queue.statuses[event_id] = {
            "event_type": "oa.sync",
            "status": "done",
            "payload": {
                "operation": "refresh_attachments",
                "row_ids": ["oa-1"],
                "affected_scope_keys": ["2026-06"],
            },
            "last_error": "secret database detail",
            "runtime_result": {
                "rows": [
                    {
                        "row_id": "oa-1",
                        "attachment_file_count": 2,
                        "importable_invoice_count": 1,
                        "unrecognized_attachment_count": 1,
                        "raw_payload": {"secret": True},
                    }
                ],
                "errors": [],
                "promotion_summary": {
                    "affected_invoice_count": 1,
                    "internal_sql": "secret",
                },
                "affected_scope_keys": ["2026-06"],
                "source_records": [{"secret": True}],
            },
        }
        service = OAAttachmentRefreshRequestService(
            queue_repository=queue,
            workflow_reader=FakeWorkflowReader([_record("oa-1", "2026-06")]),
        )

        result = service.status(event_id)

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["result"]["rows"][0]["row_id"], "oa-1")
        self.assertNotIn("raw_payload", result["result"]["rows"][0])
        self.assertNotIn("internal_sql", result["result"]["promotion_summary"])
        self.assertNotIn("last_error", result)

    def test_done_status_without_rows_is_reported_as_contract_failure(self) -> None:
        queue = FakeQueueRepository()
        event_id = "00000000-0000-0000-0000-000000000001"
        queue.statuses[event_id] = {
            "event_type": "oa.sync",
            "status": "done",
            "payload": {
                "operation": "refresh_attachments",
                "row_ids": ["oa-1"],
                "affected_scope_keys": ["2026-06"],
            },
            "runtime_result": {"promotion_summary": {}},
        }
        service = OAAttachmentRefreshRequestService(
            queue_repository=queue,
            workflow_reader=FakeWorkflowReader([_record("oa-1", "2026-06")]),
        )

        result = service.status(event_id)

        self.assertEqual(result["status"], "failed")
        self.assertIn("合同不完整", result["error"])

    def test_done_status_rejects_missing_counts_and_wrong_row_identity(self) -> None:
        queue = FakeQueueRepository()
        event_id = "00000000-0000-0000-0000-000000000001"
        queue.statuses[event_id] = {
            "event_type": "oa.sync",
            "status": "done",
            "payload": {
                "operation": "refresh_attachments",
                "row_ids": ["oa-1"],
                "affected_scope_keys": ["2026-06"],
            },
            "runtime_result": {
                "rows": [
                    {
                        "row_id": "other-row",
                        "importable_invoice_count": 1,
                        "unrecognized_attachment_count": 0,
                    }
                ],
                "errors": [],
                "promotion_summary": {},
                "affected_scope_keys": ["2026-06"],
            },
        }
        service = OAAttachmentRefreshRequestService(
            queue_repository=queue,
            workflow_reader=FakeWorkflowReader([_record("oa-1", "2026-06")]),
        )

        result = service.status(event_id)

        self.assertEqual(result["status"], "failed")
        self.assertIn("合同不完整", result["error"])

    def test_failed_status_does_not_expose_runtime_error_detail(self) -> None:
        queue = FakeQueueRepository()
        event_id = "00000000-0000-0000-0000-000000000001"
        queue.statuses[event_id] = {
            "event_type": "oa.sync",
            "status": "dead_lettered",
            "payload": {
                "operation": "refresh_attachments",
                "row_ids": ["oa-1"],
                "affected_scope_keys": ["2026-06"],
            },
            "last_error": "postgresql password=secret",
            "runtime_result": None,
        }
        service = OAAttachmentRefreshRequestService(
            queue_repository=queue,
            workflow_reader=FakeWorkflowReader([_record("oa-1", "2026-06")]),
        )

        result = service.status(event_id)

        self.assertEqual(result["status"], "dead_lettered")
        self.assertNotIn("secret", result["error"])


class FakeQueueRepository:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []
        self.statuses: dict[str, dict[str, object]] = {}
        self.active_event: RuntimeQueueEvent | None = None

    def enqueue(self, **kwargs: object) -> SimpleNamespace:
        self.enqueued.append(dict(kwargs))
        return SimpleNamespace(
            event_id="00000000-0000-0000-0000-000000000001",
            status="pending",
        )

    def get_event_status(self, event_id: str) -> dict[str, object] | None:
        return self.statuses.get(event_id)

    def get_active_event_by_dedupe_key(
        self,
        dedupe_key: str,
        *,
        tenant_id: str = "default",
    ) -> RuntimeQueueEvent | None:
        return self.active_event


class FakeWorkflowReader:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = {record.id: record for record in records}
        self.calls: list[list[str]] = []

    def list_application_records_by_row_ids(
        self,
        row_ids: list[str],
    ) -> list[OAApplicationRecord]:
        self.calls.append(list(row_ids))
        return [self.records[row_id] for row_id in row_ids if row_id in self.records]


def _record(row_id: str, month: str, *, completed: bool = True) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=row_id,
        month=month,
        section="unpaired",
        case_id=None,
        applicant="申请人",
        project_name="项目",
        apply_type="日常报销",
        amount="100.00",
        counterparty_name="",
        reason="测试",
        relation_code="pending_match",
        relation_label="待配对",
        relation_tone="warn",
        workflow_status="completed" if completed else "in_progress",
    )
