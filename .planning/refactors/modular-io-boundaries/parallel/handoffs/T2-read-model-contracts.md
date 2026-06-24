# T2 Read Model Contracts Handoff

**Date:** 2026-06-24

## Assignment

Close read model contract, documentation and test gaps that do not require controller-only state edits.

Assigned surfaces:

- `docs/modules/read-models/`
- read-model module docs for read-model-heavy page/domain modules
- backend read model manifest/tests when contracts need executable guards
- `.planning/refactors/modular-io-boundaries/analysis/read-model-*.md`

## Current Result

The shared App Status read model contract is now executable in `backend/src/fin_ops_platform/services/read_model_manifest.py` and mirrored in `docs/modules/read-models/README.md`.

Every `READ_MODEL_MANIFEST` entry records:

- `read_model_key`
- `scope_type`
- partition key contract
- scoped incremental target
- full rebuild fallback
- freshness proof contract
- force refresh contract
- operation barrier contract

`tests/test_read_model_manifest.py` verifies:

- manifest covers every App Status read model;
- manifest matches App Status registry, runtime worker registry, RabbitMQ dispatch event contracts and scope policy registry;
- repository port methods exist and have a single manifest owner;
- force refresh and operation barrier contracts are declared;
- partition/rebuild/freshness contracts are non-empty;
- `docs/modules/read-models/README.md` mirrors every manifest contract row.

## Force Refresh And Barrier Audit

No missing force refresh or operation barrier contracts remain in the manifest after this slice.

Special cases are explicit:

- `workbench`: `gateway_force_refresh_active_generation_scope` with active generation freshness proof.
- `pending_invoice`: `gateway_force_refresh_with_page_first_screen_scope`; bare `all` remains rejected.
- `bank_account_balance`: all-only scope contract.
- `cost_statistics`: queryable parent aggregate contract.
- fan-out-only `all` read models: `all` is a refresh command scope, not a queryable parent freshness proof.

All entries use `operation_barrier_contract="app_status_registry_target"`.

## Changed Files For T2

- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `tests/test_read_model_manifest.py`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/read-models/implementation-notes.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-contract-inventory-guard.md`
- `.planning/refactors/modular-io-boundaries/parallel/handoffs/T2-read-model-contracts.md`

## Verification

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v
bash scripts/verify.sh docs
```

Both passed after the T2 guard changes.

## Seven Test Category Decision

Covered:

- Read model, cache and background job tests: manifest/registry/worker/scope/doc contract guard.
- Existing feature regression tests: prevents future contract drift for read model entries.

Not applicable for this slice:

- Business core unit tests: no business rule changed.
- Service-layer tests: no service orchestration or persistence behavior changed.
- API contract tests: no HTTP response shape/status changed.
- Frontend component and interaction tests: no UI changed.
- End-to-end business-flow integration tests: no runtime flow changed.

## Remaining Risks

This handoff does not claim module/global closure. The guard proves local contract inventory completeness only. Real PostgreSQL worker drain, App Status readiness, operation-to-fresh latency, high-row SLO and browser behavior remain owned by module-specific runtime, smoke and page tests.

Do not use this handoff as permission to edit controller-only files. Any future read model behavior mismatch must be resolved in the concrete service/repository/worker owner or by updating the manifest contract and mirrored docs together.
