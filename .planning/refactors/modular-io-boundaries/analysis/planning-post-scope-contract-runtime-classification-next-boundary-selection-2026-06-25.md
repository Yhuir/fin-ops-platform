# Planning Post Scope Contract Runtime Classification Next Boundary Selection 2026-06-25

**Boundary:** `planning:post-scope-contract-runtime-classification-next-boundary-selection`
**Final status:** `planning-closed`
**Module closure:** `not-applicable`
**Controller:** T0
**Base commit:** `4b2e47f5`

## Target

Reconcile the clean row245 production read-model matrix and row246 clean scope-contract dry-run classification, then select exactly one next safe boundary. This slice must not claim module/global closure and must not create worker threads before file ownership and expected evidence are mapped.

## Evidence Read

- `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
- `analysis/commit-backed-state-reconciliation-2026-06-25.md`
- `docs/modules/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/STATE.md`
- `autonomous/NEXT-PROMPT.md`
- `12-PARALLEL-ORCHESTRATION.md`
- T1-T8 handoff summaries under `parallel/handoffs/`

## Current Evidence Reconciliation

Row245 proves current production read-model runtime health is clean:

- all App Status read-model readiness rows are `fresh`;
- all dirty scopes are `done`;
- read-model refresh outbox events are `done`;
- read-model dead-letter groups are empty;
- current workers have fresh heartbeats;
- read-model row-count/source-version tables are queryable;
- Workbench high-row table counts are visible.

Row246 removes the specific scope-contract residue concern:

- cost-statistics scope contract dry-run is `ok=true` with `violation_count=0`;
- there are no covered historical or current uncovered failures;
- invalid read-model scope dry-run is `ok=true` with `invalid_scope_count=0`;
- legacy `cost` / `tax` rows are historical `done` dirty scopes only, with no active outbox or readiness residue.

These are production evidence improvements. They still do not prove:

- authenticated API response shapes for each module;
- browser rendering and operation-barrier behavior against real production data;
- high-row page performance, export behavior or visual safety;
- module-specific mapping from local code/test/docs evidence to row245 production facts;
- final global modular IO closure;
- Go admission.

## Candidate Next Boundaries

| Candidate | Decision | Reason |
| --- | --- | --- |
| `planning:final-global-closure-audit` | Rejected | No product module has `Module Closure = closed`; browser/API/high-row and module-specific closure audits remain missing. |
| immediate worker wave | Rejected for this slice | `12-PARALLEL-ORCHESTRATION.md` requires controller to map worker scopes, file ownership, base commit and expected handoff before creating workers. |
| production `--apply` / cleanup | Rejected | Row246 dry-runs are clean; no current-effective cleanup candidate exists. |
| Go/Fiber/Go Worker admission | Rejected | Commit-backed reconciliation and T7 keep Go admission at 0; performance, shadow diff and rollback evidence remain absent. |
| broad browser/API smoke execution | Deferred | Useful, but first the controller must decide which modules, pages, credentials-free endpoints, high-row signals and file owners are in scope. |
| module-specific production closure audit wave selection | Accepted as direction | Row245/246 make it safe to move from global read-model evidence to module-specific closure mapping, but the first step must be an ownership/evidence map. |

## Selected Next Boundary

Select `planning:read-model-module-closure-evidence-ownership-map`.

This next boundary should produce a controller-owned map for the read-model-heavy modules that remain `not-module-closed` or `implementation-gap-open`, including:

- module key and route/API surface;
- local implementation evidence files and test owners;
- row245 production readiness/dirty/outbox/source-version/row-count evidence applicable to the module;
- remaining authenticated API, browser and high-row evidence gaps;
- whether evidence can be collected by T0 production read-only checks, local browser/API tests, or worker threads;
- file ownership for any worker wave;
- the exact first worker wave or single-thread boundary to execute after the map.

The next boundary must not itself claim closure unless it directly proves every closure criterion for a module, which is not expected.

## Initial Module Set For The Map

Prioritize read-model-heavy modules already represented in row245 and the module docs:

| Module | Reason to include |
| --- | --- |
| `reconciliation-workbench` | Workbench has the largest high-row production tables and active generation semantics. |
| `workbench-relations` | Many downstream pages depend on relation source-version proof. |
| `bank-details` | Bank detail has high dirty-scope counts and account-balance adjacency. |
| `bank-account-balance` | All-only read model must be mapped separately from bank detail rows. |
| `pending-invoices` | Page-first-screen scope contract and relation dependency remain closure-critical. |
| `input-invoice-usage` | Rows and filter-options combined freshness was recently fixed by T4; production/browser proof remains open. |
| `output-invoice-collections` | Same combined freshness and relation detail production fail-closed proof needs module mapping. |
| `oa-pending-payments` | Shares invoice usage worker family and relation dependencies. |
| `invoice_lifecycle` | Shared upstream lifecycle read model for multiple pages. |
| `tax-offset` | Tax page has cache warmup/runtime executor history and production/browser evidence gaps. |
| `cost-statistics` | Parent aggregate and scope-contract history require explicit module closure mapping. |
| `turnover-ledger` | Browser operation-barrier flow exists locally, but real high-row grouped ledger evidence remains open. |
| `no-oa-bank-batches` | Recent production FK fix converged, but module closure still needs read/API/browser mapping. |
| `search` | Search production fail-closed and worker fan-out evidence need API/high-row mapping. |

Batch accounting, ETC, imports, settings, app-health and runtime-workers remain relevant for final closure, but the next map should first cover the read-model production matrix modules so row245/246 evidence is usable.

## State-Machine Impact

No state-machine definitions change. This slice only advances queue accounting and selects the next planning boundary. Existing status semantics remain valid:

- row247 closes as `planning-closed`;
- module closure remains `not-applicable` for this planning slice;
- the next selected row remains `not-module-closed` until it proves otherwise.

## Docs Impact

No long-term docs update is required. The selected next boundary will read module docs and may update them only if it changes module facts, tests, risks or verification status.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | Planning-only; no business rule changed. |
| 2. Service-layer tests | Not applicable | No service/repository/worker code changed. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Evidence-only | Row245/246 production evidence is considered but this slice adds no runtime behavior. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No business flow changed. |
| 7. Existing feature regression tests | Evidence-only | This slice prevents an unsafe closure claim by preserving explicit next evidence gaps. |

## Verification Plan

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check`
