# Codex /goal 主控 Prompt

把下面整段文本作为 Codex 主控 `/goal` objective 使用。

```text
Fully close this fin-ops-platform task:

修复外部往来款管理中 OA 关联 chip 与多笔流水闭环 chip 混淆的问题，并按 GSD Phase 01 plan 完全闭环：

- 页面中每条流水必须分别展示：
  - OA/业务单据关联状态，例如 `已关联 OA` 或在无法证明 OA 时使用更保守的 `已关联业务单据`；
  - 多笔银行流水外部往来闭环状态：`已闭环` / `未闭环`。
- `已关联 OA` 只作为展示 chip，不参与确认闭环和撤回闭环的决策链路。
- `确认闭环` 只由外部往来闭环状态、同组、至少一收一支、零差额、fresh payload、版本/幂等/权限等写安全条件决定。
- `撤回闭环` 只由 `turnover_manual_closure` 关系决定。
- 如果流水 1 已配对 OA1、流水 2 已配对 OA2、流水 3 未配对，那么在外部往来款管理选择流水 1/2/3 确认闭环后，必须形成一个 active Workbench case，成员包含 OA1、OA2、流水 1、流水 2、流水 3。不是两个 active case。
- 外部往来款管理里的撤回闭环只撤回多笔流水闭环语义。如果确认闭环时合并了原 OA-bank active case，撤回时必须恢复原 OA-bank active case，不得删除或丢失 OA 关系。
- 已包含 invoice 的三栏 paired relation 不从外部往来页撤回，仍要求到关联台处理完整关系。
- 最终必须完成实现、测试、文档影响评估、验证和风险报告，不能停在分析或半成品。

Act as the main controller for /Users/yu/Desktop/fin-ops-platform. Use the fin-ops-goal-controller workflow if available. Run a closed-loop GSD workflow: in each loop, generate exactly one bounded execution prompt, execute it immediately, review the result, then decide DONE, BLOCKED, or CONTINUE. If CONTINUE, derive the next single prompt from the latest state. Do not generate a backlog of future prompts.

Primary planning artifacts to read first:

- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/index.md
- docs/modules/README.md
- docs/modules/turnover-ledger/README.md
- docs/modules/turnover-ledger/state-machine.md
- docs/modules/turnover-ledger/tests.md
- docs/modules/workbench-relations/README.md
- docs/modules/workbench-relations/state-machine.md
- .planning/phases/00-cross-page-dependency-baseline/00-PLAN.md
- .planning/phases/01-turnover-ledger-improvements/CONTEXT.md
- .planning/phases/01-turnover-ledger-improvements/RESEARCH.md
- .planning/phases/01-turnover-ledger-improvements/PLAN.md
- .planning/debug/turnover-oa-closure-chips.md

Important existing code/tests to inspect before editing:

- backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py
- backend/src/fin_ops_platform/services/workbench_relation_command_service.py
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py
- backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py
- backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py
- backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py
- web/src/pages/TurnoverLedgerPage.tsx
- web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx
- web/src/features/turnoverLedger/api.ts
- web/src/features/turnoverLedger/types.ts
- tests/test_workbench_relation_command_service.py
- tests/test_turnover_ledger_uow_contract.py
- tests/test_turnover_workbench_integration.py
- tests/test_workbench_turnover_grouping.py
- tests/test_turnover_ledger_read_model_refresh.py
- tests/test_turnover_ledger_api.py
- web/src/test/TurnoverLedgerApi.test.ts
- web/src/test/TurnoverLedgerPage.test.tsx

Global rules:

- Follow AGENTS.md and repository-local docs.
- Keep changes minimal, scoped, reversible, and clean.
- Work on main unless the user explicitly changes that instruction.
- Preserve user changes in the worktree. Do not revert unrelated edits.
- Do not leave temporary files, dead code, prompt scratch files, generated junk, or unrelated edits.
- Use apply_patch for manual edits.
- Use CodeGraph for structural questions when available. Use rg for literal strings and file discovery.
- Prefer existing encapsulations, services, repositories, platform helpers, test builders, fixtures, and verification scripts before adding new code.
- Do not duplicate existing service/repository/platform behavior under a new name.
- Do not guess API fields, DB columns, statuses, IDs, response shapes, or business rules. Inspect authoritative contracts first.
- Do not add broad fallback branches, speculative compatibility paths, placeholder logic, or “just in case” abstractions.
- If safe completion requires broader refactoring than the approved plan, pause and state the expanded scope before continuing.

Architecture gates:

- Keep server.py thin: routing, dependency wiring, and HTTP mapping only.
- Put business logic in services.
- Put SQL and table knowledge in repositories.
- Inject explicit service dependencies; do not pass the whole Application into services.
- Do not let services read HTTP cookies/headers, import app.auth, or construct HTTP responses.
- Keep workers independent from Application, app.server, app.auth, HTTP responses, and route modules.
- Route read model refresh through freshness/status/enqueue boundaries.
- Use ReadModelRefreshGateway and scope policy registry for non-transactional refresh normalize/validate/dedupe before durable queue enqueue.
- Keep transactional writer enqueue behavior inside the same business transaction and honor equivalent scope contracts.
- Do not let pages read stale read models while pretending they are fresh.
- Use Redis only after fresh gate; treat RabbitMQ only as optional transport/wakeup.
- Preserve Workbench active generation atomic publish semantics.
- For production-facing behavior, consider permissions, audit, rollback, idempotency, and data consistency.

Closed-loop state to maintain internally:

- Objective
- Current phase
- Known facts and source files
- Assumptions
- Affected modules
- Affected APIs/services/repositories/read models/workers/pages/docs/tests
- Files changed
- Tests added or changed
- Seven-category test coverage decision
- Verification commands and results
- Open risks
- Next action

Loop algorithm:

1. Analyze current state.
   - Read the planning artifacts and module docs listed above.
   - Inspect current code and tests before editing.
   - Identify the highest-risk unknown or gap.
   - Decide whether the next bounded action is test writing, backend implementation, frontend implementation, docs update, verification, or debugging.

2. Generate exactly one bounded execution prompt for the next action only.
   The prompt must include:
   - Goal
   - Evidence/files to inspect
   - Allowed files/modules
   - Architecture constraints
   - Existing abstractions/helpers/tests to reuse
   - Required edits or research
   - Tests/docs to consider
   - Stop condition
   Then execute that prompt immediately in the same run.

3. Execute the bounded prompt.
   - For behavior changes, write or update relevant tests before implementation where practical.
   - Make only necessary changes.
   - Keep backend, frontend, repository, worker, read model, and docs boundaries intact.
   - Reuse existing service, repository, platform helper, fixture, and test patterns.
   - Update module docs when facts, state machines, test matrices, API shape, cross-page behavior, or implementation decisions change.

4. Review the result.
   - Inspect the diff.
   - Check for scope creep, duplicated abstractions, dead code, temporary files, missing docs, missing tests, and contract violations.
   - Re-check backend architecture gates.
   - Run the smallest reliable verification first.
   - If tests fail, debug systematically and continue the loop.

5. Decide status.
   - DONE only when requested behavior is implemented, tests/docs decisions are handled, verification was attempted, and remaining risk is explicit.
   - BLOCKED only when a required fact cannot be discovered locally, a necessary external system/user decision is unavailable, or the same blocker has persisted through repeated attempts.
   - Otherwise CONTINUE.

6. Continue.
   If not DONE or BLOCKED, generate exactly one next execution prompt from the latest review result and execute it. Address the highest-risk remaining gap first.

Required implementation order:

1. Backend red tests for confirming closure with existing OA-bank active relations.
2. Backend implementation for merging eligible OA-bank relations into one `turnover_manual_closure` active case.
3. Backend red tests for withdrawing merged closure and restoring original OA-bank relations.
4. Backend implementation for withdraw/recover semantics.
5. API/read-model mapper tests if new fields are needed; otherwise prove existing fields preserve enough relation mode/source/case data.
6. Frontend red tests for chip split and toolbar decisions.
7. Frontend implementation for labels and selection gating.
8. Module docs update.
9. Targeted verification, then broader verification if risk justifies it.

Backend behavior requirements:

- `TurnoverLedgerWorkbenchPairPort.create_turnover_manual_closure` must keep bank-only closure behavior working.
- When selected bank rows already belong to active OA-bank relations, merge eligible active relations using canonical command service behavior, not direct mutation.
- Eligible merge candidates must have active status and row types limited to `oa` and `bank`.
- Reject relation candidates containing `invoice` or unknown/non-OA-bank owner semantics from turnover page.
- Preserve replaced OA-bank relations in history as restorable before-relations.
- Use `case_id = turnover:{relation_id}` and `relation_mode = turnover_manual_closure`.
- Keep stale precondition, idempotency, affected months, dirty/outbox, operation freshness targets, and command-service fail-fast behavior.
- Withdraw from turnover page must restore original OA-bank relations when the closure was created by merging them.
- Withdraw from turnover page must still cancel bank-only closure to no active relation.
- Withdraw from turnover page must reject invoice/three-pane relations and instruct handling from Workbench/关联台.

Frontend behavior requirements:

- Remove/replace vague turnover table wording `关联台已关联`.
- Render non-turnover linked relation as `已关联 OA` when source proves OA; otherwise use `已关联业务单据`.
- Render closure chip for each flow row: `已闭环` or `未闭环`.
- Group chip counts only `turnover_manual_closure` rows: `已闭环 · N笔` or `部分已闭环 X/Y`.
- Confirm closure must not be disabled merely because selected rows are linked to OA.
- Withdraw closure must only be enabled when selected rows all belong to one `turnover_manual_closure` relation.
- Keep stale/read-model gating, permission gating, operation overlay, fresh reload/rebind, expected_versions, idempotency, and domain event behavior.

Target verification commands:

Backend:

PYTHONPATH=backend/src python3 -m unittest \
  tests.test_workbench_relation_command_service \
  tests.test_turnover_ledger_uow_contract \
  tests.test_turnover_workbench_integration \
  tests.test_workbench_turnover_grouping \
  tests.test_turnover_ledger_read_model_refresh \
  tests.test_turnover_ledger_api -v

Frontend:

cd web && npm test -- --run \
  src/test/TurnoverLedgerApi.test.ts \
  src/test/TurnoverLedgerPage.test.tsx \
  src/test/domainEvents.test.ts \
  src/test/OperationBarrierApi.test.ts

Docs:

bash scripts/verify.sh docs

Optional broader checks when risk justifies:

PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm run build

Seven test categories to evaluate and report:

1. Business core unit tests
2. Service-layer tests
3. API contract tests
4. Read model, cache, and background job tests
5. Frontend component and interaction tests
6. End-to-end business-flow integration tests
7. Existing feature regression tests

Final response format:

- Result
- Files changed
- Tests added or changed
- Seven test categories covered
- Seven test categories not applicable and why
- Verification commands run and results
- Docs impact decision
- Remaining untested risk
```
