# Phase 2: bank-details-improvements - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning
**Mode:** auto-selected implementation decisions from SPEC.md, Phase 0 baseline, module docs, API docs, and current code structure.

<domain>
## Phase Boundary

Phase 2 delivers a bank-details L2 audit and executable improvement plan. It must answer whether `/bank-details` has risk points, unreasonable architecture, or incomplete functional loops before any behavior-changing implementation happens.

The phase is not a broad rewrite. It first classifies evidence-backed gaps, then plans only bounded fixes or manual validation steps required to close the bank-details page.
</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**9 requirements are locked.** See `02-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `02-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**

- Page-level L2 analysis for `bank-details`.
- Risk audit for architecture, read model freshness, worker boundaries, lifecycle fan-out, permissions, audit, and API contracts.
- Functional closure audit for the bank details page workflows and states.
- Cross-page impact map and minimum smoke/regression scope for bank-details changes.
- Test strategy mapped to the repository's seven test categories.
- A GSD-ready implementation plan for confirmed gaps.
- Phase-local artifacts under `.planning/phases/02-bank-details-improvements/`.

**Out of scope (from SPEC.md):**

- Rewriting bank details architecture before the audit classifies concrete gaps — scope must be justified by evidence first.
- Changing business rules for bank tagging, external turnover, no-OA batches, Workbench relations, invoice lifecycle, tax, or cost statistics without a separate product/API decision.
- Editing `.planning/codebase/*.md` — Phase 0 keeps that as the global map.
- Updating all downstream page modules by default — only update or test downstream areas when a bank-details finding affects them.
- Running production/staging worker drain or real historical-data smoke in this phase — local phase work can document this as residual risk unless an environment is explicitly provided.
- Deleting legacy or transitional paths solely because they look old — cleanup requires the Phase 0 legacy gate.
</spec_lock>

<decisions>
## Implementation Decisions

### Audit-First Execution

- **D-01:** Planning must begin with an evidence-backed audit, not implementation. The audit must read `02-SPEC.md`, `02-PAGE-BASELINE.md`, Phase 0 baseline docs, module docs, API contract docs, and current code/test entry points before recommending fixes.
- **D-02:** Every finding must be classified as `closed`, `partial`, `missing`, `manual-only`, or `deferred`. Only `partial` or `missing` findings with clear owner files, expected behavior, and testable acceptance can become implementation tasks.
- **D-03:** The plan must not create a generic backlog. It should produce the minimum tasks needed to close user-requested bank-details risk, architecture, and functional-loop questions.

### Architecture And Legacy Gate

- **D-04:** Treat `BankDetailsApiRoutes` as the route facade, but classify the active dispatch through `server.py` before editing any bank-details API contract. Existing `server.py` handlers call `_bank_details_routes()` for bank-details endpoints; the phase must verify no parallel active behavior bypasses the route facade.
- **D-05:** Preserve the current backend direction: HTTP/session/permission mapping in routes/server, business orchestration in application/domain services, SQL/table details in repositories/projections, and worker rebuild logic outside HTTP/session/Application coupling.
- **D-06:** Do not delete or bypass transitional paths unless the Phase 0 legacy cleanup gate is completed with caller inventory, canonical replacement tests, and stale-doc cleanup.

### Read Model, Worker, And Freshness Closure

- **D-07:** Treat `bank_detail` and `bank_account_balance` as separate read model contracts. The plan must not allow transaction filters, category filters, search keywords, or tag rules to recompute or overwrite fresh account balances.
- **D-08:** The audit must trace `fresh`, `refreshing`, `stale`, `schema_mismatch`, and `missing` from backend payload to frontend display. A fresh empty payload is the only state that can mean true empty data.
- **D-09:** The plan must map read model refresh through durable queue/outbox and dirty scopes; frontend events are same-browser refetch hints only.

### Mutation And Downstream Closure

- **D-10:** For auto tag save, file replacement, reapply, candidate confirmation, confirmation revoke, manual category assignment, and manual clear, the phase must map `user action -> route -> service -> write/audit -> lifecycle/dirty/outbox -> worker/read model -> frontend feedback/refetch -> tests`.
- **D-11:** Candidate confirmation must remain limited to backend-generated current `auto_candidate_categories`; manual assignment must remain limited to current `unmatched` rows. The plan must not reintroduce arbitrary frontend-side category writes.
- **D-12:** Downstream smoke scope must be selected from actual impact: Workbench, no-OA batches, turnover ledger, pending/search, cost statistics, invoice lifecycle, batch accounting, tax offset, and App Health. Do not test all downstream pages by default; choose based on the finding.

### Functional Closure And UX States

- **D-13:** The functional closure audit must cover accounts, transactions, date/account/search/category filtering, pagination, export, auto-tag rules drawer, reapply, category mutations, relation tags, account balances, loading, empty, error, stale, refreshing, permission disabled, retry/refetch, and unmount/abort behavior.
- **D-14:** UI closure is judged by user-observable behavior and API contract alignment, not component internals.
- **D-15:** Any frontend enhancement must follow existing `BankDetailsPage.tsx`, `web/src/features/bankDetails/api.ts`, `web/src/features/bankDetails/types.ts`, and test helper patterns before adding abstractions.

### Tests, Docs, And Verification

- **D-16:** The plan must evaluate all seven test categories. Existing bank-details tests are strong and should be reused as the baseline; add tests only for real uncovered gaps.
- **D-17:** Minimum local verification for planning/docs-only artifacts is `git diff --check` and, when docs references are changed, `bash scripts/verify.sh docs`. Behavior-changing follow-up plans must choose commands from `docs/modules/bank-details/tests.md`.
- **D-18:** Long-term docs are updated only if the audit or implementation changes durable facts. Otherwise final reporting should state `docs 不适用` for code-neutral phase planning.

### Auto-Selected Gray Areas

- **D-19:** Audit depth: choose comprehensive L2 audit because the user explicitly asked for risks, unreasonable architecture, and complete closure.
- **D-20:** Implementation posture: choose conservative, evidence-first fixes; manual-only for ambiguous product/business-rule changes.
- **D-21:** Downstream breadth: choose dependency-aware minimum smoke, not all-pages regression by default.
- **D-22:** Environment scope: local automated checks first; production/staging worker drain remains residual risk unless environment access and authorization are provided.

### the agent's Discretion

The planner may decide exact task splitting and file order, but it must preserve the audit-first sequence and the phase-local write boundary. It may use CodeGraph for structural impact, `rg` for literal discovery, and existing module test matrices to choose targeted verification.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope And Prior Baseline

- `.planning/phases/02-bank-details-improvements/02-SPEC.md` — locked requirements, boundaries, constraints, and acceptance criteria for this phase.
- `.planning/phases/02-bank-details-improvements/02-PAGE-BASELINE.md` — initial bank-details baseline card and current gaps to assess before L2 planning.
- `.planning/phases/00-cross-page-dependency-baseline/README.md` — required reading order for page phases.
- `.planning/phases/00-cross-page-dependency-baseline/00-CONTEXT.md` — baseline decisions about page isolation, cross-page safety, legacy cleanup, architecture gates, tests, and docs.
- `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md` — lifecycle events, frontend domain events, and operation freshness barrier.
- `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md` — bank details dependency group, upstream/downstream rows, and smoke guidance.
- `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md` — `bank_details` App Status domain, read model keys, workers, and refresh events.
- `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md` — route/server overlap and cleanup gate.
- `.planning/phases/00-cross-page-dependency-baseline/00-VALIDATION.md` — Phase 0 checks and residual page-level risks.

### Repository And Module Facts

- `AGENTS.md` — repository instructions, backend architecture direction, read model/worker governance, docs, and test reporting rules.
- `README.md` — project structure, runtime commands, and verification entry points.
- `ARCHITECTURE.md` — system boundaries, write/read model split, and production architecture direction.
- `docs/index.md` — long-term documentation map.
- `docs/app-architecture/README.md` — current app architecture maintenance entry.
- `docs/app-architecture/pages.md` — page grouping, bank-details domain, frontend events, backend lifecycle, and page responsibility boundaries.
- `docs/modules/README.md` — module index and maintenance rules.
- `docs/modules/bank-details/README.md` — bank-details module owner entry and modification triggers.
- `docs/modules/bank-details/state-machine.md` — business/UI/read model/worker states and forbidden transitions.
- `docs/modules/bank-details/tests.md` — bank-details impact matrix, test entry points, smoke flows, and untested risks.
- `docs/modules/bank-details/implementation-notes.md` — historical decisions and residual risks for bank-details changes.
- `docs/product-specs/bank-turnover-and-no-oa.md` — product contract for bank details, turnover, and no-OA flows.
- `docs/dev/api-contracts.md` — API contracts, including the bank-details section.

### Current Code And Tests

- `web/src/pages/BankDetailsPage.tsx` — bank-details page state, filters, drawer, stale/refreshing UI, events, export, and category mutation wiring.
- `web/src/features/bankDetails/api.ts` — bank-details API client and DTO/error mapping.
- `web/src/features/bankDetails/types.ts` — frontend bank-details DTO types.
- `web/src/features/bankDetails/AutoTagRulesDrawer.tsx` — auto-tag rule editing UI.
- `backend/src/fin_ops_platform/app/server.py` — active HTTP dispatch and `_bank_details_routes()` bridge.
- `backend/src/fin_ops_platform/app/routes_bank_details.py` — bank-details route facade.
- `backend/src/fin_ops_platform/services/bank_details_application_service.py` — bank-details application orchestration and mutation closure.
- `backend/src/fin_ops_platform/services/bank_details_service.py` — bank-details domain/read fallback behavior.
- `backend/src/fin_ops_platform/services/bank_detail_sql_projection.py` — SQL read model projection.
- `backend/src/fin_ops_platform/services/bank_detail_read_model_refresh.py` — bank detail worker refresh handler.
- `backend/src/fin_ops_platform/services/bank_details_export_service.py` — XLSX export behavior and limits.
- `backend/src/fin_ops_platform/services/bank_details_relation_tag_projection_service.py` — relation tag projection behavior.
- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py` — candidate confirmation and manual category business rules.
- `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py` — automatic category rule execution.
- `tests/test_bank_details_routes.py` — route facade contract tests.
- `tests/test_bank_auto_tag_rules_api.py` — auto-tag and category mutation API tests.
- `tests/test_bank_details_sql_runtime.py` — bank detail read model/runtime tests.
- `tests/test_bank_account_balance_read_model.py` — account balance read model tests.
- `tests/test_bank_details_service.py` — bank-details service and relation projection tests.
- `tests/test_bank_details_export_service.py` — export service tests.
- `tests/test_bank_transaction_category_service.py` — category service tests.
- `tests/test_bank_transaction_auto_category_service.py` — auto-category rule tests.
- `tests/test_bankdetail_write_uow_contract.py` — transaction/audit/dirty/outbox write contract tests.
- `tests/test_bankdetail_backfill_cli.py` — backfill CLI tests.
- `tests/test_restore_bank_auto_tag_rules_tool.py` — recovery tool tests.
- `web/src/test/BankDetailsApi.test.ts` — frontend API mapper tests.
- `web/src/test/BankDetailsPage.test.tsx` — frontend page interaction tests.

### Global Codebase Maps

- `.planning/codebase/STACK.md` — backend/frontend/runtime stack and page-analysis boundary.
- `.planning/codebase/ARCHITECTURE.md` — global architecture map and read/write/runtime consistency contracts.
- `.planning/codebase/TESTING.md` — global verification and testing patterns.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `BankDetailsApiRoutes` delegates bank-details reads, export, auto-tag rule mutations, category confirmation, revocation, manual assignment, and manual clearing through `BankDetailsApplicationService`.
- `BankDetailsApplicationService` already receives explicit dependencies, including services, audit, SQL read repository, runtime repositories, refresh providers, lifecycle executor, and relation/cache clearing callbacks.
- `BankDetailsPage.tsx` already tracks account/transaction read model status, page session filters, stale/refreshing state, auto-tag rules, category mutations, domain events, export feedback, and abort-like request behavior.
- `web/src/features/bankDetails/api.ts` centralizes DTO mapping and error-message handling for bank-details APIs.
- `docs/modules/bank-details/tests.md` already provides a strong command matrix for focused backend, frontend, and downstream regression selection.

### Established Patterns

- HTTP entry remains `server.py` dispatch to focused route modules; route modules are canonical boundaries for page-specific HTTP mapping, but active dispatch still needs server inventory.
- Freshness status is a first-class API/UI contract. Non-fresh states can return available data, but the page must expose stale/refreshing semantics and must not treat missing/stale empty rows as true empty.
- Writes that affect derived facts must go through application services, audit, lifecycle events, dirty scopes/outbox, workers, and post-write refetch/barrier logic.
- Frontend finance domain events are same-session hints only. Durable consistency lives in backend lifecycle/read model facts.
- Bank-details tests prefer contract behavior over internals: error codes/messages, stale/fresh fields, affected months/scopes, permission failures, and observable UI behavior.

### Integration Points

- Active frontend endpoints are `/api/bank-details/accounts`, `/transactions`, `/transactions/export`, `/auto-tag-rules`, `/auto-tag-rules/reapply`, `/auto-tag-rules/file-replacement`, `/transactions/{id}/category-confirmation`, and `/transactions/{id}/category-assignment`.
- Active backend dispatch for these endpoints appears in `server.py`, which delegates to `BankDetailsApiRoutes` via `_bank_details_routes()`.
- Runtime/read model integration points are `bank_detail.read_model.refresh`, `bank_account_balance.read_model.refresh`, workers `bank-detail` and `bank-account-balance`, App Status domain `bank_details`, and lifecycle events `bank_transaction_category_changed` / `bank_auto_tag_rules_changed` / upstream relation/import events.
- Downstream page smoke should be selected from Workbench relation core and dataflow impact: Workbench, no-OA batches, turnover ledger, batch accounting, cost statistics, pending/search, invoice lifecycle/tax, and App Health.
</code_context>

<specifics>
## Specific Ideas

- The user specifically wants to know whether bank details has risk points, unreasonable design/architecture, and whether all functionality is fully closed.
- The implementation plan should therefore include an explicit risk register and closure matrix, not just a code-change plan.
- Architecture gaps should be treated as manual-only unless the fix is narrow, testable, and clearly follows the existing service/repository/read-model direction.
</specifics>

<deferred>
## Deferred Ideas

- Production/staging worker drain using real PostgreSQL/RabbitMQ/Redis and historical data remains outside this local phase unless environment access and authorization are provided.
- Broad cleanup of all `server.py` legacy dispatch is outside this bank-details phase; only bank-details active dispatch classification belongs here.
- Downstream module documentation updates are deferred unless the bank-details audit or implementation changes durable downstream facts.
</deferred>

---

*Phase: 02-bank-details-improvements*
*Context gathered: 2026-06-16*
