# Read Model No-OA Bank Batch Event FK Delete Order Fix 2026-06-25

**Boundary:** `read-models:no-oa-bank-batch-event-fk-delete-order-fix`
**Final status:** `implementation-closed`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `e9d9ce0a7206e4e757cf12e38396e767b5ef2ace`

## Target Boundary

Fix the local repository write-order bug proven by `production-no-oa-bank-batch-dead-letter-read-only-diagnosis-2026-06-25.md`.

Production evidence showed `no_oa_bank_batch.read_model.refresh` dead-lettering because `app.no_oa_bank_batch_events` still referenced a superseded `app.no_oa_bank_batches` row that the public snapshot replacement attempted to delete.

## Changes

- Updated `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`.
- When replacing no-OA public snapshots with a non-empty retained batch set, the repository now deletes event rows referencing batches outside the retained `batch_id` set before deleting those removed batches.
- When replacing with an empty snapshot, the repository now deletes `app.no_oa_bank_batch_events` before deleting `app.no_oa_bank_batches`.
- Existing retained-batch event replacement still happens after retained batch upsert through `_replace_no_oa_bank_batch_events(...)`.

## Behavior Kept Unchanged

- No API response shape change.
- No frontend behavior change.
- No queue schema, worker event type, readiness semantics, App Status contract or scope policy change.
- No relation command behavior change.
- No business status normalization change.
- No production mutation or deployment in this implementation boundary.

## Tests Added Or Changed

- Added `tests/test_postgres_repositories_boundaries.py::test_no_oa_bank_batch_save_deletes_removed_events_before_removed_batches`.
- Added `tests/test_postgres_repositories_boundaries.py::test_no_oa_bank_batch_empty_snapshot_deletes_events_before_batches`.

## Seven Test Categories

1. Business core unit tests: not directly applicable; no no-OA batch state machine or classification rule changed.
2. Service-layer tests: covered by repository boundary tests proving persistence ordering, and by no-OA refresh service regression tests.
3. API contract tests: not applicable; HTTP contract unchanged.
4. Read model/cache/background job tests: applicable and covered because the dead-lettering worker path persists the public snapshot through this repository.
5. Frontend component and interaction tests: not applicable; no UI behavior changed.
6. End-to-end business-flow integration tests: not added locally because no local `PGSQL_URL`/staging DB exists; production convergence remains a later controlled boundary after deployment.
7. Existing feature regression tests: covered by the full `test_postgres_repositories_boundaries.py` file and no-OA read model refresh unittest module.

## Verification

```bash
PYTHONPATH=backend/src pytest tests/test_postgres_repositories_boundaries.py -q
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/workbench.py
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh -v
bash scripts/verify.sh docs
git diff --check
```

All commands passed.

## Docs Impact

Docs apply because this changes production read model persistence behavior for the no-OA module. Updated:

- `docs/modules/no-oa-bank-batches/implementation-notes.md`

Long-term product/API/architecture docs do not change because business semantics and public contracts are unchanged.

## Remaining Risk

The fix is local until deployed. Production still has:

- `no_oa_bank_batch:all` dirty scope pending;
- `no_oa_bank_batch.read_model.refresh` dead-lettered event(s);
- `read_model.app_status_readiness` failed for `no_oa_bank_batch:all`.

Next boundary must be a controlled production deploy/convergence runbook or equivalent release path before claiming production closure.
