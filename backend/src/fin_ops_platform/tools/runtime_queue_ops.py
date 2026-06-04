from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from fin_ops_platform.services.app_status_read_model_registry import read_model_by_refresh_event_type
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository


CONTROL_KEY = "runtime:rabbitmq_control"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate PostgreSQL runtime queue and RabbitMQ publish state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect a PostgreSQL outbox event by event_id.")
    inspect.add_argument("--event-id", required=True)

    requeue = subparsers.add_parser("requeue", help="Requeue failed/dead-lettered PostgreSQL event.")
    requeue.add_argument("--event-id", required=True)
    requeue.add_argument("--reason", default="operator_repair")

    resolve = subparsers.add_parser("resolve-dead-letter", help="Resolve an obsolete read-model dead-letter after readiness has converged.")
    resolve.add_argument("--event-id", required=True)
    resolve.add_argument("--reason", default="operator_resolved")

    republish = subparsers.add_parser("republish", help="Mark a pending event as unpublished for RabbitMQ redispatch.")
    republish.add_argument("--event-id", required=True)
    republish.add_argument("--reason", default="operator_republish")

    replay = subparsers.add_parser("replay-unpublished", help="Inspect or reset unpublished/failed RabbitMQ publish backlog.")
    replay.add_argument("--limit", type=int, default=100)
    mode = replay.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")

    for command in ("pause-dispatcher", "resume-dispatcher", "pause-consumer", "resume-consumer"):
        subparsers.add_parser(command, help=f"{command.replace('-', ' ')} via app.app_settings control flag.")

    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    repository = RuntimeQueueRepository(connection)

    if args.command == "inspect":
        row = _inspect_event(connection, args.event_id)
        print(json.dumps({"event": row}, default=str, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0 if row else 1
    if args.command == "requeue":
        updated = repository.requeue_event(args.event_id, reason=args.reason)
        print(json.dumps({"event_id": args.event_id, "requeued": updated}, ensure_ascii=False, sort_keys=True), file=stdout)
        return 0 if updated else 1
    if args.command == "republish":
        updated = repository.reset_publish_state(args.event_id, reason=args.reason)
        print(json.dumps({"event_id": args.event_id, "republish_requested": updated}, ensure_ascii=False, sort_keys=True), file=stdout)
        return 0 if updated else 1
    if args.command == "resolve-dead-letter":
        result = _resolve_dead_letter(connection, repository, event_id=args.event_id, reason=args.reason)
        print(json.dumps(result, default=str, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0 if result.get("resolved") else 1
    if args.command == "replay-unpublished":
        result = _replay_unpublished(connection, limit=args.limit, execute=args.execute)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0
    if args.command in {"pause-dispatcher", "resume-dispatcher", "pause-consumer", "resume-consumer"}:
        component = "dispatcher" if "dispatcher" in args.command else "consumer"
        paused = args.command.startswith("pause")
        result = _set_control_flag(connection, component=component, paused=paused)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), file=stdout)
        return 0

    print(f"unsupported command: {args.command}", file=stderr)
    return 2


def _inspect_event(connection: PostgresConnection, event_id: str) -> dict[str, Any] | None:
    return connection.fetch_one(
        """
        select
          id::text as event_id,
          tenant_id,
          event_type,
          aggregate_type,
          aggregate_id,
          scope_type,
          scope_key,
          dedupe_key,
          payload,
          source_version,
          priority,
          status,
          attempts,
          last_error,
          available_at,
          locked_by,
          locked_at,
          trace_id,
          publish_status,
          publish_attempt_count,
          publish_last_error,
          next_publish_at,
          publish_locked_by,
          publish_locked_at,
          rabbitmq_exchange,
          rabbitmq_routing_key,
          rabbitmq_message_id,
          published_at,
          publish_confirmed_at,
          created_at,
          updated_at,
          processed_at,
          dead_lettered_at
        from job.outbox_events
        where id = %s
        """,
        (event_id,),
    )


def _resolve_dead_letter(
    connection: PostgresConnection,
    repository: RuntimeQueueRepository,
    *,
    event_id: str,
    reason: str,
) -> dict[str, Any]:
    event = _inspect_event(connection, event_id)
    if not event:
        return {"event_id": event_id, "resolved": False, "reason": "event_not_found"}
    if event.get("status") != "dead_lettered":
        return {"event_id": event_id, "resolved": False, "reason": "event_not_dead_lettered", "status": event.get("status")}
    definition = read_model_by_refresh_event_type().get(str(event.get("event_type") or ""))
    if definition is None:
        return {"event_id": event_id, "resolved": False, "reason": "event_type_not_read_model", "event_type": event.get("event_type")}
    readiness = connection.fetch_one(
        """
        select count(*)::integer as fresh_count
        from read_model.app_status_readiness
        where tenant_id = %s
          and read_model_key = %s
          and status = 'fresh'
        """,
        (str(event.get("tenant_id") or "default"), definition.key),
    )
    fresh_count = _int_value((readiness or {}).get("fresh_count"))
    if fresh_count <= 0:
        return {
            "event_id": event_id,
            "resolved": False,
            "reason": "readiness_not_fresh",
            "read_model_key": definition.key,
        }
    dirty = connection.fetch_one(
        """
        select count(*)::integer as active_count
        from job.read_model_dirty_scopes
        where tenant_id = %s
          and scope_type = %s
          and status in ('pending', 'processing', 'failed')
        """,
        (str(event.get("tenant_id") or "default"), definition.scope_type),
    )
    active_dirty_count = _int_value((dirty or {}).get("active_count"))
    if active_dirty_count > 0:
        return {
            "event_id": event_id,
            "resolved": False,
            "reason": "active_dirty_scope_exists",
            "read_model_key": definition.key,
            "active_dirty_count": active_dirty_count,
        }
    resolved = repository.resolve_dead_letter_event(event_id, reason=reason)
    return {
        "event_id": event_id,
        "resolved": resolved,
        "reason": reason if resolved else "update_did_not_match",
        "event_type": event.get("event_type"),
        "read_model_key": definition.key,
    }


def _replay_unpublished(connection: PostgresConnection, *, limit: int, execute: bool) -> dict[str, Any]:
    rows = connection.fetch_all(
        """
        select id::text as event_id, event_type, scope_type, scope_key, publish_status, publish_last_error
        from job.outbox_events
        where status = 'pending'
          and publish_status in ('unpublished', 'failed')
        order by next_publish_at, available_at, created_at, id
        limit %s
        """,
        (max(1, int(limit)),),
    )
    if not execute:
        return {"mode": "dry-run", "candidate_count": len(rows), "events": rows}
    updated = connection.execute(
        """
        update job.outbox_events
        set
            publish_status = 'unpublished',
            publish_last_error = null,
            next_publish_at = now(),
            publish_locked_by = null,
            publish_locked_at = null,
            updated_at = now()
        where id = any(%s::uuid[])
        """,
        ([row["event_id"] for row in rows],),
    )
    return {"mode": "execute", "candidate_count": len(rows), "updated": updated, "events": rows}


def _set_control_flag(connection: PostgresConnection, *, component: str, paused: bool) -> dict[str, Any]:
    payload = {f"{component}_paused": paused}
    connection.execute(
        """
        insert into app.app_settings(settings_key, settings_payload, raw_payload, updated_at)
        values (%s, %s, %s, now())
        on conflict (settings_key) do update set
            settings_payload = app.app_settings.settings_payload || excluded.settings_payload,
            raw_payload = jsonb_build_object('normalized_payload', app.app_settings.settings_payload || excluded.settings_payload),
            updated_at = now()
        """,
        (CONTROL_KEY, _jsonb(connection, payload), _jsonb(connection, {"normalized_payload": payload})),
    )
    return {"settings_key": CONTROL_KEY, f"{component}_paused": paused}


def _jsonb(connection: PostgresConnection, payload: dict[str, Any]) -> Any:
    if isinstance(connection, PostgresConnection):
        from psycopg.types.json import Jsonb

        return Jsonb(payload)
    return payload


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
