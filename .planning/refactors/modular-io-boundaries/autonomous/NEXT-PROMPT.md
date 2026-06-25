# Next Prompt

Continue the user-authorized `main-read-model-closure` run from the expanded 2026-06-26 controller.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260626-050615`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`.
- Wave 1 summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-1-static-guard-and-write-target-inventory-2026-06-26.md`.
- Wave 2 summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-2-write-target-envelope-and-frontend-freshness-2026-06-26.md`.
- Write target inventory: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`.
- Admin Token was acquired through secure popup for the current controller session. Never print, hash, encode, persist or copy it into prompts, logs, files, docs, shell history, screenshots, test fixtures or worker prompts.
- User has approved production rollout, root SSH production validation, low-risk production samples, production business-operation validation, sample restore, and bounded DB restore for validation samples that lack business inverse.
- Missing business inverse restore path is not a blocker by itself. It must route into the preapproved bounded DB restore protocol; only missing snapshot, exact predicate, transaction safety, or post-restore verification can hard-stop sample recovery.

## Next Boundary

`main-read-model-closure:wave-3-remaining-write-target-coverage-and-legacy-path-quarantine`

Goal:

- Extend the Wave 2 write target envelope/freshness barrier contract to remaining write families or produce tested non-applicability proofs.
- Audit and delete or hard-quarantine old read/write/refresh paths that can still pollute normal production read model flows.
- Keep the wave high-efficiency and multi-module, but preserve explicit owners, tests and rollback points.
- Do not run production mutation in this wave unless the code reaches a verified local L3 state and the controller deliberately transitions into a separate production evidence wave.

Required first steps:

1. Confirm `git status --short --branch`; stop only for unrelated dirty files.
2. Confirm `main` remains fast-forward synced with `origin/main`.
3. Read:
   - `AGENTS.md`
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-2-write-target-envelope-and-frontend-freshness-2026-06-26.md`
   - `docs/architecture/module-boundaries/read-model-contracts.md`
   - `docs/modules/read-models/boundary-io.md`
   - `docs/modules/runtime-workers/boundary-io.md`
   - affected module `boundary-io.md` files for every module touched in this wave.
4. Use CodeGraph before shared code edits. Use `codegraph_impact` before modifying shared operation barrier, route helper, frontend API normalizer, guard helper, Workbench action facade, import write flow, or read model refresh producer symbols.

Implementation tasks:

- Use `read_model_write_targets.write_target_envelope(...)` where it fits; do not create a second target envelope abstraction.
- Cover remaining write families from the Wave 1 inventory, prioritizing normal production page flows:
  - `bank-details`: category/tag/rule/import-driven writes that affect `bank_detail`, `bank_account_balance`, Workbench/no-OA/turnover visibility.
  - `input-invoice-usage` and OA reverse writes.
  - `output-invoice-collections` receipt/red-invoice/reminder/status writes.
  - `cost-statistics` source/settings writes and parent aggregate visibility.
  - `tax-offset` save/import/apply writes.
  - `imports-oa-driven` confirm/revoke/delete/reopen/import flows.
  - `workbench` action writes and compatibility action routes.
- For each touched write family, either:
  - return/expose `affected_scope_keys`, `read_model_scope_keys`, `freshness_targets`, `operation_barrier_targets` and job/version if available, or
  - add a tested non-applicability proof explaining why the page has no direct write or why upstream writers own the affected read model targets.
- Strengthen frontend behavior where touched pages still infer freshness from local optimistic state, POST 200, fixed delay, missing status, or stale compatibility payload.
- Audit normal production callers for old path reachability:
  - stale-as-fresh status defaults
  - legacy Workbench action route surfaces
  - legacy ETC batch route surfaces
  - direct dirty/outbox SQL writes outside approved gateway/transaction boundaries
  - read model live-scan fallback that can return fresh-looking payloads
  - compat shared repository methods that remain callable from normal production paths
- Delete old code only when caller proof and tests make deletion safe. Otherwise hard-quarantine it as compat-only with:
  - owner
  - caller list
  - deletion condition
  - static guard
  - normal production path non-reachability proof
  - follow-up wave name

Acceptance:

- Do not implement Go, Go Fiber or Go Worker.
- No secret values are printed or written.
- No production DB write, queue mutation, readiness mutation, force refresh, repair, rollout or mutating HTTP sample unless the wave explicitly transitions into a separate production evidence wave after verified local L3.
- Existing API response shape remains backward-compatible unless the change is documented and tests are updated.
- Every write family touched by this wave has tests proving target envelope behavior or non-applicability.
- Frontend touched pages fail closed on missing/unknown/non-fresh status and wait for operation barrier/fresh reload when the write affects read model visibility.
- Legacy route/path quarantine guards are strengthened when deletion is not safe.
- Seven test categories must be evaluated; applicable tests must be added or updated.
- Docs impact must be handled. If module facts, I/O, status machine or deletion conditions change, update the affected `docs/modules/<module>/` docs.

Verification:

Start with targeted tests for touched modules, then run at minimum:

```bash
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_manifest tests.test_runtime_worker_registry
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_freshness tests.test_read_model_scope_contract tests.test_runtime_worker_read_model_refresh_scopes
PYTHONPATH=backend/src python3 -m unittest -q tests.test_write_operation_slo_audit tests.test_write_operation_e2e_smoke tests.test_runtime_sync_closure_gate tests.test_read_model_slo_smoke
bash scripts/verify.sh docs
npm run build
git diff --check
```

Run frontend targeted tests for every touched page/API module. If a broad verification command is unavailable, run the closest targeted substitute and record why.

End of boundary:

- Update `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-3-remaining-write-target-coverage-and-legacy-path-quarantine-2026-06-26.md`.
- Update `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
- Update this `NEXT-PROMPT.md` with the next executable wave.
- Commit verified Wave 3 artifacts on `main`.
- Immediately continue to the next wave if safe implementation work remains.
