# Phase 0: Cross-Page Dependency Baseline

**Status:** Complete
**Completed:** 2026-06-16
**Purpose:** Before improving any individual page, establish the shared page/data/read-model/worker dependency baseline so page phases do not plan in isolation.

## How To Use This Phase

Every page phase must read this directory before page-level `CONTEXT.md`, `RESEARCH.md`, `UI-SPEC.md`, or `PLAN.md` is finalized.

Required reading order for a page phase:

1. `README.md` in this directory.
2. `00-CONTEXT.md` for locked baseline decisions and scope fences.
3. `00-RESEARCH.md` for all-page inventory and baseline findings.
4. `CROSS-PAGE-DATAFLOW.md` for upstream/downstream lifecycle and event fan-out.
5. `PAGE-DEPENDENCY-MATRIX.md` for page grouping, dependency strength, and smoke scope.
6. `READ-MODEL-WORKER-MATRIX.md` for read model, worker, App Status, and operation-barrier boundaries.
7. `LEGACY-ENTRYPOINTS.md` before deleting or bypassing old code paths.
8. `IMPLEMENTATION-ORDER.md` before choosing page work order or parallel threads.
9. `00-VALIDATION.md` to see what was checked and what remains page-level risk.

## Baseline Rule

Page development does not require all 17 page phases to have deep implementation plans up front. It does require:

- Phase 0 L1 baseline completed.
- The selected page, or strongly coupled page group, completed to L2 depth before implementation.
- Any cross-page impact from the selected page explicitly mapped to read models, workers, operation barrier scopes, docs, and tests.

## Output Files

| File | Purpose |
| --- | --- |
| `00-CONTEXT.md` | Locked decisions, phase boundary, non-goals, acceptance criteria, and baseline gates. |
| `00-RESEARCH.md` | Page inventory, current architecture assessment, risk summary, and docs/test impact. |
| `CROSS-PAGE-DATAFLOW.md` | Data source, write event, lifecycle fan-out, and operation freshness model. |
| `PAGE-DEPENDENCY-MATRIX.md` | Upstream/downstream page dependencies, dependency groups, and smoke-test scope. |
| `READ-MODEL-WORKER-MATRIX.md` | App Status domain, read model, worker, event, and freshness ownership. |
| `LEGACY-ENTRYPOINTS.md` | Known legacy or transitional paths and the cleanup gate required before deletion. |
| `IMPLEMENTATION-ORDER.md` | Recommended ordering, page group strategy, and parallel-thread rules. |
| `00-PLAN.md` | Executable baseline plan that future page phases must apply. |
| `00-VALIDATION.md` | Verification commands and residual risks for this documentation-only baseline. |
| `00-VERIFICATION.md` | GSD-recognized completion record for Phase 0 baseline checks. |

## Source Of Truth Boundaries

This phase is a planning baseline, not a long-term architecture source of truth. If later page work discovers durable facts that change the current app contract, update the relevant long-term docs:

- Page/runtime facts: `docs/app-architecture/`.
- Module facts: `docs/modules/<module>/`.
- API/testing facts: `docs/dev/`.
- Worker/operations facts: `docs/operations/`.
- Business/product facts: `docs/product-specs/`.

Do not update `.planning/codebase/*.md` for page-specific analysis.
