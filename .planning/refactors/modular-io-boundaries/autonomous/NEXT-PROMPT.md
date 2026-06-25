# Next Prompt

Continue the user-authorized `main-read-model-closure` run from the expanded 2026-06-26 controller.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260626-050615`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`.
- Write target inventory: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`.
- Wave 5 summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-5-oa-driven-queued-job-legacy-and-production-evidence-prep-2026-06-26.md`.
- Admin Token was acquired through secure popup for the current controller session. Never print, hash, encode, persist or copy it into prompts, logs, files, docs, shell history, screenshots, test fixtures or worker prompts.
- User has approved production rollout, root SSH production validation, low-risk production samples, production business-operation validation, sample restore, and bounded DB restore for validation samples that lack business inverse.
- Missing business inverse restore path is not a blocker by itself. It must route into the preapproved bounded DB restore protocol; only missing operation-before snapshot, exact predicate, transaction safety, or post-restore verification can hard-stop sample recovery.

## Next Boundary

`main-read-model-closure:wave-6-queued-job-completion-and-legacy-quarantine`

Goal:

- Close queued import job completion freshness propagation after affected scopes are knowable.
- Delete old code when caller proof is complete; otherwise hard-quarantine compat-only paths with owner, caller list, deletion condition and static guard.
- Prepare, but do not prematurely execute, the production evidence wave.

Required first steps:

1. Confirm `git status --short --branch`; stop only for unrelated dirty files.
2. Confirm `main` remains fast-forward synced with `origin/main`.
3. Read:
   - `AGENTS.md`
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-5-oa-driven-queued-job-legacy-and-production-evidence-prep-2026-06-26.md`
   - `docs/modules/read-models/boundary-io.md`
   - `docs/modules/imports-bank-transactions/boundary-io.md`
   - `docs/modules/imports-invoices/boundary-io.md`
   - affected module `boundary-io.md` files for every module touched in this wave.
4. Use CodeGraph before shared code edits. Use `codegraph_impact` before modifying shared import write flow, job result mapping, frontend import job polling, operation barrier helper, read model registry, route helpers, or compat repository code.

Implementation priorities:

- Queued import job completion:
  - When a queued import job finishes and the UI consumes job result payload/summary, the result must expose operation barrier targets or a tested non-applicability proof.
  - Do not fabricate targets on queued admission before the affected scopes are knowable.
  - Frontend import job completion must wait for operation barrier targets before showing final fresh state when the job result affects read model visibility.
- Legacy deletion/quarantine:
  - stale-as-fresh defaults
  - legacy Workbench action route surfaces
  - legacy ETC/import route surfaces
  - direct dirty/outbox SQL writes outside approved gateway/transaction boundaries
  - live-scan fallback that can return fresh-looking payloads
  - compat repository methods callable from normal production paths
- Production evidence prep:
  - Prepare scripts/runbook for post-rollout read/write/freshness/performance samples.
  - Every mutating sample must have a restore plan before apply: business inverse preferred; otherwise preapproved bounded DB restore with operation-before snapshot, exact predicate, single transaction and post-restore verification.

Acceptance:

- Do not implement Go, Go Fiber or Go Worker.
- No secret values are printed or written.
- No production DB write, queue mutation, readiness mutation, force refresh, repair, rollout or mutating HTTP sample unless this wave explicitly transitions into a separate production evidence wave after verified local L3.
- Existing API response shape remains backward-compatible unless the change is documented and tests are updated.
- Every write family touched by this wave has tests proving target envelope behavior, deletion/quarantine proof or non-applicability.
- Frontend touched pages fail closed on missing/unknown/non-fresh status and wait for operation barrier/fresh reload when the write affects read model visibility.
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

- Update `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-6-queued-job-completion-and-legacy-quarantine-2026-06-26.md`.
- Update `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
- Update this `NEXT-PROMPT.md` with the next executable wave.
- Commit verified Wave 6 artifacts on `main`.
- Immediately continue to the next wave if safe implementation work remains.
