# T8 Module IO Contracts Handoff

**Date:** 2026-06-24
**Workstream:** T8 Module docs/contracts
**Status:** ready for controller review
**Runtime behavior:** unchanged

## Scope Completed

Reconciled the shared `read-models` module contract because the T8 prompt did not include a concrete assigned page module list and the requested targets map directly to the shared read model/runtime boundary:

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
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-read-models.md`
- `.planning/refactors/modular-io-boundaries/parallel/handoffs/T8-module-io-contracts.md`

## Evidence Used

- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- Existing module docs for bank detail, account balance, workbench relations, search, no-OA, turnover, cost, tax, invoice usage and pending/OA pending read models.
- Existing modular IO analysis files under `.planning/refactors/modular-io-boundaries/analysis/`.

## Source Limitations

- This handoff file did not exist before this pass.
- No `analysis/module-contract-*.md` files existed before this pass.
- No specific assigned module list was present in the T8 prompt.
- No runtime code, controller-only files or production evidence files were edited.

## Contract Decisions

- `READ_MODEL_MANIFEST` is the executable contract source for read model key, scope type, refresh event, worker, query status, projection strategy, all-scope semantics, partition key, scoped incremental target, full rebuild fallback, freshness proof, force refresh, operation barrier, repository port, owners and test owner.
- `docs/modules/read-models/README.md` now records the shared IO surface rather than duplicating per-page DTO fields.
- Page modules continue to own page-specific API shape, UI state, export fields, permission wording and business rules.
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
