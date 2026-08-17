from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the PostgreSQL runtime queue.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect a PostgreSQL outbox event by event_id.")
    inspect.add_argument("--event-id", required=True)

    requeue = subparsers.add_parser("requeue", help="Requeue failed/dead-lettered PostgreSQL event.")
    requeue.add_argument("--event-id", required=True)
    requeue.add_argument("--reason", default="operator_repair")

    resolve = subparsers.add_parser("resolve-dead-letter", help="Resolve one obsolete dead-letter event by id.")
    resolve.add_argument("--event-id", required=True)
    resolve.add_argument("--reason", default="operator_resolved")

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

    prune_history = subparsers.add_parser(
        "prune-history",
        help="Dry-run or delete completed runtime queue history under the controlled retention policy.",
    )
    prune_history.add_argument("--keep-days", type=int, default=30)
    prune_history.add_argument("--keep-recent-per-type", type=int, default=512)
    prune_history.add_argument("--limit", type=int, default=20_000)
    prune_history_mode = prune_history.add_mutually_exclusive_group(required=True)
    prune_history_mode.add_argument("--dry-run", action="store_true")
    prune_history_mode.add_argument("--execute", action="store_true")

    enqueue_oa_sync = subparsers.add_parser("enqueue-oa-sync", help="Enqueue a durable OA Mongo projection sync event.")
    enqueue_oa_sync.add_argument("--scope", default="all")
    enqueue_oa_sync.add_argument("--reason", default="scheduled_oa_sync")
    enqueue_oa_sync.add_argument("--triggered-by", default="system")

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
    if args.command == "resolve-dead-letter":
        result = _resolve_dead_letter(connection, repository, event_id=args.event_id, reason=args.reason)
        print(json.dumps(result, default=str, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0 if result.get("resolved") else 1
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
    if args.command == "prune-history":
        if args.execute:
            result = repository.prune_runtime_queue_history(
                keep_days=args.keep_days,
                keep_recent_per_type=args.keep_recent_per_type,
                limit=args.limit,
            )
        else:
            result = repository.preview_runtime_queue_history_retention(
                keep_days=args.keep_days,
                keep_recent_per_type=args.keep_recent_per_type,
                limit=args.limit,
            )
        print(json.dumps(result, default=str, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0
    if args.command == "enqueue-oa-sync":
        scope_key = str(args.scope or "all").strip() or "all"
        event = repository.enqueue(
            event_type="oa.sync",
            aggregate_type="oa",
            aggregate_id=scope_key,
            scope_type="oa",
            scope_key=scope_key,
            dedupe_key=f"oa.sync:{scope_key}",
            payload={
                "scope_key": scope_key,
                "triggered_by": str(args.triggered_by or "system"),
                "reason": str(args.reason or "scheduled_oa_sync"),
            },
        )
        print(
            json.dumps(
                {
                    "event_id": getattr(event, "event_id", None),
                    "event_type": "oa.sync",
                    "scope_key": scope_key,
                    "status": getattr(event, "status", None),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=stdout,
        )
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
    resolved = repository.resolve_dead_letter_event(event_id, reason=reason)
    return {
        "event_id": event_id,
        "resolved": resolved,
        "reason": reason if resolved else "update_did_not_match",
        "event_type": event.get("event_type"),
    }


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


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
