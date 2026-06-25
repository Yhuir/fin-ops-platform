# Next Prompt

Continue the user-authorized `main-read-model-closure` run.

## Current State

- Branch: `main`.
- Current main commit: `2c7a9eac64c1758e5f7e6bf0de1a6667b3b50f1b`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260625-230543`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest completed boundary: `main-read-model-closure:production-or-equivalent-freshness-performance-evidence`.
- Evidence gap report: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-equivalent-evidence-gap-2026-06-25.md`.
- Local closure audit: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-local-owner-split-closure-audit-2026-06-25.md`.
- Local PSCIP-L3 owner split is complete for all known non-Workbench App Status read models.
- Workbench remains the documented active-generation exception and must not be mechanically converted.
- PSCIP-L4 is not proven.

## Evidence Summary

- Production is reachable read-only through `finops-prod-root`.
- Production service is running release commit `67271c7f67291a2fcf393f1fa0ad33be9e84f413`, not current `main`.
- Current `main` includes owner split commits after that release, so existing production evidence cannot prove current-main PSCIP-L4.
- A current-code/local-backend probe over SSH-tunneled production dependencies showed:
  - `bank_details`, `no_oa_bank_batch`, and `workbench` sampled endpoints were fresh.
  - `search` was `stale`.
  - `cost_statistics` and `tax_offset` were `refreshing`.
  - Fresh gates did not report sampled stale/mismatched payloads as fresh.
- Local SSH-tunnel latency is not acceptable as production performance evidence.
- No production DB write, deploy, queue mutation, readiness mutation, worker replay, service restart or secret output occurred.

## Required First Steps On Resume

1. Confirm `git status --short --branch`; stop if unrelated dirty files would be committed.
2. Confirm `main` is fast-forward synced with `origin/main`.
3. Read:
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-equivalent-evidence-gap-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-local-owner-split-closure-audit-2026-06-25.md`
   - `deploy/oa/README.md`
   - `scripts/deploy-oa.sh`
   - `scripts/deploy_oa.py`
   - `docs/operations/runtime-worker-governance.md`
4. Use CodeGraph before code edits. If the boundary is deployment/evidence-only, code edits are not expected.

## Next Boundary

`main-read-model-closure:controlled-main-deploy-and-post-deploy-read-model-evidence-runbook`

Goal:
- Prepare the minimal safe path to deploy current `main` and collect post-deploy PSCIP-L4 evidence.
- Do not deploy until the runbook is explicit and the operator has approved production deploy/restart operations.

Acceptance:
- If deployment is approved, deploy current `main` using the repository production entrypoint and collect post-deploy evidence:
  - release identity equals current `main`;
  - `/health` and `/health/ready` are ready;
  - App Status readiness is fresh for all manifest read models;
  - dirty scopes/outbox/dead-letter facts converge;
  - required workers are current and healthy;
  - sampled API/browser endpoints return fresh or correct stale/refreshing status;
  - hot-path/high-row query plan or latency evidence is collected for Workbench, search, bank detail, no-OA bank batch, turnover ledger, cost statistics, and tax offset.
- If deployment is not approved or cannot be performed safely, do not claim PSCIP-L4. Write a precise deploy/evidence hard-stop report and keep the goal active or blocked only after the strict blocked-audit threshold is met.
- No production DB write, queue mutation, readiness mutation, worker replay, force refresh, or repair unless a committed/recorded explicit-scope runbook is approved.
- Do not implement Go, Go Fiber or Go Worker.
- This boundary is deploy/evidence only; any Go hot-path work remains separately admission-gated by performance evidence, rollback proof, and an explicit implementation prompt.
- Update this `NEXT-PROMPT.md` and `autonomous/JOURNAL.md` at the end of the boundary.

Suggested local verification before any deploy/evidence action:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

Do not claim global closure without production/equivalent freshness and performance evidence from the current main implementation.
