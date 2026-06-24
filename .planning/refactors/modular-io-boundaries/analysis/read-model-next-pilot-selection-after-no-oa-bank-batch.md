# Read Model Next Pilot Selection After No-OA Bank Batch

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-no-oa-bank-batch`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Select the next non-Go read model modular IO pilot after local no-OA support was accounted for, without starting Go/Fiber/Go Worker work.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-post-full-state-local-implementation-closure-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-search-and-no-oa-bank-batch-contract.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-and-bank-account-balance-contract.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/bank-details/README.md`
- `docs/modules/bank-details/state-machine.md`
- `docs/modules/bank-details/tests.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- CodeGraph impact for `rebuild_search_index_scope` and `rebuild_bank_account_balance_read_model`

## Candidate Comparison

| Candidate | Stale-read / cross-page risk | Current boundary quality | First useful boundary | Decision |
| --- | --- | --- | --- | --- |
| `search` | High. Search indexes Workbench, bank, invoice and relation-derived user navigation; relation/import/tax/cost/lifecycle changes enqueue it, and stale index rows can send users to old group context. | Manifest, worker registry, scope policy and tests exist, but search query, source-version proof, enqueue, rebuild and invalidation helpers still live on `Application`; projection uses broad `PostgresReadModelRepository` for `save_search_index_rows(...)`. Multiple worker lanes (`search`, `search-secondary`, `search-tertiary`, compat `search-pending`) increase contamination risk. | `read-models:search-repository-port-extraction`: add a narrow `SearchReadModelRepositoryPort` for `search_index` and `save_search_index_rows`, then wire SQL read/projection paths through it without changing API shape or worker semantics. | Select now. |
| `bank_account_balance` | Medium. It is user-visible on Bank Details accounts and important after bank import, but it is a supporting read model under the already-started Bank Details domain rather than a broad cross-page index. | Manifest, App Status, worker registry, backfill, projection tests and freshness behavior exist. Main local gaps are narrower: projection writes through broad repository, reads are exposed through Bank Detail read port/service, and derived lifecycle enqueue still has an app-owned helper. | Later `read-models:bank-account-balance-repository-port-extraction` or freshness audit. | Defer. |

## Decision

Select `search` as the twelfth non-Go read model implementation pilot.

Rationale:

- It has the larger cross-page stale-read blast radius after Workbench relation, invoice lifecycle, pending invoice, tax/cost and import fan-out changes.
- It still has app-owned query/freshness/enqueue/rebuild/invalidation helpers in `Application`, which conflicts with the modular IO target more strongly than the narrower account balance gaps.
- It is a better prerequisite before Go hot-path admission because Go/Fiber search/read-model-builder candidates must not inherit broad Python `Application` helper ownership.
- `bank_account_balance` remains important but narrower and already documented under Bank Details; it should follow after search or as a dedicated Bank Details support read model slice.

## Next Boundary

Insert and execute:

`read-models:search-repository-port-extraction`

First-slice scope:

- Add a narrow search read model repository port exposing only manifest-listed `search_index(...)` and `save_search_index_rows(...)`.
- Wire search API SQL read model access and `SearchPendingSqlProjectionBuilder.rebuild_search_index_scope(...)` through the port.
- Preserve existing API response shape, `read_model_status` semantics, source-version proof, worker events, scope policy, queue schema, Redis/cache behavior, permissions and frontend behavior.
- Do not remove app-owned search helpers in this slice unless the port extraction makes a helper provably unused; helper quarantine should be a follow-up audit/extraction boundary.
- Do not implement Go/Fiber/Go Worker.

## State Machine Impact

- `read-models:next-pilot-selection-after-no-oa-bank-batch` transitions to `analysis-closed`.
- `search` becomes the next selected non-Go read model pilot but remains `implementation-gap-open`.
- `bank_account_balance` remains deferred as a later candidate.
- Go hot-path admission remains `blocked-by-read-model-implementation-prerequisites`.
- No workflow state definitions changed; no module state-machine definitions changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | This selection slice changes no search ranking, matching, amount, relation, invoice or bank business rule. |
| 2. Service-layer tests | Not applicable for this slice | No service behavior changes; next implementation slice must add repository port/service wiring tests. |
| 3. API contract tests | Not applicable for this slice | No HTTP status, payload shape, error or permission behavior changes. |
| 4. Read model/cache/background job tests | Applicable as planning evidence | Existing search and balance read model tests were identified as required verification for the next slice. |
| 5. Frontend component and interaction tests | Not applicable | `/api/search` currently has no independent frontend route; no UI behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No import/relation/worker execution changed in this slice. |
| 7. Existing feature regression tests | Applicable as planning evidence | Next search slice must preserve `tests/test_search_pending_sql_runtime.py`, runtime worker registry and manifest contracts. |

## Verification

Required for this planning slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

If Python code changes before commit, also run:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```
