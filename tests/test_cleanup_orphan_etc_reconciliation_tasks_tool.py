from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import unittest

from fin_ops_platform.services.etc_reconciliation_models import EtcReconciliationTaskStatus
from fin_ops_platform.tools.cleanup_orphan_etc_reconciliation_tasks import _execute_task_cleanup, _plan_task_cleanup


@dataclass
class _Task:
    task_id: str
    status: EtcReconciliationTaskStatus
    version: int


class _ReconciliationTaskService:
    def __init__(self, task: _Task | None) -> None:
        self.task = task
        self.deleted_calls: list[dict[str, object]] = []

    def snapshot(self) -> dict[str, object]:
        if self.task is None:
            return {"tasks": {}}
        return {
            "tasks": {
                self.task.task_id: {
                    "task_id": self.task.task_id,
                    "status": self.task.status.value,
                    "version": self.task.version,
                }
            }
        }

    def get_task(self, task_id: str) -> _Task:
        if self.task is None or self.task.task_id != task_id or self.task.status == EtcReconciliationTaskStatus.DELETED:
            raise KeyError(task_id)
        return self.task

    def delete_task(self, **kwargs: object) -> dict[str, object]:
        self.deleted_calls.append(dict(kwargs))
        if self.task is None:
            raise KeyError(kwargs.get("task_id"))
        self.task.status = EtcReconciliationTaskStatus.DELETED
        self.task.version += 1
        return {"deleted": True, "taskId": self.task.task_id, "kind": "reconciliation_task"}


class _EtcService:
    def __init__(self, business_batch_ids: list[str] | None = None) -> None:
        self.business_batch_ids = list(business_batch_ids or [])

    def list_business_batches(self, *, task_id: str | None = None) -> list[object]:
        return [SimpleNamespace(business_batch_id=batch_id) for batch_id in self.business_batch_ids]


class CleanupOrphanEtcReconciliationTasksToolTests(unittest.TestCase):
    def test_dry_run_blocks_task_with_active_business_batch(self) -> None:
        app = SimpleNamespace(
            _etc_reconciliation_task_service=_ReconciliationTaskService(
                _Task("ETC-RECON-000001", EtcReconciliationTaskStatus.DRAFT, 1)
            ),
            _etc_service=_EtcService(["etc_business_batch_0001"]),
        )

        result = _plan_task_cleanup(app, "ETC-RECON-000001")

        self.assertEqual(result["status"], "blocked_active_business_batch")
        self.assertEqual(result["active_business_batch_ids"], ["etc_business_batch_0001"])

    def test_execute_deletes_ready_orphan_task_and_is_idempotent(self) -> None:
        reconciliation_service = _ReconciliationTaskService(
            _Task("ETC-RECON-000001", EtcReconciliationTaskStatus.DRAFT, 3)
        )
        app = SimpleNamespace(
            _etc_reconciliation_task_service=reconciliation_service,
            _etc_service=_EtcService(),
        )

        first = _execute_task_cleanup(app, "ETC-RECON-000001", reason="cleanup_test")
        second = _execute_task_cleanup(app, "ETC-RECON-000001", reason="cleanup_test_retry")

        self.assertEqual(first["status"], "deleted")
        self.assertEqual(first["result"], {"deleted": True, "taskId": "ETC-RECON-000001", "kind": "reconciliation_task"})
        self.assertEqual(second["status"], "already_deleted")
        self.assertEqual(len(reconciliation_service.deleted_calls), 1)
        self.assertEqual(reconciliation_service.deleted_calls[0]["expected_version"], 3)
        self.assertEqual(reconciliation_service.deleted_calls[0]["import_cleanup_confirmed"], True)


if __name__ == "__main__":
    unittest.main()
