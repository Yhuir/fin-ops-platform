# P005 Frontend Modular Closure And Final Audit

Use this as the next bounded execution prompt inside the `/goal` controller.

```text
Goal:
Close the remaining `bank-flow-rule-batches` modularity gap by splitting the frontend page into feature modules with clear boundaries and I/O, then run a final backend/frontend/docs closure audit. Keep public API behavior stable.

Evidence to inspect first:
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/BASELINE_AUDIT.md`
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/P002_IMPLEMENTATION_REPORT.md`
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/P003_IMPLEMENTATION_REPORT.md`
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/P004_IMPLEMENTATION_REPORT.md`
- `docs/modules/bank-flow-rule-batches/README.md`
- `docs/modules/bank-flow-rule-batches/boundary-io.md`
- `docs/modules/bank-flow-rule-batches/tests.md`
- `web/src/pages/BankFlowRuleBatchPage.tsx`
- `web/src/features/bankFlowRuleBatches/*`
- `web/src/test/BankFlowRuleBatchPage.test.tsx`
- `web/src/test/BankFlowRuleBatchApi.test.ts`
- `web/src/test/BankFlowRuleBatchPolicy.test.ts`
- `web/e2e/bank-flow-rule-batches-flow.spec.ts`

Allowed implementation scope:
- Frontend-only module extraction under `web/src/features/bankFlowRuleBatches/`.
- Tests that need import path updates.
- Small API client type/interface cleanup if it improves explicit I/O.
- Docs updates for frontend file/module boundaries.
- No backend behavior changes unless tests reveal a contract bug.

Architecture constraints:
- Keep cards/panels/layout visually unchanged unless extraction reveals a real bug.
- No public API shape changes.
- Do not reintroduce no-OA naming into bank-flow feature modules.
- Each extracted module must have explicit inputs/outputs:
  - API client and DTO types;
  - policy/permission helpers;
  - list/read-model state adapter;
  - tag-rules drawer/grid state;
  - batch action toolbar/reset/rebaseline actions;
  - operation barrier handling.
- Remove old duplicated or dead inline logic from `BankFlowRuleBatchPage.tsx`; the page should compose modules, not own all behavior.

Required analysis:
1. Map current `BankFlowRuleBatchPage.tsx` responsibilities and state variables.
2. Identify existing `web/src/features/bankFlowRuleBatches/*` modules and decide which ones to keep, merge, or remove.
3. Produce a before/after module I/O table in the implementation report.

Required edits:
1. Extract cohesive frontend modules with clear I/O and no duplicate old logic.
2. Keep `BankFlowRuleBatchPage.tsx` as orchestration/composition only.
3. Update or add tests for:
   - tag rules drawer read/save/error behavior;
   - list stale/missing/fresh state;
   - reset/rebaseline action state and operation barrier targets;
   - no `selected_tag_codes` write payload;
   - permission-hidden/disabled controls.
4. Run final code search:
   - no bank-flow frontend module calls `/api/no-oa-bank-batches`;
   - no bank-flow write payload sends `selected_tag_codes`;
   - no current docs claim bank-flow uses no-OA physical storage or no-OA rule settings.
5. Update docs if file boundaries changed.

Verification to run:
- `npm --prefix web test -- --run BankFlowRuleBatchPage.test.tsx BankFlowRuleBatchApi.test.ts BankFlowRuleBatchPolicy.test.ts CandidateGroupGrid.test.tsx`
- `npm --prefix web run build`
- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_app_settings_service.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py -q`
- `git diff --check -- web/src/pages web/src/features web/src/test docs .planning/quick/20260701-bank-flow-rule-batches-full-closure-goal`

Stop condition:
- Frontend modules have clear boundaries and I/O.
- Old inline page logic is removed from the main page instead of duplicated.
- Backend P002/P003/P004 tests still pass.
- Docs and GSD reports reflect the final state.
- If all MASTER goal acceptance criteria are satisfied, mark the goal complete; otherwise create exactly one final `P006_*` prompt for the remaining verified gap.
```
