---
phase: 27-read-model-fan-out
plan: "01"
subsystem: read-model-governance
tags: [coverage, read-model, fan-out, drawers, static-guards]

requires:
  - phase: 26-oa
    provides: frozen Turnover relation correctness and controlled production fan-out latency baseline
  - phase: 19-cross-page-audit
    provides: 17-page registry, read-model manifest and strict freshness/Audit contracts
provides:
  - Mechanically checked coverage of all 17 pages, 110 mutating/read-like API exports and 22 business Drawers
  - Bidirectional coverage of 23 browser dynamic openers and all 15 manifest read models
  - Count-sensitive registry for 36 direct lifecycle, enqueue and frontend barrier calls
  - Four operation classes and an honest current-state versus target-state migration contract
affects: [27-02, 27-03, 27-04, 27-05, 27-06, 27-07]

tech-stack:
  added: []
  patterns: [test-time source parsing, bidirectional inventory guards, vertical-slice deletion gates]

key-files:
  created:
    - .planning/phases/27-read-model-fan-out/27-COVERAGE-MATRIX.md
  modified:
    - tests/test_permissions_write_entry_inventory.py
    - tests/test_read_model_manifest.py
    - docs/app-architecture/pages.md
    - docs/architecture/module-boundaries/read-model-contracts.md
    - docs/modules/permissions-and-audit/write-entry-inventory.md

key-decisions:
  - "Reuse PageRuntimeContext, the existing query/refresh gateways, PostgreSQL durable queue and workers; do not add a coordinator or second dependency registry."
  - "Classify exported POST/PUT/PATCH/DELETE clients as fact-write, rule-write, read-like-command or explicit-batch before changing runtime behavior."
  - "Delete a write-side signal only after that vertical slice has independent read-side canonical version/drift proof and production evidence."

patterns-established:
  - "Coverage gate: new or removed page/API/Drawer/opener/read-model/direct call must update the matrix or fail tests."
  - "Target contract: ordinary command commits canonical facts; current page reconciles exact scope; other pages converge on access."

requirements-completed: [RMF-01]

duration: 52min
completed: 2026-07-23
---

# Phase 27 Plan 01: Full Coverage Contract Summary

**The migration now starts from a mechanically enforced whole-app inventory, without adding any production runtime layer or claiming that the target behavior is already deployed.**

## Performance

- **Duration:** 52 min
- **Completed:** 2026-07-23T01:24:00+08:00
- **Tasks:** 3
- **Production runtime files changed:** 0

## Accomplishments

- Recorded exactly 17 registered pages and the real page/read-model ownership, including pages that intentionally have no independent read model.
- Recursively classified exactly 110 exported feature API functions that reach POST/PUT/PATCH/DELETE, including preview/calculate/barrier functions that are read-like rather than durable business mutations.
- Classified all 22 business `Drawer.tsx` components as `read-only`, `writable` or `mixed`, and matched all 23 Browser role-matrix dynamic opener ids.
- Mirrored all 15 `READ_MODEL_MANIFEST` keys with their current scope/query owners and consumer pages/resources.
- Counted all 36 direct `.plan_event`, direct enqueue and frontend `waitForOperationFreshness` calls in 23 file/sentinel groups and assigned `retain`, `migrate` or `delete` status.
- Documented the access-driven target without rewriting current production facts: ordinary commands target zero downstream page fan-out, explicit batch/full-history work remains a durable exception, and Workbench keeps active-generation atomic publish.

## Commit

- **Plan implementation and coverage contract:** `7fd3ffccb` (`docs(27-01): freeze fan-out migration coverage`)

## Verification Evidence

- `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory tests.test_read_model_manifest -v` — **46 passed**.
- `bash scripts/verify.sh docs` — passed.
- `bash scripts/verify.sh lint` — passed.
- `git diff --check` — passed after normalizing trailing blank lines in newly created Phase 27 planning files.

## Seven-Category Test Assessment

1. **Business core:** not applicable yet; Plan 27-01 changes no business rules or runtime behavior.
2. **Service layer:** not applicable yet; no service/repository/queue implementation changed.
3. **API contract:** static exported-function coverage added; HTTP response contracts remain unchanged.
4. **Read model/cache/background job:** manifest key/scope/query-owner and direct lifecycle/enqueue/barrier coverage added; runtime behavior is deferred to vertical slices.
5. **Frontend interaction:** every business Drawer and dynamic opener is now bidirectionally inventoried; no component behavior changed.
6. **End-to-end:** not applicable to this documentation/static-gate plan; vertical and production flows begin in 27-02.
7. **Existing regression:** existing permission inventory and manifest tests remain green, and stale documentation/source rows fail bidirectionally.

## Grill-me / Ponytail Review

- The matrix is a test/planning artifact only and never enters production I/O.
- No runtime registry, page coordinator, dependency package, schema, queue, worker or cache was introduced.
- Existing `PageRuntimeContext`, query gateway, refresh gateway, durable queue and manifest remain the implementation boundaries.
- The static parser is intentionally local to tests; adding a TypeScript parser dependency or code-generation pipeline would be unjustified for the current contract.
- Current and target behavior are explicitly separated, so later plans cannot delete safety signals based on aspirational documentation.

## Deviations from Plan

None. The only mechanical cleanup removed extra blank lines at EOF from newly created Phase 27 planning files so the repository whitespace gate could pass.

## Next Phase Readiness

- Plan 27-02 can change only the bank-details and cost-statistics vertical slice while the new hard gate protects the rest of the app.
- The first slice must establish canonical/rule version proof before deleting category/rule fan-out and cross-page barriers.
- Phase 26 frozen Turnover correctness remains untouched; its measured production fan-out latency is the baseline Phase 27 must improve.

---
*Phase: 27-read-model-fan-out*
*Completed: 2026-07-23*
