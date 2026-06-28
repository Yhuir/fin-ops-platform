# Next Prompt

Continue the user-authorized `main-read-model-closure` run from the expanded 2026-06-26 controller.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260626-050615`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`.
- Wave 1 summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-1-static-guard-and-write-target-inventory-2026-06-26.md`.
- Write target inventory: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`.
- Admin Token was acquired through secure popup for the current controller session. Never print, hash, encode, persist or copy it into prompts, logs, files or worker prompts.
- User has approved production rollout, root SSH production validation, low-risk production samples, production business-operation validation, sample restore, and bounded DB restore for validation samples that lack business inverse.
- Missing business inverse restore path is not a blocker by itself. It must route into the preapproved bounded DB restore protocol; only missing snapshot, exact predicate, transaction safety, or post-restore verification can hard-stop sample recovery.

## Next Boundary

`main-read-model-closure:wave-2-write-target-envelope-and-frontend-freshness`

Goal:

- Implement a shared write-response target contract for page mutations that affect read models.
- Remove frontend missing/unknown read model status defaulting to `fresh`.
- Prove representative write-after-read paths do not render final fresh state until operation barrier or fresh reload succeeds.
- Keep this as a high-efficiency multi-module wave, but do not mix unrelated physical SQL owner split or production sample mutation work into this wave.

Required first steps:

1. Confirm `git status --short --branch`; stop only for unrelated dirty files.
2. Confirm `main` remains fast-forward synced with `origin/main`.
3. Read:
   - `AGENTS.md`
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-write-target-inventory-2026-06-26.md`
   - `docs/architecture/module-boundaries/read-model-contracts.md`
   - `docs/modules/read-models/boundary-io.md`
   - `docs/modules/runtime-workers/boundary-io.md`
   - affected module `boundary-io.md` files for every module touched in this wave.
4. Use CodeGraph before shared code edits. Use `codegraph_impact` before modifying shared operation barrier, route helper, frontend API normalizer or guard helper symbols.

Implementation tasks:

- Inspect existing write response shapes and operation barrier helpers before introducing new abstractions.
- Prefer an existing local helper if one already represents affected read model scopes, freshness targets, operation barrier targets, job/version or mutation source version.
- If no shared helper exists, add a small backend helper with explicit I/O. It must not import Flask, app auth, route modules, `Application`, or HTTP response objects.
- Update representative write APIs across module families so success responses expose a consistent target envelope or a documented non-applicability proof:
  - `batch-accounting`
  - `no-oa-bank-batches`
  - `turnover-ledger`
  - `pending-invoices`
  - `oa-pending-payments`
  - at least one bank-details or import/OA-driven write path if the existing service result already exposes affected scopes safely.
- Add or update backend API/service tests proving the target envelope contains explicit affected scopes or barrier targets for touched writes.
- Remove frontend default-`fresh` fallbacks classified in Wave 1 when touched. Unknown/missing `readModelStatus` must remain unknown/refreshing/non-fresh and must not be displayed as final fresh data.
- Update frontend API/page tests for touched pages proving write success waits for barrier/fresh reload or keeps refreshing/non-fresh status.
- Keep legacy path deletion/quarantine changes only where they directly support this target envelope/freshness wave; otherwise leave deletion to a later legacy wave with its own tests.

Acceptance:

- Do not implement Go, Go Fiber or Go Worker.
- No production DB write, queue mutation, readiness mutation, force refresh, repair, rollout or mutating HTTP sample in this wave.
- No secret values are printed or written.
- Touched write APIs return or expose affected scopes/freshness targets/operation barrier targets/job/version, or have a tested non-applicability proof.
- Touched frontend code no longer defaults missing/unknown/stale read model status to `fresh`.
- `tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_frontend_read_model_status_default_fresh_sites_are_classified` must be updated only by deleting allowlist entries that the implementation truly removed, or by replacing entries with stricter non-fresh behavior evidence.
- Existing API response shape must remain backward-compatible unless the change is documented and tests are updated.
- Seven test categories must be evaluated; applicable tests must be added or updated.
- Docs impact must be handled. If module facts, I/O, status machine or deletion conditions change, update the affected `docs/modules/<module>/` docs.

Verification:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_scope_contract tests.test_runtime_worker_read_model_refresh_scopes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_slo_audit tests.test_write_operation_e2e_smoke tests.test_runtime_sync_closure_gate tests.test_read_model_slo_smoke -v
bash scripts/verify.sh docs
git diff --check
```

Add targeted backend/frontend tests for touched modules. If a broad verification command is unavailable, run the closest targeted substitute and record why.

End of boundary:

- Update `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-2-write-target-envelope-and-frontend-freshness-2026-06-26.md`.
- Update `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
- Update this `NEXT-PROMPT.md` with the next executable wave.
- Commit verified Wave 2 artifacts on `main`.
- Immediately continue to Wave 3 if safe implementation work remains.
