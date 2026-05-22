# RabbitMQ All Runtime Events - 2026-05-22

## Scope

- Generated the final execution prompt in `docs/superpowers/plans/2026-05-22-rabbitmq-all-runtime-events.md`.
- Implemented independent RabbitMQ routing/topology metadata for:
  - `workbench.read_model.refresh`
  - `search.read_model.refresh`
  - `pending_invoice.read_model.refresh`
  - `cost_statistics.read_model.refresh`
  - `tax_offset.read_model.refresh`
  - `oa.sync`
  - `file_object.gridfs_migration`
- PostgreSQL remains the task and business fact source. RabbitMQ is only the envelope transport.

## Local, Staging, And Production Verification

- Targeted local tests: `56 passed, 1 skipped`.
- Failure-path patch tests: `46 passed`.
- `git diff --check`: passed.
- Real staging preflight: `pass`.
- Latest staging report: `docs/database-migration/reports/rabbitmq-staging-preflight-latest.json`.
- Final production read-only verification:
  - RabbitMQ dispatcher and all RabbitMQ worker services are `active/enabled` with `NRestarts=0`.
  - Old PostgreSQL polling workers are `inactive/disabled`.
  - All target RabbitMQ queues and DLQs have `0` messages and `0` unacked messages.
  - Target runtime event families have no pending, publishing, or publish-failed PostgreSQL backlog.
- The local `local-postgres.env`/`staging-rabbitmq.env` files are not present in this workstation anymore, so the staging preflight was not re-run during final production verification.

## Production Runtime Deployment

- Deployed standalone RabbitMQ runtime release:
  - `/opt/fin-ops/rabbitmq-runtime/20260522-224452`
- The main API service was not restarted.
- `/opt/fin-ops/current/backend` was not overwritten.
- Dispatcher now runs from the standalone RabbitMQ runtime release.
- Workbench RabbitMQ worker now runs from the standalone RabbitMQ runtime release.

## Production Topology

The broker has independent live queues and DLQs for workbench, search, pending invoice, cost/tax, OA sync, and file migration. The active production dispatcher allowlist now covers every supported runtime event family:

```text
workbench.read_model.refresh,search.read_model.refresh,pending_invoice.read_model.refresh,cost_statistics.read_model.refresh,tax_offset.read_model.refresh,oa.sync,file_object.gridfs_migration
```

## Production Cutover Completed

Completed the remaining event-family cutovers:

- Stopped and disabled old PostgreSQL polling worker:
  - `fin-ops-worker-search-pending.service`
- Started and enabled RabbitMQ consumer:
  - `fin-ops-worker@search-pending-rabbitmq.service`
- Stopped and disabled old PostgreSQL polling workers:
  - `fin-ops-worker-cost-tax.service`
  - `fin-ops-worker-oa-sync.service`
- Started and enabled RabbitMQ consumers:
  - `fin-ops-worker@cost-tax-rabbitmq.service`
  - `fin-ops-worker@oa-sync-rabbitmq.service`
  - `fin-ops-worker@file-migration-rabbitmq.service`
- Active consumers after cutover:
  - `finops.workbench.read_model.refresh`: 1
  - `finops.search.read_model.refresh`: 1
  - `finops.pending_invoice.read_model.refresh`: 1
  - `finops.cost_statistics.read_model.refresh`: 1
  - `finops.tax_offset.read_model.refresh`: 1
  - `finops.oa.sync`: 1
  - `finops.file_object.gridfs_migration`: 1
- Queue depth and DLQ for these queues: 0.

Validated production events:

- Existing `search.read_model.refresh` backlog event `6f5af725-cd54-422f-bba2-94eb6d800740` was published and processed through RabbitMQ.
- Search shard events for `2025-12` through `2026-05` were published and processed through RabbitMQ.
- Controlled `pending_invoice.read_model.refresh` event `28562081-8cbe-4cb5-9ef5-9ac931d290a4` with scope `expense:all` was published and processed through RabbitMQ.
- Controlled `cost_statistics.read_model.refresh` event `1a423c71-5d3d-4a1a-8c64-fcde2439c2cc` with scope `active:2026-05` was published and processed through RabbitMQ.
- Controlled `tax_offset.read_model.refresh` event `a513e124-d4fc-498f-b22e-885d689354a4` with scope `2026-05` was published and processed through RabbitMQ.
- Controlled `oa.sync` event `42804695-2044-4b68-a29d-c3022d8f96fb` with scope `2026-05` was published and processed through RabbitMQ; result scanned 24 records and upserted 24 records.
- Controlled `file_object.gridfs_migration` event `ccf7a6ce-e8ff-4d94-87db-7146216f0c3f` with action `verify` checked 5 objects with 0 failures.

## Production Repair During Cutover

One operator-created validation event used invalid pending invoice scope `all`:

- Event: `58540948-27d9-4d00-aed4-9ddd23476ce7`
- Final status: `failed`
- Error: `operator_invalid_scope_pending_invoice_all`

This exposed two real failure-path bugs before the broader rollout:

- `RuntimeQueueRepository.fail_event(...)` needed explicit PostgreSQL type casts inside `jsonb_build_object`.
- `RuntimeQueueRepository.mark_publish_failed(...)` needed explicit PostgreSQL type casts inside `jsonb_build_object`.
- `RabbitMqPublisher.close()` now ignores close on an already closed connection so the original publish failure is preserved.

These were fixed, tested, and deployed to the standalone RabbitMQ runtime release.

## Final Production State

- `fin-ops-rabbitmq-dispatcher.service`: active/enabled.
- `fin-ops-worker@workbench-rabbitmq.service`: active/enabled.
- `fin-ops-worker@search-pending-rabbitmq.service`: active/enabled.
- `fin-ops-worker@cost-tax-rabbitmq.service`: active/enabled.
- `fin-ops-worker@oa-sync-rabbitmq.service`: active/enabled.
- `fin-ops-worker@file-migration-rabbitmq.service`: active/enabled.
- Old PostgreSQL polling services disabled where they existed:
  - `fin-ops-worker-workbench.service`
  - `fin-ops-worker-search-pending.service`
  - `fin-ops-worker-cost-tax.service`
  - `fin-ops-worker-oa-sync.service`

Rollback for search/pending:

```bash
systemctl stop 'fin-ops-worker@search-pending-rabbitmq.service'
systemctl disable 'fin-ops-worker@search-pending-rabbitmq.service'
systemctl enable fin-ops-worker-search-pending.service
systemctl start fin-ops-worker-search-pending.service
```

Rollback for cost/tax:

```bash
systemctl stop 'fin-ops-worker@cost-tax-rabbitmq.service'
systemctl disable 'fin-ops-worker@cost-tax-rabbitmq.service'
systemctl enable fin-ops-worker-cost-tax.service
systemctl start fin-ops-worker-cost-tax.service
```

Rollback for OA sync:

```bash
systemctl stop 'fin-ops-worker@oa-sync-rabbitmq.service'
systemctl disable 'fin-ops-worker@oa-sync-rabbitmq.service'
systemctl enable fin-ops-worker-oa-sync.service
systemctl start fin-ops-worker-oa-sync.service
```

Rollback for file migration:

```bash
systemctl stop 'fin-ops-worker@file-migration-rabbitmq.service'
systemctl disable 'fin-ops-worker@file-migration-rabbitmq.service'
```
