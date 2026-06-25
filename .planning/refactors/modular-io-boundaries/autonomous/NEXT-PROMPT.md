# Next Prompt

Continue the user-authorized `main-read-model-closure` run from the expanded 2026-06-26 controller.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260626-050615`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`.
- Write target inventory: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`.
- Wave 6 summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-6-queued-job-completion-and-legacy-quarantine-2026-06-26.md`.
- Admin Token was acquired through secure popup for the current controller session. Never print, hash, encode, persist or copy it into prompts, logs, files, docs, shell history, screenshots, test fixtures or worker prompts.
- User has approved production rollout, root SSH production validation, low-risk production samples, production business-operation validation, sample restore, and bounded DB restore for validation samples that lack business inverse.
- Missing business inverse restore path is not a blocker by itself. It must route into the preapproved bounded DB restore protocol; only missing operation-before snapshot, exact predicate, transaction safety, or post-restore verification can hard-stop sample recovery.

## Next Boundary

`main-read-model-closure:wave-7-legacy-quarantine-and-production-evidence-runbook`

Goal:

- Delete old read/write/freshness code where caller proof is complete.
- Where deletion is not safe, hard-quarantine compat-only paths with owner, caller list, deletion condition and static guard.
- Prepare the post-rollout production evidence wave without claiming PSCIP-L4 before evidence passes.

Required first steps:

1. Confirm `git status --short --branch`; stop only for unrelated dirty files.
2. Confirm `main` remains fast-forward synced with `origin/main`.
3. Read:
   - `AGENTS.md`
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-6-queued-job-completion-and-legacy-quarantine-2026-06-26.md`
   - `docs/modules/read-models/boundary-io.md`
   - affected module `boundary-io.md` files for every legacy path touched in this wave.
4. Use CodeGraph before shared code edits. Use `codegraph_impact` before modifying route helpers, legacy Workbench/ETC routes, compat repositories, live-scan fallback, frontend status normalizers, operation barrier helper or read model registry code.

Implementation priorities:

- Legacy deletion/quarantine sweep:
  - `routes_legacy_workbench_actions.py`
  - `routes_etc_legacy_batches.py`
  - live-scan fallback that can return fresh-looking payloads
  - compat repository methods callable from normal production paths
  - frontend missing/unknown status defaults that can still render final fresh
  - direct dirty/outbox SQL writes outside approved gateway/transaction boundaries
- Production evidence prep:
  - Create or update a bounded runbook/script set for post-rollout read/write/freshness/performance samples.
  - Every mutating sample must have a restore plan before apply: business inverse preferred; otherwise preapproved bounded DB restore with operation-before snapshot, exact predicate, single transaction and post-restore verification.
  - No Admin Token value or production secret may be written to disk or logs.

Acceptance:

- Do not implement Go, Go Fiber or Go Worker.
- No secret values are printed or written.
- No production DB write, queue mutation, readiness mutation, force refresh, repair, rollout or mutating HTTP sample unless this wave explicitly transitions into a separate production evidence wave after verified local L3.
- Existing API response shape remains backward-compatible unless the change is documented and tests are updated.
- Every old path touched by this wave is deleted or has a static guard proving normal production read/write/freshness paths cannot reach it.
- Docs impact must be handled for every changed module.

Verification:

Start with targeted backend/frontend tests for touched modules, then run at minimum:

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

- Update `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-7-legacy-quarantine-and-production-evidence-runbook-2026-06-26.md`.
- Update `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
- Update this `NEXT-PROMPT.md` with the next executable wave.
- Commit verified Wave 7 artifacts on `main`.
- Immediately continue to the next wave if safe implementation work remains.
