# Next Prompt

Continue the user-authorized `main-read-model-closure` run from the expanded 2026-06-26 controller.

## Current State

- Branch: `main`.
- Current main commit at reconciliation start: `aa9b2232e261db2e4efe5776a7784705ab2e760d`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260626-050615`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`.
- Previous local owner split audit: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-local-owner-split-closure-audit-2026-06-25.md`.
- Previous production evidence gap: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-equivalent-evidence-gap-2026-06-25.md`.
- Previous deploy runbook: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-controlled-deploy-evidence-runbook-2026-06-25.md`.
- User has now approved production rollout, root SSH production validation, low-risk production samples, production business-operation validation, sample restore, and bounded DB restore for validation samples that lack business inverse.
- Admin Token was acquired through secure popup for the current controller session. Never print, hash, encode, persist or copy it into prompts, logs, files or worker prompts.

## Updated Objective

The target is no longer only repository owner split or production L4 evidence. Complete all page read/write Read Model closure:

- every page read API must expose explicit fresh/stale/refreshing/failed/missing/unavailable behavior;
- every page write API that affects page data must expose affected read model scopes, freshness targets, operation barrier targets, job/version or a documented non-applicability proof;
- frontend mutations must wait for operation barrier or fresh reload before final fresh state;
- dirty scope/outbox/worker/projection/readiness/API/UI must be traceable;
- old read model code, old modules, old fallback and default-fresh assumptions must be deleted or hard-quarantined from normal production read/write/refresh paths;
- production samples must be applied through business API/UI/command and restored by business inverse or the preapproved bounded DB restore protocol.

## Next Boundary

`main-read-model-closure:wave-1-static-guard-and-write-target-inventory`

Goal:

- Build source-backed inventory for all page read/write operations and their read model targets.
- Add or strengthen guard tests that prevent stale-as-fresh and old path pollution from regressing.
- Do not run production mutation yet; finish local guard/inventory first.

Required first steps:

1. Confirm `git status --short --branch`; stop only for unrelated dirty files.
2. Confirm `main` remains fast-forward synced with `origin/main`.
3. Read:
   - `AGENTS.md`
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`
   - `docs/architecture/module-boundaries/read-model-contracts.md`
   - `docs/architecture/module-boundaries/inventory.md`
   - `docs/modules/read-models/boundary-io.md`
   - `docs/modules/runtime-workers/boundary-io.md`
   - all directly affected page/module `boundary-io.md` files.
4. Use CodeGraph before shared code edits. Use `codegraph_impact` before modifying shared guard/helper symbols.

Implementation tasks:

- Inspect and extend `tests/test_read_model_architecture_guards.py` and `tests/test_platform_runtime_boundary_guards.py`.
- Add a guard or report-backed test for route/service `read_model_status="fresh"` assignments. Allow only assignments proven to originate from fresh gate/projection owner/test fixtures.
- Add a guard or report-backed test for frontend defaulting missing/unknown read model status to `fresh`. Allow only safe initial local placeholders that cannot render final fresh state without a backend payload.
- Add a guard or report-backed test for normal production reachability of:
  - `backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py`
  - `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
  - turnover ledger legacy fallback facades in `turnover_ledger_write_adapters.py`
  - legacy Workbench stale payload fallback in `server.py`
- Generate an inventory artifact under `.planning/refactors/modular-io-boundaries/analysis/` listing every page mutation route/API and whether its response already exposes `freshness_targets`, affected scopes, barrier targets or equivalent proof.
- Update module docs only if the source-backed boundary facts change; otherwise record docs not applicable for this wave.

Acceptance:

- Do not implement Go, Go Fiber or Go Worker.
- Guard tests are executable and either fail on real gaps that must be fixed in Wave 2/3 or pass with an explicit allowlist that names owner and deletion condition.
- Inventory covers at least these modules: workbench, batch accounting, bank details/balance, pending invoices, input invoice usage, OA pending payments, output invoice collections, cost statistics, tax offset, no-OA bank batches, turnover ledger, imports/OA-driven updates.
- No secret values are printed or written.
- No production DB write, queue mutation, readiness mutation, force refresh, repair or mutating HTTP sample in this wave.

Verification:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
bash scripts/verify.sh docs
git diff --check
```

End of boundary:

- Update `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
- Update this `NEXT-PROMPT.md` with the next executable wave.
- Commit verified Wave 1 artifacts on `main`.
- Immediately continue to Wave 2 if safe implementation work remains.
