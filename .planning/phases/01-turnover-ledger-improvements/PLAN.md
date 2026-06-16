---
phase: "01"
plan: "turnover-oa-closure-case-merge"
type: "tdd"
wave: 1
depends_on:
  - ".planning/phases/00-cross-page-dependency-baseline/00-PLAN.md"
  - ".planning/phases/01-turnover-ledger-improvements/CONTEXT.md"
  - ".planning/phases/01-turnover-ledger-improvements/RESEARCH.md"
  - ".planning/debug/turnover-oa-closure-chips.md"
requirements:
  - "PAGE-01"
  - "PAGE-05"
autonomous: false
planner_status: "inline-generated"
plan_checker_status: "not-run: Codex subagent policy requires explicit user authorization"
execution_status: "completed"
verification_status: "passed"
---

# Phase 01 Plan: 外部往来 OA 关联与流水闭环语义拆分

## Objective

修复外部往来款管理中 `关联台已关联` 混淆 OA 关联与多笔流水闭环的问题，并支持用户确认的业务口径：

- 流水 1 已配对 OA1、流水 2 已配对 OA2、流水 3 未配对时，选择流水 1/2/3 确认闭环后，形成一个 active Workbench case，成员为 OA1、OA2、流水 1、流水 2、流水 3。
- `已关联 OA` 只作为展示 chip，不参与确认闭环/撤回闭环按钮判断。
- `已闭环` / `未闭环` 表示多笔银行流水之间的外部往来闭环状态，并且只由 `turnover_manual_closure` 关系驱动。
- 外部往来款管理的撤回闭环只撤回多笔流水闭环语义；如果闭环确认时合并了原 OA-bank active case，撤回时必须恢复原 OA-bank case，不得丢失 OA 关系。

## Scope

本计划覆盖：

- 后端 Workbench relation command / Turnover pair port：允许外部往来闭环确认合并已有 OA-bank active relations。
- 后端撤回：从合并后的 `turnover_manual_closure` case 撤回时恢复 confirm history 中的原 OA-bank relations。
- Turnover read model payload：继续使用 fresh `workbench_relation` distribution 投影关系状态；不新增前端-only 状态。
- 前端 chip 和 toolbar：拆分 OA 关联展示与闭环状态，确认/撤回只按 `turnover_manual_closure` 判断。
- 模块文档和测试矩阵更新。

本计划不覆盖：

- 已包含 invoice 的三栏 paired relation 从外部往来页撤回。仍必须从关联台处理完整关系。
- 新增第二套外部往来闭环表。
- 绕过 `WorkbenchRelationCommandService` 的 direct pair mutation。
- 用前端 domain event 直接改变业务事实。

## Key Decisions

1. **单 active case 口径**
   - 确认闭环不是创建第二条 active case。
   - 若所选 bank rows 已分别属于 OA-bank active relation，确认闭环应通过 canonical relation 替换/合并路径生成一个 `turnover_manual_closure` active case。
   - 新 case 的 row set 是：所选 bank rows + 这些 bank rows 所属的可合并 OA-bank active relation 的全部 rows。

2. **可合并关系范围**
   - 允许合并 row types 只包含 `oa` 和 `bank` 的 active relations。
   - 拒绝合并包含 `invoice`、OA 附件发票、ETC、no-OA、batch accounting 或未知 owner 的 active relations，返回明确 conflict。
   - 允许多个 OA-bank case 被同一次外部往来闭环合并，只要它们没有 invoice 且只和所选 bank rows 重叠。

3. **撤回恢复语义**
   - 合并确认必须把被替换的 OA-bank relations 写入 history `before_relations`，并标记可恢复。
   - 外部往来页撤回闭环时调用 command service 的 withdraw/recover 语义，而不是简单 cancel。
   - bank-only `turnover_manual_closure` 撤回后无 restored relations；merged OA-bank `turnover_manual_closure` 撤回后恢复原 OA-bank active relations。

4. **UI 状态拆分**
   - `workbenchRelationStatus=linked && workbenchRelationMode !== turnover_manual_closure` 展示为 `已关联 OA` 或更保守的 `已关联业务单据`。
   - `workbenchRelationStatus=linked && workbenchRelationMode === turnover_manual_closure` 展示为 `已闭环`。
   - 每条 flow row 都展示闭环 chip：`已闭环` 或 `未闭环`。
   - 组级 chip 只按 `turnover_manual_closure` 计算：`已闭环 · N笔` / `部分已闭环 X/Y`。

## Task 1: 后端失败测试 - 合并已有 OA-bank case

**Files**

- `tests/test_workbench_relation_command_service.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_workbench_integration.py`

**Action**

先写 red tests，证明当前确认闭环会被 active row conflict 阻断，且目标行为是合并。

Required tests:

- `WorkbenchRelationCommandService.confirm_relation(... replace_existing=True ...)` 可以把两个已有 OA-bank active relations 替换为一个 `turnover_manual_closure` relation，并保存 `before_relations`。
- `TurnoverLedgerWorkbenchPairPort.create_turnover_manual_closure` 传给 command service 的 row set 包含原 OA row 和所选 bank rows，`replace_existing=True`，`before_relations` 包含被合并的 OA-bank relations。
- API/integration：流水 1 已关联 OA1、流水 2 已关联 OA2、流水 3 未关联时，`POST /api/turnover-ledger/closures/confirm` 成功后 Workbench active snapshot 只有一个 relevant active case，包含 OA1、OA2、bank1、bank2、bank3。

**Acceptance Criteria**

- 测试当前应失败或揭示缺口。
- 测试不放宽 bank row category/version stale precondition。
- 测试明确拒绝 invoice relation 被外部往来页合并。

## Task 2: 后端实现 - 确认闭环合并关系

**Files**

- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py` if an explicit merge helper is needed
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py` only if existing restore marking is insufficient

**Action**

Implement minimal backend behavior:

- In `TurnoverLedgerWorkbenchPairPort.create_turnover_manual_closure`, before confirming, inspect active relations for selected bank row ids through command service or canonical pair snapshot.
- Validate merge candidates:
  - relation status active
  - row types subset of `{"oa", "bank"}`
  - no invoice row type
  - no relation mode explicitly owned by no-OA, ETC, batch accounting, or other non-OA-bank owner
- Build merged row ids/types preserving original relation rows and appending unlinked selected bank rows.
- Call `confirm_relation` with:
  - `case_id = turnover:{relation_id}`
  - `relation_mode = turnover_manual_closure`
  - `replace_existing = true` when any active OA-bank relation is being merged
  - `before_relations = active merge candidates`
  - `special_metadata.turnover_relation_id`
  - `special_metadata.turnover_closure_bank_row_ids`
  - `history_operation_type = turnover_manual_closure_confirm`

**Acceptance Criteria**

- Existing bank-only closure behavior remains valid.
- Active OA-bank relations are not lost; they are preserved in history as restorable before-relations.
- Active invoice/three-pane relations return conflict and do not half-write Turnover relation.
- Command service missing remains fail-fast.

## Task 3: 后端失败测试 - 撤回闭环恢复 OA 关系

**Files**

- `tests/test_workbench_relation_command_service.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_workbench_integration.py`

**Action**

Add red tests for withdraw:

- With active `turnover_manual_closure` containing OA1/OA2/bank1/bank2/bank3 and confirm history before-relations containing case OA1-bank1 and case OA2-bank2, withdrawing from turnover restores those two OA-bank active relations.
- Bank-only closure still withdraws to no active relation.
- A `turnover_manual_closure` relation containing invoice is rejected from turnover withdraw with existing `turnover_closure_withdraw_requires_workbench` semantics.

**Acceptance Criteria**

- Tests prove current simple cancel path is insufficient for merged OA closure.
- Tests assert restored relation case ids and row sets.
- Tests assert `affected_row_ids` / changed case ids include cancelled turnover case and restored OA cases.

## Task 4: 后端实现 - 撤回使用 recover 语义

**Files**

- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py` if the existing `withdraw_relation` return shape needs normalization

**Action**

- Change turnover closure withdraw port from `cancel_relation(...)` to command service `withdraw_relation(...)` or an explicit owner-safe recover command.
- Update withdraw precondition:
  - allow `turnover_manual_closure` relations whose row types are subset of `{"oa", "bank"}`;
  - reject any relation containing `invoice` or unknown row types;
  - continue requiring fresh relation facade when used for precheck.
- Preserve `history_operation_type = turnover_manual_closure_withdraw`.
- Return `restored_relations` in response if command service provides them, without changing frontend contract unless needed.

**Acceptance Criteria**

- Merged OA closure withdraw restores original OA relations.
- Bank-only closure withdraw still returns cancelled workbench pair relation.
- Invoice-upgraded closure still blocked from external turnover page.
- No Turnover local relation is withdrawn if Workbench withdraw precheck fails.

## Task 5: Read model/API mapper tests

**Files**

- `tests/test_turnover_ledger_read_model_refresh.py`
- `web/src/test/TurnoverLedgerApi.test.ts`
- `web/src/features/turnoverLedger/api.ts`
- `web/src/features/turnoverLedger/types.ts`

**Action**

Keep payload source as existing `workbench_relation_status/case_ids/mode/source/row_ids`. Add mapper-level tests if new derived frontend fields are introduced.

Preferred minimal route:

- Do not add backend fields unless necessary.
- Derive `hasOaRelation` / `hasTurnoverClosure` in frontend helper functions from existing fields.

If existing fields cannot identify OA-linked rows clearly enough, add explicit fields and update backend projection + API mapper tests:

- `workbench_relation_row_types`
- `workbench_relation_owner`

**Acceptance Criteria**

- API mapper preserves non-turnover linked relation mode/source/case ids.
- Turnover closure rows can be distinguished from OA-linked rows.
- Stale/non-fresh `workbench_relation` still fails projection and does not publish fake fresh turnover payload.

## Task 6: 前端失败测试 - chip 和 toolbar 拆分

**Files**

- `web/src/test/TurnoverLedgerPage.test.tsx`
- `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`
- `web/src/pages/TurnoverLedgerPage.tsx`

**Action**

Add red tests:

- A row with `workbench_relation_status=linked` and non-`turnover_manual_closure` mode renders `已关联 OA` and `未闭环`; `确认闭环` is enabled when the selection otherwise satisfies closure rules.
- A row with `workbench_relation_status=linked` and `workbench_relation_mode=turnover_manual_closure` renders `已闭环`; `确认闭环` disabled and `撤回闭环` enabled only when all selected rows belong to the same closure relation.
- Mixed OA-linked + unlinked selected rows can open confirm closure when at least two rows, same group, one income, one expense, zero delta.
- Group chip uses closure count only: `部分已闭环 X/Y`; OA-linked rows do not count as closed.

**Acceptance Criteria**

- No user-facing `关联台已关联` text remains in turnover ledger table for this scenario.
- `已关联 OA` chip never triggers withdraw button by itself.
- Each visible flow row has a closure chip.

## Task 7: 前端实现 - state helpers and labels

**Files**

- `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`
- `web/src/pages/TurnoverLedgerPage.tsx`

**Action**

- Replace `selectedRowsContainLinkedWorkbenchRelation` with `selectedRowsContainTurnoverClosure`.
- Keep `isTurnoverManualClosureLinkedRow` as the only closure decision helper.
- Update group and row chip rendering:
  - render OA relation chip separately for linked non-turnover rows;
  - render closure chip for every flow row;
  - group label counts only turnover closure rows.
- Keep existing stale/read-model gating and operation overlay behavior unchanged.

**Acceptance Criteria**

- Confirm closure path no longer blocked by OA-linked chip.
- Withdraw path still only available for selected same `turnover_manual_closure` relation.
- No layout regressions in grouped table.

## Task 8: Docs impact update

**Files**

- `docs/modules/turnover-ledger/README.md`
- `docs/modules/turnover-ledger/state-machine.md`
- `docs/modules/turnover-ledger/tests.md`
- `docs/modules/turnover-ledger/implementation-notes.md`
- `docs/modules/workbench-relations/state-machine.md` if relation merge/restore semantics become long-term contract
- `docs/dev/api-contracts.md` only if API fields change

**Action**

Update docs after implementation:

- Distinguish OA relation display from turnover closure status.
- Document that turnover manual closure may merge OA-bank active relations into one `turnover_manual_closure` active case.
- Document withdraw semantics: bank-only cancels to none; merged OA-bank closure restores before-relations; invoice/three-pane closure must be handled from Workbench.
- Update test matrix with new regression names.

**Acceptance Criteria**

- Docs describe the final behavior, not the original prompt.
- No docs update is needed for unchanged API shape; if unchanged, final response must state `docs/dev/api-contracts.md 不适用`.

## Verification Plan

Target backend verification:

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_workbench_relation_command_service \
  tests.test_turnover_ledger_uow_contract \
  tests.test_turnover_workbench_integration \
  tests.test_workbench_turnover_grouping \
  tests.test_turnover_ledger_read_model_refresh \
  tests.test_turnover_ledger_api -v
```

Target frontend verification:

```bash
cd web && npm test -- --run \
  src/test/TurnoverLedgerApi.test.ts \
  src/test/TurnoverLedgerPage.test.tsx \
  src/test/domainEvents.test.ts \
  src/test/OperationBarrierApi.test.ts
```

Docs verification:

```bash
bash scripts/verify.sh docs
```

Optional full safety check if time allows:

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm run build
```

## Seven Test Categories

| Category | Applies | Planned coverage |
| --- | --- | --- |
| 1. Business core unit tests | Yes | Workbench relation replacement/restore and turnover relation closure rules. |
| 2. Service-layer tests | Yes | Turnover UoW + Workbench command service merge/withdraw transaction behavior. |
| 3. API contract tests | Yes | Confirm/withdraw responses, conflict errors, freshness targets if shape changes. |
| 4. Read model/cache/background job tests | Yes | Turnover projection consumes fresh Workbench relation context and does not fake closure state. |
| 5. Frontend component and interaction tests | Yes | Chips, confirm/withdraw toolbar, stale/permission disabled states. |
| 6. End-to-end business-flow integration tests | Yes | OA1-bank1 + OA2-bank2 + bank3 confirm closure, then withdraw restore OA relations. |
| 7. Existing feature regression tests | Yes | Bank-only turnover closure, invoice-upgraded withdraw rejection, operation overlay, domain event reload. |

## Execution Order

1. Write backend red tests for merge confirm and withdraw restore.
2. Implement backend merge confirm.
3. Implement backend withdraw restore.
4. Write frontend red tests for chips and toolbar decisions.
5. Implement frontend helper/label changes.
6. Run target backend and frontend verification.
7. Update module docs and rerun docs verification.

## Open Questions Before Execution

1. Label wording: use `已关联 OA` for every non-turnover linked relation, or use `已关联业务单据` when row types are not exposed and OA cannot be proven from payload.
2. API shape: keep deriving from existing `workbench_relation_*` fields, or add row types/owner fields for precise chip wording.
3. Confirmation conflict wording: when selected bank row belongs to invoice/three-pane relation, should user-facing message be “该流水已完成完整关联，请到关联台处理”?

## Execution Result

User approved the plan with `同意`; implementation and verification were completed on 2026-06-17.

Implemented:

- Backend confirm closure now merges eligible active OA-bank relations into one `turnover_manual_closure` active case instead of creating a second active case.
- Backend withdraw closure now uses Workbench withdraw/recover semantics so merged OA-bank relations are restored; bank-only closure still withdraws to no active relation.
- Existing turnover closures, invoice/three-pane relations, and incomplete/unknown relation structures are rejected from external turnover-page closure handling.
- Frontend row chips now separate OA/business document association from turnover closure state.
- Frontend confirm/withdraw buttons now depend only on `turnover_manual_closure`, not OA association chips.
- Module/product/API architecture docs and test matrix were updated.

Verified:

```bash
PYTHONPATH=backend/src python3 -m unittest -q \
  tests.test_workbench_pair_relation_service \
  tests.test_workbench_relation_command_service \
  tests.test_turnover_ledger_uow_contract \
  tests.test_turnover_workbench_integration \
  tests.test_workbench_turnover_grouping \
  tests.test_turnover_ledger_read_model_refresh \
  tests.test_turnover_ledger_api
```

Result: passed, 272 tests.

```bash
cd web && npm test -- --run \
  src/test/TurnoverLedgerApi.test.ts \
  src/test/TurnoverLedgerPage.test.tsx \
  src/test/domainEvents.test.ts \
  src/test/OperationBarrierApi.test.ts \
  src/test/GlobalOperationOverlayContext.test.tsx
```

Result: passed, 38 tests.

```bash
bash scripts/verify.sh docs
git diff --check
```

Result: both passed.

Remaining risk:

- The frontend `已关联 OA` chip derives OA evidence from existing relation mode/row ids; if production payloads use non-`oa-*` OA row ids without an OA-indicative relation mode, the UI falls back to `已关联业务单据`.
- No browser screenshot smoke was run; coverage is through component/API tests.
