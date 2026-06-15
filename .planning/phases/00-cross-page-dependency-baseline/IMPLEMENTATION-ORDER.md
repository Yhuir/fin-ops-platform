# Implementation Order Baseline

**Purpose:** Define how to move from cross-page baseline to page implementation without over-planning all pages or ignoring dependencies.

## Correct Strategy

Do not wait for all 17 pages to have complete implementation plans. Do not implement a page as an isolated island.

Use this sequence:

1. Complete Phase 0 baseline. Done.
2. Pick a page or strongly coupled page group.
3. Run page-level `gsd-discuss-phase` to capture user goals and decisions.
4. Run page-level research to produce `RESEARCH.md`.
5. Generate UI/spec/plan only for that page or group.
6. Implement with tests and docs impact.
7. Update long-term docs only when durable facts changed.

## Recommended Group Order

The safest order depends on the user's target. If no target is given, use this order:

| Order | Group | Phases | Reason |
| --- | --- | --- | --- |
| 0 | Cross-page baseline | Phase 0 | Shared dependency map before page work. |
| 1 | Runtime safety and observability gates | Phase 14, selected docs/tests only if needed | App Health/readiness makes failures visible before broad data-flow changes. Do not overbuild UI first. |
| 2 | Import source facts | Phases 15, 16, 17 | Source facts feed downstream pages. Shared import workflow changes should be stabilized before dependent pages rely on new facts. |
| 3 | Workbench relation core | Phases 4, 2, 11, 10, 1 | Relation/categorization writes affect many pages. Canonical relation path and stale/fresh behavior should be stable before analytics. |
| 4 | Invoice lifecycle pages | Phases 6, 7, 8, 9, 3 | Invoice lifecycle drives pending invoices, usage, OA pending, output collections, and tax. |
| 5 | ETC chain | Phases 17, 12, then smoke Phases 4, 3, 5 | ETC import/business batch affects Workbench/tax/cost. If ETC is target, handle as a group. |
| 6 | Analytics and settings | Phases 5, 13, 14 | Cost statistics is downstream aggregate; settings reset/project scope are cross-system and should have focused risk gates. |

If the user selects a specific page, do not force the whole order. Instead:

- Complete that page's L2 phase.
- Read upstream/downstream rows from the matrices.
- Add smoke/regression checks for strong dependencies.
- Create follow-up phases for newly discovered dependent work.

## Page-Level L2 Definition

A page is ready for implementation only when its phase contains:

- Page status: route, frontend entry, API client, backend route/service, read model/worker.
- Feature gap classification: UX-only, API/UI contract, business rule, data-flow/read model, legacy cleanup.
- Risk list: permissions, audit, stale/fresh, cross-page refresh, worker, export, historical data.
- Test matrix: seven categories, existing test entries, new/changed tests, verification commands.
- Docs impact: module docs and long-term facts that need updates.
- Architecture assessment: route/service/repository/worker/read model boundary fitness.
- Legacy cleanup gate: active old paths, canonical boundary, migration/deletion conditions.
- Implementation plan: test-first or TDD where applicable, then scoped code changes, then verification.

## Parallel Thread Rules

Allowed in parallel:

- Different page phases writing only their own `.planning/phases/<phase>/` files.
- Read-only research over shared docs/code.
- UI-only planning for pages that have no shared runtime code edits.

Needs coordination:

- `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`.
- `docs/app-architecture/*` and `docs/modules/README.md`.
- `DerivedDataLifecycleService`.
- `app_status_domain_registry.py`, `app_status_read_model_registry.py`, `runtime_worker_registry.py`.
- `web/src/components/imports/ImportWorkflowPage.tsx`.
- `web/src/features/imports/api.ts`, `web/src/features/etc/api.ts` shared import paths.
- Workbench relation command/read/projection services.
- `server.py` dispatch changes.

Do not run two implementation threads that both modify Workbench relation, import workflow, invoice lifecycle, App Status registry, or settings reset without an explicit merge plan.

## Per-Page Command Pattern

For a selected page phase `N`:

```bash
$gsd-discuss-phase N --batch=3
$gsd-plan-phase --research-phase N --research
$gsd-ui-phase N
$gsd-plan-phase N --tdd
```

Notes:

- Use `--skip-ui` only when the page work truly has no UI/interaction contract.
- Use `--tdd` for business rules, API contracts, transformations, validation, state machines, and workflows.
- If research shows the page belongs to a strong dependency group, plan the group explicitly before executing.

## Done Criteria For A Page Phase

Before `$gsd-execute-phase N`:

- `N-CONTEXT.md` references Phase 0 decisions and records page-specific user choices.
- `N-RESEARCH.md` maps upstream/downstream pages, read models, workers, lifecycle events, legacy paths, and tests.
- `N-PLAN.md` or plan files include test-first tasks for applicable categories.
- Legacy cleanup tasks are explicit when old paths exist.
- Docs impact is explicit.
- Verification commands include targeted tests and at least one cross-page smoke when dependencies are strong.
