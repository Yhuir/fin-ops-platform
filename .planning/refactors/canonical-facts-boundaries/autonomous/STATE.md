# Canonical Facts Closure State

日期：2026-06-28

## Current State

- Active wave: `wave-6-final-closure`
- Status: `closed`
- Current PSCF level: `PSCF-L1`
- Read model conflict policy: 07 explicitly allowed the coordinated `file_object.gridfs_migration` deletion slice.
- Latest completed slice: tool runtime state I/O was tightened after final closure: retained bank/ETC tools now build a `tool_runtime_application`, `Application.tool_runtime_ports()` no longer exposes the whole `state_store`, and the old `full snapshot application` helper name is removed.

## Wave Status

| Wave | Status | Evidence |
| --- | --- | --- |
| wave-1-contract-foundation | completed | canonical facts GSD state, architecture contract, module docs and indexes created; docs verification passed |
| wave-2-owner-boundary-io | completed | 16 owner module boundary docs updated with canonical facts ownership |
| wave-3-legacy-removal-inventory | completed | `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-wave-3-legacy-removal-inventory.md` classifies old source-of-truth paths |
| wave-4-static-guards | completed | static removal baseline added in `tests/test_platform_runtime_boundary_guards.py`; targeted test passed |
| wave-5-code-removal | completed | Old exporter/reconcile/staging/transform/import-consistency names remain only in removal guards; retained operational tools no longer access `Application._*`, `_state_store` or `_initialize_runtime_services`; App Mongo/full snapshot/`state:*` production fallback paths are removed or guarded; `ApplicationStateStore` / local pickle is accepted as guarded non-production fixture/tooling I/O. |
| wave-6-final-audit | completed | `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-final-closure-report-2026-06-29.md` records closed surfaces. `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-wave-6-tool-runtime-public-port-boundary.md` records the tool public-port boundary tightening. `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-wave-6-tool-runtime-state-port-closure.md` records the final tool runtime state port narrowing. `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-wave-6-final-blocker-audit.md` records coordinated GridFS worker deletion as resolved. |

## Blockers

- None for 08 canonical-facts final closure after the coordinated GridFS worker deletion slice.

## Accepted Non-Blocking Maintenance

- `tools/runtime_application.py` is now a small public-port adapter for currently documented ETC historical migration/link/cleanup and bank auto-tag restore operations. It does not directly access `Application._*`, `_state_store` or `_initialize_runtime_services`, does not expose the whole `state_store` through `tool_runtime_ports()`, and no longer uses the old `full snapshot application` helper name. Delete it only when those tools are retired or folded into owner module CLIs without duplicating app dependency assembly.
- `ApplicationStateStore` / `local_pickle` implementation still exists only as guarded non-production fixture/tooling I/O. It no longer opens App Mongo, GridFS, full-state bootstrap or production factory wiring; production app/service/tool paths are guarded from importing it.
- `LegacySnapshotBootstrap` class and allowlist symbols have been deleted; full snapshot bootstrap no longer exists as a runtime service.
- OA sync worker no longer directly constructs `MongoOAAdapter`; direct construction is confined to `services/oa_sync_source_adapter.py` as the OA external input/admission boundary into PostgreSQL projection facts.
- ETC backend legacy `/api/etc/batches*` route/services/gate have been deleted. Remaining ETC legacy work is limited to historical repair/backfill tools and old docs history, not production API wiring.
- Full `tests.test_platform_runtime_boundary_guards` has 3 previously observed failures in 07-owned NEXT-PROMPT expectations; 08 must not fix those while 07 owns that file.
