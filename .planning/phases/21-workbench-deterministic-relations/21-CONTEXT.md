---
phase: 21-workbench-deterministic-relations
source: Grillme decisions approved across the current task
created: 2026-07-14
---

# Phase 21 Context

<domain>
## Scope

Close the reconciliation Workbench relation-visibility defect end to end. The canonical relation fact remains `app.workbench_pair_relations`; the Workbench and downstream read models are projections, never alternate relation truth. The implementation must repair both deterministic automatic matching and exact visibility without changing unrelated business relation modes.

</domain>

<decisions>
## Locked Decisions

### D-01 — Exactly two user-visible relation states

The Workbench exposes only:

1. Paired: the fact is a member of one active canonical relation.
2. Unpaired: the eligible fact is not in an active relation and appears as its own row.

Candidate, proposed, automatic-decision, automatic-match, source-linked and auto-closed are not user-visible or persisted business relation states.

### D-02 — Exact visibility partition

Let `C` be eligible canonical facts, `R` active relation members, `P` visible paired facts and `U` visible unpaired facts. The invariant is `P = R`, `U = C - R`, `P ∩ U = ∅`, `P ∪ U = C`, and each canonical fact appears exactly once.

### D-03 — Safe automatic results become formal immediately

A deterministic safe match must call the existing `WorkbenchRelationCommandService`/relation UoW and create or extend an active formal relation in the same orchestration path. No candidate or decision row is written first. Results that do not pass the safe rule create no relationship and leave every fact visible as an unpaired singleton.

### D-04 — Formal relation origin is audit metadata only

Manual confirmation, historical creation and system automatic creation share the same lifecycle, visibility and downstream behavior. Origin/rule/version/evidence may remain in immutable audit metadata, but must not branch relation status, projection or API behavior. Existing `manual_confirmed` storage may be treated as the generic confirmed mode rather than adding `automatic_confirmed`.

### D-05 — Existing active relations are preserved

Every pre-migration active canonical relation remains active and unchanged. Historical group IDs such as `case:decision:*` do not control visibility. If the current canonical state is active, the group is paired.

### D-06 — Cross-month matching

Matching must not stop at the selected month. Explicit unique business references may search all retained history. Strong composite evidence may search a bounded 365-day window. Amount-only, fuzzy-only or date-only similarity never creates a formal relation.

### D-07 — Arbitrary N:M:K shapes

The business model supports one-or-many OA rows, one-or-many bank rows and one-or-many invoices, including legitimate two-pane shapes such as OA+invoice or bank+invoice. There is no business cardinality cap. Computation must cluster by evidence first, remain resource-bounded and fail closed when limits are reached.

### D-08 — Deterministic safety and ambiguity

Inferred formalization requires currency/direction compatibility, exact amount closure across the participating panes, connected strong-evidence graph, a unique valid partition, no active-row overlap and no withdrawal block. Multiple valid partitions, conflicts or incomplete evidence create no relation. Explicit unique source references may create or extend a formal partial relation before amount closure when the reference itself proves ownership.

### D-09 — Negative/refund/reversal safety

Generic inferred matching applies to compatible positive flows. Red invoices, refunds and reversals auto-formalize only when an explicit unique original-reference link proves the relationship; otherwise they remain unpaired.

### D-10 — Simple lifecycle

An active relation persists until an explicit audited withdraw/cancel. Source-version changes do not automatically withdraw it. Hard corruption is an internal audit/repair condition, not a third relation state. An explicit user withdrawal blocks automatic recreation of the same canonical row set.

### D-11 — Projection is relation-only

Projection reads canonical facts plus active relations. Active relations become paired groups; every remaining eligible fact becomes one unpaired singleton. Projection must not infer, promote, demote, merge or hide candidate groups.

### D-12 — All-scope composition

`month=all` must union every active month-shard member by canonical object identity. It must aggregate group headers without choosing only the latest shard, and list/detail/Audit must share the same active-generation boundary. The known 13 omitted active input invoices are a required regression fixture.

### D-13 — One modular I/O chain

The target flow is: bulk canonical fact reader -> pure deterministic matcher -> orchestrator -> existing formal relation command/UoW -> history/outbox -> read-model workers. SQL stays in repositories; routes/pages never infer relationships; services do no per-row I/O; refresh uses the existing gateway and durable PostgreSQL queue. No replacement candidate service/table is allowed.

### D-14 — Full legacy removal

After a whole-repository caller scan and porting still-valid deterministic rules, remove both legacy systems: `workbench_candidate_matches`/`WorkbenchCandidateMatchService` and `workbench_reconciliation_decisions`/`WorkbenchReconciliationDecisionStore`, including models, protocols, adapters, orchestrator dual mode, projection hooks/stubs, grouping heuristics, repository automatic-group filters, API/frontend states, tests, tools, grants and indexes. Use a forward migration; never rewrite historical migrations. Unrelated UI selection variables named `candidate` and exception evidence are not relation states and are out of this deletion scope.

### D-15 — Manifest-driven migration and rollback

Before backfill, capture canonical fact hashes, active relations/history, visibility sets, queue/freshness state and old candidate/decision inventories. Re-evaluate old candidate material from current canonical facts; never trust old status/confidence. Only `promote_safe` groups create formal relations. Rollback may withdraw only relation IDs created by the migration manifest. Existing relations and canonical facts are never rewritten.

### D-16 — Required counterexamples and closure evidence

The Yunnan Lifu invoice `26532000000716859331` (`inv_imported_0369`), OA `oa-pay-2169`, amount 520.00 already exists in an active canonical relation and must display as paired without recreation. The 13 active input invoices previously omitted by all-scope composition, totaling 1709.49, must display as unpaired singleton rows unless a canonical active relation exists. Data hashes, active relation preservation, no overlap, no hidden facts, worker drain, freshness and System Audit must all pass.

</decisions>

<canonical_refs>
## Canonical References

### Product and architecture

- `docs/product-specs/workbench.md` — Workbench business behavior.
- `docs/product-specs/reconciliation.md` — Relation/reconciliation rules.
- `docs/architecture/module-boundaries/canonical-facts.md` — Canonical fact ownership.
- `docs/architecture/module-boundaries/read-model-contracts.md` — Freshness and projection contracts.
- `docs/operations/runtime-worker-governance.md` — Durable queue and worker operations.

### Module boundaries

- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`
- `docs/modules/reconciliation-workbench/state-machine.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/read-models/boundary-io.md`
- `docs/modules/runtime-workers/boundary-io.md`

### Current code entry points

- `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`
- `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`
- `backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`
- `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
- `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/features/workbench/api.ts`

</canonical_refs>

<scope_fence>
## Scope Fence

- Preserve unrelated relation modes such as ETC, batch accounting, turnover closure and no-OA/bank-flow batches; they encode business ownership rather than creation origin.
- Do not create a new universal fact service, a new relation status hierarchy or a replacement candidate table.
- Do not deploy to or mutate a real production environment without passing repository safety gates and using the authorized operational entry points. Local and disposable-PostgreSQL verification must complete first.
- No raw user prompt is copied into long-term `docs/`; only approved business and architecture facts are promoted after implementation review.

</scope_fence>

<deferred>
## Deferred Ideas

None. The phase must close implementation, legacy deletion, migration, tests, docs and controlled data verification together.

</deferred>
