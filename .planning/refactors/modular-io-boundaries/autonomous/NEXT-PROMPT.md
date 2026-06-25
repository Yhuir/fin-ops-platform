# Next Prompt

Continue after `planning:local-modular-code-closure-reconciliation`.

## Current State

- Branch: `dev`.
- Last completed boundary: `planning:local-modular-code-closure-reconciliation`.
- Commit-backed refresh: `.planning/refactors/modular-io-boundaries/analysis/commit-backed-state-reconciliation-2026-06-25-local-first-refresh.md`.
- Local closure reconciliation: `.planning/refactors/modular-io-boundaries/analysis/local-modular-code-closure-reconciliation-2026-06-25.md`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-route-owner-residual-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `docs/modules/etc-tickets/README.md`
   - `docs/modules/imports-etc-invoices/README.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - relevant ETC/import API tests.
3. Use CodeGraph to inspect:
   - `Application` ETC/import/reconciliation handlers in `server.py`;
   - existing `EtcBusinessBatchApiRoutes` in `routes_etc.py`;
   - current tests covering ETC import/reconciliation routes.
4. Classify one bounded handler group as:
   - extract now;
   - compat-only delegate;
   - already route-owned;
   - blocked by unclear contract.
5. Write an analysis file with the proposed first implementation boundary and required tests/guards.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not do broad `server.py` line-count splitting.
- Do not duplicate existing route owners, services or repositories.
- Do not change business/API response semantics without explicit tests.
