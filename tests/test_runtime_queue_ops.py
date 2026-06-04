from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import runtime_queue_ops


class FakeConnection:
    def __init__(self, fetch_one_rows: list[dict[str, object] | None] | None = None) -> None:
        self.fetch_one_rows = list(fetch_one_rows or [])
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        self.fetch_one_calls.append((sql, params))
        return self.fetch_one_rows.pop(0) if self.fetch_one_rows else None

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


class FakeRuntimeQueueRepository:
    def __init__(self, resolved: bool = True) -> None:
        self.resolved = resolved
        self.resolve_calls: list[tuple[str, str]] = []

    def resolve_dead_letter_event(self, event_id: str, *, reason: str = "operator_resolved") -> bool:
        self.resolve_calls.append((event_id, reason))
        return self.resolved


class RuntimeQueueOpsTests(unittest.TestCase):
    def test_inspect_command_serializes_datetime_fields(self) -> None:
        connection = FakeConnection(
            fetch_one_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "workbench.read_model.refresh",
                    "updated_at": datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
                    "status": "dead_lettered",
                }
            ]
        )
        stdout = StringIO()

        with (
            patch.object(runtime_queue_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(runtime_queue_ops, "PostgresConnection", return_value=connection),
            patch.object(runtime_queue_ops, "RuntimeQueueRepository", return_value=FakeRuntimeQueueRepository()),
        ):
            exit_code = runtime_queue_ops.main(
                ["inspect", "--event-id", "00000000-0000-0000-0000-000000000001"],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        payload = stdout.getvalue()
        self.assertIn('"updated_at": "2026-06-04 12:00:00+00:00"', payload)

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

    def test_resolve_dead_letter_requires_fresh_readiness_and_no_active_dirty_scope(self) -> None:
        connection = FakeConnection(
            fetch_one_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "tenant_id": "default",
                    "event_type": "pending_invoice.read_model.refresh",
                    "scope_type": "pending_invoice",
                    "scope_key": "all",
                    "status": "dead_lettered",
                },
                {"fresh_count": 1},
                {"active_count": 0},
            ]
        )
        repository = FakeRuntimeQueueRepository()

        result = runtime_queue_ops._resolve_dead_letter(
            connection,
            repository,  # type: ignore[arg-type]
            event_id="00000000-0000-0000-0000-000000000001",
            reason="readiness_converged_obsolete_invalid_scope",
        )

        self.assertTrue(result["resolved"])
        self.assertEqual(result["read_model_key"], "pending_invoice")
        self.assertEqual(
            repository.resolve_calls,
            [("00000000-0000-0000-0000-000000000001", "readiness_converged_obsolete_invalid_scope")],
        )
        readiness_sql, readiness_params = connection.fetch_one_calls[1]
        dirty_sql, dirty_params = connection.fetch_one_calls[2]
        self.assertIn("read_model.app_status_readiness", " ".join(readiness_sql.lower().split()))
        self.assertEqual(readiness_params, ("default", "pending_invoice"))
        self.assertIn("job.read_model_dirty_scopes", " ".join(dirty_sql.lower().split()))
        self.assertEqual(dirty_params, ("default", "pending_invoice"))

    def test_resolve_dead_letter_refuses_when_dirty_scope_is_active(self) -> None:
        connection = FakeConnection(
            fetch_one_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "tenant_id": "default",
                    "event_type": "cost_statistics.read_model.refresh",
                    "scope_type": "cost_statistics",
                    "scope_key": "all",
                    "status": "dead_lettered",
                },
                {"fresh_count": 1},
                {"active_count": 2},
            ]
        )
        repository = FakeRuntimeQueueRepository()

        result = runtime_queue_ops._resolve_dead_letter(
            connection,
            repository,  # type: ignore[arg-type]
            event_id="00000000-0000-0000-0000-000000000001",
            reason="readiness_converged_obsolete_invalid_scope",
        )

        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "active_dirty_scope_exists")
        self.assertEqual(result["active_dirty_count"], 2)
        self.assertEqual(repository.resolve_calls, [])


if __name__ == "__main__":
    unittest.main()
