from __future__ import annotations

import os
import unittest
from dataclasses import asdict
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

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
        completed_at=f"{month}-05 16:30:00+08:00",
        detail_fields={
            "OA单号": row_id.removeprefix("oa-pay-").removeprefix("oa-exp-"),
            "申请日期": f"{month}-02",
            "审批完成时间": f"{month}-05 16:30:00+08:00",
        },
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

    def test_postgres_oa_workflow_row_lookup_enriches_source_aliases_in_one_statement(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAWorkflowRepository

        payload = asdict(oa_record(row_id="oa-exp-current"))
        payload["source_aliases"] = ["oa-exp-payload-alias"]
        connection = OAProjectionConnection(
            rows=[
                {
                    "row_id": "oa-exp-current",
                    "month": "2026-05",
                    "workflow_status": "completed",
                    "normalized_payload": payload,
                    "raw_payload": {"normalized_payload": payload},
                }
            ]
        )

        records = PostgresOAWorkflowRepository(connection).list_application_records_by_row_ids(
            ["oa-exp-current"]
        )

        self.assertEqual(records[0].source_aliases, ["oa-exp-payload-alias"])
        self.assertEqual(len(connection.executed), 1)
        executed_sql = connection.executed[0][0]
        self.assertIn("from app.oa_application_items item", executed_sql)
        self.assertIn("from app.oa_attachments attachment", executed_sql)
        self.assertIn("join app.oa_attachment_invoice_cache_sources cache_source", executed_sql)
        self.assertIn("cache_source.source_attachment_key = attachment.source_attachment_key", executed_sql)
        self.assertIn("cache_source.cache_source_attachment_key = attachment.source_attachment_key", executed_sql)
        self.assertIn("from app.oa_source_aliases alias_row", executed_sql)
        self.assertIn("alias_row.status = 'active'", executed_sql)

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
        self.assertIn("approved_at", executed_sql)
        self.assertIn("returning id::text as application_id", executed_sql)
        self.assertIn("delete from app.oa_application_items", executed_sql)
        self.assertIn("insert into app.oa_application_items", executed_sql)
        self.assertIn("delete from app.oa_attachments", executed_sql)
        self.assertIn("insert into app.oa_attachments", executed_sql)
        self.assertIn("('attachment_identity_' || source.source_kind)", executed_sql)
        identity_bridge_calls = [
            params
            for sql, params in connection.executed
            if "cache_evidence_sources as" in sql
        ]
        self.assertEqual(
            identity_bridge_calls,
            [(True, ["oa-exp-structured"], False, [])],
        )
        item_insert = [params for sql, params in connection.executed if "insert into app.oa_application_items" in sql]
        attachment_inserts = [params for sql, params in connection.executed if "insert into app.oa_attachments" in sql]
        self.assertEqual(len(item_insert), 1)
        self.assertEqual(len(attachment_inserts), 2)
        self.assertIsNone(item_insert[0][4])
        app_insert = [params for sql, params in connection.executed if "insert into app.oa_applications" in sql]
        self.assertEqual(app_insert[0][4], "structured")
        self.assertEqual(app_insert[0][6], "completed")

    def test_postgres_oa_projection_repository_does_not_use_internal_identity_as_workflow_number(self) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository

        record = oa_record(row_id="oa-exp-technical-only")
        record.detail_fields.pop("OA单号")
        connection = OAProjectionWriteConnection()

        PostgresOAProjectionRepository(connection).upsert_application_records([record], scope_key="2026-05")

        app_insert = [params for sql, params in connection.executed if "insert into app.oa_applications" in sql]
        self.assertIsNone(app_insert[0][4])
        self.assertEqual(app_insert[0][1], "expense_claim")
        self.assertEqual(app_insert[0][9], "2026-05-05 16:30:00+08:00")

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
        self.assertFalse(any("cache_evidence_sources as" in sql for sql, _params in connection.executed))

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

    def test_postgres_oa_projection_repository_migrates_legacy_expense_relations_without_scope_cleanup(self) -> None:
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
        self.assertEqual(stale_delete, [])

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
            def load_sync_application_batch(
                self,
                scope_key: str,
                *,
                retention_cutoff_month: str | None = None,
            ) -> object:
                del retention_cutoff_month
                records = [oa_record(month=scope_key)]
                return SimpleNamespace(projection_records=records, admission_records=records)

        class ProjectionRepository:
            def __init__(self) -> None:
                self.records: list[OAApplicationRecord] = []
                self.runs: list[dict[str, object]] = []

            def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
                self.records.extend(records)
                return len(records)

            def record_sync_run(self, payload: dict[str, object]) -> None:
                self.runs.append(payload)

        repository = ProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=SourceAdapter(),
            projection_repository=repository,
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
        self.assertFalse(hasattr(service, "_queue_repository"))
        self.assertEqual(repository.runs[0]["status"], "succeeded")

    def test_oa_sync_all_scope_respects_retention_cutoff_months(self) -> None:
        from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService

        class SourceAdapter:
            def __init__(self) -> None:
                self.loaded_scopes: list[str] = []

            def load_sync_application_batch(
                self,
                scope_key: str,
                *,
                retention_cutoff_month: str | None = None,
            ) -> object:
                del retention_cutoff_month
                self.loaded_scopes.append(scope_key)
                records = [
                    oa_record(row_id="oa-2025-12", month="2025-12"),
                    oa_record(row_id="oa-2026-01", month="2026-01"),
                    oa_record(row_id="oa-2026-02", month="2026-02"),
                ]
                return SimpleNamespace(projection_records=records, admission_records=records)

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

        self.assertEqual(source.loaded_scopes, ["all"])
        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual([record.month for record in repository.records], ["2026-01", "2026-02"])

    def test_oa_sync_all_scope_prunes_non_manual_projection_rows_before_cutoff(self) -> None:
        from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService

        class SourceAdapter:
            def load_sync_application_batch(
                self,
                _scope_key: str,
                *,
                retention_cutoff_month: str | None = None,
            ) -> object:
                del retention_cutoff_month
                records = [oa_record(row_id="oa-2026-01", month="2026-01")]
                return SimpleNamespace(projection_records=records, admission_records=records)

        class ProjectionRepository:
            def __init__(self) -> None:
                self.pruned_cutoff_months: list[str] = []

            def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
                return len(records)

            def prune_records_before(self, cutoff_month: str) -> list[str]:
                self.pruned_cutoff_months.append(cutoff_month)
                return ["2025-12"]

        repository = ProjectionRepository()
        service = OAProjectionSyncService(
            source_adapter=SourceAdapter(),
            projection_repository=repository,
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
        self.assertFalse(hasattr(service, "_queue_repository"))

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
            def load_sync_application_batch(
                self,
                _scope_key: str,
                *,
                retention_cutoff_month: str | None = None,
            ) -> object:
                del retention_cutoff_month
                return SimpleNamespace(
                    projection_records=[source_record],
                    admission_records=[source_record],
                )

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

    def test_api_module_has_no_in_process_polling_server(self) -> None:
        self.assertFalse(hasattr(server_module, "run_http_server"))
        self.assertFalse(hasattr(server_module, "ThreadingHTTPServer"))
