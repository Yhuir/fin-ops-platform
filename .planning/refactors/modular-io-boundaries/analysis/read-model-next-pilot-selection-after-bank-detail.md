# Read Model Next Pilot Selection After Bank Detail

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-bank-detail`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Select `workbench_relation` as the next read model implementation pilot after `bank_detail`.

The next implementation boundary is:

`read-models:workbench-relation-repository-port-extraction`

This slice is planning and selection only. It does not change runtime code, API behavior, read model behavior, workers, production state, or Go/Fiber/Go Worker admission.

## Why `workbench_relation`

`workbench_relation` is the highest-value next pilot because it is the shared relation distribution read model for the pages most likely to show "page A updated, page B still stale" bugs:

- pending invoices;
- OA pending payments;
- input invoice usage;
- output invoice collection;
- bank detail relation tags;
- no-OA bank batches;
- turnover ledger;
- batch accounting;
- cost/tax/search downstream source-version checks.

It already has enough structure for a small, testable next slice:

- `WorkbenchRelationReadFacade` is the downstream read boundary.
- `WorkbenchRelationReadModelRefreshService` handles `workbench_relation.read_model.refresh`.
- `WorkbenchRelationSqlProjectionBuilder` owns scoped distribution projection.
- `READ_MODEL_MANIFEST` already registers key/scope/event/worker/repository methods/test owner.
- `tests/test_workbench_relation_read_facade.py` and workbench relation module tests already cover freshness and candidate/linked semantics.

The first implementation step should not migrate the whole relation write lifecycle. That would pull in workbench command service, pending invoice, no-OA, turnover, ETC, batch accounting and multiple browser flows at once. The safest production-grade next slice is to narrow the read-model repository surface first, matching the successful `bank_detail` repository-port pattern.

## Candidate Comparison

| Candidate | Cross-page freshness value | Current structure | Risk | Decision |
| --- | --- | --- | --- | --- |
| `workbench_relation` | Highest. It is the shared relation distribution source consumed by invoice, OA, bank detail, no-OA, turnover, batch accounting, cost/tax/search flows. | Has read facade, refresh service, projection builder, manifest entry and test matrix. | Large downstream blast radius if write lifecycle is migrated too early. | **Select as next pilot; first boundary is repository port extraction.** |
| `pending_invoice` | High user visibility. | Has page-first-screen scope and source-version checks. | Depends on `bank_detail` and `workbench_relation` source versions; better after relation read boundary narrows. | Defer until `workbench_relation` read boundary is stable. |
| `oa_pending_payment` | High user visibility. | Has OA pending service and relation source-version tests. | Depends on OA facts and relation distribution; fan-out is heavier. | Defer. |
| `invoice_lifecycle` | Medium/high. | Has facade/projection tests. | Shared with pending and invoice usage; less central than relation distribution. | Defer. |
| `input_invoice_usage` | High for downstream relation correctness. | Has relation facade consumers and stale reason tests. | Depends directly on `workbench_relation_source_versions`. | Defer until relation port exists. |
| `output_invoice_collection` | Medium/high. | Has service/API tests. | Relation fan-out dependent. | Defer. |
| `cost_statistics` | High performance/summary value. | Has special parent aggregate semantics. | More complex scope semantics; not the first post-bank-detail pilot. | Defer. |
| `tax_offset` | Medium/high. | Has refresh/runtime tests. | Depends on invoice/relation freshness but less central. | Defer. |
| `turnover_ledger` | Medium/high. | Has relation source-version dependency. | Write lifecycle and relation restore rules are broader than read port. | Defer. |
| `search` | High discoverability value. | Has search-pending projection tests. | Broad index semantics; should follow relation/pending facts. | Defer. |
| `no_oa_bank_batch` | Medium/high. | Has app service/read model refresh docs/tests. | Relation write/read dependencies still need relation boundary first. | Defer. |

## Evidence

Docs and planning evidence:

- `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md` identifies `workbench_relation` as the shared downstream relation distribution read model.
- `.planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md` explicitly deferred `workbench_relation` until after `bank_detail` because the value was highest but blast radius was larger.
- `docs/modules/workbench-relations/README.md` defines `WorkbenchRelationReadFacade` as the only backend read boundary for downstream pages.
- `docs/modules/workbench-relations/tests.md` lists existing unit, API, read model, frontend and E2E coverage that can protect incremental migration.

Code evidence:

- `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py` uses repository methods by dynamic lookup:
  - `get_workbench_relation_rows_by_ids`;
  - `list_workbench_relation_rows`;
  - `get_workbench_relation_groups_by_ids`.
- `backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py` writes distribution through `save_workbench_relation_distribution` and `mark_workbench_relation_scope_empty`.
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` still owns the relation read model SQL together with many other read models.
- `backend/src/fin_ops_platform/services/read_model_manifest.py` registers the current repository contract but it is still a broad `PostgresReadModelRepository.workbench_relation` surface, not a narrow port.

## Next Boundary Contract

`read-models:workbench-relation-repository-port-extraction` should:

- add or identify a narrow `WorkbenchRelationReadModelRepositoryPort`;
- expose only the workbench relation read-model methods needed by the facade/projection builder:
  - `get_workbench_relation_rows_by_ids`;
  - `list_workbench_relation_rows`;
  - `get_workbench_relation_groups_by_ids`;
  - `workbench_relation_source_versions`;
  - `save_workbench_relation_distribution`;
  - `mark_workbench_relation_scope_empty`;
- wire `WorkbenchRelationReadFacade` and `WorkbenchRelationSqlProjectionBuilder` through that port where the app currently passes the broad `read_model_repository`;
- add tests proving unrelated read model repository methods are not exposed through the port;
- preserve all current payload shapes, freshness statuses, source-version semantics, candidate/linked/unlinked semantics and refresh enqueue behavior;
- avoid migrating canonical relation write lifecycle in the same slice;
- avoid Go/Fiber/Go Worker.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/state-machine.md`

No new global or module state definition is required. Existing statuses are sufficient:

- this slice: `analysis-closed`;
- next slice: `implementation-pending`;
- module closure: `implementation-gap-open`;
- Go candidates: `blocked-by-prerequisite`.

Progress/accounting files must be updated to set the next prompt to `read-models:workbench-relation-repository-port-extraction`.

## Seven Test Categories

This slice is analysis-only, so no runtime tests are added.

For the next implementation slice:

| Category | Applies? | Reason |
| --- | --- | --- |
| Business core unit tests | Not for repository port extraction unless relation semantics change; they must remain covered by existing relation service tests. |
| Service-layer tests | Applies. Test the facade/projection builder consume the narrow port and do not require broad repository access. |
| API contract tests | Not directly unless app wiring changes API behavior; keep response-shape regression risk visible. |
| Read model/cache/background job tests | Applies. Preserve freshness, missing/stale enqueue, source versions and distribution save/mark behavior. |
| Frontend component and interaction tests | Not directly for the first port extraction; no UI behavior should change. |
| E2E business-flow integration tests | Not directly for the first port extraction; existing E2E remains regression evidence. |
| Existing feature regression tests | Applies. Ensure linked/candidate/unlinked semantics and downstream source-version behavior remain unchanged. |

## Verification

Required for this analysis-only slice:

- `bash scripts/verify.sh docs`
- `git diff --check`

No application tests are required because runtime code is unchanged.

## Completion Claim

This slice only selects and queues the next pilot. It does not close `workbench_relation`, `bank_detail`, the read model roadmap, or any Go hot-path gate.
