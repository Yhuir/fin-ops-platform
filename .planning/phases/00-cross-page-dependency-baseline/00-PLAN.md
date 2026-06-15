---
phase: 00-cross-page-dependency-baseline
plan: 00
type: docs
wave: 0
requirements: [BASE-00, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]
---

# Plan 00: Establish Cross-Page Dependency Baseline

<objective>
Create the shared baseline that every page implementation phase must use before planning or coding.
</objective>

<tasks>

<task id="00-01">
<name>Create baseline phase entry</name>
<read_first>
- `.planning/ROADMAP.md`
- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/STATE.md`
</read_first>
<action>
Add Phase 0 to the GSD planning workspace, mark it as the cross-page dependency baseline, and make Phases 1-17 depend on Phase 0 for implementation planning.
</action>
<acceptance_criteria>
- `.planning/ROADMAP.md` contains `### Phase 0`.
- Phases 1-17 have `Depends on:` text referencing Phase 0.
- `.planning/REQUIREMENTS.md` maps `BASE-00` to Phase 0.
- `.planning/STATE.md` records Phase 0 baseline completion.
</acceptance_criteria>
</task>

<task id="00-02">
<name>Document all-page inventory</name>
<read_first>
- `web/src/app/pageRegistry.tsx`
- `docs/modules/README.md`
- `docs/dev/testing-closure-dependency-map.md`
</read_first>
<action>
Create a page inventory covering all registered pages, frontend entries, API clients, backend owner boundaries, read models, workers, and App Status domains.
</action>
<acceptance_criteria>
- `00-RESEARCH.md` contains 17 page rows.
- `READ-MODEL-WORKER-MATRIX.md` includes App Status domain and read model registry rows.
</acceptance_criteria>
</task>

<task id="00-03">
<name>Document cross-page dataflow</name>
<read_first>
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `web/src/features/domainEvents.ts`
</read_first>
<action>
Create a lifecycle and frontend event map showing durable backend fan-out versus browser-only refresh hints.
</action>
<acceptance_criteria>
- `CROSS-PAGE-DATAFLOW.md` lists lifecycle events from `DerivedDataLifecycleService`.
- `CROSS-PAGE-DATAFLOW.md` states frontend domain events are not freshness proof.
- Operation freshness barrier rules are included.
</acceptance_criteria>
</task>

<task id="00-04">
<name>Document legacy cleanup gate</name>
<read_first>
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/modules/workbench-relations/README.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
</read_first>
<action>
Create a reusable legacy cleanup gate for route/service/repository/worker/client paths.
</action>
<acceptance_criteria>
- `LEGACY-ENTRYPOINTS.md` classifies known transitional areas.
- `LEGACY-ENTRYPOINTS.md` includes removal criteria and a page-phase template.
</acceptance_criteria>
</task>

<task id="00-05">
<name>Document implementation ordering</name>
<read_first>
- `CROSS-PAGE-DATAFLOW.md`
- `PAGE-DEPENDENCY-MATRIX.md`
- `READ-MODEL-WORKER-MATRIX.md`
</read_first>
<action>
Create ordering guidance that lets page work proceed without requiring all 17 full plans while still respecting cross-page dependencies.
</action>
<acceptance_criteria>
- `IMPLEMENTATION-ORDER.md` states Phase 0 + page-level L2 is required before implementation.
- `IMPLEMENTATION-ORDER.md` distinguishes safe parallel work from coordinated shared-boundary work.
</acceptance_criteria>
</task>

</tasks>

<verification>

Run:

```bash
node /Users/yu/.codex/gsd-core/bin/gsd-tools.cjs query init.phase-op 0
git diff --check
bash scripts/verify.sh docs
```

</verification>

<artifacts_this_phase_produces>

- `.planning/phases/00-cross-page-dependency-baseline/README.md`
- `.planning/phases/00-cross-page-dependency-baseline/00-CONTEXT.md`
- `.planning/phases/00-cross-page-dependency-baseline/00-RESEARCH.md`
- `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
- `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
- `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
- `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`
- `.planning/phases/00-cross-page-dependency-baseline/IMPLEMENTATION-ORDER.md`
- `.planning/phases/00-cross-page-dependency-baseline/00-PLAN.md`
- `.planning/phases/00-cross-page-dependency-baseline/00-VALIDATION.md`
- `.planning/phases/00-cross-page-dependency-baseline/00-VERIFICATION.md`

</artifacts_this_phase_produces>
