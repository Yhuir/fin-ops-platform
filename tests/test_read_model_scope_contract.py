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
        self.dirty_scopes: list[dict[str, object]] = []
        self.outbox_events: list[dict[str, object]] = []
        self.read_model_outbox_failures: list[dict[str, object]] = []
        self.readiness: list[dict[str, object]] = []
        self.policy_managed_dirty_scopes: list[dict[str, object]] = []
        self.policy_managed_outbox_events: list[dict[str, object]] = []
        self.policy_managed_readiness: list[dict[str, object]] = []
        self.deleted_dirty_scope_ids: list[str] = []
        self.deleted_outbox_event_ids: list[str] = []
        self.deleted_readiness: list[dict[str, str]] = []
        self.repair_audit_events: list[dict[str, object]] = []
        self.orphaned_import_fact_dirty_scopes: list[dict[str, object]] = []

    def list_cost_statistics_dirty_scopes(self) -> list[dict[str, object]]:
        return [row for row in self.dirty_scopes if str(row.get("id") or "") not in self.deleted_dirty_scope_ids]

    def list_cost_statistics_outbox_events(self) -> list[dict[str, object]]:
        return [row for row in self.outbox_events if str(row.get("id") or "") not in self.deleted_outbox_event_ids]

    def list_read_model_outbox_failures(self) -> list[dict[str, object]]:
        return [row for row in self.read_model_outbox_failures if str(row.get("id") or "") not in self.deleted_outbox_event_ids]

    def list_cost_statistics_readiness(self) -> list[dict[str, object]]:
        deleted_keys = {
            (item["tenant_id"], item["read_model_key"], item["scope_type"], item["scope_key"])
            for item in self.deleted_readiness
        }
        return [
            row
            for row in self.readiness
            if (
                str(row.get("tenant_id") or "default"),
                str(row.get("read_model_key") or "cost_statistics"),
                str(row.get("scope_type") or "cost_statistics"),
                str(row.get("scope_key") or ""),
            )
            not in deleted_keys
        ]

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
        self.assertEqual(params, (["cost_statistics", "no_oa_bank_batch", "pending_invoice"],))
        self.assertIn("scope_type = any(%s)", sql)
        self.assertIn("status in ('pending', 'processing', 'failed')", sql)

    def test_postgres_repository_lists_policy_managed_outbox_events(self) -> None:
        connection = CapturingConnection()

        rows = PostgresReadModelScopeContractRepository(connection).list_policy_managed_outbox_events()

        self.assertEqual(rows, [])
        sql, params = connection.fetch_all_calls[-1]
        self.assertEqual(params, (["cost_statistics", "no_oa_bank_batch", "pending_invoice"],))
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
                ["cost_statistics", "no_oa_bank_batch", "pending_invoice"],
                ["cost_statistics", "no_oa_bank_batch", "pending_invoice"],
            ),
        )
        self.assertIn("from read_model.app_status_readiness", sql)
        self.assertIn("scope_type = any(%s)", sql)
        self.assertIn("read_model_key = any(%s)", sql)

    def test_check_reports_non_canonical_cost_statistics_scope_rows_without_writes(self) -> None:
        repository = FakeScopeContractRepository()
        repository.dirty_scopes = [
            {"id": "dirty-1", "tenant_id": "default", "scope_type": "cost_statistics", "scope_key": "2026-03", "status": "failed"},
            {"id": "dirty-2", "tenant_id": "default", "scope_type": "cost_statistics", "scope_key": "active:2026-03", "status": "pending"},
        ]
        repository.outbox_events = [
            {"id": "event-1", "tenant_id": "default", "event_type": "cost_statistics.read_model.refresh", "scope_key": "all", "status": "dead_lettered"},
        ]
        repository.readiness = [
            {
                "tenant_id": "default",
                "read_model_key": "cost_statistics",
                "scope_type": "cost_statistics",
                "scope_key": "archived:2026-03",
                "status": "failed",
            },
        ]

        report = ReadModelScopeContractService(repository).check_cost_statistics_contract()

        self.assertFalse(report["ok"])
        self.assertEqual(report["violation_count"], 3)
        self.assertEqual(
            report["summary"],
            {
                "job.read_model_dirty_scopes": {"legacy": 1, "invalid": 0, "total": 1},
                "job.outbox_events": {"legacy": 1, "invalid": 0, "total": 1},
                "read_model.app_status_readiness": {"legacy": 0, "invalid": 1, "total": 1},
            },
        )
        self.assertEqual(
            report["replacement_scope_keys"],
            ["active:2026-03", "all:2026-03", "active:all", "all:all"],
        )
        self.assertEqual(repository.deleted_dirty_scope_ids, [])
        self.assertEqual(repository.deleted_outbox_event_ids, [])
        self.assertEqual(repository.deleted_readiness, [])

    def test_check_reports_repair_manifest_categories_and_outbox_current_state(self) -> None:
        repository = FakeScopeContractRepository()
        repository.dirty_scopes = [
            {
                "id": "dirty-legacy",
                "tenant_id": "default",
                "scope_type": "cost_statistics",
                "scope_key": "2026-03",
                "status": "failed",
                "last_error": "legacy dirty failed",
                "updated_at": "2026-06-04T09:00:00+00:00",
            },
        ]
        repository.outbox_events = [
            {
                "id": "outbox-legacy",
                "tenant_id": "default",
                "event_type": "cost_statistics.read_model.refresh",
                "scope_type": "cost_statistics",
                "scope_key": "all",
                "status": "dead_lettered",
                "last_error": "legacy outbox failed",
                "updated_at": "2026-06-04T09:01:00+00:00",
            },
        ]
        repository.readiness = [
            {
                "tenant_id": "default",
                "read_model_key": "cost_statistics",
                "scope_type": "cost_statistics",
                "scope_key": "all",
                "status": "failed",
                "last_error": "legacy readiness failed",
                "updated_at": "2026-06-04T09:02:00+00:00",
            },
        ]
        repository.read_model_outbox_failures = [
            {
                "id": "covered-output",
                "tenant_id": "default",
                "event_type": "output_invoice_collection.read_model.refresh",
                "scope_type": "output_invoice_collection",
                "scope_key": "2026-05",
                "status": "dead_lettered",
                "last_error": "old output projection failed",
                "updated_at": "2026-06-04T08:00:00+00:00",
                "covered_by_later_done": False,
                "covered_by_later_readiness": True,
            },
            {
                "id": "current-bank",
                "tenant_id": "default",
                "event_type": "bank_detail.read_model.refresh",
                "scope_type": "bank_detail",
                "scope_key": "all",
                "status": "failed",
                "last_error": "current bank detail failure",
                "updated_at": "2026-06-04T10:00:00+00:00",
                "covered_by_later_done": False,
                "covered_by_later_readiness": False,
            },
        ]

        report = ReadModelScopeContractService(repository).check_cost_statistics_contract()

        manifest = report["repair_manifest"]
        self.assertEqual(
            manifest["summary"],
            {
                "cost_statistics_legacy_dirty_scopes": 1,
                "cost_statistics_legacy_outbox_events": 1,
                "cost_statistics_legacy_readiness_rows": 1,
                "cost_statistics_invalid_dirty_scopes": 0,
                "cost_statistics_invalid_outbox_events": 0,
                "cost_statistics_invalid_readiness_rows": 0,
                "covered_historical_outbox_failures": 1,
                "current_uncovered_outbox_failures": 1,
            },
        )
        covered = next(item for item in manifest["items"] if item["category"] == "covered_historical_outbox_failures")
        self.assertEqual(covered["scope_type"], "output_invoice_collection")
        self.assertEqual(covered["scope_key"], "2026-05")
        self.assertEqual(covered["event_type"], "output_invoice_collection.read_model.refresh")
        self.assertEqual(covered["status"], "dead_lettered")
        self.assertEqual(covered["last_error"], "old output projection failed")
        self.assertEqual(covered["updated_at"], "2026-06-04T08:00:00+00:00")
        self.assertEqual(covered["covered_by"], ["fresh_readiness"])
        self.assertEqual(covered["proposed_action"], "operator_resolve_historical_outbox_failure")
        self.assertIn("restore", covered["rollback_hint"])

        current = next(item for item in manifest["items"] if item["category"] == "current_uncovered_outbox_failures")
        self.assertEqual(current["proposed_action"], "retain_current_blocker_investigate_or_requeue")
        self.assertEqual(current["covered_by"], [])
        self.assertEqual(report["current_uncovered_outbox_failure_count"], 1)
        self.assertEqual(repository.repair_audit_events, [])

    def test_apply_deletes_violations_and_enqueues_deduped_replacement_scopes(self) -> None:
        repository = FakeScopeContractRepository()
        repository.dirty_scopes = [
            {"id": "dirty-1", "tenant_id": "default", "scope_type": "cost_statistics", "scope_key": "2026-03", "status": "failed"},
        ]
        repository.outbox_events = [
            {"id": "event-1", "tenant_id": "default", "event_type": "cost_statistics.read_model.refresh", "scope_key": "2026-03", "status": "failed"},
        ]
        repository.readiness = [
            {
                "tenant_id": "tenant-a",
                "read_model_key": "cost_statistics",
                "scope_type": "cost_statistics",
                "scope_key": "all",
                "status": "failed",
            },
        ]
        gateway = FakeRefreshGateway()

        report = ReadModelScopeContractService(repository).repair_cost_statistics_contract(
            apply=True,
            refresh_gateway=gateway,
            reason="manual_scope_repair",
        )

        self.assertEqual(repository.deleted_dirty_scope_ids, ["dirty-1"])
        self.assertEqual(repository.deleted_outbox_event_ids, ["event-1"])
        self.assertEqual(
            repository.deleted_readiness,
            [
                {
                    "tenant_id": "tenant-a",
                    "read_model_key": "cost_statistics",
                    "scope_type": "cost_statistics",
                    "scope_key": "all",
                }
            ],
        )
        self.assertEqual(
            gateway.enqueued,
            [
                {
                    "scope_type": "cost_statistics",
                    "scope_keys": ["active:2026-03", "all:2026-03", "active:all", "all:all"],
                    "reason": "manual_scope_repair",
                }
            ],
        )
        self.assertEqual(report["cleanup"]["deleted"]["job.read_model_dirty_scopes"], 1)
        self.assertEqual(report["replacement_enqueue"]["enqueued_count"], 4)

    def test_apply_records_audit_with_manifest_cleanup_and_rollback_without_deleting_current_failures(self) -> None:
        repository = FakeScopeContractRepository()
        repository.dirty_scopes = [
            {"id": "dirty-1", "tenant_id": "default", "scope_type": "cost_statistics", "scope_key": "2026-03", "status": "failed"},
        ]
        repository.outbox_events = [
            {"id": "event-legacy", "tenant_id": "default", "event_type": "cost_statistics.read_model.refresh", "scope_key": "all", "status": "dead_lettered"},
        ]
        repository.read_model_outbox_failures = [
            {
                "id": "current-bank",
                "tenant_id": "default",
                "event_type": "bank_detail.read_model.refresh",
                "scope_type": "bank_detail",
                "scope_key": "all",
                "status": "failed",
                "covered_by_later_done": False,
                "covered_by_later_readiness": False,
            },
        ]
        gateway = FakeRefreshGateway()

        report = ReadModelScopeContractService(repository).repair_cost_statistics_contract(
            apply=True,
            refresh_gateway=gateway,
            reason="manual_scope_repair",
        )

        self.assertEqual(repository.deleted_dirty_scope_ids, ["dirty-1"])
        self.assertEqual(repository.deleted_outbox_event_ids, ["event-legacy"])
        self.assertNotIn("current-bank", repository.deleted_outbox_event_ids)
        self.assertEqual(len(repository.repair_audit_events), 1)
        audit = repository.repair_audit_events[0]
        self.assertEqual(audit["event_type"], "read_model_scope_contract_repair")
        self.assertEqual(audit["object_type"], "read_model_runtime_repair")
        self.assertEqual(audit["reason"], "manual_scope_repair")
        self.assertEqual(audit["payload"]["repair_manifest"]["summary"]["current_uncovered_outbox_failures"], 1)
        self.assertEqual(audit["payload"]["cleanup"]["deleted"]["job.outbox_events"], 1)
        self.assertEqual(report["repair_audit"]["recorded"], True)
        self.assertEqual(report["repair_audit"]["event_id"], "audit-1")
        self.assertIn("restore deleted rows", report["rollback"]["strategy"])

    def test_apply_is_idempotent_after_rows_are_deleted(self) -> None:
        repository = FakeScopeContractRepository()
        repository.dirty_scopes = [
            {"id": "dirty-1", "tenant_id": "default", "scope_type": "cost_statistics", "scope_key": "2026-03", "status": "failed"},
        ]
        gateway = FakeRefreshGateway()
        service = ReadModelScopeContractService(repository)

        first = service.repair_cost_statistics_contract(apply=True, refresh_gateway=gateway)
        second = service.repair_cost_statistics_contract(apply=True, refresh_gateway=gateway)

        self.assertEqual(first["cleanup"]["deleted"]["job.read_model_dirty_scopes"], 1)
        self.assertEqual(second["violation_count"], 0)
        self.assertEqual(second["cleanup"]["deleted"]["job.read_model_dirty_scopes"], 0)
        self.assertEqual(len(gateway.enqueued), 1)
        self.assertEqual(len(repository.repair_audit_events), 1)

    def test_apply_without_replacement_enqueue_only_deletes_invalid_rows(self) -> None:
        repository = FakeScopeContractRepository()
        repository.readiness = [
            {
                "tenant_id": "default",
                "read_model_key": "cost_statistics",
                "scope_type": "cost_statistics",
                "scope_key": "archived:2026-03",
                "status": "failed",
            },
        ]

        report = ReadModelScopeContractService(repository).repair_cost_statistics_contract(
            apply=True,
            enqueue_replacements=False,
        )

        self.assertEqual(len(repository.deleted_readiness), 1)
        self.assertEqual(report["replacement_scope_keys"], [])
        self.assertEqual(report["replacement_enqueue"]["enabled"], False)

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
        self.assertEqual(audit["payload"]["orphaned_dirty_scope_count"], 2)
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
                "scope_type": "pending_invoice",
                "scope_key": "all",
                "status": "pending",
                "reason": "read_model_slo_smoke",
            },
            {
                "id": "dirty-valid",
                "tenant_id": "default",
                "scope_type": "pending_invoice",
                "scope_key": "expense:all",
                "status": "pending",
            },
        ]
        repository.policy_managed_outbox_events = [
            {
                "id": "outbox-invalid",
                "tenant_id": "default",
                "event_type": "pending_invoice.read_model.refresh",
                "scope_type": "pending_invoice",
                "scope_key": "all",
                "status": "pending",
            }
        ]
        repository.policy_managed_readiness = [
            {
                "tenant_id": "default",
                "read_model_key": "pending_invoice",
                "scope_type": "pending_invoice",
                "scope_key": "all",
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
                "scope_type": "pending_invoice",
                "scope_key": "all",
                "status": "pending",
                "reason": "read_model_slo_smoke",
            }
        ]
        repository.policy_managed_outbox_events = [
            {
                "id": "outbox-invalid",
                "tenant_id": "default",
                "event_type": "pending_invoice.read_model.refresh",
                "scope_type": "pending_invoice",
                "scope_key": "all",
                "status": "pending",
            }
        ]
        repository.policy_managed_readiness = [
            {
                "tenant_id": "default",
                "read_model_key": "pending_invoice",
                "scope_type": "pending_invoice",
                "scope_key": "all",
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
                    "read_model_key": "pending_invoice",
                    "scope_type": "pending_invoice",
                    "scope_key": "all",
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
        self.assertEqual(audit["payload"]["invalid_scope_count"], 3)
        self.assertEqual(report["repair_audit"]["recorded"], True)
        self.assertEqual(report["repair_audit"]["event_id"], "audit-1")

    def test_invalid_read_model_scope_repair_is_idempotent(self) -> None:
        repository = FakeScopeContractRepository()
        repository.policy_managed_dirty_scopes = [
            {
                "id": "dirty-invalid",
                "tenant_id": "default",
                "scope_type": "pending_invoice",
                "scope_key": "all",
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
