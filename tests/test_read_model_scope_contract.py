from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.read_model_scope_contracts import (
    PostgresReadModelScopeContractRepository,
)
from fin_ops_platform.services.read_model_scope_contract import ReadModelScopeContractService


class CapturingConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, object]] = []

    def fetch_all(self, sql: str, params: object = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return []


class FakeScopeContractRepository:
    def __init__(self) -> None:
        self.read_model_outbox_failures: list[dict[str, object]] = []
        self.policy_managed_dirty_scopes: list[dict[str, object]] = []
        self.policy_managed_outbox_events: list[dict[str, object]] = []
        self.policy_managed_readiness: list[dict[str, object]] = []
        self.deleted_dirty_scope_ids: list[str] = []
        self.deleted_outbox_event_ids: list[str] = []
        self.deleted_readiness: list[dict[str, str]] = []
        self.repair_audit_events: list[dict[str, object]] = []
        self.orphaned_import_fact_dirty_scopes: list[dict[str, object]] = []

    def list_read_model_outbox_failures(self) -> list[dict[str, object]]:
        return [row for row in self.read_model_outbox_failures if str(row.get("id") or "") not in self.deleted_outbox_event_ids]

    def list_orphaned_import_fact_dirty_scopes(self) -> list[dict[str, object]]:
        return [
            row
            for row in self.orphaned_import_fact_dirty_scopes
            if str(row.get("id") or "") not in self.deleted_dirty_scope_ids
        ]

    def list_policy_managed_dirty_scopes(self) -> list[dict[str, object]]:
        return [
            row
            for row in self.policy_managed_dirty_scopes
            if str(row.get("id") or "") not in self.deleted_dirty_scope_ids
        ]

    def list_policy_managed_outbox_events(self) -> list[dict[str, object]]:
        return [
            row
            for row in self.policy_managed_outbox_events
            if str(row.get("id") or "") not in self.deleted_outbox_event_ids
        ]

    def list_policy_managed_readiness(self) -> list[dict[str, object]]:
        deleted_keys = {
            (item["tenant_id"], item["read_model_key"], item["scope_type"], item["scope_key"])
            for item in self.deleted_readiness
        }
        return [
            row
            for row in self.policy_managed_readiness
            if (
                str(row.get("tenant_id") or "default"),
                str(row.get("read_model_key") or ""),
                str(row.get("scope_type") or ""),
                str(row.get("scope_key") or ""),
            )
            not in deleted_keys
        ]

    def delete_dirty_scope(self, row_id: str) -> int:
        if row_id in self.deleted_dirty_scope_ids:
            return 0
        self.deleted_dirty_scope_ids.append(row_id)
        return 1

    def delete_outbox_event(self, row_id: str) -> int:
        if row_id in self.deleted_outbox_event_ids:
            return 0
        self.deleted_outbox_event_ids.append(row_id)
        return 1

    def delete_readiness(self, *, tenant_id: str, read_model_key: str, scope_type: str, scope_key: str) -> int:
        deletion = {
            "tenant_id": tenant_id,
            "read_model_key": read_model_key,
            "scope_type": scope_type,
            "scope_key": scope_key,
        }
        if deletion in self.deleted_readiness:
            return 0
        self.deleted_readiness.append(
            deletion
        )
        return 1

    def record_repair_audit(self, event: dict[str, object]) -> str:
        self.repair_audit_events.append(dict(event))
        return f"audit-{len(self.repair_audit_events)}"


class FakeRefreshGateway:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def can_enqueue(self) -> bool:
        return True

    def enqueue_many(self, scope_type: str, scope_keys: list[str], *, reason: str) -> list[str]:
        self.enqueued.append({"scope_type": scope_type, "scope_keys": list(scope_keys), "reason": reason})
        return list(scope_keys)


class ReadModelScopeContractServiceTests(unittest.TestCase):
    def test_postgres_repository_outbox_failure_query_escapes_psycopg_percent_pattern(self) -> None:
        connection = CapturingConnection()

        rows = PostgresReadModelScopeContractRepository(connection).list_read_model_outbox_failures()

        self.assertEqual(rows, [])
        sql, params = connection.fetch_all_calls[-1]
        self.assertEqual(params, ())
        self.assertIn("like '%%.read_model.refresh'", sql)
        self.assertNotIn("like '%.read_model.refresh'", sql)

    def test_postgres_repository_lists_only_orphaned_import_fact_dirty_scopes(self) -> None:
        connection = CapturingConnection()

        rows = PostgresReadModelScopeContractRepository(connection).list_orphaned_import_fact_dirty_scopes()

        self.assertEqual(rows, [])
        sql, params = connection.fetch_all_calls[-1]
        self.assertEqual(params, ())
        self.assertIn("reason = 'import_facts_changed'", sql)
        self.assertIn("not exists", sql.lower())
        self.assertIn("event_type = 'import.fact.changed'", sql)
        self.assertIn("status in ('pending', 'processing')", sql)

    def test_postgres_repository_lists_policy_managed_dirty_scopes(self) -> None:
        connection = CapturingConnection()

        rows = PostgresReadModelScopeContractRepository(connection).list_policy_managed_dirty_scopes()

        self.assertEqual(rows, [])
        sql, params = connection.fetch_all_calls[-1]
        self.assertEqual(params, (["workbench_relation", "search", "no_oa_bank_batch"],))
        self.assertIn("scope_type = any(%s)", sql)
        self.assertIn("status in ('pending', 'processing', 'failed')", sql)

    def test_postgres_repository_lists_policy_managed_outbox_events(self) -> None:
        connection = CapturingConnection()

        rows = PostgresReadModelScopeContractRepository(connection).list_policy_managed_outbox_events()

        self.assertEqual(rows, [])
        sql, params = connection.fetch_all_calls[-1]
        self.assertEqual(params, (["workbench_relation", "search", "no_oa_bank_batch"],))
        self.assertIn("coalesce(scope_type, payload->>'scope_type') = any(%s)", sql)
        self.assertIn("event_type like '%%.read_model.refresh'", sql)

    def test_postgres_repository_lists_policy_managed_readiness(self) -> None:
        connection = CapturingConnection()

        rows = PostgresReadModelScopeContractRepository(connection).list_policy_managed_readiness()

        self.assertEqual(rows, [])
        sql, params = connection.fetch_all_calls[-1]
        self.assertEqual(
            params,
            (
                ["workbench_relation", "search", "no_oa_bank_batch"],
                ["workbench_relation", "search", "no_oa_bank_batch"],
            ),
        )
        self.assertIn("from read_model.app_status_readiness", sql)
        self.assertIn("scope_type = any(%s)", sql)
        self.assertIn("read_model_key = any(%s)", sql)

    def test_check_reports_orphaned_import_fact_dirty_scopes_without_writes(self) -> None:
        repository = FakeScopeContractRepository()
        repository.orphaned_import_fact_dirty_scopes = [
            {
                "id": "dirty-import-1",
                "tenant_id": "default",
                "scope_type": "bank_detail",
                "scope_key": "2026-06",
                "status": "pending",
                "reason": "import_facts_changed",
                "updated_at": "2026-06-20T15:14:09+00:00",
            }
        ]

        report = ReadModelScopeContractService(repository).check_orphaned_import_fact_dirty_scopes()

        self.assertFalse(report["ok"])
        self.assertEqual(report["orphaned_dirty_scope_count"], 1)
        self.assertEqual(report["cleanup"], {"applied": False, "deleted": {"job.read_model_dirty_scopes": 0}})
        self.assertEqual(report["items"][0]["proposed_action"], "delete_orphaned_legacy_import_fact_dirty_scope")
        self.assertEqual(repository.deleted_dirty_scope_ids, [])
        self.assertEqual(repository.repair_audit_events, [])

    def test_apply_deletes_orphaned_import_fact_dirty_scopes_and_records_audit(self) -> None:
        repository = FakeScopeContractRepository()
        repository.orphaned_import_fact_dirty_scopes = [
            {
                "id": "dirty-import-1",
                "tenant_id": "default",
                "scope_type": "bank_detail",
                "scope_key": "2026-06",
                "status": "pending",
                "reason": "import_facts_changed",
                "updated_at": "2026-06-20T15:14:09+00:00",
            },
            {
                "id": "dirty-import-2",
                "tenant_id": "default",
                "scope_type": "pending_invoice",
                "scope_key": "global",
                "status": "pending",
                "reason": "import_facts_changed",
                "updated_at": "2026-06-20T15:13:36+00:00",
            },
        ]

        report = ReadModelScopeContractService(repository).repair_orphaned_import_fact_dirty_scopes(
            apply=True,
            reason="manual_import_fact_cleanup",
        )

        self.assertEqual(repository.deleted_dirty_scope_ids, ["dirty-import-1", "dirty-import-2"])
        self.assertEqual(report["cleanup"]["deleted"], {"job.read_model_dirty_scopes": 2})
        self.assertEqual(len(repository.repair_audit_events), 1)
        audit = repository.repair_audit_events[0]
        self.assertEqual(audit["event_type"], "orphaned_import_fact_dirty_scope_repair")
        self.assertEqual(audit["object_id"], "import_facts_changed")
        self.assertEqual(audit["reason"], "manual_import_fact_cleanup")
        self.assertEqual(len(audit["payload"]["items"]), 2)
        self.assertEqual(report["repair_audit"]["recorded"], True)
        self.assertEqual(report["repair_audit"]["event_id"], "audit-1")

    def test_orphaned_import_fact_repair_is_idempotent(self) -> None:
        repository = FakeScopeContractRepository()
        repository.orphaned_import_fact_dirty_scopes = [
            {
                "id": "dirty-import-1",
                "tenant_id": "default",
                "scope_type": "bank_detail",
                "scope_key": "2026-06",
                "status": "pending",
                "reason": "import_facts_changed",
            }
        ]
        service = ReadModelScopeContractService(repository)

        first = service.repair_orphaned_import_fact_dirty_scopes(apply=True)
        second = service.repair_orphaned_import_fact_dirty_scopes(apply=True)

        self.assertEqual(first["cleanup"]["deleted"]["job.read_model_dirty_scopes"], 1)
        self.assertEqual(second["orphaned_dirty_scope_count"], 0)
        self.assertEqual(second["cleanup"]["deleted"]["job.read_model_dirty_scopes"], 0)
        self.assertEqual(len(repository.repair_audit_events), 1)

    def test_check_reports_invalid_policy_managed_read_model_scopes_without_writes(self) -> None:
        repository = FakeScopeContractRepository()
        repository.policy_managed_dirty_scopes = [
            {
                "id": "dirty-invalid",
                "tenant_id": "default",
                "scope_type": "search",
                "scope_key": "active:2026-05",
                "status": "pending",
                "reason": "read_model_slo_smoke",
            },
            {
                "id": "dirty-valid",
                "tenant_id": "default",
                "scope_type": "search",
                "scope_key": "2026-05",
                "status": "pending",
            },
        ]
        repository.policy_managed_outbox_events = [
            {
                "id": "outbox-invalid",
                "tenant_id": "default",
                "event_type": "search.read_model.refresh",
                "scope_type": "search",
                "scope_key": "active:2026-05",
                "status": "pending",
            }
        ]
        repository.policy_managed_readiness = [
            {
                "tenant_id": "default",
                "read_model_key": "search",
                "scope_type": "search",
                "scope_key": "active:2026-05",
                "status": "failed",
            }
        ]

        report = ReadModelScopeContractService(repository).check_invalid_read_model_refresh_scopes()

        self.assertFalse(report["ok"])
        self.assertEqual(report["invalid_scope_count"], 3)
        self.assertEqual(
            report["summary"],
            {
                "job.read_model_dirty_scopes": 1,
                "job.outbox_events": 1,
                "read_model.app_status_readiness": 1,
            },
        )
        self.assertEqual(repository.deleted_dirty_scope_ids, [])
        self.assertEqual(repository.deleted_outbox_event_ids, [])
        self.assertEqual(repository.deleted_readiness, [])
        self.assertEqual(report["items"][0]["proposed_action"], "delete_invalid_runtime_row_no_replacement")

    def test_apply_deletes_invalid_policy_managed_read_model_scopes_and_records_audit(self) -> None:
        repository = FakeScopeContractRepository()
        repository.policy_managed_dirty_scopes = [
            {
                "id": "dirty-invalid",
                "tenant_id": "default",
                "scope_type": "search",
                "scope_key": "active:2026-05",
                "status": "pending",
                "reason": "read_model_slo_smoke",
            }
        ]
        repository.policy_managed_outbox_events = [
            {
                "id": "outbox-invalid",
                "tenant_id": "default",
                "event_type": "search.read_model.refresh",
                "scope_type": "search",
                "scope_key": "active:2026-05",
                "status": "pending",
            }
        ]
        repository.policy_managed_readiness = [
            {
                "tenant_id": "default",
                "read_model_key": "search",
                "scope_type": "search",
                "scope_key": "active:2026-05",
                "status": "failed",
            }
        ]

        report = ReadModelScopeContractService(repository).repair_invalid_read_model_refresh_scopes(
            apply=True,
            reason="manual_invalid_scope_cleanup",
        )

        self.assertEqual(repository.deleted_dirty_scope_ids, ["dirty-invalid"])
        self.assertEqual(repository.deleted_outbox_event_ids, ["outbox-invalid"])
        self.assertEqual(
            repository.deleted_readiness,
            [
                {
                    "tenant_id": "default",
                    "read_model_key": "search",
                    "scope_type": "search",
                    "scope_key": "active:2026-05",
                }
            ],
        )
        self.assertEqual(report["cleanup"]["deleted"]["job.read_model_dirty_scopes"], 1)
        self.assertEqual(report["cleanup"]["deleted"]["job.outbox_events"], 1)
        self.assertEqual(report["cleanup"]["deleted"]["read_model.app_status_readiness"], 1)
        self.assertEqual(len(repository.repair_audit_events), 1)
        audit = repository.repair_audit_events[0]
        self.assertEqual(audit["event_type"], "invalid_read_model_refresh_scope_repair")
        self.assertEqual(audit["object_id"], "invalid_read_model_refresh_scopes")
        self.assertEqual(audit["reason"], "manual_invalid_scope_cleanup")
        self.assertEqual(len(audit["payload"]["items"]), 3)
        self.assertEqual(report["repair_audit"]["recorded"], True)
        self.assertEqual(report["repair_audit"]["event_id"], "audit-1")

    def test_invalid_read_model_scope_repair_is_idempotent(self) -> None:
        repository = FakeScopeContractRepository()
        repository.policy_managed_dirty_scopes = [
            {
                "id": "dirty-invalid",
                "tenant_id": "default",
                "scope_type": "search",
                "scope_key": "active:2026-05",
                "status": "pending",
            }
        ]
        service = ReadModelScopeContractService(repository)

        first = service.repair_invalid_read_model_refresh_scopes(apply=True)
        second = service.repair_invalid_read_model_refresh_scopes(apply=True)

        self.assertEqual(first["cleanup"]["deleted"]["job.read_model_dirty_scopes"], 1)
        self.assertEqual(second["invalid_scope_count"], 0)
        self.assertEqual(second["cleanup"]["deleted"]["job.read_model_dirty_scopes"], 0)
        self.assertEqual(len(repository.repair_audit_events), 1)


if __name__ == "__main__":
    unittest.main()
