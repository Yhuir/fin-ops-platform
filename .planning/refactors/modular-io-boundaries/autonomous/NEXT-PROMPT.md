# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:search-and-no-oa-bank-batch-contract`
- Last status: `closed-autonomous`
- Search is guarded as a partitioned scoped index with `search` as primary worker and search auxiliary workers explicitly bounded.
- no-OA bank batch is guarded as a scoped incremental read model with `NoOaBankBatchApplicationService` query owner and `no-oa-bank-batch` worker ownership.

## Next Boundary

`read-models:legacy-read-path-removal-guards`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-and-no-oa-bank-batch-contract.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-query-gateway-contract-and-status-parity.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-refresh-gateway-force-refresh-and-operation-barrier.md`
4. Use CodeGraph for `ReadModelRefreshGateway`, `ReadModelQueryGateway`, `RuntimeQueueRepository.enqueue_read_model_refresh`, direct `read_model_status=fresh` writers, direct `source_version_mismatch_reasons`, direct SQL writes to `job.outbox_events` / `job.read_model_dirty_scopes`, and legacy live scan/read fallback call paths.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-legacy-read-path-removal-guards.md`.
6. Keep implementation narrow: add or tighten static architecture guards, remove a proven-unused old path, or quarantine one compat-only path with owner/caller/deletion condition. Do not rewrite read model gateways, workers, repositories, Go/Fiber, Go Worker, or production state.

## Stop Condition

Complete one narrow verified legacy read-path removal/quarantine guard slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
