# T8 Module IO Contracts Handoff

**Date:** 2026-06-24
**Workstream:** T8 Module docs/contracts
**Status:** ready for controller review
**Runtime behavior:** unchanged

## Scope Completed

Reconciled the shared `read-models` module contract because the T8 prompt did not include a concrete assigned page module list and the requested targets map directly to the shared read model/runtime boundary.

After T1-T7 handoffs became available, T8 also consumed concrete page-module contract implications from T4 frontend freshness work and reconciled:

- `input-invoice-usage`
- `output-invoice-collections`
- `workbench-relations`
- `runtime-workers`
- `reconciliation-workbench`
- `batch-accounting`

The page contracts now explicitly record that rows and filter-options must both be fresh before the page may show a normal empty state or enable export. Workbench, Workbench relation, batch accounting and runtime worker contracts now have module-contract analysis artifacts covering route-owner/legacy quarantine, durable queue/App Status/operation barrier, relation command boundaries and Go admission deferral boundaries.

- input/output/state/event/read model/permission/test contracts
- public/internal surfaces
- legacy status
- read model refresh and force refresh contracts
- partitioned scoped incremental projection target

## Files Changed

- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/input-invoice-usage/state-machine.md`
- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/output-invoice-collections/state-machine.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-read-models.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-input-invoice-usage.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-output-invoice-collections.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-workbench-relations.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-runtime-workers.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-reconciliation-workbench.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-batch-accounting.md`
- `.planning/refactors/modular-io-boundaries/parallel/handoffs/T8-module-io-contracts.md`

## Evidence Used

- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- Existing module docs for bank detail, account balance, workbench relations, search, no-OA, turnover, cost, tax, invoice usage and pending/OA pending read models.
- Existing modular IO analysis files under `.planning/refactors/modular-io-boundaries/analysis/`.
- `T1-server-route-owner.md` for Workbench group detail route-owner contract.
- `T3-worker-queue-app-status.md` for worker/durable queue/App Status/operation barrier contract.
- `T4-frontend-freshness.md` for input/output invoice rows + filter-options combined freshness contract.
- `T5-legacy-contamination.md` for Workbench row-detail and batch-accounting legacy quarantine constraints.
- `T7-go-admission-evidence.md` for runtime worker Go admission deferral constraints.

## Source Limitations

- This handoff file did not exist before this pass.
- No `analysis/module-contract-*.md` files existed before this pass.
- No specific assigned module list was present in the T8 prompt.
- No runtime code, controller-only files or production evidence files were edited.

## Contract Decisions

- `READ_MODEL_MANIFEST` is the executable contract source for read model key, scope type, refresh event, worker, query status, projection strategy, all-scope semantics, partition key, scoped incremental target, full rebuild fallback, freshness proof, force refresh, operation barrier, repository port, owners and test owner.
- `docs/modules/read-models/README.md` now records the shared IO surface rather than duplicating per-page DTO fields.
- Page modules continue to own page-specific API shape, UI state, export fields, permission wording and business rules.
- `input-invoice-usage` and `output-invoice-collections` now explicitly treat rows and filter-options as a combined page freshness proof. Rows fresh + filter-options stale remains non-fresh for empty/export behavior.
- `workbench-relations` module contract records group-detail route owner as read-only HTTP mapping, relation writes through command service, and legacy row-detail / batch-accounting repair paths as quarantined compatibility surfaces.
- `runtime-workers` module contract records durable queue/App Status/operation barrier ownership and keeps Go hot-path work blocked/deferred until admission evidence is complete.
- `reconciliation-workbench` module contract records Workbench active-generation/query/action boundaries, route-owner HTTP mapping and legacy action quarantine.
- `batch-accounting` module contract records GET read-only route ownership, submit/withdraw relation command-service boundaries and the retained legacy case-id repair quarantine.
- Legacy/local query fallback is `compat-only` and cannot serve production fresh data.
- Force refresh requires controlled caller, scope validation, dedupe/idempotency, readiness proof and audit.
- Fan-out-only `all` is a refresh command, not a queryable freshness proof, unless a real parent aggregate proof is explicitly defined.

## Test Contract Decision

- No tests were added because this is documentation/accounting only.
- Applicable existing regression layers:
  - `tests/test_read_model_manifest.py`
  - `tests/test_read_model_refresh_gateway.py`
  - `tests/test_operation_freshness_barrier.py`
  - `tests/test_runtime_worker_registry.py`
  - `tests/test_read_model_scope_contract.py`
  - `tests/test_read_model_architecture_guards.py`
  - `web/src/test/InputInvoiceUsagePage.test.tsx`
  - `web/src/test/OutputInvoiceCollectionsPage.test.tsx`
  - module-specific SQL runtime and repository port tests.

## Verification

Recommended/attempted by T8:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Controller Follow-Up

- If T0 intended a concrete page-module subset for T8, assign that list explicitly. The next worker should fill page-specific API/DTO/UI/export/permission details inside those module docs while keeping the shared read-model contract as the baseline.
- If T0 accepts this shared-contract pass, no runtime follow-up is required from T8.
