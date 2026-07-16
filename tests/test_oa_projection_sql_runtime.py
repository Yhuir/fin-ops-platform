from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from unittest.mock import patch
import unittest

from fin_ops_platform.app import server as server_module
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService


def oa_record(row_id: str = "oa-pay-001", month: str = "2026-05") -> OAApplicationRecord:
    return OAApplicationRecord(
        id=row_id,
        month=month,
        section="unpaired",
        case_id=None,
        applicant="刘际涛",
        project_name="玉烟维护项目",
        apply_type="支付申请",
        amount="199.00",
        counterparty_name="昆明供应商",
        reason="材料款",
        relation_code="pending_match",
        relation_label="待找流水与发票",
        relation_tone="warn",
        workflow_status="completed",
        detail_fields={"申请日期": f"{month}-02"},
    )


def etc_oa_projection_payload() -> dict[str, object]:
    payload = asdict(oa_record(row_id="oa-pay-etc-001", month="2026-05"))
    payload.update(
        {
            "amount": "53.84",
            "reason": "ETC批量提交\nbusiness_batch_id=etc_business_batch_0001\netc_batch_id=etc_20260519_001",
            "invoiceCount": 2,
            "invoice_count": 2,
            "applicant": "user-001",
            "owner_org_id": "org-001",
            "created_at": "2026-05-19T09:05:00",
            "process_status": "in_progress",
        }
    )
    detail_fields = dict(payload.get("detail_fields") or {})
    detail_fields.update(
        {
            "表单ID": "2",
            "流程状态": "进行中",
            "申请日期": "2026-05-19",
            "ETC发票数量": "2",
            "部门ID": "org-001",
        }
    )
    payload["detail_fields"] = detail_fields
    return payload


def oa_record_with_structured_attachments(row_id: str = "oa-exp-structured", month: str = "2026-05") -> OAApplicationRecord:
    record = oa_record(row_id=row_id, month=month)
    record.expense_items = [
        {
            "expense_item_id": f"{row_id}:item:1",
            "row_index": "0",
            "expense_content": "设备款",
            "settlement_amount": "199.00",
            "attachment_invoices": [
                {
                    "source_attachment_key": f"{row_id}:invoice:1",
                    "source_attachment_name": "发票.pdf",
                    "invoice_no": "INV-STRUCT-001",
                    "seller_name": "杭州供应商",
                    "total_with_tax": "199.00",
                }
            ],
            "attachment_artifacts": [
                {
                    "source_attachment_key": f"{row_id}:payment:1",
                    "source_attachment_name": "付款截图.png",
                    "evidence_type": "payment_receipt",
                }
            ],
        }
    ]
    return record


def oa_record_with_attachment_files(row_id: str = "oa-exp-files", month: str = "2026-05") -> OAApplicationRecord:
    record = oa_record(row_id=row_id, month=month)
    record.expense_items = [
        {
            "expense_item_id": f"{row_id}:item:1",
            "row_index": "0",
            "expense_content": "交通费",
            "settlement_amount": "88.00",
            "attachment_files": [
                {"fileName": "交通发票.pdf", "filePath": "/交通发票.pdf", "suffix": "pdf"},
                {"fileName": "付款截图.jpg", "filePath": "/付款截图.jpg", "suffix": "jpg"},
            ],
        }
    ]
    return record


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class OAProjectionConnection:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = list(rows or [])
        self.executed: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.executed.append((normalized, params))
        if "distinct to_char" in normalized:
            return [{"month": row["month"]} for row in self.rows]
        if "from app.oa_applications" not in normalized:
            return []
        if "row_id = any" in normalized:
            wanted = set(params[0])
            return [row for row in self.rows if row["row_id"] in wanted]
        if "scope_month = %s::date" in normalized:
            month = str(params[0])[:7]
            return [row for row in self.rows if row["month"] == month]
        return list(self.rows)

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((" ".join(sql.lower().split()), params))


class OAProjectionWriteConnection(OAProjectionConnection):
    def __init__(self) -> None:
        super().__init__(rows=[])

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.executed.append((" ".join(sql.lower().split()), params))
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.executed.append((" ".join(sql.lower().split()), params))
        if "returning id::text" in self.executed[-1][0]:
            return {"application_id": "00000000-0000-0000-0000-000000000001"}
        return None


class OAProjectionNoChangeConnection(OAProjectionWriteConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.executed.append((" ".join(sql.lower().split()), params))
        return None


class OAProjectionSqlRuntimeTests(unittest.TestCase):
    def test_postgres_oa_projection_repository_lists_records_by_month(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository

        connection = OAProjectionConnection(
            rows=[
                {
                    "row_id": "oa-pay-001",
                    "month": "2026-05",
                    "normalized_payload": asdict(oa_record()),
                    "raw_payload": {"normalized_payload": asdict(oa_record())},
                }
            ]
        )
        repository = PostgresOAProjectionRepository(connection)

        records = repository.list_application_records("2026-05")

        self.assertEqual([record.id for record in records], ["oa-pay-001"])
        self.assertEqual(records[0].project_name, "玉烟维护项目")
        self.assertEqual(records[0].workflow_status, "completed")
        self.assertIn("workflow_status in", connection.executed[0][0])
        self.assertIn("'completed'", connection.executed[0][0])
        self.assertIn("'已完成'", connection.executed[0][0])

    def test_postgres_oa_projection_repository_normalizes_only_the_legacy_open_section(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository

        legacy_payload = asdict(oa_record(row_id="oa-pay-legacy-open"))
        legacy_payload["section"] = "open"
        missing_section_payload = asdict(oa_record(row_id="oa-pay-missing-section"))
        missing_section_payload.pop("section")
        paired_payload = asdict(oa_record(row_id="oa-pay-paired"))
        paired_payload["section"] = "paired"
        connection = OAProjectionConnection(
            rows=[
                {
                    "row_id": payload["id"],
                    "month": "2026-05",
                    "normalized_payload": payload,
                    "raw_payload": {"normalized_payload": payload},
                }
                for payload in (legacy_payload, missing_section_payload, paired_payload)
            ]
        )
        repository = PostgresOAProjectionRepository(connection)

        records = repository.list_application_records("2026-05")

        self.assertEqual(
            {record.id: record.section for record in records},
            {
                "oa-pay-legacy-open": "unpaired",
                "oa-pay-missing-section": "unpaired",
                "oa-pay-paired": "paired",
            },
        )

    def test_postgres_oa_projection_repository_rejects_unknown_stored_section(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository

        payload = asdict(oa_record(row_id="oa-pay-invalid-section"))
        payload["section"] = "candidate"

        with self.assertRaisesRegex(ValueError, "Unsupported stored OA Workbench section"):
            PostgresOAProjectionRepository._record_from_payload(payload)

    def test_postgres_oa_projection_repository_writes_structured_items_and_attachments(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository

        connection = OAProjectionWriteConnection()
        repository = PostgresOAProjectionRepository(connection)

        count = repository.upsert_application_records(
            [oa_record_with_structured_attachments()],
            scope_key="2026-05",
        )

        self.assertEqual(count, 1)
        executed_sql = "\n".join(sql for sql, _params in connection.executed)
        self.assertIn("insert into app.oa_applications", executed_sql)
        self.assertIn("workflow_status", executed_sql)
        self.assertIn("returning id::text as application_id", executed_sql)
        self.assertIn("delete from app.oa_application_items", executed_sql)
        self.assertIn("insert into app.oa_application_items", executed_sql)
        self.assertIn("delete from app.oa_attachments", executed_sql)
        self.assertIn("insert into app.oa_attachments", executed_sql)
        item_insert = [params for sql, params in connection.executed if "insert into app.oa_application_items" in sql]
        attachment_inserts = [params for sql, params in connection.executed if "insert into app.oa_attachments" in sql]
        self.assertEqual(len(item_insert), 1)
        self.assertEqual(len(attachment_inserts), 2)
        app_insert = [params for sql, params in connection.executed if "insert into app.oa_applications" in sql]
        self.assertEqual(app_insert[0][6], "completed")

    def test_postgres_oa_projection_repository_does_not_rewrite_identical_records(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository

        connection = OAProjectionNoChangeConnection()
        repository = PostgresOAProjectionRepository(connection)

        count = repository.upsert_application_records(
            [oa_record_with_structured_attachments()],
            scope_key="2026-05",
        )

        self.assertEqual(count, 0)
        executed_sql = "\n".join(sql for sql, _params in connection.executed)
        self.assertIn("is distinct from", executed_sql)
        self.assertFalse(
            any(sql.startswith("delete from app.oa_application_items where") for sql, _params in connection.executed)
        )
        self.assertFalse(
            any(sql.startswith("insert into app.oa_application_items") for sql, _params in connection.executed)
        )
        self.assertFalse(
            any(sql.startswith("delete from app.oa_attachments where") for sql, _params in connection.executed)
        )
        self.assertFalse(
            any(sql.startswith("insert into app.oa_attachments") for sql, _params in connection.executed)
        )

    def test_postgres_oa_projection_repository_writes_attachment_files_as_structured_attachments(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository

        connection = OAProjectionWriteConnection()
        repository = PostgresOAProjectionRepository(connection)

        count = repository.upsert_application_records(
            [oa_record_with_attachment_files()],
            scope_key="2026-05",
        )

        self.assertEqual(count, 1)
        attachment_inserts = [params for sql, params in connection.executed if "insert into app.oa_attachments" in sql]
        self.assertEqual(len(attachment_inserts), 2)
        self.assertEqual(attachment_inserts[0][4], "oa-exp-files:attachment:oa-exp-files:item:1:0:交通发票.pdf")
        self.assertEqual(attachment_inserts[0][7], None)
        self.assertEqual(attachment_inserts[0][9].obj["source_expense_item_id"], "oa-exp-files:item:1")

    def test_postgres_oa_projection_repository_replaces_month_scope_and_migrates_legacy_expense_relations(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository

        connection = OAProjectionWriteConnection()
        repository = PostgresOAProjectionRepository(connection)
        record = oa_record(row_id="oa-exp-2007", month="2026-03")
        record.expense_items = [
            {"row_index": "0", "expense_item_id": "oa-exp-2007:item:0"},
            {"row_index": "1", "expense_item_id": "oa-exp-2007:item:1"},
        ]

        count = repository.upsert_application_records(
            [record],
            scope_key="2026-03",
        )

        self.assertEqual(count, 1)
        relation_update = [
            (sql, params)
            for sql, params in connection.executed
            if "update app.workbench_pair_relations relation" in sql
        ]
        self.assertEqual(len(relation_update), 1)
        self.assertEqual(
            relation_update[0][1],
            (["oa-exp-2007-1", "oa-exp-2007-2"], ["oa-exp-2007", "oa-exp-2007"], ["oa-exp-2007-1", "oa-exp-2007-2"]),
        )
        self.assertIn("raw_payload = jsonb_set", relation_update[0][0])
        self.assertIn("normalized_payload,row_ids", relation_update[0][0])
        override_update = [
            (sql, params)
            for sql, params in connection.executed
            if "update app.workbench_row_overrides override" in sql
        ]
        self.assertEqual(len(override_update), 1)
        self.assertIn("override_payload = jsonb_set", override_update[0][0])
        self.assertIn("normalized_payload,row_id", override_update[0][0])
        stale_delete = [
            (sql, params)
            for sql, params in connection.executed
            if "delete from app.oa_applications oa" in sql and "stale" in sql
        ]
        self.assertEqual(len(stale_delete), 1)
        self.assertIn("oa.scope_month = %s::date", stale_delete[0][0])
        self.assertEqual(stale_delete[0][1], ("2026-03-01", ["oa-exp-2007"]))

    def test_workbench_query_service_reads_oa_rows_from_sql_projection_adapter(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionAdapter

        class ProjectionRepository:
            def __init__(self) -> None:
                self.months: list[str] = []

            def list_application_records(self, month: str) -> list[OAApplicationRecord]:
                self.months.append(month)
                return [oa_record(month=month)]

            def get_read_status(self):
                from fin_ops_platform.services.oa_adapter import OAReadStatus

                return OAReadStatus(code="ready", message="OA projection ready")

        repository = ProjectionRepository()
        service = WorkbenchQueryService(oa_adapter=PostgresOAProjectionAdapter(repository))

        payload = service.get_workbench("2026-05")

        self.assertEqual(repository.months, ["2026-05"])
        self.assertEqual(payload["summary"]["oa_count"], 1)
        self.assertEqual(payload["unpaired"]["oa"][0]["id"], "oa-pay-001")
        self.assertEqual(payload["oa_status"], {"code": "ready", "message": "OA projection ready"})

    def test_oa_sync_worker_persists_projection_and_marks_downstream_scopes_dirty(self) -> None:
        from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService

        class SourceAdapter:
            def list_application_records(self, month: str) -> list[OAApplicationRecord]:
                return [oa_record(month=month)]

        class ProjectionRepository:
            def __init__(self) -> None:
                self.records: list[OAApplicationRecord] = []
                self.runs: list[dict[str, object]] = []

            def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
                self.records.extend(records)
                return len(records)

            def record_sync_run(self, payload: dict[str, object]) -> None:
                self.runs.append(payload)

        queue = QueueRecorder()
        repository = ProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=SourceAdapter(),
            projection_repository=repository,
            queue_repository=queue,
        )
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="default",
            event_type="oa.sync",
            aggregate_type="oa",
            aggregate_id="2026-05",
            scope_type="oa",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result["upserted_count"], 1)
        self.assertEqual([record.id for record in repository.records], ["oa-pay-001"])
        self.assertIn(("workbench", "2026-05", "oa_projection_sync"), queue.refreshes)
        self.assertIn(("workbench", "all", "oa_projection_sync"), queue.refreshes)
        self.assertIn(("search", "2026-05", "oa_projection_sync"), queue.refreshes)
        self.assertIn(("pending_invoice", "expense:all", "oa_projection_sync"), queue.refreshes)
        for read_model_key in (
            "workbench_relation",
            "bank_detail",
            "invoice_lifecycle",
            "input_invoice_usage",
            "output_invoice_collection",
            "turnover_ledger",
            "no_oa_bank_batch",
            "bank_flow_rule_batch",
        ):
            self.assertIn((read_model_key, "2026-05", "oa_projection_sync"), queue.refreshes)
        self.assertEqual(repository.runs[0]["status"], "succeeded")

    def test_oa_sync_all_scope_respects_retention_cutoff_months(self) -> None:
        from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService

        class SourceAdapter:
            def __init__(self) -> None:
                self.listed_months: list[str] = []
                self.list_all_called = False

            def list_available_months(self) -> list[str]:
                return ["2025-12", "2026-01", "2026-02"]

            def list_all_application_records(self) -> list[OAApplicationRecord]:
                self.list_all_called = True
                return [oa_record(row_id="oa-old", month="2025-12")]

            def list_application_records(self, month: str) -> list[OAApplicationRecord]:
                self.listed_months.append(month)
                return [oa_record(row_id=f"oa-{month}", month=month)]

        class ProjectionRepository:
            def __init__(self) -> None:
                self.records: list[OAApplicationRecord] = []

            def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
                self.records.extend(records)
                return len(records)

        source = SourceAdapter()
        repository = ProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=source,
            projection_repository=repository,
            queue_repository=QueueRecorder(),
            retention_cutoff_date_provider=lambda: "2026-01-01",
        )
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="default",
            event_type="oa.sync",
            aggregate_type="oa",
            aggregate_id="all",
            scope_type="oa",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertFalse(source.list_all_called)
        self.assertEqual(source.listed_months, ["2026-01", "2026-02"])
        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual([record.month for record in repository.records], ["2026-01", "2026-02"])

    def test_oa_sync_all_scope_prunes_non_manual_projection_rows_before_cutoff(self) -> None:
        from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService

        class SourceAdapter:
            def list_available_months(self) -> list[str]:
                return ["2026-01"]

            def list_application_records(self, month: str) -> list[OAApplicationRecord]:
                return [oa_record(row_id="oa-2026-01", month=month)]

        class ProjectionRepository:
            def __init__(self) -> None:
                self.pruned_cutoff_months: list[str] = []

            def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
                return len(records)

            def prune_records_before(self, cutoff_month: str) -> list[str]:
                self.pruned_cutoff_months.append(cutoff_month)
                return ["2025-12"]

        queue = QueueRecorder()
        repository = ProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=SourceAdapter(),
            projection_repository=repository,
            queue_repository=queue,
            retention_cutoff_date_provider=lambda: "2026-01-01",
        )
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="default",
            event_type="oa.sync",
            aggregate_type="oa",
            aggregate_id="all",
            scope_type="oa",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(repository.pruned_cutoff_months, ["2026-01"])
        self.assertEqual(result["pruned_count"], 1)
        self.assertIn(("workbench", "2025-12", "oa_projection_sync"), queue.refreshes)
        self.assertIn(("search", "2025-12", "oa_projection_sync"), queue.refreshes)

    def test_oa_sync_projection_preserves_source_bound_invoice_attachment_facts(self) -> None:
        from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService

        source_record = oa_record(row_id="oa-exp-001", month="2026-02")
        source_record.attachment_invoices = [
            {"invoice_no": "INV-001", "attachment_name": "invoice.pdf", "source_attachment_key": "root-invoice"},
        ]
        source_record.attachment_evidences = [
            {"evidence_type": "invoice", "attachment_name": "invoice-evidence.pdf", "source_attachment_key": "root-evidence"},
            {"evidence_type": "payment_receipt", "attachment_name": "payment.png"},
            {"evidence_type": "unknown", "attachment_name": "note.docx"},
        ]
        source_record.attachment_artifacts = [
            {"document_kind": "invoice", "attachment_name": "invoice-artifact.pdf", "source_attachment_key": "root-artifact"},
            {"attachment_name": "payment.png"},
            {"attachment_name": "note.docx"},
        ]
        source_record.expense_items = [
            {
                "expense_item_id": "oa-exp-001:item:1",
                "row_index": "0",
                "attachment_invoices": [
                    {"invoice_no": "INV-ITEM-001", "source_attachment_key": "item-invoice"},
                ],
                "attachment_evidences": [
                    {"evidence_type": "invoice", "source_attachment_key": "item-evidence"},
                    {"evidence_type": "payment_receipt", "source_attachment_key": "item-payment"},
                ],
                "attachment_artifacts": [
                    {"document_kind": "invoice", "source_attachment_key": "item-artifact"},
                    {"document_kind": "payment_receipt", "source_attachment_key": "item-payment-artifact"},
                ],
            }
        ]

        class SourceAdapter:
            def list_application_records(self, month: str) -> list[OAApplicationRecord]:
                return [source_record]

        class ProjectionRepository:
            def __init__(self) -> None:
                self.records: list[OAApplicationRecord] = []

            def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
                self.records.extend(records)
                return len(records)

        repository = ProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=SourceAdapter(),
            projection_repository=repository,
            queue_repository=QueueRecorder(),
        )
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="default",
            event_type="oa.sync",
            aggregate_type="oa",
            aggregate_id="2026-02",
            scope_type="oa",
            scope_key="2026-02",
            dedupe_key=None,
            payload={"scope_key": "2026-02"},
            attempts=1,
            status="processing",
        )

        service.handle_runtime_event(event)

        self.assertEqual(repository.records[0].attachment_invoices, source_record.attachment_invoices)
        self.assertEqual(
            repository.records[0].attachment_evidences,
            [source_record.attachment_evidences[0], source_record.attachment_evidences[1]],
        )
        self.assertEqual(
            repository.records[0].attachment_artifacts,
            [source_record.attachment_artifacts[0], source_record.attachment_artifacts[1]],
        )
        self.assertEqual(repository.records[0].expense_items[0]["attachment_invoices"], source_record.expense_items[0]["attachment_invoices"])
        self.assertEqual(
            repository.records[0].expense_items[0]["attachment_evidences"],
            [
                source_record.expense_items[0]["attachment_evidences"][0],
                source_record.expense_items[0]["attachment_evidences"][1],
            ],
        )
        self.assertEqual(
            repository.records[0].expense_items[0]["attachment_artifacts"],
            [
                source_record.expense_items[0]["attachment_artifacts"][0],
                source_record.expense_items[0]["attachment_artifacts"][1],
            ],
        )

    def test_manual_oa_sync_api_enqueues_worker_job_without_running_sync_inline(self) -> None:
        app = object.__new__(server_module.Application)
        enqueued: list[dict[str, object]] = []
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {
                "queue_repository": type(
                    "Queue",
                    (),
                    {
                        "enqueue": lambda *_args, **kwargs: enqueued.append(kwargs),
                    },
                )()
            },
        )()
        app._integration_service = type(
            "IntegrationService",
            (),
            {"sync": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("OA sync API must not run sync inline"))},
        )()

        response = app._handle_oa_sync(json.dumps({"actor_id": "tester", "scope": "2026-05"}))
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(enqueued[0]["event_type"], "oa.sync")
        self.assertEqual(enqueued[0]["scope_key"], "2026-05")

    def test_manual_oa_sync_api_fails_closed_when_queue_is_unavailable(self) -> None:
        app = object.__new__(server_module.Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": None})()
        app._integration_service = type(
            "IntegrationService",
            (),
            {"sync": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("OA sync API must not run sync inline"))},
        )()

        response = app._handle_oa_sync(json.dumps({"actor_id": "tester", "scope": "2026-05"}))
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.SERVICE_UNAVAILABLE))
        self.assertEqual(payload["error"], "oa_sync_queue_unavailable")

    def test_http_server_does_not_support_in_process_oa_polling(self) -> None:
        class FakeServer:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

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
            if key not in {"FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED"}
        }
        env["FIN_OPS_OA_POLLING_ENABLED"] = "1"
        with patch.dict(os.environ, env, clear=True), patch.object(server_module, "ThreadingHTTPServer", FakeServer):
            server_module.run_http_server("127.0.0.1", 0, app)

        self.assertFalse(app.workbench_dirty_started)
