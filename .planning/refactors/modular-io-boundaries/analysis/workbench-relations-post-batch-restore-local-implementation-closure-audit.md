# Workbench Relations Post-Batch Restore Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:post-batch-restore-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Do not mark `workbench_relation` locally closed or production-evidence-deferred yet.

Select the next narrow audit:

`workbench-relations:turnover-workbench-pair-port-boundary-audit`

## Evidence Reviewed

Completed local support slices now include:

- read model repository port extraction;
- derived lifecycle executor extraction;
- transaction persist repository owner split;
- command repository snapshot adapter extraction;
- non-transactional pair relation persist service extraction;
- pair relation rollback restore service extraction;
- exception rollback restore service extraction;
- batch-accounting pair restore helper audit;
- batch-accounting pair restore service delegation.

Code/text scan reviewed:

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- relevant downstream module docs for batch-accounting, turnover-ledger, no-OA, pending-invoices and ETC tickets.

## Remaining Local Surfaces

| Surface | Current classification | Reason |
| --- | --- | --- |
| `WorkbenchWriteFacade` pair relation callbacks | partially acceptable dependency assembly, still large | It still accepts `pair_relation_service`, persist/schedule/restore callbacks and relation command service factory. Several callbacks now delegate to explicit services, but the facade still mixes domain read snapshot usage and write orchestration. Needs later focused audit; too large to be the next immediate slice. |
| `TurnoverLedgerWorkbenchPairPort` and turnover primary/fallback builders | implementation-gap-open | It still accepts `pair_relation_service`, `persist_pair_relations(_in_transaction)` and relation command factory. Current code appears to prefer command service for writes, but the pair service/fallback wiring needs classification before full module closure. |
| `PendingInvoiceQueryService` and `PendingInvoiceApplicationService` pair relation constructor dependency | implementation-gap-open | Pending invoice writes require command service, but constructors still accept the pair relation service and store `_pair_relation_service`. Needs a separate read/write dependency classification before removal/quarantine. |
| `NoOaBankBatchService` and `NoOaBankBatchApplicationService` pair relation constructor dependency | implementation-gap-open | Prior slices removed direct legacy writes, but constructors still retain pair relation service references. Needs a separate classification of read-only compatibility versus removable dependency. |
| Historical ETC repair/link/migration `persist_pair_relations` callback | likely compat-only, not closed | ETC write paths use command service, but repair/link services still receive persist callback for relation metadata/update side effects. Needs narrower audit before claiming closure. |
| App-level pair relation service bootstrap/read helpers | expected domain/runtime state, not automatically removable | `_workbench_pair_relation_service` is still the in-memory domain snapshot for local/runtime compatibility and command repository adapter. It is not itself a bug, but every downstream direct dependency must be classified. |

## Next Boundary Rationale

`TurnoverLedgerWorkbenchPairPort` is the smallest high-value next audit because:

- it is isolated in `turnover_ledger_write_adapters.py`;
- `server.py` wiring has clear primary and legacy fallback builder call sites;
- the docs already require turnover closure/withdraw to use `WorkbenchRelationCommandService` and guard against pair-service-only fallback;
- it directly affects cross-page relation consistency and local closure semantics;
- it is narrower than auditing all WorkbenchWriteFacade callbacks or all pending/no-OA dependencies at once.

The next audit should decide whether the turnover pair port can become command-service-only, or whether any pair service dependency must remain `compat-only` with an owner, caller list, deletion condition, forbidden write list and guard tests.

## Closure Assessment

| Requirement | Local status |
| --- | --- |
| IO contract | partially satisfied through read facade, command service and extracted helper services |
| Public/internal boundary | still open because turnover, pending, no-OA, ETC and WorkbenchWriteFacade relation dependencies remain classified only partially |
| Canonical fact owner | partially satisfied; command service owns many writes, but remaining pair service dependencies must be proven read-only/compat-only or removed |
| Shared fact source | partially satisfied; `workbench_relation` read model remains shared downstream source |
| Read model/freshness/force refresh/operation barrier | locally covered for many paths, but module-level closure still cannot be claimed without remaining dependency classification and production evidence/defer |
| Legacy removal/quarantine | incomplete |
| Permission/audit/test contracts | partially covered by existing Workbench/downstream tests; not full module closed |
| Environment evidence | production PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable in this local run |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This audit closes as `analysis-closed`; `workbench_relation` remains `implementation-gap-open`.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. No business rule changed in this audit. |
| Service-layer tests | Not applicable for this audit. |
| API contract tests | Not applicable. No HTTP behavior changed. |
| Read model/cache/background job tests | Not applicable. No runtime behavior changed. |
| Frontend component and interaction tests | Not applicable. |
| End-to-end business-flow integration tests | Not applicable. |
| Existing feature regression tests | Applicable through docs/diff verification and impact review. |

## Verification

Required before commit:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the post-batch-restore local implementation closure audit. It does not close `workbench_relation`, validate production evidence, or unblock Go admission.
