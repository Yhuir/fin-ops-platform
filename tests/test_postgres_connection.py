from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


class FakePool:
    def __init__(self) -> None:
        self.wait_calls: list[int] = []

    def wait(self, *, timeout: int) -> None:
        self.wait_calls.append(timeout)


class PostgresConnectionTests(unittest.TestCase):
    def test_warm_up_waits_for_existing_pool(self) -> None:
        connection = PostgresConnection(
            PostgresSettings(
                database_url="postgresql://user:secret@db/fin_ops",
                connect_timeout_seconds=7,
                pool_enabled=True,
            )
        )
        pool = FakePool()
        connection._pool = pool

        connection.warm_up()

        self.assertEqual(pool.wait_calls, [7])


if __name__ == "__main__":
    unittest.main()
