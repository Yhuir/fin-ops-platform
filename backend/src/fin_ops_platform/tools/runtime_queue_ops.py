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

    stale_processing = subparsers.add_parser(
        "release-stale-processing",
        help="Dry-run or release PostgreSQL processing events whose lock exceeded the runtime lock timeout.",
    )
    stale_processing.add_argument("--stale-after-seconds", type=int, default=300)
    stale_processing.add_argument("--limit", type=int, default=100)
    stale_processing.add_argument("--event-type", action="append", default=[])
    stale_processing.add_argument("--reason", default="operator_stale_processing_release")
    stale_processing_mode = stale_processing.add_mutually_exclusive_group(required=True)
    stale_processing_mode.add_argument("--dry-run", action="store_true")
    stale_processing_mode.add_argument("--execute", action="store_true")

    superseded_processing = subparsers.add_parser(
        "resolve-superseded-processing",
        help="Dry-run or resolve stale processing events covered by a newer same-dedupe event.",
    )
    superseded_processing.add_argument("--stale-after-seconds", type=int, default=300)
    superseded_processing.add_argument("--limit", type=int, default=100)
    superseded_processing.add_argument("--event-type", action="append", default=[])
    superseded_processing.add_argument("--reason", default="operator_superseded_processing_resolution")
    superseded_processing_mode = superseded_processing.add_mutually_exclusive_group(required=True)
    superseded_processing_mode.add_argument("--dry-run", action="store_true")
    superseded_processing_mode.add_argument("--execute", action="store_true")

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
    if args.command == "replay-unpublished":
        result = _replay_unpublished(connection, limit=args.limit, execute=args.execute)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0
    if args.command == "release-stale-processing":
        result = _release_stale_processing(
            connection,
            repository,
            stale_after_seconds=args.stale_after_seconds,
            limit=args.limit,
            event_types=args.event_type,
            reason=args.reason,
            execute=args.execute,
        )
        print(json.dumps(result, default=str, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0
    if args.command == "resolve-superseded-processing":
        result = _resolve_superseded_processing(
            connection,
            repository,
            stale_after_seconds=args.stale_after_seconds,
            limit=args.limit,
            event_types=args.event_type,
            reason=args.reason,
            execute=args.execute,
        )
        print(json.dumps(result, default=str, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
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


def _release_stale_processing(
    connection: PostgresConnection,
    repository: RuntimeQueueRepository,
    *,
    stale_after_seconds: int,
    limit: int,
    event_types: Sequence[str],
    reason: str,
    execute: bool,
) -> dict[str, Any]:
    normalized_event_types = [str(event_type).strip() for event_type in event_types if str(event_type).strip()]
    candidates = _stale_processing_events(
        connection,
        stale_after_seconds=stale_after_seconds,
        limit=limit,
        event_types=normalized_event_types,
    )
    released: list[dict[str, Any]] = []
    if execute and candidates:
        released = repository.release_stale_processing_events(
            stale_after_seconds=stale_after_seconds,
            limit=limit,
            reason=reason,
            event_types=normalized_event_types,
        )
    return {
        "mode": "execute" if execute else "dry-run",
        "candidate_count": len(candidates),
        "released_count": len(released),
        "stale_after_seconds": max(1, int(stale_after_seconds)),
        "event_types": list(normalized_event_types),
        "reason": reason,
        "events": released if execute else candidates,
    }


def _stale_processing_events(
    connection: PostgresConnection,
    *,
    stale_after_seconds: int,
    limit: int,
    event_types: Sequence[str],
) -> list[dict[str, Any]]:
    normalized_stale_after_seconds = max(1, int(stale_after_seconds))
    normalized_limit = max(1, int(limit))
    normalized_event_types = [str(event_type).strip() for event_type in event_types if str(event_type).strip()]
    event_type_filter = ""
    params: tuple[Any, ...]
    if normalized_event_types:
        event_type_filter = "and stale.event_type = any(%s)"
        params = (normalized_stale_after_seconds, normalized_event_types, normalized_limit)
    else:
        params = (normalized_stale_after_seconds, normalized_limit)
    return list(
        connection.fetch_all(
            f"""
            with ranked as (
              select
                id,
                row_number() over (
                  partition by tenant_id, coalesce(dedupe_key, id::text)
                  order by coalesce(source_version, 0) desc, created_at desc, id desc
                ) as dedupe_rank,
                locked_at,
                created_at
              from job.outbox_events stale
              where status = 'processing'
                and locked_at < now() - (%s * interval '1 second')
                {event_type_filter}
                and not exists (
                  select 1
                  from job.outbox_events pending
                  where pending.tenant_id = stale.tenant_id
                    and pending.dedupe_key = stale.dedupe_key
                    and pending.status = 'pending'
                    and stale.dedupe_key is not null
                )
            )
            select
              event.id::text as event_id,
              event.tenant_id,
              event.event_type,
              event.scope_type,
              event.scope_key,
              event.dedupe_key,
              event.source_version,
              event.priority,
              event.status,
              event.attempts,
              event.last_error,
              event.locked_by,
              event.locked_at,
              round(extract(epoch from now() - event.locked_at))::integer as locked_age_seconds,
              event.created_at,
              event.updated_at
            from ranked
            join job.outbox_events event on event.id = ranked.id
            where ranked.dedupe_rank = 1
            order by ranked.locked_at nulls first, ranked.created_at, ranked.id
            limit %s
            """,
            params,
        )
    )


def _resolve_superseded_processing(
    connection: PostgresConnection,
    repository: RuntimeQueueRepository,
    *,
    stale_after_seconds: int,
    limit: int,
    event_types: Sequence[str],
    reason: str,
    execute: bool,
) -> dict[str, Any]:
    normalized_event_types = [str(event_type).strip() for event_type in event_types if str(event_type).strip()]
    candidates = _superseded_processing_events(
        connection,
        stale_after_seconds=stale_after_seconds,
        limit=limit,
        event_types=normalized_event_types,
    )
    resolved: list[dict[str, Any]] = []
    if execute and candidates:
        resolved = repository.resolve_superseded_processing_events(
            stale_after_seconds=stale_after_seconds,
            limit=limit,
            reason=reason,
            event_types=normalized_event_types,
        )
    return {
        "mode": "execute" if execute else "dry-run",
        "candidate_count": len(candidates),
        "resolved_count": len(resolved),
        "stale_after_seconds": max(1, int(stale_after_seconds)),
        "event_types": list(normalized_event_types),
        "reason": reason,
        "events": resolved if execute else candidates,
    }


def _superseded_processing_events(
    connection: PostgresConnection,
    *,
    stale_after_seconds: int,
    limit: int,
    event_types: Sequence[str],
) -> list[dict[str, Any]]:
    normalized_stale_after_seconds = max(1, int(stale_after_seconds))
    normalized_limit = max(1, int(limit))
    normalized_event_types = [str(event_type).strip() for event_type in event_types if str(event_type).strip()]
    event_type_filter = ""
    params: tuple[Any, ...]
    if normalized_event_types:
        event_type_filter = "and stale.event_type = any(%s)"
        params = (normalized_stale_after_seconds, normalized_event_types, normalized_limit)
    else:
        params = (normalized_stale_after_seconds, normalized_limit)
    return list(
        connection.fetch_all(
            f"""
            select
              stale.id::text as event_id,
              stale.tenant_id,
              stale.event_type,
              stale.scope_type,
              stale.scope_key,
              stale.dedupe_key,
              stale.source_version,
              stale.priority,
              stale.status,
              stale.attempts,
              stale.last_error,
              stale.locked_by,
              stale.locked_at,
              round(extract(epoch from now() - stale.locked_at))::integer as locked_age_seconds,
              cover.id::text as covered_by_event_id,
              cover.status as covered_by_status,
              cover.source_version as covered_by_source_version,
              stale.created_at,
              stale.updated_at
            from job.outbox_events stale
            join lateral (
              select newer.id, newer.status, newer.source_version
              from job.outbox_events newer
              where newer.tenant_id = stale.tenant_id
                and newer.dedupe_key = stale.dedupe_key
                and newer.id <> stale.id
                and newer.status in ('pending', 'processing', 'done')
                and stale.dedupe_key is not null
                and coalesce(newer.source_version, 0) >= coalesce(stale.source_version, 0)
                and (
                  newer.created_at > stale.created_at
                  or (newer.created_at = stale.created_at and newer.id > stale.id)
                )
              order by coalesce(newer.source_version, 0) desc, newer.created_at desc, newer.id desc
              limit 1
            ) cover on true
            where stale.status = 'processing'
              and stale.locked_at < now() - (%s * interval '1 second')
              {event_type_filter}
            order by stale.locked_at nulls first, stale.created_at, stale.id
            limit %s
            """,
            params,
        )
    )


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
