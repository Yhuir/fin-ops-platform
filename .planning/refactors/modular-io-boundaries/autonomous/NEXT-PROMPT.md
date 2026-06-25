# Next Prompt

Continue the user-authorized `main-read-model-closure` run from the expanded 2026-06-26 controller.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260626-050615`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`.
- Write target inventory: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`.
- Wave 1 summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-1-static-guard-and-write-target-inventory-2026-06-26.md`.
- Wave 2 summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-2-write-target-envelope-and-frontend-freshness-2026-06-26.md`.
- Wave 3 summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-3-remaining-write-target-coverage-and-legacy-path-quarantine-2026-06-26.md`.
- Admin Token was acquired through secure popup for the current controller session. Never print, hash, encode, persist or copy it into prompts, logs, files, docs, shell history, screenshots, test fixtures or worker prompts.
- User has approved production rollout, root SSH production validation, low-risk production samples, production business-operation validation, sample restore, and bounded DB restore for validation samples that lack business inverse.
- Missing business inverse restore path is not a blocker by itself. It must route into the preapproved bounded DB restore protocol; only missing operation-before snapshot, exact predicate, transaction safety, or post-restore verification can hard-stop sample recovery.

## Next Boundary

`main-read-model-closure:wave-4-import-cost-tax-balance-and-legacy-deletion`

Goal:

- Close the remaining high-impact write families that can still leave page read models stale or old-path polluted.
- Either add unified target envelopes and frontend barrier waits, or produce tested non-applicability/deletion proof.
- Delete old code when caller proof is complete; otherwise hard-quarantine compat-only paths with owner, caller list, deletion condition and static guard.
- Keep the wave high-efficiency and multi-module, but do not claim PSCIP-L4 until production rollout/evidence gates pass.

Required first steps:

1. Confirm `git status --short --branch`; stop only for unrelated dirty files.
2. Confirm `main` remains fast-forward synced with `origin/main`.
3. Read:
   - `AGENTS.md`
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-3-remaining-write-target-coverage-and-legacy-path-quarantine-2026-06-26.md`
   - `docs/modules/read-models/boundary-io.md`
   - `docs/modules/runtime-workers/boundary-io.md`
   - affected module `boundary-io.md` files for every module touched in this wave.
4. Use CodeGraph before shared code edits. Use `codegraph_impact` before modifying shared route helpers, import write flow, Workbench action facade, refresh producer, frontend API normalizer, operation barrier helper or read model registry code.

Implementation priorities:

- Imports/OA-driven writes:
  - confirm/revoke/delete/reopen/import flows must expose affected read model scopes or be routed to existing owners that do.
  - confirm no normal production path returns stale-as-fresh after import mutation.
- Cost statistics:
  - source/settings writes and parent aggregate visibility must have target envelopes or tested non-applicability.
  - preserve cost/tax shared projection boundaries and avoid making `tax_offset` the source for cost facts.
- Tax offset:
  - tax certified import confirm/apply/warmup/rebuild flows must return or enqueue explicit scoped targets.
  - ensure frontend import confirm waits on operation barrier or job completion plus fresh reload.
- Bank account balance induced writes:
  - bank-detail/import/category paths that affect `bank_account_balance` must have explicit target evidence or documented owner handoff.
- Remaining Workbench/cash-special/personal-advance action surfaces:
  - normal production actions must not drop affected scopes.
  - relation writes target `workbench_relation`; active generation `workbench` remains the special projection exception.
- Legacy deletion/quarantine:
  - stale-as-fresh defaults
  - legacy Workbench action route surfaces
  - legacy ETC batch route surfaces
  - direct dirty/outbox SQL writes outside approved gateway/transaction boundaries
  - live-scan fallback that can return fresh-looking payloads
  - compat repository methods callable from normal production paths

Acceptance:

- Do not implement Go, Go Fiber or Go Worker.
- No secret values are printed or written.
- No production DB write, queue mutation, readiness mutation, force refresh, repair, rollout or mutating HTTP sample unless the wave explicitly transitions into a separate production evidence wave after verified local L3.
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

- Update `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-4-import-cost-tax-balance-and-legacy-deletion-2026-06-26.md`.
- Update `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
- Update this `NEXT-PROMPT.md` with the next executable wave.
- Commit verified Wave 4 artifacts on `main`.
- Immediately continue to the next wave if safe implementation work remains.
