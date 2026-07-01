# P005 Implementation Report - Frontend Modular Closure

Date: 2026-07-01

## Goal

Close the remaining `bank-flow-rule-batches` frontend modularity gap by splitting pure view-model and reusable UI primitives out of the monolithic page while keeping public API behavior stable.

## Before / After Module I/O

| Responsibility | Before | After |
| --- | --- | --- |
| HTTP and DTO mapping | `features/bankFlowRuleBatches/api.ts` | unchanged |
| Domain/API types | `features/bankFlowRuleBatches/types.ts` | unchanged |
| Status/selection policy | `features/bankFlowRuleBatches/policy.ts` | unchanged |
| Formatting, tag-rule drawer rows, draft requirements, operation-barrier target helpers | inline in `BankFlowRuleBatchPage.tsx` | `features/bankFlowRuleBatches/viewModel.ts` |
| Pagination controls, status tag, label rail | inline in `BankFlowRuleBatchPage.tsx` | `features/bankFlowRuleBatches/components.tsx` |
| Page state, effects, mutation orchestration, page composition | mixed with helpers/components | remains in `BankFlowRuleBatchPage.tsx` |

## Implemented

- Added `web/src/features/bankFlowRuleBatches/viewModel.ts`.
  - Owns current month, formatting helpers, tag label normalization, drawer row grouping, draft requirement helpers, row label helpers, and mutation barrier helper.
- Added `web/src/features/bankFlowRuleBatches/components.tsx`.
  - Owns `PageControls`, `BatchStatusTag`, and `LabelRail`.
- Reduced `BankFlowRuleBatchPage.tsx` from 1773 lines to 1379 lines.
- Updated static page tests to scan the extracted feature files for primitive/style contracts.
- Updated docs with frontend module/file boundaries.

## Static Closure Checks

- `web/src/features/bankFlowRuleBatches` and `BankFlowRuleBatchPage.tsx` do not call `/api/no-oa-bank-batches`.
- `selected_tag_codes` appears only in response compatibility mapping, empty initial state, and tests; save payload still sends only `rules`.
- Long-term docs no longer state that bank-flow uses no-OA physical storage or no-OA rule settings as runtime source of truth.

## Verification

```bash
npm --prefix web test -- --run BankFlowRuleBatchPage.test.tsx BankFlowRuleBatchApi.test.ts BankFlowRuleBatchPolicy.test.ts CandidateGroupGrid.test.tsx
npm --prefix web run build
PYTHONPATH=backend/src:. python3 -m pytest tests/test_app_settings_service.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py -q
```

Results:

- Frontend Vitest: `80 passed`.
- Frontend build: passed. Existing CSS minifier warnings and chunk-size warning remain.
- Backend pytest: `130 passed, 5 warnings, 15 subtests passed`.

## Seven Test Categories

- Business core unit tests: not directly applicable; frontend extraction did not change business rules.
- Service-layer tests: backend regression rerun.
- API contract tests: `BankFlowRuleBatchApi.test.ts` and backend routes rerun.
- Read model/cache/background job tests: backend read model/repository regressions covered by P004 and rerun through repository boundary tests.
- Frontend component and interaction tests: covered by `BankFlowRuleBatchPage.test.tsx`, API/policy tests, and candidate grid tests.
- End-to-end business-flow integration tests: browser E2E not rerun in P005; existing E2E contract remains unchanged.
- Existing feature regression tests: candidate grouping and backend no-OA/bank-flow regressions rerun.

## Remaining Risks

- Full browser E2E was not rerun in this final slice.
- Production deployment/smoke on `139.155.5.132` was not executed in this local implementation pass.
- Existing web build warnings are unrelated to this slice and remain as follow-up build hygiene.
