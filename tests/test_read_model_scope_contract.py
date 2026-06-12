from __future__ import annotations

import unittest

from fin_ops_platform.services.read_model_scope_contract import ReadModelScopeContractService


class FakeScopeContractRepository:
    def __init__(self) -> None:
        self.dirty_scopes: list[dict[str, object]] = []
        self.outbox_events: list[dict[str, object]] = []
        self.read_model_outbox_failures: list[dict[str, object]] = []
        self.readiness: list[dict[str, object]] = []
        self.deleted_dirty_scope_ids: list[str] = []
        self.deleted_outbox_event_ids: list[str] = []
        self.deleted_readiness: list[dict[str, str]] = []
        self.repair_audit_events: list[dict[str, object]] = []

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


if __name__ == "__main__":
    unittest.main()
