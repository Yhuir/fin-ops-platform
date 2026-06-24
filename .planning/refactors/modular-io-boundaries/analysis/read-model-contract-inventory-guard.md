# Read model contract inventory guard

**Date:** 2026-06-24

## Scope

Close documentation/test gaps for read model contracts that do not require controller-only state edits.

Allowed scope used:

- `docs/modules/read-models/`
- backend read model manifest/tests
- `.planning/refactors/modular-io-boundaries/analysis/read-model-*.md`

The requested handoff path `.planning/refactors/modular-io-boundaries/parallel/handoffs/T2-read-model-contracts.md` was not present; only `.planning/refactors/modular-io-boundaries/parallel/handoffs/.gitkeep` exists.

## Findings

`READ_MODEL_MANIFEST` already covered:

- `read_model_key`
- `scope_type`
- refresh event
- primary and auxiliary worker instances
- query freshness contract
- projection strategy
- `all` scope semantics
- force refresh contract
- operation barrier contract
- repository/query/permission/test owners

The local gap was that the manifest and central docs did not explicitly require every entry to record:

- partition key contract
- scoped incremental target
- full rebuild fallback
- freshness proof contract

## Changes

- Added `partition_key_contract`, `scoped_incremental_target`, `full_rebuild_fallback` and `freshness_proof_contract` to `ReadModelManifestEntry`.
- Populated the four fields for all 14 App Status read models.
- Added `tests/test_read_model_manifest.py::ReadModelManifestTests.test_manifest_entries_record_partition_rebuild_and_freshness_contracts` so future entries cannot omit these contract facts.
- Added the mirrored 14-row contract inventory to `docs/modules/read-models/README.md`.
- Added read-models test matrix and implementation notes entries for this guard.

## Contract Coverage

The updated manifest records each read model's force refresh and operation barrier contract:

- `workbench`: active generation force refresh; App Status operation barrier target.
- `pending_invoice`: page-first-screen force refresh; App Status operation barrier target.
- all other listed read models: gateway force refresh; App Status operation barrier target.

The manifest also records each read model's partition/freshness proof. Special cases are explicit:

- `bank_account_balance` remains all-only.
- `pending_invoice` rejects bare `all`.
- `cost_statistics` has queryable parent aggregate semantics.
- fan-out-only `all` scopes are documented as fan-out control scopes, not queryable parent freshness proofs.

## Tests

Added/changed:

- `tests/test_read_model_manifest.py`

Covered categories:

- Read model, cache and background job tests: manifest parity and contract completeness guard.
- Existing feature regression tests: prevents read model contract drift when new entries or scope/refresh/barrier fields are changed.

Not applicable:

- Business core unit tests: no business rule/state transition changed.
- Service-layer tests: no service orchestration or repository behavior changed.
- API contract tests: no HTTP response shape/status changed.
- Frontend component and interaction tests: no UI changed.
- End-to-end business-flow integration tests: no cross-module runtime behavior changed.

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v
```

Result: passed.

## Remaining Risk

This slice proves the contract is recorded and guarded locally. It does not prove real PostgreSQL worker drain, App Status freshness, production operation-barrier latency, high-row performance or browser behavior; those remain owned by the module-specific runtime and smoke tests.
