# Next Prompt

Continue the user-authorized `main-read-model-closure` run.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260625-230543`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest completed boundary: `main-read-model-closure:local-owner-split-closure-audit-and-production-evidence-gate`.
- Local closure audit: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-local-owner-split-closure-audit-2026-06-25.md`.
- Reconciliation file: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-25.md`.
- Wave 3 analysis file: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-3-remaining-read-model-owner-split-2026-06-25.md`.
- Local PSCIP-L3 owner split is complete for all known non-Workbench App Status read models.
- Workbench remains the documented active-generation exception and must not be mechanically converted.
- No production/server/DB access was used. No secret, production DB mutation, queue mutation, readiness mutation or worker replay occurred.
- No PSCIP-L4 global closure is claimed.

## Required First Steps On Resume

1. Confirm `git status --short --branch`; stop if unrelated dirty files would be committed.
2. Confirm `main` is fast-forward synced with `origin/main`.
3. Read:
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-local-owner-split-closure-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/production-post-convergence-readiness-worker-db-aggregate-evidence-sweep-2026-06-25.md`
4. Use CodeGraph before code edits. If the boundary is evidence-only, no code edit is expected.

## Next Boundary

`main-read-model-closure:production-or-equivalent-freshness-performance-evidence`

Goal:
- Collect production or equivalent runtime evidence required for PSCIP-L4.
- Prove all pages/read models return fresh data or correctly expose refreshing/stale status, never stale-as-fresh.
- Prove worker/queue convergence from PostgreSQL durable queue facts.
- Prove hot-path performance is acceptable for high-row pages.

Access strategy:
- If SSH/production DB credentials are available, first run read-only checks only.
- Do not mutate production DB, queue, readiness flags, worker state, or app state without an explicit runbook and approval.
- If SSH/production DB access is unavailable, use an equivalent staging/local Postgres evidence harness if present; otherwise write a hard-stop evidence gap report.

Minimum evidence:
- App Status read model readiness/status sweep for all manifest entries.
- PostgreSQL durable queue dirty-scope/outbox convergence sweep.
- API or browser smoke covering Workbench, search, bank detail, pending invoice, invoice lifecycle, input invoice usage, output invoice collection, OA pending payment, cost statistics, tax offset, no-OA bank batch, turnover ledger, and bank account balance.
- Performance evidence for Workbench active generation, search, bank detail, no-OA bank batch, turnover ledger, cost statistics, and tax offset.
- Evidence that Redis/RabbitMQ are not freshness truth and stale cache is gated behind fresh status.

Acceptance:
- PSCIP-L4 may be claimed only if evidence proves freshness/status correctness, queue convergence, and acceptable performance.
- If evidence cannot be collected, do not claim closure; write an analysis hard-stop report with exact missing access/evidence.
- If evidence finds stale/fresh bugs or performance regressions, fix locally with tests first, then rerun evidence.
- Update this `NEXT-PROMPT.md` and `autonomous/JOURNAL.md` at the end of the boundary.

Suggested local verification before any evidence report:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

Do not claim global closure without production/equivalent freshness and performance evidence.
