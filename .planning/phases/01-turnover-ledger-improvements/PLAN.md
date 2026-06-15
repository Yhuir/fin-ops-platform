# Phase 01 外部往来款管理 L2 Plan

## Scope

本计划覆盖两条工作流：

1. BUG-001：确认闭环时报“银行流水状态已变化”。
2. 新功能：外部往来款管理展示并撤回关联台闭环关系，且与关联台撤回双向一致。

本计划不执行实现。实现必须在下一步 GSD execute / TDD 流程中进行。

## Architecture Gate

实现必须复用现有统一边界：

- Turnover 写：`TurnoverLedgerWriteFacade` / `TurnoverLedgerWriteUnitOfWork`。
- Turnover stale precondition：`TurnoverLedgerBankRowStalePreconditionPort`。
- Turnover relation：`TurnoverRelationService` / relation repository。
- Workbench relation 写：`TurnoverLedgerWorkbenchPairPort` / `WorkbenchRelationCommandService`。
- Workbench relation 读：`WorkbenchRelationReadFacade` / `workbench_relation` read model。
- Read model refresh：PostgreSQL durable queue + runtime worker。
- 前端 operation closure：`GlobalOperationOverlayProvider` + operation barrier。

禁止新增：

- 第二套外部往来闭环状态表。
- 前端-only 闭环 chip 状态。
- 绕过 command service 的 direct pair mutation。
- 忽略 stale precondition 的自动重试。

## Slice 1：BUG-001 TDD 修复

### 目标

修复确认闭环误报 `银行流水状态已变化`，但保留并发保护。

### Red Tests

1. 后端转换测试：
   - SQL bank detail row 缺 `category_version`。
   - row 有 `manual_category_version=9`。
   - `_turnover_bank_transaction_row_from_bank_detail(...)` 应返回 `category_version=9`。

2. 后端 fallback 测试：
   - 缺 `category_version` 和 `manual_category_version`。
   - row 有 `version=5`。
   - 返回 `category_version=5`。

3. 优先级测试：
   - 同时有 `category_version=3`、`manual_category_version=9`。
   - 返回 `category_version=3`。

4. 前端现有测试保持通过：
   - `refreshes the grouped ledger before manual closure and submits latest bank row versions`。

### Expected Fix

最小修复应在 SQL bank detail -> turnover bank row 转换边界做版本归一化：

- 位置候选：`Application._turnover_bank_transaction_row_from_bank_detail(...)`。
- 逻辑：`category_version` -> `manual_category_version` -> `version`。
- 输出统一写入 `category_version`。

### Verification

目标命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
cd web && npm test -- --run src/test/TurnoverLedgerPage.test.tsx src/test/TurnoverLedgerApi.test.ts
```

如改动只在后端转换，可先跑最小 pytest/unittest，再跑上述目标验证。

## Slice 2：关联台闭环状态投影

### 目标

在 `turnover_ledger` fresh payload 中表达 Workbench canonical relation 状态。

### Research Tasks

- 找出现有 `turnover_ledger` SQL projection builder 的 source rows 和 payload shape。
- 找出现有 `workbench_relation` distribution 中 bank-only `turnover_manual_closure` relation 的 row ids、case id、relation mode、version。
- 决定 enrichment 放在 projection builder，还是 query service 通过 relation read facade enrichment。

### API Contract

建议新增或确认等价字段：

- flow row:
  - `workbench_relation_id`
  - `workbench_relation_mode`
  - `workbench_relation_status`
  - `workbench_relation_row_ids`
  - `workbench_relation_source`
  - `workbench_relation_version`
- group:
  - `workbench_closure_status`: `none | partial | closed | mixed_relations | refreshing`
  - `workbench_closed_row_count`
  - `workbench_total_flow_row_count`

### Tests

Backend:

- `turnover_ledger` payload shows closed status for rows in active `turnover_manual_closure`.
- partial group returns `partial` and correct counts.
- multiple relations in same group returns `mixed_relations`.
- stale/missing `workbench_relation` does not fake closed status; returns refreshing/diagnostic state.

Frontend:

- group chip renders `关联台已闭环 · N笔`。
- row chip renders `关联台已闭环` only on rows in relation.
- partial group renders `部分已闭环 X/Y`。
- stale relation status disables relation-scoped withdraw.

## Slice 3：外部往来页撤回关联台闭环

### 目标

用户在外部往来款管理选择已闭环流水时，按 relation 撤回 canonical Workbench relation。

### UX Rules

- 普通未闭环 flow checkbox 仍用于确认闭环。
- 已闭环 flow selection 进入 relation selection mode。
- 选中任一已闭环 flow，自动选中同 relation 的所有 flow rows。
- toolbar 显示：`已选择 1 个关联台闭环关系，包含 N 笔流水`。
- 按钮文案：`撤回关联台闭环`。
- 确认弹窗展示全部流水、影响说明和可选备注。

### Backend Contract

撤回请求必须使用 relation identifier 和 expected version，而不是任意 row ids：

- `relation_id` / `case_id`
- `expected_versions`
- `idempotency_key`
- `note`

现有 `POST /api/turnover-ledger/relations/{id}/withdraw` 可作为候选入口，但必须确认它撤回的是 Workbench bank-only `turnover_manual_closure`，并返回足够 freshness targets。

### Tests

Backend:

- manual bank-only `turnover_manual_closure` 可撤回。
- system/generated relation 拒绝撤回。
- 已升级为 OA + bank + invoice paired 的 relation 拒绝从 turnover 页面撤回。
- stale relation version 拒绝。
- Workbench command service 缺失时 fail fast，无 Turnover 半写。

Frontend:

- 选中已闭环 row 自动扩展到同 relation rows。
- 撤回确认弹窗列出 relation 全部 rows。
- 撤回成功后等待 freshness targets 并 reload。
- 无权限、stale、write safety blocked 时按钮禁用。

## Slice 4：关联台撤回反向刷新外部往来款

### 目标

在关联台撤回外部往来 relation 后，外部往来页面 fresh 后准确反映 chip/按钮变化。

### Research Tasks

- 找出关联台 withdraw 返回的 freshness targets。
- 确认 `turnover_manual_closure` relation withdraw 是否 enqueue `turnover_ledger` refresh。
- 如果没有，补齐 relation command / lifecycle fan-out，而不是让前端硬改状态。

### Tests

Backend/integration:

- Workbench withdraw `turnover_manual_closure` enqueues `turnover_ledger` refresh。
- `turnover_ledger` rebuild 后不再显示该 relation closed status。

Frontend:

- 收到 `workbenchRelationUpdated` 后仅触发 reload/refresh hint。
- fresh payload 更新后 chip 消失。

## Docs Impact Plan

实现后可能需要同步：

- `docs/modules/turnover-ledger/state-machine.md`
- `docs/modules/turnover-ledger/tests.md`
- `docs/modules/turnover-ledger/implementation-notes.md`
- `docs/dev/api-contracts.md`，如果新增 payload 字段或 API response shape。
- `docs/app-architecture/pages.md`，如果页面跨页状态契约变化。
- `docs/operations/runtime-worker-governance.md`，如果新增 refresh target / worker registry 变化。

## Verification Matrix

后端目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api tests.test_turnover_ledger_uow_contract tests.test_turnover_workbench_integration tests.test_workbench_turnover_grouping tests.test_turnover_ledger_query_service tests.test_turnover_ledger_read_model_refresh -v
```

前端目标验证：

```bash
cd web && npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/domainEvents.test.ts src/test/OperationBarrierApi.test.ts
```

文档验证：

```bash
bash scripts/verify.sh docs
```

## Execution Order

1. 先修 BUG-001，因为它会阻断当前闭环主流程。
2. 再做 read/API payload projection，不做 UI 假状态。
3. 再做前端 chip 和 relation-scoped selection。
4. 再接外部往来页撤回。
5. 最后验证关联台撤回反向刷新。

每个 slice 都必须先写 red test，再实现，再跑目标验证。
