from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
    PostgresWorkbenchIdempotencyRepository,
)
from fin_ops_platform.services.workbench_idempotency import InMemoryWorkbenchIdempotencyRepository


DOC_PATH = Path("docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md")


class _Connection:
    pass


class _PostgresStateStore:
    storage_backend = "postgres"

    def __init__(self, connection: object) -> None:
        self._connection = connection


class _QueueRepository:
    pass


def _new_application(connection: object | None = None) -> Application:
    app = object.__new__(Application)
    app._state_store = _PostgresStateStore(connection or _Connection())
    app._runtime_repositories = SimpleNamespace(queue_repository=_QueueRepository())
    return app


class WorkbenchDurableIdempotencyRolloutTests(unittest.TestCase):
    def test_rollout_readiness_document_exists_and_records_gate_matrix(self) -> None:
        self.assertTrue(DOC_PATH.exists(), "PF-P040 must add a durable idempotency rollout readiness document.")

        text = DOC_PATH.read_text(encoding="utf-8")
        for token in (
            "Rollout Readiness Matrix",
            "ready",
            "blocked",
            "documented-risk",
            "future-test-needed",
            "FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY",
            "default-off safety",
            "opt-in feature flag wiring",
            "transaction-bound reserve/commit",
            "committed replay",
            "same-key different-fingerprint conflict",
            "expired reserved takeover",
            "in-progress duplicate policy",
            "actor/tenant auth context",
            "cleanup/retention",
            "rollback",
        ):
            self.assertIn(token, text)

    def test_feature_flag_remains_default_off_and_opt_in_only(self) -> None:
        app = _new_application()
        with patch.dict(os.environ, {"FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY": ""}, clear=False):
            default_uow = Application._workbench_confirm_link_unit_of_work(app)

        self.assertIsNotNone(default_uow)
        self.assertIsInstance(default_uow._idempotency_store, InMemoryWorkbenchIdempotencyRepository)

        enabled_app = _new_application()
        with patch.dict(os.environ, {"FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY": "1"}, clear=False):
            enabled_uow = Application._workbench_confirm_link_unit_of_work(enabled_app)

        self.assertIsNotNone(enabled_uow)
        self.assertIsInstance(enabled_uow._idempotency_store, PostgresWorkbenchIdempotencyRepository)

    def test_readiness_document_keeps_unimplemented_target_contracts_as_blockers(self) -> None:
        self.assertTrue(DOC_PATH.exists(), "PF-P040 must document blockers before durable idempotency can be enabled.")

        text = DOC_PATH.read_text(encoding="utf-8")
        for blocker in (
            "expired reserved takeover",
            "failed reservation policy",
            "real PostgreSQL row-lock concurrency",
            "actor/tenant auth context",
        ):
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, text)
        self.assertIn("| reserved/in-progress duplicate policy | ready |", text)
        self.assertIn("Feature flag must remain off", text)


if __name__ == "__main__":
    unittest.main()
