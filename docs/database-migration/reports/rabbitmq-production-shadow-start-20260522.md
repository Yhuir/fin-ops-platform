# RabbitMQ Production Shadow Start - 2026-05-22

## Scope

- Deployed a standalone RabbitMQ runtime release to `/opt/fin-ops/rabbitmq-runtime/20260522-2104`.
- Existing `fin-ops.service` API release was not changed or restarted.
- Started only the dispatcher shadow publisher service.
- Prepared the workbench RabbitMQ consumer unit and env, but left it disabled and inactive.

## Dispatcher

- Unit: `fin-ops-rabbitmq-dispatcher.service`
- State: `active`
- Restart count: `0`
- Publisher id: `rabbitmq-dispatcher-shadow-1`
- Event allowlist: `workbench.read_model.refresh`
- Queue backend mode: `postgres`
- Shadow publish: `true`

## Consumer Gray Switch Readiness

- Unit template: `fin-ops-worker@.service`
- Prepared instance env: `fin-ops.worker.workbench-rabbitmq.env`
- Prepared instance: `fin-ops-worker@workbench-rabbitmq.service`
- State: `disabled` / `inactive`
- Worker check: passed with handler `workbench.read_model.refresh` and runtime transport `rabbitmq`.

## Initial Production Metrics

```json
{
  "dirty_scopes": {
    "done": 432,
    "pending": 1
  },
  "queue_backlog": {
    "done": 443,
    "pending": 1
  },
  "rabbitmq_consumer_count": 0,
  "rabbitmq_dispatch_event_types": [
    "workbench.read_model.refresh"
  ],
  "rabbitmq_dispatcher_lag_seconds": null,
  "rabbitmq_dlq_count": 0,
  "rabbitmq_publish_failed_backlog": 0,
  "rabbitmq_publish_status": {},
  "rabbitmq_queue_depth": 0,
  "rabbitmq_unacked_messages": 0,
  "rabbitmq_unpublished_backlog": 0
}
```

## Notes

- Current production backlog has one pending non-workbench event. The dispatcher is intentionally filtered to workbench events because the declared topology only contains the workbench queue and DLQ.
- No eligible pending workbench event existed at startup, so the initial shadow run verified the idle/no-error path rather than an actual publisher-confirmed workbench message.
- Keep PostgreSQL polling workers as the rollback path until shadow publish has been observed for 30-60 minutes.

## Rollback

```bash
systemctl stop fin-ops-rabbitmq-dispatcher.service
systemctl disable fin-ops-rabbitmq-dispatcher.service
systemctl stop 'fin-ops-worker@workbench-rabbitmq.service'
systemctl disable 'fin-ops-worker@workbench-rabbitmq.service'
systemctl enable fin-ops-worker-workbench.service
systemctl start fin-ops-worker-workbench.service
```

## Observation After 60 Minutes - 2026-05-22 22:09 CST

Systemd:

- `fin-ops-rabbitmq-dispatcher.service`: `active`
- `NRestarts`: `0`
- `MainPID`: `2090646`
- `ActiveEnterTimestamp`: `Fri 2026-05-22 21:05:57 CST`
- `fin-ops-worker@workbench-rabbitmq.service`: `disabled` / `inactive`
- Dispatcher journal since the last 10 minutes: no entries.
- Existing PostgreSQL polling `worker-workbench` is still running in the active API release. Do not inject a production workbench test event unless that worker is intentionally paused for a controlled cutover window.

Metrics:

```json
{
  "dirty_scopes": {
    "done": 432,
    "pending": 1
  },
  "queue_backlog": {
    "done": 443,
    "pending": 1
  },
  "rabbitmq_consumer_count": 0,
  "rabbitmq_dispatch_event_types": [
    "workbench.read_model.refresh"
  ],
  "rabbitmq_dispatcher_lag_seconds": null,
  "rabbitmq_dlq_count": 0,
  "rabbitmq_publish_failed_backlog": 0,
  "rabbitmq_publish_status": {},
  "rabbitmq_queue_depth": 0,
  "rabbitmq_unacked_messages": 0,
  "rabbitmq_unpublished_backlog": 0
}
```

This confirms the dispatcher remains healthy in shadow mode for more than 60 minutes and the prepared consumer remains off. It is still an idle-path observation because no pending `workbench.read_model.refresh` event exists in production; staging preflight remains the evidence for an actual publisher-confirmed message path.

## Workbench RabbitMQ Consumer Gray Switch - 2026-05-22 22:22 CST

Actions:

- Stopped `fin-ops-worker-workbench.service`.
- Started `fin-ops-worker@workbench-rabbitmq.service`.
- Enqueued one controlled `workbench.read_model.refresh` event for month shard `2026-05`.
- Verified PostgreSQL publish state, RabbitMQ publisher confirm, consumer processing, PostgreSQL ack, empty queue, and empty DLQ.
- Disabled old `fin-ops-worker-workbench.service`.
- Enabled new `fin-ops-worker@workbench-rabbitmq.service` so the gray switch survives reboot.

Service state after switch:

- `fin-ops-rabbitmq-dispatcher.service`: `active` / `enabled` / `NRestarts=0`
- `fin-ops-worker@workbench-rabbitmq.service`: `active` / `enabled` / `NRestarts=0`
- `fin-ops-worker-workbench.service`: `inactive` / `disabled`

Validated event:

```json
{
  "attempts": 1,
  "event_id": "0cfec9fd-16d0-43ec-b934-dc84aee9020b",
  "event_type": "workbench.read_model.refresh",
  "processed_at": "2026-05-22 22:22:44.982001+08:00",
  "publish_attempt_count": 1,
  "publish_confirmed_at": "2026-05-22 22:22:44.921389+08:00",
  "publish_last_error": null,
  "publish_status": "published",
  "published_at": "2026-05-22 22:22:44.921389+08:00",
  "rabbitmq_exchange": "finops.events",
  "rabbitmq_message_id": "0cfec9fd-16d0-43ec-b934-dc84aee9020b",
  "rabbitmq_publish": {
    "confirm_latency_ms": 4.072,
    "exchange": "finops.events",
    "message_id": "0cfec9fd-16d0-43ec-b934-dc84aee9020b",
    "routing_key": "workbench.read_model.refresh"
  },
  "rabbitmq_routing_key": "workbench.read_model.refresh",
  "runtime_result": {
    "base_scope_key": "2026-05",
    "duration_ms": 53.258,
    "ignored_row_count": 0,
    "row_count": 18,
    "scope_key": "2026-05"
  },
  "scope_key": "2026-05",
  "scope_type": "workbench",
  "source_version": 9,
  "status": "done"
}
```

Post-switch RabbitMQ metrics:

```json
{
  "rabbitmq_consumer_count": 1,
  "rabbitmq_dispatcher_lag_seconds": null,
  "rabbitmq_dlq_count": 0,
  "rabbitmq_publish_failed_backlog": 0,
  "rabbitmq_queue_depth": 0,
  "rabbitmq_unacked_messages": 0,
  "rabbitmq_unpublished_backlog": 0
}
```

Current production RabbitMQ coverage:

- `workbench.read_model.refresh`: RabbitMQ dispatcher + RabbitMQ consumer active.
- `search.read_model.refresh`, `pending_invoice.read_model.refresh`, `cost_statistics.read_model.refresh`, `tax_offset.read_model.refresh`, `oa.sync`, and `file_object.gridfs_migration`: still on PostgreSQL polling workers until their own topology, DLQ, consumer unit, and rollback path are created and validated.
