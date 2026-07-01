# P001 Baseline Audit And Migration Plan

Use this as the first bounded execution prompt inside the `/goal` controller.

```text
Goal:
Establish the authoritative current-state baseline for fully closing `bank-flow-rule-batches`, then produce the smallest safe implementation plan for the first code-changing slice. Do not implement migrations or refactors in this prompt unless the audit proves a tiny single-file guard is immediately required.

Evidence to inspect:
- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/index.md`
- `docs/app-architecture/README.md`
- `docs/modules/README.md`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/bank-flow-rule-batches/README.md`
- `docs/modules/bank-flow-rule-batches/boundary-io.md`
- `docs/modules/bank-flow-rule-batches/state-machine.md`
- `docs/modules/bank-flow-rule-batches/tests.md`
- `docs/modules/bank-flow-rule-batches/e2e-coverage.md`
- `docs/modules/no-oa-bank-batches/boundary-io.md`
- `docs/modules/read-models/boundary-io.md`
- `docs/modules/runtime-workers/boundary-io.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/dev/api-contracts.md`

Code and tests to inspect:
- `backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py`
- `backend/src/fin_ops_platform/services/bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/bank_batch_service.py`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_read_model_repository.py`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_read_model_refresh_producer.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- PostgreSQL repository/state-store/migration files that mention `bank_flow_rule_batch`, `bank_flow_rule_batches`, `no_oa_bank_batch_rows`, or `requirements_by_tag_code`
- `web/src/pages/BankFlowRuleBatchPage.tsx`
- `web/src/features/bankFlowRuleBatches/*`
- `tests/test_bank_flow_rule_batch*.py`
- affected no-OA regression tests
- `web/src/test/BankFlowRuleBatch*.test.*`
- `web/e2e/bank-flow-rule-batches-flow.spec.ts`

Use CodeGraph for:
- callers/impact of `update_no_oa_bank_batch_tag_selection`
- callers/impact of `save_bank_flow_rule_batch_mutation`
- callers/impact of `save_bank_flow_rule_batches_scope`
- callers/impact of `list_bank_flow_rule_batch_rows`
- callers/impact of `_refresh_bank_flow_rule_batch_runtime_snapshot`
- route/service/read-model flow from `/api/bank-flow-rule-batches` to repository/persistence

Use `rg` for literal checks:
- `selected_tag_codes`
- `selectedTagCodes`
- `no_oa_bank_batch_tag_selection`
- `bank_flow_rule_batch`
- `save_bank_flow_rule`
- `list_bank_flow_rule`
- `scope_key="all"`
- `read_model.no_oa_bank_batch_rows`
- `app.no_oa_bank_batches`

Required output artifact:
- Create or update `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/BASELINE_AUDIT.md`.
- The audit must include:
  - current storage facts and migration gap
  - current rule persistence facts and migration gap
  - current read model/worker facts and migration gap
  - current performance hot paths and unbounded scope usage
  - current frontend module boundaries and split candidates
  - current test coverage mapped to the seven AGENTS.md categories
  - exact old-code deletion conditions
  - risk-ranked first implementation slice
  - the next single execution prompt to run, named `P002_*`, but do not generate multiple future prompts

Architecture constraints:
- Do not change behavior in this audit unless a blocking correctness issue is found.
- Do not add speculative abstractions.
- Do not plan a big-bang rewrite.
- Prefer a migration-compatible vertical slice:
  1. add independent tables and repository ports,
  2. dual-read only if required for migration safety and explicitly temporary,
  3. cut bank-flow writes/reads to independent storage,
  4. remove bank-flow dependence on no-OA physical storage,
  5. then move rule persistence.
- Preserve no-OA legacy behavior and tests.

Verification to run:
- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_bank_flow_rule_batch_application_service.py -q`
- `npm --prefix web test -- --run src/test/BankFlowRuleBatchApi.test.ts src/test/BankFlowRuleBatchPolicy.test.ts src/test/BankFlowRuleBatchPage.test.tsx`
- `git diff --check -- .planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/BASELINE_AUDIT.md`

Stop condition:
- `BASELINE_AUDIT.md` exists and is specific enough that the next controller loop can execute one bounded implementation slice without rediscovering the whole module.
- Targeted baseline tests either pass or failures are captured with root-cause notes and become the next prompt.
```

