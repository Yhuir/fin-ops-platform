from __future__ import annotations

import json
import os
from dataclasses import asdict
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
        section="open",
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
        detail_fields={"申请日期": f"{month}-02"},
    )


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
        self.assertEqual(payload["open"]["oa"][0]["id"], "oa-pay-001")
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
        self.assertEqual(repository.runs[0]["status"], "succeeded")

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

    def test_http_server_does_not_start_in_process_oa_polling_by_default(self) -> None:
        class FakeServer:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def serve_forever(self) -> None:
                raise KeyboardInterrupt()

            def server_close(self) -> None:
                pass

        class FakeApplication:
            def __init__(self) -> None:
                self.started = False

            def start_oa_sync_polling_worker(self) -> bool:
                self.started = True
                return True

            def start_workbench_matching_dirty_scope_worker(self) -> bool:
                return True

        app = FakeApplication()
        env = {key: value for key, value in os.environ.items() if key != "FIN_OPS_OA_POLLING_ENABLED"}
        with patch.dict(os.environ, env, clear=True), patch.object(server_module, "ThreadingHTTPServer", FakeServer):
            server_module.run_http_server("127.0.0.1", 0, app)

        self.assertFalse(app.started)
