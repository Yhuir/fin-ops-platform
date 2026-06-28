from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import runtime_queue_ops


class FakeConnection:
    def __init__(
        self,
        fetch_one_rows: list[dict[str, object] | None] | None = None,
        fetch_all_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.fetch_one_rows = list(fetch_one_rows or [])
        self.fetch_all_rows = fetch_all_rows
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        self.fetch_one_calls.append((sql, params))
        return self.fetch_one_rows.pop(0) if self.fetch_one_rows else None

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        self.fetch_all_calls.append((sql, params))
        if self.fetch_all_rows is not None:
            return list(self.fetch_all_rows)
        return [
            {
                "event_id": "00000000-0000-0000-0000-000000000001",
                "event_type": "background.sample.changed",
                "scope_type": "legacy_sample",
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
        self.release_stale_calls: list[dict[str, object]] = []
        self.resolve_superseded_calls: list[dict[str, object]] = []

    def release_stale_processing_events(
        self,
        *,
        stale_after_seconds: int,
        limit: int = 100,
        reason: str = "operator_stale_processing_release",
        event_types=(),
    ):
        self.release_stale_calls.append(
            {
                "stale_after_seconds": stale_after_seconds,
                "limit": limit,
                "reason": reason,
                "event_types": tuple(event_types),
            }
        )
        return [
            {
                "event_id": "00000000-0000-0000-0000-000000000001",
                "event_type": "background.sample.changed",
                "status": "pending",
            }
        ]

    def resolve_superseded_processing_events(
        self,
        *,
        stale_after_seconds: int,
        limit: int = 100,
        reason: str = "operator_superseded_processing_resolution",
        event_types=(),
    ):
        self.resolve_superseded_calls.append(
            {
                "stale_after_seconds": stale_after_seconds,
                "limit": limit,
                "reason": reason,
                "event_types": tuple(event_types),
            }
        )
        return [
            {
                "event_id": "00000000-0000-0000-0000-000000000001",
                "event_type": "background.sample.changed",
                "status": "done",
            }
        ]


class RuntimeQueueOpsTests(unittest.TestCase):
    def test_inspect_command_serializes_datetime_fields(self) -> None:
        connection = FakeConnection(
            fetch_one_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "background.sample.changed",
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

    def test_release_stale_processing_dry_run_lists_candidates_without_update(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "background.sample.changed",
                    "status": "processing",
                    "locked_age_seconds": 600,
                }
            ]
        )
        repository = FakeRuntimeQueueRepository()

        result = runtime_queue_ops._release_stale_processing(
            connection,
            repository,  # type: ignore[arg-type]
            stale_after_seconds=300,
            limit=25,
            event_types=["background.sample.changed"],
            reason="rabbitmq_stale_processing_repair",
            execute=False,
        )

        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["released_count"], 0)
        self.assertEqual(repository.release_stale_calls, [])
        sql, params = connection.fetch_all_calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("status = 'processing'", normalized_sql)
        self.assertIn("locked_at < now() - (%s * interval '1 second')", normalized_sql)
        self.assertIn("stale.event_type = any(%s)", normalized_sql)
        self.assertIn("dedupe_rank = 1", normalized_sql)
        self.assertEqual(params, (300, ["background.sample.changed"], 25))

    def test_release_stale_processing_execute_uses_repository_boundary(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "background.sample.changed",
                    "status": "processing",
                    "locked_age_seconds": 600,
                }
            ]
        )
        repository = FakeRuntimeQueueRepository()

        result = runtime_queue_ops._release_stale_processing(
            connection,
            repository,  # type: ignore[arg-type]
            stale_after_seconds=300,
            limit=25,
            event_types=["background.sample.changed"],
            reason="rabbitmq_stale_processing_repair",
            execute=True,
        )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["released_count"], 1)
        self.assertEqual(
            repository.release_stale_calls,
            [
                {
                    "stale_after_seconds": 300,
                    "limit": 25,
                    "reason": "rabbitmq_stale_processing_repair",
                    "event_types": ("background.sample.changed",),
                }
            ],
        )

    def test_resolve_superseded_processing_dry_run_lists_candidates_without_update(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "background.sample.changed",
                    "status": "processing",
                    "locked_age_seconds": 600,
                    "covered_by_event_id": "00000000-0000-0000-0000-000000000002",
                    "covered_by_status": "pending",
                }
            ]
        )
        repository = FakeRuntimeQueueRepository()

        result = runtime_queue_ops._resolve_superseded_processing(
            connection,
            repository,  # type: ignore[arg-type]
            stale_after_seconds=300,
            limit=25,
            event_types=["background.sample.changed"],
            reason="rabbitmq_stale_processing_superseded",
            execute=False,
        )

        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["resolved_count"], 0)
        self.assertEqual(repository.resolve_superseded_calls, [])
        sql, params = connection.fetch_all_calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("join lateral", normalized_sql)
        self.assertIn("newer.status in ('pending', 'processing', 'done')", normalized_sql)
        self.assertIn("stale.event_type = any(%s)", normalized_sql)
        self.assertEqual(params, (300, ["background.sample.changed"], 25))

    def test_resolve_superseded_processing_execute_uses_repository_boundary(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "background.sample.changed",
                    "status": "processing",
                    "locked_age_seconds": 600,
                    "covered_by_event_id": "00000000-0000-0000-0000-000000000002",
                    "covered_by_status": "pending",
                }
            ]
        )
        repository = FakeRuntimeQueueRepository()

        result = runtime_queue_ops._resolve_superseded_processing(
            connection,
            repository,  # type: ignore[arg-type]
            stale_after_seconds=300,
            limit=25,
            event_types=["background.sample.changed"],
            reason="rabbitmq_stale_processing_superseded",
            execute=True,
        )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["resolved_count"], 1)
        self.assertEqual(
            repository.resolve_superseded_calls,
            [
                {
                    "stale_after_seconds": 300,
                    "limit": 25,
                    "reason": "rabbitmq_stale_processing_superseded",
                    "event_types": ("background.sample.changed",),
                }
            ],
        )

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

    def test_read_model_dead_letter_resolve_commands_are_removed(self) -> None:
        command_names = set(runtime_queue_ops.build_parser()._subparsers._group_actions[0].choices)

        self.assertNotIn("resolve-dead-letter", command_names)
        self.assertNotIn("resolve-covered-dead-letters", command_names)


if __name__ == "__main__":
    unittest.main()
