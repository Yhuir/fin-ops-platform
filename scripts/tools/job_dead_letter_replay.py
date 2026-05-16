#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from typing import Any
from uuid import UUID


OUTBOX_REPLAY_SQL = """
with source_dead_letter as (
  select dl.*, e.aggregate_type, e.aggregate_id, e.event_type, e.subject, e.payload as event_payload,
         e.idempotency_key as event_idempotency_key, e.trace_id, e.created_by
  from job.dead_letters dl
  join job.outbox_events e on e.id = dl.source_id
  where dl.id = %s
    and dl.source_kind = 'outbox'
    and dl.replay_status = 'open'
  for update of dl
),
new_event as (
  insert into job.outbox_events (
    aggregate_type,
    aggregate_id,
    event_type,
    subject,
    payload,
    status,
    idempotency_key,
    trace_id,
    created_by,
    available_at
  )
  select
    aggregate_type,
    aggregate_id,
    event_type,
    subject,
    jsonb_set(
      event_payload,
      '{replay}',
      jsonb_build_object('dead_letter_id', id::text, 'operator_id', %s, 'reason', %s),
      true
    ),
    'pending',
    event_idempotency_key || ':replay:' || left(id::text, 8),
    trace_id,
    created_by,
    now()
  from source_dead_letter
  returning id
),
updated_dead_letter as (
  update job.dead_letters dl
  set replay_status = 'replayed',
      replayed_by = %s,
      replayed_at = now()
  from source_dead_letter source
  where dl.id = source.id
  returning dl.id
),
audit_insert as (
  insert into audit.events (
    event_type,
    action,
    entity_type,
    entity_id,
    actor_id,
    actor_type,
    source_type,
    source_id,
    metadata
  )
  select
    'job.dead_letter_replayed',
    'dead_letter_replay',
    'job.dead_letter',
    source.id,
    %s,
    'user',
    'job_dead_letter_replay',
    (select id::text from new_event),
    jsonb_build_object(
      'source_kind', source.source_kind,
      'source_id', source.source_id::text,
      'new_outbox_event_id', (select id::text from new_event),
      'reason', %s,
      'result', 'outbox_event_created'
    )
  from source_dead_letter source
  returning id
)
select
  (select id::text from new_event) as new_outbox_event_id,
  null::text as new_worker_task_id,
  (select count(*) from updated_dead_letter) as replayed_count
"""


WORKER_REPLAY_SQL = """
with source_dead_letter as (
  select
    dl.*,
    coalesce(nullif(dl.payload->>'task_id', '')::uuid, dl.source_id) as original_task_id
  from job.dead_letters dl
  where dl.id = %s
    and dl.source_kind in ('worker_task', 'nats_message')
    and dl.replay_status = 'open'
  for update
),
source_task as (
  select t.*, source.id as dead_letter_id, source.payload as dead_letter_payload, source.source_kind
  from source_dead_letter source
  join job.worker_tasks t on t.id = source.original_task_id
),
new_task as (
  insert into job.worker_tasks (
    task_type,
    status,
    phase,
    priority,
    idempotency_key,
    owner_user_id,
    visibility,
    label,
    source,
    payload,
    affected_scopes,
    affected_months,
    total_count,
    max_attempts,
    available_at,
    created_by
  )
  select
    task_type,
    'queued',
    'queued',
    priority,
    idempotency_key || ':replay:' || left(dead_letter_id::text, 8),
    owner_user_id,
    visibility,
    label || ' replay',
    source,
    payload,
    affected_scopes,
    affected_months,
    total_count,
    max_attempts,
    now(),
    created_by
  from source_task
  returning id, task_type, idempotency_key, source, payload, owner_user_id
),
event_seed as (
  select gen_random_uuid() as id
),
new_event as (
  insert into job.outbox_events (
    id,
    aggregate_type,
    aggregate_id,
    event_type,
    subject,
    payload,
    status,
    idempotency_key,
    trace_id,
    created_by,
    available_at
  )
  select
    event_seed.id,
    'worker_task',
    new_task.id,
    new_task.task_type || '.replay_requested',
    'finops.jobs.' || new_task.task_type,
    jsonb_set(
      jsonb_set(
        jsonb_set(
          coalesce(source_task.dead_letter_payload, '{}'::jsonb),
          '{task_id}',
          to_jsonb(new_task.id::text),
          true
        ),
        '{message_id}',
        to_jsonb(event_seed.id::text),
        true
      ),
      '{idempotency_key}',
      to_jsonb(new_task.idempotency_key),
      true
    ),
    'pending',
    new_task.idempotency_key,
    coalesce(source_task.dead_letter_payload->>'trace_id', null),
    new_task.owner_user_id,
    now()
  from source_task, new_task, event_seed
  returning id
),
updated_dead_letter as (
  update job.dead_letters dl
  set replay_status = 'replayed',
      replayed_by = %s,
      replayed_at = now()
  from source_dead_letter source
  where dl.id = source.id
  returning dl.id
),
audit_insert as (
  insert into audit.events (
    event_type,
    action,
    entity_type,
    entity_id,
    actor_id,
    actor_type,
    source_type,
    source_id,
    metadata
  )
  select
    'job.dead_letter_replayed',
    'dead_letter_replay',
    'job.dead_letter',
    source.id,
    %s,
    'user',
    'job_dead_letter_replay',
    (select id::text from new_event),
    jsonb_build_object(
      'source_kind', source.source_kind,
      'source_id', source.source_id::text,
      'new_worker_task_id', (select id::text from new_task),
      'new_outbox_event_id', (select id::text from new_event),
      'reason', %s,
      'result', 'worker_task_and_outbox_event_created'
    )
  from source_dead_letter source
  returning id
)
select
  (select id::text from new_event) as new_outbox_event_id,
  (select id::text from new_task) as new_worker_task_id,
  (select count(*) from updated_dead_letter) as replayed_count
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="List or replay PostgreSQL job.dead_letters without exposing secrets.")
    parser.add_argument("action", choices=["list", "replay"])
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--dead-letter-id")
    parser.add_argument("--task-id", help="Filter worker_task/nats_message dead letters by task id.")
    parser.add_argument("--event-id", help="Filter outbox dead letters by outbox event id or payload source.event_id.")
    parser.add_argument("--source-kind", choices=["outbox", "worker_task", "nats_message"])
    parser.add_argument("--operator-id", "--operator", "--replayed-by", dest="operator_id")
    parser.add_argument("--reason")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required.")
    try:
        import psycopg  # type: ignore[import-not-found]
        from psycopg.rows import dict_row  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("psycopg is required for dead-letter replay.") from exc

    with psycopg.connect(args.database_url, row_factory=dict_row) as connection:
        if args.action == "list":
            return list_dead_letters(
                connection,
                limit=args.limit,
                dead_letter_id=args.dead_letter_id,
                task_id=args.task_id,
                event_id=args.event_id,
                source_kind=args.source_kind,
            )
        if not args.operator_id:
            raise SystemExit("--operator-id is required for replay.")
        if not args.reason or not args.reason.strip():
            raise SystemExit("--reason is required for replay.")
        return replay_dead_letters(
            connection,
            operator_id=args.operator_id,
            reason=args.reason.strip(),
            limit=args.limit,
            dead_letter_id=args.dead_letter_id,
            task_id=args.task_id,
            event_id=args.event_id,
            source_kind=args.source_kind,
        )


def list_dead_letters(
    connection: Any,
    *,
    limit: int,
    dead_letter_id: str | None = None,
    task_id: str | None = None,
    event_id: str | None = None,
    source_kind: str | None = None,
) -> int:
    rows = connection.execute(
        _select_dead_letters_sql(),
        _filter_params(dead_letter_id=dead_letter_id, task_id=task_id, event_id=event_id, source_kind=source_kind)
        + (max(1, min(int(limit), 500)),),
    ).fetchall()
    print(json.dumps(rows, ensure_ascii=False, default=str, indent=2))
    return 0


def replay_dead_letters(
    connection: Any,
    *,
    operator_id: str,
    reason: str,
    limit: int,
    dead_letter_id: str | None = None,
    task_id: str | None = None,
    event_id: str | None = None,
    source_kind: str | None = None,
) -> int:
    operator_uuid = UUID(operator_id)
    rows = connection.execute(
        _select_dead_letters_sql(),
        _filter_params(dead_letter_id=dead_letter_id, task_id=task_id, event_id=event_id, source_kind=source_kind)
        + (max(1, min(int(limit), 500)),),
    ).fetchall()
    replayed: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    with connection.transaction():
        for row in rows:
            source = row["source_kind"]
            sql = build_replay_sql(source)
            if source == "outbox":
                params = (row["id"], str(operator_uuid), reason, operator_uuid, str(operator_uuid), reason)
            elif source in {"worker_task", "nats_message"}:
                params = (row["id"], operator_uuid, str(operator_uuid), reason)
            else:
                skipped.append({"dead_letter_id": row["id"], "source_kind": source, "result": "unsupported_source_kind"})
                continue
            result = connection.execute(sql, params).fetchone()
            if result and int(result["replayed_count"] or 0) == 1:
                replayed.append(
                    {
                        "dead_letter_id": row["id"],
                        "source_kind": source,
                        "new_outbox_event_id": result["new_outbox_event_id"],
                        "new_worker_task_id": result["new_worker_task_id"],
                        "result": "replayed",
                    }
                )
            else:
                skipped.append({"dead_letter_id": row["id"], "source_kind": source, "result": "not_replayed"})

    print(json.dumps({"requested": len(rows), "replayed": replayed, "skipped": skipped}, ensure_ascii=False, default=str))
    return 0


def build_replay_sql(source_kind: str) -> str:
    if source_kind == "outbox":
        return OUTBOX_REPLAY_SQL
    if source_kind in {"worker_task", "nats_message"}:
        return WORKER_REPLAY_SQL
    raise ValueError(f"unsupported source_kind: {source_kind}")


def _select_dead_letters_sql() -> str:
    return """
    select
      id::text,
      source_kind,
      source_id::text,
      subject,
      task_type,
      idempotency_key,
      error_code,
      error_summary,
      created_at
    from job.dead_letters
    where replay_status = 'open'
      and (%s::uuid is null or id = %s::uuid)
      and (%s is null or source_kind = %s)
      and (
        %s::uuid is null
        or (source_kind = 'worker_task' and source_id = %s::uuid)
        or (payload->>'task_id') = %s
      )
      and (
        %s::uuid is null
        or (source_kind = 'outbox' and source_id = %s::uuid)
        or (payload #>> '{source,event_id}') = %s
      )
    order by created_at asc
    limit %s
    """


def _filter_params(
    *,
    dead_letter_id: str | None,
    task_id: str | None,
    event_id: str | None,
    source_kind: str | None,
) -> tuple[object, ...]:
    dead_letter_uuid = _optional_uuid(dead_letter_id, "dead-letter-id")
    task_uuid = _optional_uuid(task_id, "task-id")
    event_uuid = _optional_uuid(event_id, "event-id")
    task_text = str(task_uuid) if task_uuid else None
    event_text = str(event_uuid) if event_uuid else None
    return (
        dead_letter_uuid,
        dead_letter_uuid,
        source_kind,
        source_kind,
        task_uuid,
        task_uuid,
        task_text,
        event_uuid,
        event_uuid,
        event_text,
    )


def _optional_uuid(value: str | None, name: str) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise SystemExit(f"--{name} must be a UUID.") from exc


if __name__ == "__main__":
    raise SystemExit(main())
