# Canonical Facts Wave 3: Legacy Removal Inventory

日期：2026-06-28

## Scope

本清单只处理会污染 PostgreSQL canonical facts 的旧 source-of-truth 路径。判定标准是生产可达性：旧代码只要还能在 production app/API/worker 链路中读、写、恢复、bootstrap、refresh 或覆盖同一业务事实，就必须删除或阻断；迁移、审计、回滚、一次性 repair 工具即使保留，也不算 closure。

## Classification

| Path / signal | Evidence | Classification | Owner | Required action |
| --- | --- | --- | --- | --- |
| Legacy full snapshot bootstrap | Wave 5 deleted `LegacySnapshotBootstrap`, allowlist symbols, `load_bootstrap_snapshot(...)` loaders and Application bootstrap calls. | `deleted` | platform runtime / canonical facts | No remaining action for this path; keep guards that prevent full snapshot bootstrap symbols from returning. |
| PostgreSQL full-state snapshot | Wave 5 removed `state:full_state` read/write fallback from `PostgresStateStore`; deploy/readiness guards still reject the old env. | `deleted-production-path` | platform runtime / settings | Keep deploy/readiness guard; do not restore `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` as write/read behavior. |
| Local pickle / App local state store | `build_state_store()` now only accepts `FIN_OPS_APP_STORAGE_BACKEND=postgres`; `ApplicationStateStore` still implements local pickle I/O for tests/local tooling. | `production-path-removed-tooling-deferred` | platform runtime | Do not reconnect local pickle to app/API/worker production wiring. Final closure needs either deletion after tests move to fakes or explicit non-production fixture acceptance. |
| `app.app_settings` `state:*` JSON facts | Wave 5 removed production runtime reads/writes, generic `PostgresStateStore` state helper API, repair tool writers and selected transform outputs. | `deleted-production-path` | settings + owning business modules | Keep negative tests/guards. Any remaining `state:*` text should be test fixture, historical docs, or explicit non-production migration evidence only. |
| Workbench candidate snapshot repair tool | `tools/repair_workbench_candidate_snapshot.py` wrote `state:workbench_candidate_matches`; wave 5 deleted the tool and added a guard that it must not return. | `deleted` | reconciliation-workbench / read model owner | No remaining action for this path. |
| Cutover/shadow/preflight tools using local pickle or Mongo readonly | `run_shadow_read_rehearsal.py`, `services/shadow_read_rehearsal.py`, `run_runtime_state_policy_preflight.py`, `run_controlled_mirror_write_rehearsal.py` and `verify_cutover_preflight.py` are deleted; `cutover_preflight.py` keeps only secret redaction helpers used by other tools. | `deleted-except-shared-redaction-helper` | platform runtime | No remaining cutover checker action; do not restore old cutover preflight CLI/checker. |
| GridFS file fallback | `file_object.gridfs_migration` worker and `GridFSObjectMigrationService` read legacy GridFS; docs say GridFS is migration/audit/rollback source only. | `tool-only-deferred` | imports/files | Keep as migration worker only until all legacy objects are backfilled. Production file reads must use canonical `app.file_objects` + object storage and fail instead of fallback when missing. |
| App Mongo snapshot | operations docs allow App Mongo for rollback/shadow/audit only. | `tool-only-deferred` | platform runtime | Keep outside production app source-of-truth. Closure requires no production API/worker app fact read from App Mongo. |
| OA Mongo adapter | `MongoOAAdapter` is used by OA sync/worker and a parser-version helper; OA pending in-progress reads use OA Mongo as external source with OA MySQL admission. | `not-source-of-truth` for app canonical facts; `tool-only-deferred` for direct API fallback risk | oa-integration | OA Mongo is external input, not app canonical facts. It must stay read-only and enter app facts via OA projection/sync or explicit admitted projection; direct page/API fresh payload fallback remains forbidden. |
| ETC legacy batch routes/services | Wave 5 deleted `routes_etc_legacy_batches.py`, `etc_legacy_batch_*`, dispatch/readiness wiring and compatibility tests. | `deleted` | etc-tickets / imports-etc-invoices | No remaining production API action. Historical repair/backfill docs/tools stay separate and do not count as production route closure. |
| Workbench direct pair relation fallback | workbench docs/tests show major direct pair write fallback paths were migrated to `WorkbenchRelationCommandService`; remaining scans should only allow command service or domain internals. | `remove-now` if production caller remains; otherwise `not-source-of-truth` | workbench-relations | Wave 4 should add/confirm static guard that production services cannot regain direct pair mutation fallback. Any remaining non-tool production caller must be removed. |
| No-OA legacy relation repair/consolidation | docs state old direct pair writes were migrated; retained pair service is read/snapshot validation only. | `remove-now` if production direct write remains; otherwise `not-source-of-truth` | no-oa-bank-batches / workbench-relations | Confirm with static guard. Do not allow hidden repair during read model refresh or GET/list paths. |
| Turnover legacy fallback adapter | Wave 5 deleted Turnover bank-row-tags, tag-selection, relation-extra, confirm, closure and withdraw legacy fallback factories/classes/providers. | `deleted` | turnover-ledger | Keep guards that prevent fallback factories/classes/providers from returning. |
| Batch accounting legacy repair | docs keep explicit compat repair path for case-id collision, with command service required. | `tool-only-deferred` | batch-accounting / workbench-relations | Accept only as explicit repair path through `WorkbenchRelationCommandService`; no GET/list auto repair or direct pair fallback. |
| Read model tables / Redis / RabbitMQ / frontend events | canonical facts docs exclude `read_model.*`, Redis, RabbitMQ and frontend events. | `not-source-of-truth` | read-models / runtime / frontend | Do not edit 07 files. Canonical facts wave only verifies these do not write back as business facts. |

## Wave 4 Guard Targets

1. Static guard for production app/API/worker path not importing or calling full snapshot/local pickle/App Mongo fallback as business fact source.
2. Static guard for `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` not allowed under production runtime guard.
3. Static guard for direct Workbench pair mutation fallback outside `WorkbenchRelationCommandService` / domain internals / explicit tools.
4. Static guard or targeted test for ETC legacy batch production routes not being treated as canonical source-of-truth closure.
5. Static guard for `GridFSObjectMigrationService` staying migration-worker scoped and not normal file read fallback.

## Result

Wave 3 does not close canonical facts. It converts the old-code problem into deletion/guard slices. The next safe wave is `wave-4-static-guards`; code deletion should start only after those guards prove the highest-risk old production paths cannot silently return.
