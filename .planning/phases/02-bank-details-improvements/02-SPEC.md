# Phase 2: bank-details-improvements — Specification

**Created:** 2026-06-16
**Ambiguity score:** 0.13 (gate: <= 0.20)
**Requirements:** 9 locked

## Goal

Phase 2 produces a page-level L2 audit and executable improvement plan for `/bank-details` that identifies risk points, architecture gaps, and functional closure gaps before any bank-details behavior is changed.

## Background

The bank details page is not a simple list page. It is the upstream display and mutation surface for bank transaction facts, automatic tag rules, candidate confirmation, manual classification, relation tags, no-OA status, account balances, export, and downstream refresh effects.

Current code and docs already define substantial boundaries:

- Frontend entry: `web/src/pages/BankDetailsPage.tsx`.
- Frontend API client: `web/src/features/bankDetails/api.ts`.
- Backend route facade: `backend/src/fin_ops_platform/app/routes_bank_details.py`.
- Backend application service: `backend/src/fin_ops_platform/services/bank_details_application_service.py`.
- Read model workers: `bank-detail` and `bank-account-balance`.
- Read models: `bank_detail` and `bank_account_balance`.
- Core module docs: `docs/modules/bank-details/README.md`, `state-machine.md`, `tests.md`, and `implementation-notes.md`.
- Phase 0 baseline classifies bank details as part of the `Workbench relation core` dependency group.

Known risk themes from the current source of truth:

- `bank_detail` and `bank_account_balance` freshness must not be faked by frontend state or old rows.
- Tag/category writes must write audit facts and trigger durable dirty scopes/outbox, not just emit frontend events.
- Candidate confirmation must only accept current backend-generated candidates.
- Manual category assignment must only apply to `unmatched` rows.
- Account balance is a separate read model and must not be recomputed from current filtered detail rows.
- Bank details changes can affect Workbench, no-OA batches, turnover ledger, pending/search, cost statistics, invoice lifecycle, App Status, and exports.
- `server.py` and route modules may overlap, so active dispatch must be classified before any API contract change.

## Requirements

1. **Current-state inventory**: The phase must identify the active bank-details module facts, code entry points, API boundaries, read models, workers, frontend events, tests, and module docs.
   - Current: The phase directory has only `02-PAGE-BASELINE.md`; detailed L2 analysis artifacts do not yet exist.
   - Target: Phase artifacts list the canonical frontend, backend, service, repository/projection, read model, worker, App Status, domain event, docs, and tests entry points used by bank details.
   - Acceptance: A reviewer can open the phase artifacts and trace `/bank-details` from page route to API client, backend route, application service, read model/query boundary, worker, and existing test coverage without using `.planning/codebase/` as a page-specific scratchpad.

2. **Architecture risk audit**: The phase must classify bank-details architecture risks against repository architecture gates.
   - Current: The module has route facade, application service, SQL read models, workers, and transitional `server.py` dispatch risk, but this phase has not yet classified which boundaries are canonical, transitional, dead, or unknown.
   - Target: The audit explicitly checks thin route mapping, service/repository separation, explicit dependency injection, no HTTP/auth coupling in services/workers, no direct dirty-scope SQL writes from business services, and no new reliance on compatibility paths.
   - Acceptance: The phase includes a pass/fail architecture section with evidence for each gate and records every unresolved or manual-only architecture risk with owner files and verification needed.

3. **Read model and worker closure**: The phase must verify the bank detail and account balance read model contracts as page-level acceptance gates.
   - Current: Docs and tests define `fresh`, `refreshing`, `stale`, `schema_mismatch`, and `missing` semantics, but this phase has not yet checked whether planned page work preserves those semantics end to end.
   - Target: The analysis maps `bank_detail` and `bank_account_balance` scope keys, refresh events, workers, App Status domain, enqueue behavior, stale/fresh response fields, cache boundary, and UI handling.
   - Acceptance: A verifier can confirm that the plan prevents stale/missing/schema-mismatch payloads from being displayed as true empty data and keeps account balance independent from transaction filters and tag rules.

4. **Tag and category mutation closure**: The phase must audit all bank-details mutation flows for business, permission, audit, idempotency, version, and downstream refresh completeness.
   - Current: API docs define auto tag rules, file replacement, reapply, category confirmation, revocation, manual assignment, and manual clearing; this phase has not yet turned them into a closed-loop risk checklist.
   - Target: The phase maps each mutation to its allowed states, permission check, error envelope, audit action, affected months/scopes, lifecycle event, dirty/outbox behavior, frontend feedback, and regression tests.
   - Acceptance: Each mutation flow has an explicit closure line showing `user action -> API -> service -> write/audit -> lifecycle/dirty/outbox -> worker/read model -> UI/domain event/refetch -> tests`.

5. **Functional closure audit**: The phase must determine whether all expected bank-details page capabilities are complete or intentionally out of scope.
   - Current: The page supports accounts, transactions, filters, category counts, auto tag rules drawer, category mutation, export, stale/refreshing feedback, and domain events, but this phase has not yet evaluated completeness against user workflows.
   - Target: The audit covers initial load, account/date/search/category filtering, pagination, export, rules drawer, reapply, candidate confirmation, manual classification, relation tags, balance display, loading/empty/error/stale/refreshing states, permission-disabled states, and retry/refetch behavior.
   - Acceptance: Each capability is classified as `closed`, `partial`, `missing`, `manual-only`, or `deferred`, with a concrete reason and next action.

6. **Cross-page impact and smoke scope**: The phase must identify every downstream page or read model that can be affected by bank-details reads or writes.
   - Current: Phase 0 identifies bank details as a Workbench relation core member with downstream effects, but this phase has not yet chosen bank-details-specific smoke targets.
   - Target: The phase records upstream dependencies from bank import/settings/workbench relation facts and downstream impacts for Workbench, no-OA batches, turnover ledger, pending/search, cost statistics, invoice lifecycle, batch accounting, tax offset, and App Health where applicable.
   - Acceptance: The improvement plan names the minimum smoke or regression scope for any planned change and explains why unrelated pages are not included.

7. **Test strategy and seven-category coverage**: The phase must map existing and missing tests before implementation starts.
   - Current: `docs/modules/bank-details/tests.md` lists strong existing coverage, but this phase has not yet mapped user-requested risk/closure questions to automated and manual validation.
   - Target: The phase maps all seven repository test categories to bank-details business rules, service orchestration, API contract, read model/worker, frontend interaction, cross-module integration, and existing-feature regression.
   - Acceptance: The plan says which tests already protect each risk, which tests must be added or changed if implementation happens, which checks are manual-only, and which risks require staging/nightly infrastructure.

8. **Docs impact and long-term fact handling**: The phase must decide whether findings require updates outside the phase directory.
   - Current: Repository rules require docs impact assessment for functionality, API, architecture, read model/worker, operations, permissions, or data-flow changes.
   - Target: Phase artifacts separate page-specific planning notes from durable facts. Long-term docs are updated only if the audit or implementation changes current facts.
   - Acceptance: The final phase summary contains a docs impact decision: either `docs 不适用` with reason, or a list of exact long-term docs updated.

9. **Executable improvement plan**: The phase must produce a bounded implementation plan only after risks and closure gaps are classified.
   - Current: Phase 2 has no `PLAN.md`; jumping directly to code could miss cross-page and read-model obligations.
   - Target: `gsd-plan-phase 2` produces an executable plan that fixes or documents prioritized gaps without broad rewrites and without modifying `.planning/codebase/*.md`.
   - Acceptance: The generated plan has scoped tasks, acceptance checks, verification commands, docs impact handling, and stop conditions for any broader refactor or ambiguous business decision.

## Boundaries

**In scope:**

- Page-level L2 analysis for `bank-details`.
- Risk audit for architecture, read model freshness, worker boundaries, lifecycle fan-out, permissions, audit, and API contracts.
- Functional closure audit for the bank details page workflows and states.
- Cross-page impact map and minimum smoke/regression scope for bank-details changes.
- Test strategy mapped to the repository's seven test categories.
- A GSD-ready implementation plan for confirmed gaps.
- Phase-local artifacts under `.planning/phases/02-bank-details-improvements/`.

**Out of scope:**

- Rewriting bank details architecture before the audit classifies concrete gaps — scope must be justified by evidence first.
- Changing business rules for bank tagging, external turnover, no-OA batches, Workbench relations, invoice lifecycle, tax, or cost statistics without a separate product/API decision.
- Editing `.planning/codebase/*.md` — Phase 0 keeps that as the global map.
- Updating all downstream page modules by default — only update or test downstream areas when a bank-details finding affects them.
- Running production/staging worker drain or real historical-data smoke in this phase — local phase work can document this as residual risk unless an environment is explicitly provided.
- Deleting legacy or transitional paths solely because they look old — cleanup requires the Phase 0 legacy gate.

## Constraints

- Follow `AGENTS.md`, `docs/modules/bank-details/*`, Phase 0 baseline docs, `docs/app-architecture/pages.md`, `docs/dev/api-contracts.md`, and `docs/product-specs/bank-turnover-and-no-oa.md`.
- Preserve existing backend architecture direction: routes map HTTP, services own business orchestration, repositories/projections own SQL/table details, workers stay independent of HTTP/Application/session concerns.
- Read model refresh truth remains PostgreSQL durable queue/outbox and dirty scopes; Redis is only after fresh gate, RabbitMQ only optional wakeup/transport.
- Frontend domain events are refresh hints only and cannot prove cross-page consistency.
- Any behavior-changing follow-up must add or update applicable tests and report all seven test categories.
- Keep this phase's planning writes isolated to `.planning/phases/02-bank-details-improvements/` unless a long-term doc fact actually changes.

## Acceptance Criteria

- [ ] Phase 2 has a SPEC, CONTEXT or RESEARCH, PLAN, and validation path that are all scoped to `.planning/phases/02-bank-details-improvements/`.
- [ ] The artifacts identify bank-details docs, frontend/backend entry points, service/projection boundaries, read models, workers, App Status domain, domain events, and test files.
- [ ] The audit records architecture risks with evidence and classifies each as `closed`, `partial`, `missing`, `manual-only`, or `deferred`.
- [ ] The audit records functional closure status for accounts, transactions, filters, pagination, export, rules drawer, category mutations, relation tags, balance display, stale/refreshing/error states, and permissions.
- [ ] The plan maps bank-details writes to lifecycle events, dirty scopes/outbox, workers, read model freshness, frontend refetch, and downstream smoke scope.
- [ ] The plan maps all seven test categories and names the exact verification commands that should run for any implemented changes.
- [ ] The docs impact assessment is explicit and does not store raw prompts in long-term docs.
- [ ] No page-specific analysis overwrites `.planning/codebase/*.md`.

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
| --- | --- | --- | --- | --- |
| Goal Clarity | 0.90 | 0.75 | met | User asked specifically for bank-details risks, architecture reasonableness, and complete functional closure; phase roadmap confirms page analysis and improvement planning. |
| Boundary Clarity | 0.86 | 0.70 | met | Scope is phase-local analysis and planning before implementation; long-term docs/code only change if later findings require it. |
| Constraint Clarity | 0.83 | 0.65 | met | Repository architecture, read model, worker, docs, testing, and Phase 0 constraints are explicit. |
| Acceptance Criteria | 0.88 | 0.70 | met | Pass/fail criteria are tied to phase artifacts, risk classification, closure map, and test/docs mapping. |
| **Ambiguity** | 0.13 | <=0.20 | met | Ready for `gsd-discuss-phase 2`. |

Status: met = meets minimum, below = planner treats as assumption.

## Interview Log

| Round | Perspective | Question summary | Decision locked |
| --- | --- | --- | --- |
| 1 | Researcher | What exists today for bank details? | Code and docs already define page, API client, route facade, application service, read models, workers, tests, and module docs; phase lacks L2 audit artifacts. |
| 1 | Researcher | What triggered this phase? | User wants risk, architecture reasonableness, and functional closure checked before improving bank details. |
| 2 | Simplifier | What is the irreducible core? | Produce evidence-backed audit and executable plan before behavior-changing code. |
| 3 | Boundary Keeper | What is out of scope? | No broad rewrite, no business-rule change, no `.planning/codebase/` overwrite, no deletion of legacy paths without cleanup gate evidence. |
| 4 | Failure Analyst | What would make the phase fail? | Treating frontend events as durable consistency, treating stale read models as fresh empty results, skipping downstream smoke, or planning code changes without test/docs impact. |
| auto | Seed Closer | Is the spec ready without more user questions? | Auto-selected yes because roadmap, Phase 0, module docs, API docs, and user intent make the WHAT/WHY sufficiently clear. |

---

*Phase: 02-bank-details-improvements*
*Spec created: 2026-06-16*
*Next step: $gsd-discuss-phase 2 --text — implementation decisions (how to build what's specified above)*
