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

    resolve_covered = subparsers.add_parser(
        "resolve-covered-dead-letters",
        help="Dry-run or resolve read-model dead-letters that have exact-scope fresh/done proof.",
    )
    resolve_covered.add_argument("--limit", type=int, default=100)
    resolve_covered.add_argument("--reason", default="readiness_converged_obsolete_dead_letter")
    resolve_covered_mode = resolve_covered.add_mutually_exclusive_group(required=True)
    resolve_covered_mode.add_argument("--dry-run", action="store_true")
    resolve_covered_mode.add_argument("--execute", action="store_true")

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
    if args.command == "resolve-covered-dead-letters":
        result = _resolve_covered_dead_letters(
            connection,
            repository,
            limit=args.limit,
            reason=args.reason,
            execute=args.execute,
        )
        print(json.dumps(result, default=str, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0
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
    eligibility = _dead_letter_resolution_eligibility(connection, event)
    if not eligibility.get("eligible"):
        return {"event_id": event_id, "resolved": False, **eligibility}
    resolved = repository.resolve_dead_letter_event(event_id, reason=reason)
    return {
        "event_id": event_id,
        "resolved": resolved,
        "reason": reason if resolved else "update_did_not_match",
        "event_type": event.get("event_type"),
        "read_model_key": definition.key,
        "scope_type": eligibility.get("scope_type"),
        "scope_key": eligibility.get("scope_key"),
        "covered_by": eligibility.get("covered_by"),
    }


def _resolve_covered_dead_letters(
    connection: PostgresConnection,
    repository: RuntimeQueueRepository,
    *,
    limit: int,
    reason: str,
    execute: bool,
) -> dict[str, Any]:
    rows = _dead_letter_read_model_events(connection, limit=limit)
    events: list[dict[str, Any]] = []
    eligible_count = 0
    resolved_count = 0
    for row in rows:
        eligibility = _dead_letter_resolution_eligibility(connection, row)
        eligible = bool(eligibility.get("eligible"))
        if eligible:
            eligible_count += 1
        resolved = False
        if execute and eligible:
            resolved = repository.resolve_dead_letter_event(str(row.get("event_id") or ""), reason=reason)
            if resolved:
                resolved_count += 1
        events.append(
            {
                "event_id": row.get("event_id"),
                "event_type": row.get("event_type"),
                "scope_type": row.get("scope_type"),
                "scope_key": row.get("scope_key"),
                "updated_at": row.get("updated_at"),
                "eligible": eligible,
                "resolved": resolved,
                "reason": reason if resolved else eligibility.get("reason"),
                "proof": eligibility,
            }
        )
    return {
        "mode": "execute" if execute else "dry-run",
        "candidate_count": len(rows),
        "eligible_count": eligible_count,
        "resolved_count": resolved_count,
        "reason": reason,
        "events": events,
    }


def _dead_letter_read_model_events(connection: PostgresConnection, *, limit: int) -> list[dict[str, Any]]:
    return list(
        connection.fetch_all(
            """
            select
              id::text as event_id,
              tenant_id,
              event_type,
              scope_type,
              scope_key,
              source_version,
              status,
              attempts,
              last_error,
              created_at,
              updated_at,
              processed_at,
              dead_lettered_at
            from job.outbox_events
            where status = 'dead_lettered'
              and event_type like '%%.read_model.refresh'
            order by updated_at, created_at, id
            limit %s
            """,
            (max(1, int(limit)),),
        )
    )


def _dead_letter_resolution_eligibility(connection: PostgresConnection, event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "")
    definition = read_model_by_refresh_event_type().get(event_type)
    if definition is None:
        return {"eligible": False, "reason": "event_type_not_read_model", "event_type": event_type}
    tenant_id = str(event.get("tenant_id") or "default")
    scope_type = str(event.get("scope_type") or definition.scope_type or "").strip()
    scope_key = str(event.get("scope_key") or event.get("aggregate_id") or "").strip()
    if not scope_type or not scope_key:
        return {
            "eligible": False,
            "reason": "scope_missing",
            "read_model_key": definition.key,
            "scope_type": scope_type,
            "scope_key": scope_key,
        }
    readiness = connection.fetch_one(
        """
        select count(*)::integer as fresh_count, max(updated_at) as latest_fresh_at
        from read_model.app_status_readiness
        where tenant_id = %s
          and read_model_key = %s
          and scope_type = %s
          and scope_key = %s
          and status = 'fresh'
        """,
        (tenant_id, definition.key, scope_type, scope_key),
    )
    later_done = connection.fetch_one(
        """
        select count(*)::integer as done_count, max(updated_at) as latest_done_at
        from job.outbox_events
        where tenant_id = %s
          and event_type = %s
          and scope_type = %s
          and scope_key = %s
          and status = 'done'
          and id <> %s::uuid
          and updated_at > coalesce(%s::timestamptz, '-infinity'::timestamptz)
        """,
        (tenant_id, event_type, scope_type, scope_key, event.get("event_id"), event.get("updated_at")),
    )
    dirty = connection.fetch_one(
        """
        select count(*)::integer as active_count
        from job.read_model_dirty_scopes
        where tenant_id = %s
          and scope_type = %s
          and scope_key = %s
          and status in ('pending', 'processing', 'failed')
        """,
        (tenant_id, scope_type, scope_key),
    )
    fresh_count = _int_value((readiness or {}).get("fresh_count"))
    later_done_count = _int_value((later_done or {}).get("done_count"))
    active_dirty_count = _int_value((dirty or {}).get("active_count"))
    covered_by = []
    if fresh_count > 0:
        covered_by.append("fresh_readiness")
    if later_done_count > 0:
        covered_by.append("later_done")
    result = {
        "eligible": active_dirty_count <= 0 and bool(covered_by),
        "reason": "eligible" if active_dirty_count <= 0 and covered_by else "coverage_not_proven",
        "read_model_key": definition.key,
        "scope_type": scope_type,
        "scope_key": scope_key,
        "fresh_count": fresh_count,
        "latest_fresh_at": (readiness or {}).get("latest_fresh_at"),
        "later_done_count": later_done_count,
        "latest_done_at": (later_done or {}).get("latest_done_at"),
        "active_dirty_count": active_dirty_count,
        "covered_by": covered_by,
    }
    if active_dirty_count > 0:
        result["reason"] = "active_dirty_scope_exists"
    return result


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
