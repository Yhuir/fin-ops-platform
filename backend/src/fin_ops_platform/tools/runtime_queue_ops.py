from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from fin_ops_platform.services.app_status_read_model_registry import read_model_by_refresh_event_type
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.read_model_scope_policy import DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY
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

    enqueue_read_model = subparsers.add_parser(
        "enqueue-read-model-refresh",
        help="Validate and enqueue read-model refreshes through the canonical gateway.",
    )
    enqueue_read_model.add_argument(
        "--scope",
        action="append",
        required=True,
        help="Repeatable scope_type=scope_key target.",
    )
    enqueue_read_model.add_argument("--reason", default="operator_audit_contract_rebuild")
    enqueue_read_model.add_argument("--tenant-id", default="default")
    enqueue_read_model.add_argument("--priority", choices=("low", "normal", "high"), default="high")
    enqueue_read_model.add_argument("--trace-id")
    enqueue_read_model_mode = enqueue_read_model.add_mutually_exclusive_group(required=True)
    enqueue_read_model_mode.add_argument("--dry-run", action="store_true")
    enqueue_read_model_mode.add_argument("--execute", action="store_true")

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
    if args.command == "enqueue-read-model-refresh":
        targets = _normalize_read_model_refresh_targets(args.scope)
        result = _enqueue_read_model_refreshes(
            repository,
            targets=targets,
            tenant_id=args.tenant_id,
            reason=args.reason,
            priority=args.priority,
            trace_id=args.trace_id,
            execute=args.execute,
        )
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


def _normalize_read_model_refresh_targets(raw_targets: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for raw_target in list(raw_targets or []):
        target = str(raw_target or "").strip()
        if "=" not in target:
            raise ValueError(f"Invalid read-model target {target!r}; expected scope_type=scope_key.")
        scope_type, scope_key = (part.strip() for part in target.split("=", 1))
        if not scope_type or not scope_key:
            raise ValueError(f"Invalid read-model target {target!r}; expected scope_type=scope_key.")
        grouped.setdefault(scope_type, []).append(scope_key)
    return {
        scope_type: DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY.normalize_and_validate(scope_type, scope_keys)
        for scope_type, scope_keys in grouped.items()
    }


def _enqueue_read_model_refreshes(
    repository: RuntimeQueueRepository,
    *,
    targets: dict[str, list[str]],
    tenant_id: str,
    reason: str,
    priority: str,
    trace_id: str | None,
    execute: bool,
) -> dict[str, object]:
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    normalized_reason = str(reason or "operator_audit_contract_rebuild").strip()
    normalized_trace_id = str(trace_id or "").strip() or None
    requested = [
        {"scope_type": scope_type, "scope_key": scope_key}
        for scope_type, scope_keys in targets.items()
        for scope_key in scope_keys
    ]
    if not execute:
        return {
            "mode": "dry-run",
            "tenant_id": normalized_tenant_id,
            "reason": normalized_reason,
            "priority": priority,
            "target_count": len(requested),
            "targets": requested,
            "event_ids": [],
        }

    gateway = ReadModelRefreshGateway(queue_repository=repository)
    events: list[object] = []
    for scope_type, scope_keys in targets.items():
        events.extend(
            gateway.enqueue_many_events(
                scope_type,
                scope_keys,
                reason=normalized_reason,
                tenant_id=normalized_tenant_id,
                priority=priority,
                trace_id=normalized_trace_id,
                metadata={"action_name": "production_audit_contract_rebuild"},
            )
        )
    return {
        "mode": "execute",
        "tenant_id": normalized_tenant_id,
        "reason": normalized_reason,
        "priority": priority,
        "target_count": len(requested),
        "targets": requested,
        "enqueued_count": len(events),
        "event_ids": [str(getattr(event, "event_id", "")) for event in events],
    }


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


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
