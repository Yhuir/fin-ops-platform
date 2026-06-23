# Workbench Relations Pending Invoice Pair Service Boundary Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:pending-invoice-pair-service-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit `PendingInvoiceQueryService` and `PendingInvoiceApplicationService` relation dependencies, classify their `pair_relation_service` usage, and select the next narrow boundary without changing pending invoice behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-turnover-workbench-pair-port-unused-persist-callback-removal.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/state-machine.md`
- `docs/modules/pending-invoices/tests.md`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_pending_invoice_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for `PendingInvoiceQueryService`, `PendingInvoiceApplicationService`, `pair_relation_service`, `relation_facade`, and `relation_command_service`.

## Findings

`PendingInvoiceQueryService` currently accepts and stores `pair_relation_service`, but the class does not call it. Relation reads are performed through `relation_facade.get_by_row_ids(...)` in `_relation_distribution_row(...)`.

`PendingInvoiceApplicationService` currently accepts and stores `pair_relation_service`, but the class does not call it. Relation reads are performed through `relation_facade.get_by_row_ids(...)` in `_active_relation_dicts_for_row_ids(...)` and `_relation_distribution_row(...)`. Relation writes are performed through `_require_relation_command_service()` and `WorkbenchRelationCommandService.confirm_relation(...)`.

`Application` still injects `self._workbench_pair_relation_service` into both pending invoice services:

- `PendingInvoiceQueryService(... pair_relation_service=self._workbench_pair_relation_service, relation_facade=self._workbench_relation_read_facade(), ...)`
- `PendingInvoiceApplicationService(... pair_relation_service=self._workbench_pair_relation_service, relation_facade=self._workbench_relation_read_facade(), relation_command_service=self._workbench_relation_command_service(), ...)`

`tests/test_pending_invoice_service.py` fixtures still pass `pair_relation_service`, including blocking fake services whose purpose was to prove writes do not fall back to the legacy pair service. Those tests remain useful, but the stronger next-state guard should prove the pending invoice services do not accept `pair_relation_service` at all.

`tests/test_platform_runtime_boundary_guards.py` already contains a downstream query-service guard that forbids several relation consumers from accepting `pair_relation_service`, but it does not yet include `pending_invoice_service.py`. It also contains legacy allowed-context entries for pending invoice direct pair relation reads; those entries are stale because the audited class now uses `relation_facade` / `relation_command_service`.

## Classification

| Surface | Current classification | Target classification | Evidence |
| --- | --- | --- | --- |
| `PendingInvoiceQueryService.pair_relation_service` | unused injection | removable legacy dependency | Only constructor parameter and `_pair_relation_service` assignment remain. Query relation reads use `relation_facade`. |
| `PendingInvoiceApplicationService.pair_relation_service` | unused injection | removable legacy dependency | Only constructor parameter and `_pair_relation_service` assignment remain. Reads use `relation_facade`; writes use `relation_command_service`. |
| `PendingInvoiceQueryService.relation_facade` | canonical read dependency | keep | Required for relation distribution-backed rows/detail/candidate context. |
| `PendingInvoiceApplicationService.relation_facade` | canonical read dependency | keep | Required for conflict/merge checks and idempotent relation recovery reads. |
| `PendingInvoiceApplicationService.relation_command_service` | canonical write dependency | keep | Required for manual/attach relation confirm and precondition checks. |
| `Application` pending invoice pair service wiring | unused legacy injection | remove next | `server.py` still passes `_workbench_pair_relation_service` to both services. |
| pending invoice tests passing pair service | stale fixture dependency | remove next | Test setup should use facade/command-service fakes only. |

## Decision

The next boundary should be an implementation slice:

`workbench-relations:pending-invoice-unused-pair-service-removal`

Scope:

- Remove `pair_relation_service` parameter and `_pair_relation_service` field from `PendingInvoiceQueryService`.
- Remove `pair_relation_service` parameter and `_pair_relation_service` field from `PendingInvoiceApplicationService`.
- Remove pending invoice `pair_relation_service=...` wiring in `server.py`.
- Update pending invoice tests and fixtures to stop passing pair services.
- Strengthen runtime boundary guards so pending invoice query/application services cannot re-accept or import `WorkbenchPairRelationService`.
- Remove stale guard allowed-context entries for pending invoice pair relation reads if they are no longer needed.

Not in scope:

- Do not change pending invoice attach/manual invoice business rules.
- Do not change API payloads, dirty scope, read model refresh, relation distribution, command log, audit, finalizer or production state.
- Do not change `relation_facade` or `relation_command_service` semantics.
- Do not implement Go/Fiber/Go Worker.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/pending-invoices/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice closes only pending invoice relation dependency classification. `workbench_relation` remains `implementation-gap-open`.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. No business rules changed. |
| Service-layer tests | Not changed in this audit slice. Next implementation slice should update pending invoice service tests/fixtures and boundary guards. |
| API contract tests | Not applicable. No HTTP/API shape changed. |
| Read model/cache/background job tests | Not applicable. No refresh, dirty scope, cache or worker behavior changed. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice. |
| Existing feature regression tests | Covered indirectly by existing pending invoice relation tests remaining unchanged; next implementation slice must run targeted pending invoice service and boundary guard tests. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the pending invoice pair service boundary audit. It does not remove code, close `workbench_relation`, validate production evidence, or unblock Go admission.
