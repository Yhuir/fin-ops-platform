from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings, PostgresTransaction


class FakePool:
    def __init__(self) -> None:
        self.wait_calls: list[int] = []

    def wait(self, *, timeout: int) -> None:
        self.wait_calls.append(timeout)


class FakeCursor:
    def __init__(self, connection: "FakeRawConnection") -> None:
        self.connection = connection
        self.rowcount = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.connection.executed.append((" ".join(sql.lower().split()), params))
        self.rowcount = max(1, sql.count("), (") + 1)

    def executemany(self, sql: str, params_seq: list[tuple]) -> None:
        rows = list(params_seq)
        self.connection.executemany_calls.append((" ".join(sql.lower().split()), rows))
        self.rowcount = len(rows)


class FakeRawConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.executemany_calls: list[tuple[str, list[tuple]]] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


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

    def test_execute_many_values_batches_insert_values(self) -> None:
        connection = FakeRawConnection()
        transaction = PostgresTransaction(connection)

        affected = transaction.execute_many_values(
            """
            insert into read_model.workbench_rows(generation_id, row_id, generated_at, payload)
            values (%s, %s, coalesce(%s::timestamptz, now()), %s)
            on conflict (generation_id, row_id) do update set payload = excluded.payload
            """,
            [
                ("gen-1", "row-1", "2026-06-01T00:00:00+08:00", {"id": "row-1"}),
                ("gen-1", "row-2", "2026-06-01T00:00:00+08:00", {"id": "row-2"}),
                ("gen-1", "row-3", "2026-06-01T00:00:00+08:00", {"id": "row-3"}),
            ],
            chunk_size=2,
        )

        self.assertEqual(affected, 3)
        self.assertEqual(len(connection.executed), 2)
        self.assertIn("), (", connection.executed[0][0])
        self.assertEqual(
            connection.executed[0][1],
            (
                "gen-1",
                "row-1",
                "2026-06-01T00:00:00+08:00",
                {"id": "row-1"},
                "gen-1",
                "row-2",
                "2026-06-01T00:00:00+08:00",
                {"id": "row-2"},
            ),
        )
        self.assertEqual(connection.executed[1][1], ("gen-1", "row-3", "2026-06-01T00:00:00+08:00", {"id": "row-3"}))
        self.assertEqual(connection.executemany_calls, [])

    def test_execute_many_values_defaults_to_large_chunks_for_read_model_writes(self) -> None:
        connection = FakeRawConnection()
        transaction = PostgresTransaction(connection)
        rows = [(f"gen-{index}", f"row-{index}") for index in range(1001)]

        affected = transaction.execute_many_values(
            """
            insert into read_model.workbench_rows(generation_id, row_id)
            values (%s, %s)
            on conflict (generation_id, row_id) do update set row_id = excluded.row_id
            """,
            rows,
        )

        self.assertEqual(affected, 1001)
        self.assertEqual(len(connection.executed), 2)
        self.assertEqual(len(connection.executed[0][1]), 2000)
        self.assertEqual(len(connection.executed[1][1]), 2)
        self.assertEqual(connection.executemany_calls, [])

    def test_execute_many_values_falls_back_for_non_insert_values_sql(self) -> None:
        connection = FakeRawConnection()
        transaction = PostgresTransaction(connection)

        affected = transaction.execute_many_values(
            "update read_model.workbench_rows set status = %s where row_id = %s",
            [("open", "row-1"), ("paired", "row-2")],
        )

        self.assertEqual(affected, 2)
        self.assertEqual(connection.executed, [])
        self.assertEqual(len(connection.executemany_calls), 1)


if __name__ == "__main__":
    unittest.main()
