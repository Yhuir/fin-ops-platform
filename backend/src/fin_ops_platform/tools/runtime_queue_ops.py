from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

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
        print(json.dumps({"event": row}, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0 if row else 1
    if args.command == "requeue":
        updated = repository.requeue_event(args.event_id, reason=args.reason)
        print(json.dumps({"event_id": args.event_id, "requeued": updated}, ensure_ascii=False, sort_keys=True), file=stdout)
        return 0 if updated else 1
    if args.command == "republish":
        updated = repository.reset_publish_state(args.event_id, reason=args.reason)
        print(json.dumps({"event_id": args.event_id, "republish_requested": updated}, ensure_ascii=False, sort_keys=True), file=stdout)
        return 0 if updated else 1
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
          scope_type,
          scope_key,
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


if __name__ == "__main__":
    raise SystemExit(main())
