from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
    PostgresWorkbenchIdempotencyRepository,
)
from fin_ops_platform.services.workbench_idempotency import InMemoryWorkbenchIdempotencyRepository


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
    app._state_store = _PostgresStateStore(
        connection
        or PostgresConnection(
            PostgresSettings(database_url="postgresql://finops-test@127.0.0.1/finops-test", pool_enabled=False)
        )
    )
    app._runtime_repositories = SimpleNamespace(queue_repository=_QueueRepository())
    return app


class WorkbenchDurableIdempotencyRolloutTests(unittest.TestCase):

    def test_postgres_runtime_always_uses_durable_idempotency(self) -> None:
        app = _new_application()
        uow = Application._workbench_confirm_link_unit_of_work(app)

        self.assertIsNotNone(uow)
        self.assertIsInstance(uow._idempotency_store, PostgresWorkbenchIdempotencyRepository)

    def test_local_test_runtime_keeps_explicit_in_memory_adapter(self) -> None:
        app = object.__new__(Application)
        app._state_store = SimpleNamespace(storage_backend="local")

        store = Application._workbench_write_idempotency_store(app, "_test_idempotency_store", _Connection())

        self.assertIsInstance(store, InMemoryWorkbenchIdempotencyRepository)


if __name__ == "__main__":
    unittest.main()
