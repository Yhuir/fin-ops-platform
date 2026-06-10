from __future__ import annotations

import unittest

from fin_ops_platform.services.read_model_scope_contract import ReadModelScopeContractService


class FakeScopeContractRepository:
    def __init__(self) -> None:
        self.dirty_scopes: list[dict[str, object]] = []
        self.outbox_events: list[dict[str, object]] = []
        self.readiness: list[dict[str, object]] = []
        self.deleted_dirty_scope_ids: list[str] = []
        self.deleted_outbox_event_ids: list[str] = []
        self.deleted_readiness: list[dict[str, str]] = []

    def list_cost_statistics_dirty_scopes(self) -> list[dict[str, object]]:
        return list(self.dirty_scopes)

    def list_cost_statistics_outbox_events(self) -> list[dict[str, object]]:
        return list(self.outbox_events)

    def list_cost_statistics_readiness(self) -> list[dict[str, object]]:
        return list(self.readiness)

    def delete_dirty_scope(self, row_id: str) -> int:
        self.deleted_dirty_scope_ids.append(row_id)
        return 1

    def delete_outbox_event(self, row_id: str) -> int:
        self.deleted_outbox_event_ids.append(row_id)
        return 1

    def delete_readiness(self, *, tenant_id: str, read_model_key: str, scope_type: str, scope_key: str) -> int:
        self.deleted_readiness.append(
            {
                "tenant_id": tenant_id,
                "read_model_key": read_model_key,
                "scope_type": scope_type,
                "scope_key": scope_key,
            }
        )
        return 1


class FakeRefreshGateway:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def can_enqueue(self) -> bool:
        return True

    def enqueue_many(self, scope_type: str, scope_keys: list[str], *, reason: str) -> list[str]:
        self.enqueued.append({"scope_type": scope_type, "scope_keys": list(scope_keys), "reason": reason})
        return list(scope_keys)


class ReadModelScopeContractServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
