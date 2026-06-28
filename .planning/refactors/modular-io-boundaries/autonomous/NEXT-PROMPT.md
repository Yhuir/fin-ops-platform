# Next Prompt

Continue the user-authorized `main-read-model-closure` run from Wave 9.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260626-050615`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`.
- Latest wave summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-9-public-authenticated-api-sse-and-write-matrix-closure-2026-06-26.md`.
- Production evidence runbook: `docs/operations/read-model-production-evidence-runbook.md`.
- User has approved production rollout, root SSH production validation, low-risk production samples, production business-operation validation, sample restore, and bounded DB restore for validation samples that lack business inverse.
- Missing business inverse restore path is not a blocker by itself. It must route into the preapproved bounded DB restore protocol; only missing operation-before snapshot, exact predicate, transaction safety, or post-restore verification can hard-stop sample recovery.
- Do not print or persist any secret. Use secure credential manager/session secret handling only for Admin Token use.
- Do not implement Go, Go Fiber or Go Worker.

## Completed In Current Wave So Far

Wave 9 found a concrete production write-matrix gap: turnover write-operation SLO long tails caused by normal write paths refreshing broad `all` scopes.

Local fix completed:

- `TurnoverLedgerWriteFacade` now uses affected month scope keys for bank-row-tags, relation confirm, manual closure confirm, and relation withdraw.
- `TurnoverLedgerConfirmRequestBoundaryFacade` returns affected `turnover_ledger:<month>` targets plus affected `workbench_relation:<month>` targets for closure visibility.
- `TurnoverLedgerPage` waits for affected turnover ledger month scopes before manual closure fresh rebind, falling back to `all` only when row months cannot be parsed.
- Module docs and read-model implementation notes were updated.

Local verification already passed:

```bash
PYTHONPATH=backend/src python3 -m unittest -q tests.test_turnover_ledger_api tests.test_turnover_ledger_uow_contract tests.test_read_model_write_targets
npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx
PYTHONPATH=backend/src python3 -m unittest -q tests.test_turnover_ledger_api tests.test_turnover_ledger_uow_contract tests.test_read_model_write_targets tests.test_write_operation_slo_audit tests.test_slo_tool_defaults tests.test_read_model_manifest tests.test_runtime_worker_read_model_refresh_scopes tests.test_operation_freshness_barrier
```

## Next Boundary

`main-read-model-closure:wave-9-deploy-and-production-write-matrix-retest`

Goal:

- Finish local verification and commit/push the turnover write-target narrowing.
- Deploy current `main` to production via `./scripts/deploy-oa.sh`.
- Re-run production read model health and critical SLO smoke.
- Re-run controlled production write-operation samples, focusing first on turnover relation/closure write SLO and then no-OA/workbench matrix gaps.
- Restore samples through business inverse where available; use bounded DB restore only when no business restore path exists and the operation-before snapshot + exact predicate + transaction safety + post-restore verification are established.

Required first steps:

1. Confirm `git status --short --branch`; stop only for unrelated dirty files.
2. Run final local checks:
   - `git diff --check`
   - `bash scripts/verify.sh docs`
   - targeted backend/frontend tests if not already fresh in this session.
3. Review diff for secrets, unrelated files, stale docs, and accidental broad scope regressions.
4. Commit and push to `origin/main`.
5. Deploy with `./scripts/deploy-oa.sh`.
6. On production, verify release consistency, services/workers active, dirty/outbox/readiness aggregates converged, and critical read model SLO.
7. Re-run write-operation SLO samples and record sanitized evidence in the Wave 9 analysis file.

No-block policy:

- Do not ask the user for sample approval, rollout approval, SSH approval, or DB restore approval; these are already granted.
- Do not directly modify DB for the validation operation itself.
- Bounded DB write is allowed only to restore a validation sample to its operation-before state when no business restore path exists.
- Do not claim PSCIP-L4/global closure until production read/write evidence passes.

End of boundary:

- Update `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-9-public-authenticated-api-sse-and-write-matrix-closure-2026-06-26.md`.
- Update `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
- Update this `NEXT-PROMPT.md` with the next executable wave or final closure prompt.
- Commit verified non-secret artifacts on `main`.
- Continue automatically unless a precise hard stop is reached.
