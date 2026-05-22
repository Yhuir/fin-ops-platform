from __future__ import annotations

import unittest

from fin_ops_platform.tools import runtime_queue_ops


class FakeConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        self.fetch_all_calls.append((sql, params))
        return [
            {
                "event_id": "00000000-0000-0000-0000-000000000001",
                "event_type": "workbench.read_model.refresh",
                "scope_type": "workbench",
                "scope_key": "all",
                "publish_status": "failed",
                "publish_last_error": "broker down",
            }
        ]

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.execute_calls.append((sql, params))
        return 1


class RuntimeQueueOpsTests(unittest.TestCase):
    def test_replay_unpublished_dry_run_lists_candidates_without_update(self) -> None:
        connection = FakeConnection()

        result = runtime_queue_ops._replay_unpublished(connection, limit=25, execute=False)

        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(connection.execute_calls, [])
        sql, params = connection.fetch_all_calls[0]
        self.assertIn("publish_status in ('unpublished', 'failed')", " ".join(sql.lower().split()))
        self.assertEqual(params, (25,))

    def test_replay_unpublished_execute_resets_publish_state(self) -> None:
        connection = FakeConnection()

        result = runtime_queue_ops._replay_unpublished(connection, limit=10, execute=True)

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["updated"], 1)
        sql, params = connection.execute_calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("publish_status = 'unpublished'", normalized_sql)
        self.assertIn("next_publish_at = now()", normalized_sql)
        self.assertEqual(params, (["00000000-0000-0000-0000-000000000001"],))

    def test_set_control_flag_writes_app_settings_control_key(self) -> None:
        connection = FakeConnection()

        result = runtime_queue_ops._set_control_flag(connection, component="dispatcher", paused=True)

        self.assertEqual(result, {"settings_key": "runtime:rabbitmq_control", "dispatcher_paused": True})
        sql, params = connection.execute_calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("insert into app.app_settings", normalized_sql)
        self.assertIn("on conflict (settings_key) do update", normalized_sql)
        self.assertEqual(params[0], "runtime:rabbitmq_control")
        self.assertEqual(params[1], {"dispatcher_paused": True})


if __name__ == "__main__":
    unittest.main()
