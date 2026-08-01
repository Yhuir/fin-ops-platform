from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.runtime_paths import default_data_dir


@contextmanager
def turnover_ledger_canonical_snapshot(
    connection: Any,
) -> Iterator[tuple[PostgresStateStore, Any]]:
    """Expose one read-only canonical snapshot to the Turnover query service."""

    with connection.transaction() as transaction:
        transaction.execute("set transaction isolation level repeatable read read only")
        yield PostgresStateStore(data_dir=default_data_dir(), connection=transaction), transaction
