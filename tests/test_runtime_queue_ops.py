from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError
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
                "event_type": "workbench_relation.read_model.refresh",
                "scope_type": "workbench_relation",
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
        self.release_stale_calls: list[dict[str, object]] = []
        self.resolve_superseded_calls: list[dict[str, object]] = []
        self.preview_retention_calls: list[dict[str, object]] = []
        self.prune_retention_calls: list[dict[str, object]] = []
        self.enqueue_calls: list[dict[str, object]] = []
        self.enqueue_read_model_refresh_calls: list[dict[str, object]] = []

    def enqueue(self, **kwargs):
        self.enqueue_calls.append(dict(kwargs))
        return type(
            "Event",
            (),
            {
                "event_id": "00000000-0000-0000-0000-000000000099",
                "status": "pending",
            },
        )()

    def enqueue_read_model_refresh(self, **kwargs):
        self.enqueue_read_model_refresh_calls.append(dict(kwargs))
        event_number = len(self.enqueue_read_model_refresh_calls)
        return type(
            "Event",
            (),
            {
                "event_id": f"00000000-0000-0000-0000-{event_number:012d}",
                "status": "pending",
            },
        )()

    def resolve_dead_letter_event(self, event_id: str, *, reason: str = "operator_resolved") -> bool:
        self.resolve_calls.append((event_id, reason))
        return self.resolved

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
                "event_type": "workbench_relation.read_model.refresh",
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
                "event_type": "workbench_relation.read_model.refresh",
                "status": "done",
            }
        ]

    def preview_runtime_queue_history_retention(
        self,
        *,
        keep_days: int,
        keep_recent_per_type: int,
        limit: int,
    ) -> dict[str, object]:
        self.preview_retention_calls.append(
            {
                "keep_days": keep_days,
                "keep_recent_per_type": keep_recent_per_type,
                "limit": limit,
            }
        )
        return {
            "mode": "dry-run",
            "policy": {
                "keep_days": keep_days,
                "keep_recent_per_type": keep_recent_per_type,
                "limit": limit,
            },
            "outbox_events": {"candidate_count": 2},
            "read_model_dirty_scopes": {"candidate_count": 1},
        }

    def prune_runtime_queue_history(
        self,
        *,
        keep_days: int,
        keep_recent_per_type: int,
        limit: int,
    ) -> dict[str, object]:
        self.prune_retention_calls.append(
            {
                "keep_days": keep_days,
                "keep_recent_per_type": keep_recent_per_type,
                "limit": limit,
            }
        )
        return {
            "mode": "execute",
            "policy": {
                "keep_days": keep_days,
                "keep_recent_per_type": keep_recent_per_type,
                "limit": limit,
            },
            "outbox_events": {"deleted_count": 2},
            "read_model_dirty_scopes": {"deleted_count": 1},
        }


class RuntimeQueueOpsTests(unittest.TestCase):
    def test_inspect_command_serializes_datetime_fields(self) -> None:
        connection = FakeConnection(
            fetch_one_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "workbench_relation.read_model.refresh",
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

    def test_prune_history_cli_defaults_to_dry_run_repository_boundary(self) -> None:
        connection = FakeConnection()
        repository = FakeRuntimeQueueRepository()
        stdout = StringIO()

        with (
            patch.object(runtime_queue_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(runtime_queue_ops, "PostgresConnection", return_value=connection),
            patch.object(runtime_queue_ops, "RuntimeQueueRepository", return_value=repository),
        ):
            exit_code = runtime_queue_ops.main(["prune-history", "--dry-run"], stdout=stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            repository.preview_retention_calls,
            [{"keep_days": 30, "keep_recent_per_type": 512, "limit": 20_000}],
        )
        self.assertEqual(repository.prune_retention_calls, [])
        self.assertIn('"mode": "dry-run"', stdout.getvalue())

    def test_prune_history_cli_execute_forwards_controlled_policy(self) -> None:
        connection = FakeConnection()
        repository = FakeRuntimeQueueRepository()
        stdout = StringIO()

        with (
            patch.object(runtime_queue_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(runtime_queue_ops, "PostgresConnection", return_value=connection),
            patch.object(runtime_queue_ops, "RuntimeQueueRepository", return_value=repository),
        ):
            exit_code = runtime_queue_ops.main(
                [
                    "prune-history",
                    "--execute",
                    "--keep-days",
                    "14",
                    "--keep-recent-per-type",
                    "256",
                    "--limit",
                    "5000",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(repository.preview_retention_calls, [])
        self.assertEqual(
            repository.prune_retention_calls,
            [{"keep_days": 14, "keep_recent_per_type": 256, "limit": 5000}],
        )
        payload = stdout.getvalue()
        self.assertIn('"mode": "execute"', payload)
        self.assertIn('"deleted_count": 2', payload)

    def test_enqueue_oa_sync_cli_writes_durable_event(self) -> None:
        connection = FakeConnection()
        repository = FakeRuntimeQueueRepository()
        stdout = StringIO()

        with (
            patch.object(runtime_queue_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(runtime_queue_ops, "PostgresConnection", return_value=connection),
            patch.object(runtime_queue_ops, "RuntimeQueueRepository", return_value=repository),
        ):
            exit_code = runtime_queue_ops.main(
                [
                    "enqueue-oa-sync",
                    "--scope",
                    "all",
                    "--reason",
                    "scheduled_oa_sync",
                    "--triggered-by",
                    "system",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            repository.enqueue_calls,
            [
                {
                    "event_type": "oa.sync",
                    "aggregate_type": "oa",
                    "aggregate_id": "all",
                    "scope_type": "oa",
                    "scope_key": "all",
                    "dedupe_key": "oa.sync:all",
                    "payload": {
                        "scope_key": "all",
                        "triggered_by": "system",
                        "reason": "scheduled_oa_sync",
                    },
                }
            ],
        )
        self.assertIn('"event_type": "oa.sync"', stdout.getvalue())

    def test_read_model_refresh_dry_run_validates_and_expands_registered_scopes(self) -> None:
        connection = FakeConnection()
        repository = FakeRuntimeQueueRepository()
        stdout = StringIO()

        with (
            patch.object(runtime_queue_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(runtime_queue_ops, "PostgresConnection", return_value=connection),
            patch.object(runtime_queue_ops, "RuntimeQueueRepository", return_value=repository),
        ):
            exit_code = runtime_queue_ops.main(
                [
                    "enqueue-read-model-refresh",
                    "--scope",
                    "workbench_relation=all",
                    "--dry-run",
                ],
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(
            payload["targets"],
            [
                {"scope_key": "all", "scope_type": "workbench_relation"},
            ],
        )
        self.assertEqual(repository.enqueue_read_model_refresh_calls, [])

    def test_read_model_refresh_rejects_retired_workbench_page_scope(self) -> None:
        with self.assertRaisesRegex(ReadModelScopeError, "Retired read model refresh scope_type"):
            runtime_queue_ops._normalize_read_model_refresh_targets(["workbench=all"])

    def test_read_model_refresh_execute_uses_gateway_and_durable_queue_repository(self) -> None:
        connection = FakeConnection()
        repository = FakeRuntimeQueueRepository()
        stdout = StringIO()

        with (
            patch.object(runtime_queue_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(runtime_queue_ops, "PostgresConnection", return_value=connection),
            patch.object(runtime_queue_ops, "RuntimeQueueRepository", return_value=repository),
        ):
            exit_code = runtime_queue_ops.main(
                [
                    "enqueue-read-model-refresh",
                    "--scope",
                    "turnover_ledger=all",
                    "--reason",
                    "phase19_audit_rebuild",
                    "--trace-id",
                    "phase19-production",
                    "--force-refresh",
                    "--execute",
                ],
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "execute")
        self.assertEqual(payload["enqueued_count"], 1)
        self.assertEqual(
            repository.enqueue_read_model_refresh_calls,
            [
                {
                    "scope_type": "turnover_ledger",
                    "scope_key": "all",
                    "reason": "phase19_audit_rebuild",
                    "priority": "high",
                    "trace_id": "phase19-production",
                    "metadata": {
                        "action_name": "production_audit_contract_rebuild",
                        "force_refresh": True,
                    },
                }
            ],
        )
        self.assertTrue(payload["force_refresh"])

    def test_release_stale_processing_dry_run_lists_candidates_without_update(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "workbench_relation.read_model.refresh",
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
            event_types=["workbench_relation.read_model.refresh"],
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
        self.assertEqual(params, (300, ["workbench_relation.read_model.refresh"], 25))

    def test_release_stale_processing_execute_uses_repository_boundary(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "workbench_relation.read_model.refresh",
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
            event_types=["workbench_relation.read_model.refresh"],
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
                    "event_types": ("workbench_relation.read_model.refresh",),
                }
            ],
        )

    def test_resolve_superseded_processing_dry_run_lists_candidates_without_update(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "workbench_relation.read_model.refresh",
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
            event_types=["workbench_relation.read_model.refresh"],
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
        self.assertEqual(params, (300, ["workbench_relation.read_model.refresh"], 25))

    def test_resolve_superseded_processing_execute_uses_repository_boundary(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "event_type": "workbench_relation.read_model.refresh",
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
            event_types=["workbench_relation.read_model.refresh"],
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
                    "event_types": ("workbench_relation.read_model.refresh",),
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

    def test_resolve_dead_letter_requires_fresh_readiness_and_no_active_dirty_scope(self) -> None:
        connection = FakeConnection(
            fetch_one_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "tenant_id": "default",
                    "event_type": "workbench_relation.read_model.refresh",
                    "scope_type": "workbench_relation",
                    "scope_key": "all",
                    "status": "dead_lettered",
                },
                {"fresh_count": 1, "latest_fresh_at": datetime(2026, 6, 4, 12, 10, tzinfo=timezone.utc)},
                {"done_count": 0, "latest_done_at": None},
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
        self.assertEqual(result["read_model_key"], "workbench_relation")
        self.assertEqual(
            repository.resolve_calls,
            [("00000000-0000-0000-0000-000000000001", "readiness_converged_obsolete_invalid_scope")],
        )
        readiness_sql, readiness_params = connection.fetch_one_calls[1]
        later_done_sql, later_done_params = connection.fetch_one_calls[2]
        dirty_sql, dirty_params = connection.fetch_one_calls[3]
        self.assertIn("read_model.app_status_readiness", " ".join(readiness_sql.lower().split()))
        self.assertIn("scope_key = %s", " ".join(readiness_sql.lower().split()))
        self.assertEqual(readiness_params, ("default", "workbench_relation", "workbench_relation", "all"))
        self.assertIn("status = 'done'", " ".join(later_done_sql.lower().split()))
        self.assertEqual(
            later_done_params,
            ("default", "workbench_relation.read_model.refresh", "workbench_relation", "all", "00000000-0000-0000-0000-000000000001", None),
        )
        self.assertIn("job.read_model_dirty_scopes", " ".join(dirty_sql.lower().split()))
        self.assertEqual(dirty_params, ("default", "workbench_relation", "all"))

    def test_resolve_dead_letter_refuses_when_dirty_scope_is_active(self) -> None:
        connection = FakeConnection(
            fetch_one_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "tenant_id": "default",
                    "event_type": "workbench_relation.read_model.refresh",
                    "scope_type": "workbench_relation",
                    "scope_key": "all",
                    "status": "dead_lettered",
                },
                {"fresh_count": 1, "latest_fresh_at": datetime(2026, 6, 4, 12, 10, tzinfo=timezone.utc)},
                {"done_count": 0, "latest_done_at": None},
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

    def test_resolve_dead_letter_refuses_when_exact_scope_is_not_covered(self) -> None:
        connection = FakeConnection(
            fetch_one_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "tenant_id": "default",
                    "event_type": "workbench_relation.read_model.refresh",
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-03",
                    "status": "dead_lettered",
                },
                {"fresh_count": 0, "latest_fresh_at": None},
                {"done_count": 0, "latest_done_at": None},
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

        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "coverage_not_proven")
        self.assertEqual(result["scope_key"], "2026-03")
        self.assertEqual(repository.resolve_calls, [])

    def test_resolve_covered_dead_letters_dry_run_lists_exact_scope_proof_without_update(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "tenant_id": "default",
                    "event_type": "workbench_relation.read_model.refresh",
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-03",
                    "status": "dead_lettered",
                    "updated_at": datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
                }
            ],
            fetch_one_rows=[
                {"fresh_count": 1, "latest_fresh_at": datetime(2026, 6, 4, 12, 10, tzinfo=timezone.utc)},
                {"done_count": 0, "latest_done_at": None},
                {"active_count": 0},
            ],
        )
        repository = FakeRuntimeQueueRepository()

        result = runtime_queue_ops._resolve_covered_dead_letters(
            connection,
            repository,  # type: ignore[arg-type]
            limit=25,
            reason="readiness_converged_obsolete_dead_letter",
            execute=False,
        )

        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["eligible_count"], 1)
        self.assertEqual(result["resolved_count"], 0)
        self.assertEqual(result["events"][0]["proof"]["covered_by"], ["fresh_readiness"])
        self.assertEqual(repository.resolve_calls, [])
        sql, params = connection.fetch_all_calls[0]
        self.assertIn("status = 'dead_lettered'", " ".join(sql.lower().split()))
        self.assertEqual(params, (25,))

    def test_resolve_covered_dead_letters_execute_resolves_only_eligible_events(self) -> None:
        connection = FakeConnection(
            fetch_all_rows=[
                {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "tenant_id": "default",
                    "event_type": "workbench_relation.read_model.refresh",
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-03",
                    "status": "dead_lettered",
                    "updated_at": datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
                },
                {
                    "event_id": "00000000-0000-0000-0000-000000000002",
                    "tenant_id": "default",
                    "event_type": "workbench_relation.read_model.refresh",
                    "scope_type": "workbench_relation",
                    "scope_key": "all",
                    "status": "dead_lettered",
                    "updated_at": datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
                },
            ],
            fetch_one_rows=[
                {"fresh_count": 1, "latest_fresh_at": datetime(2026, 6, 4, 12, 10, tzinfo=timezone.utc)},
                {"done_count": 0, "latest_done_at": None},
                {"active_count": 0},
                {"fresh_count": 0, "latest_fresh_at": None},
                {"done_count": 0, "latest_done_at": None},
                {"active_count": 0},
            ],
        )
        repository = FakeRuntimeQueueRepository()

        result = runtime_queue_ops._resolve_covered_dead_letters(
            connection,
            repository,  # type: ignore[arg-type]
            limit=100,
            reason="readiness_converged_obsolete_dead_letter",
            execute=True,
        )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["eligible_count"], 1)
        self.assertEqual(result["resolved_count"], 1)
        self.assertEqual(
            repository.resolve_calls,
            [("00000000-0000-0000-0000-000000000001", "readiness_converged_obsolete_dead_letter")],
        )
        self.assertTrue(result["events"][0]["resolved"])
        self.assertFalse(result["events"][1]["resolved"])
        self.assertEqual(result["events"][1]["reason"], "coverage_not_proven")


if __name__ == "__main__":
    unittest.main()
