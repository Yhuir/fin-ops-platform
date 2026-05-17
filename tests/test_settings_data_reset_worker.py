from __future__ import annotations

import unittest
from datetime import UTC, datetime

from fin_ops_platform.services.settings_data_reset_service import RESET_BANK_TRANSACTIONS_ACTION
from fin_ops_platform.services.worker_task_protocol import (
    PermanentWorkerError,
    WorkerTaskEnvelope,
)
from fin_ops_platform.services.settings_data_reset_worker import SettingsDataResetWorkerHandler
from tests.test_worker_task_protocol import valid_message


class FakeWorkerContext:
    attempt_id = "attempt-001"
    attempt_no = 1

    def __init__(self) -> None:
        self.heartbeat_count = 0

    def heartbeat(self) -> None:
        self.heartbeat_count += 1


class SettingsDataResetWorkerTests(unittest.TestCase):
    def _envelope(self, **overrides: object) -> WorkerTaskEnvelope:
        payload = {
            "schema_version": "finops.platform_legacy.data_reset_request.v1",
            "action": RESET_BANK_TRANSACTIONS_ACTION,
            "approval_id": "approval-123",
            "backup_evidence_id": "backup-456",
            "scope": {"domain": "bank_transactions"},
        }
        source = {
            "action": RESET_BANK_TRANSACTIONS_ACTION,
            "approval_id": "approval-123",
            "backup_evidence_id": "backup-456",
            "scope": {"domain": "bank_transactions"},
        }
        payload_override = overrides.pop("payload", None)
        source_override = overrides.pop("source", None)
        if payload_override is not None:
            payload = payload_override  # type: ignore[assignment]
        if source_override is not None:
            source = source_override  # type: ignore[assignment]
        message = valid_message(
            task_type="settings_data_reset",
            idempotency_key="data-reset:bank:approval-123",
            source=source,
            payload=payload,
            scope={"domain": "bank_transactions"},
            trace_id="trace-data-reset-001",
            **overrides,
        )
        return WorkerTaskEnvelope.from_mapping(message)

    def test_worker_requires_explicit_allow_flag_before_destructive_execution(self) -> None:
        calls: list[str] = []
        handler = SettingsDataResetWorkerHandler(
            reset_executor=lambda action, progress=None: calls.append(action) or {"status": "completed"},
            allow_destructive=False,
            clock=lambda: datetime(2026, 5, 17, 10, 0, tzinfo=UTC),
        )

        with self.assertRaises(PermanentWorkerError) as raised:
            handler(self._envelope(), FakeWorkerContext())

        self.assertEqual(raised.exception.error_code, "DATA_RESET_WORKER_NOT_ALLOWED")
        self.assertEqual(calls, [])

    def test_worker_requires_approval_and_backup_evidence_before_execution(self) -> None:
        calls: list[str] = []
        handler = SettingsDataResetWorkerHandler(
            reset_executor=lambda action, progress=None: calls.append(action) or {"status": "completed"},
            allow_destructive=True,
        )

        with self.assertRaises(PermanentWorkerError) as raised:
            handler(
                self._envelope(
                    source={
                        "action": RESET_BANK_TRANSACTIONS_ACTION,
                        "approval_id": "",
                        "backup_evidence_id": "backup-456",
                        "scope": {},
                    },
                    payload={
                        "schema_version": "finops.platform_legacy.data_reset_request.v1",
                        "action": RESET_BANK_TRANSACTIONS_ACTION,
                        "approval_id": "",
                        "backup_evidence_id": "backup-456",
                        "scope": {},
                    }
                ),
                FakeWorkerContext(),
            )

        self.assertEqual(raised.exception.error_code, "DATA_RESET_APPROVAL_REQUIRED")
        self.assertEqual(calls, [])

    def test_worker_executes_supported_task_and_returns_lineage_proof_without_password(self) -> None:
        executor_calls: list[tuple[str, object]] = []

        def executor(action: str, progress=None) -> dict[str, object]:
            executor_calls.append((action, progress))
            if progress is not None:
                progress("clear", "clearing", 10)
            return {
                "status": "completed",
                "deleted_counts": {"bank_transactions": 2},
                "message": "done",
                "oa_password": "must-not-leak",
            }

        context = FakeWorkerContext()
        handler = SettingsDataResetWorkerHandler(
            reset_executor=executor,
            allow_destructive=True,
            clock=lambda: datetime(2026, 5, 17, 10, 0, tzinfo=UTC),
        )

        summary = handler(
            self._envelope(
                payload={
                    "schema_version": "finops.platform_legacy.data_reset_request.v1",
                    "action": RESET_BANK_TRANSACTIONS_ACTION,
                    "approval_id": "approval-123",
                    "backup_evidence_id": "backup-456",
                    "scope": {"domain": "bank_transactions"},
                    "oa_password": "ignored-secret",
                }
            ),
            context,
        )

        self.assertEqual(executor_calls[0][0], RESET_BANK_TRANSACTIONS_ACTION)
        self.assertGreaterEqual(context.heartbeat_count, 2)
        self.assertEqual(summary["status"], "completed")
        proof = summary["worker_proof"]
        self.assertEqual(proof["task_id"], "22222222-2222-4222-8222-222222222222")
        self.assertEqual(proof["attempt_id"], "attempt-001")
        self.assertEqual(proof["trace_id"], "trace-data-reset-001")
        serialized = str(summary)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("ignored-secret", serialized)
        self.assertNotIn("oa_password", serialized)


if __name__ == "__main__":
    unittest.main()
