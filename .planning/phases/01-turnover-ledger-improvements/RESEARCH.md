# Phase 01 外部往来款管理 L2 Research

## 读取来源

- `.planning/phases/01-turnover-ledger-improvements/01-PAGE-BASELINE.md`
- `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
- `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
- `docs/modules/turnover-ledger/README.md`
- `docs/modules/turnover-ledger/state-machine.md`
- `docs/modules/turnover-ledger/tests.md`
- `web/src/pages/TurnoverLedgerPage.tsx`
- `web/src/features/turnoverLedger/api.ts`
- `web/src/features/turnoverLedger/types.ts`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/turnover_relation_service.py`

## 当前架构结论

### 读侧

- `GET /api/turnover-ledger` 通过 `TurnoverLedgerQueryService` / `ReadModelQueryGateway` 读取 `turnover_ledger` SQL read model。
- `turnover_ledger` read model key 绑定 `turnover-ledger` worker 和 `turnover_ledger.read_model.refresh` job type。
- 页面必须区分 `fresh`、`refreshing`、`stale`、`missing`，不能把旧 payload 当 final truth。

### 写侧

手动闭环当前主链路：

```text
TurnoverLedgerPage.handleConfirmClosure
  -> wait turnover_ledger:all fresh
  -> reload grouped ledger
  -> rebind selected bank row ids to latest flow rows
  -> confirmTurnoverClosure(bank_row_ids, expected_versions, idempotency_key)
  -> POST /api/turnover-ledger/closures/confirm
  -> TurnoverLedgerConfirmRequestBoundaryFacade
  -> TurnoverLedgerWriteFacade.confirm_zero_difference_closure
  -> TurnoverLedgerWriteUnitOfWork
  -> TurnoverLedgerBankRowStalePreconditionPort
  -> TurnoverRelationService.confirm_zero_difference_closure
  -> TurnoverLedgerWorkbenchPairPort.create_turnover_manual_closure
  -> WorkbenchRelationCommandService
  -> enqueue turnover/workbench/workbench_relation/cost/search refresh
```

这条链路已经满足“统一事实源”的方向。后续功能应复用，不应新建外部往来闭环状态表。

### 当前 refresh targets

`TurnoverLedgerWriteFacade.confirm_zero_difference_closure` 已 enqueue：

- `turnover_ledger`
- `workbench`
- `workbench_relation`
- `cost_statistics`
- `search`

请求边界还会给前端返回用于可见性的 freshness targets：

- `turnover_ledger:all`
- affected months 的 `workbench_relation`
- affected months 的 `workbench`
- `workbench:all`

## Bug 根因分析

### 现象

确认闭环时后端返回：

```text
银行流水状态已变化，请刷新后重试。
```

该文案来自 `TurnoverLedgerBankRowStalePreconditionPort.assert_current(...)`。

### 触发条件

前端提交的 `expected_versions` key 形如：

```json
{
  "turnover_bank_row:txn_imported_1278": 0
}
```

后端写前校验用 `TurnoverLedgerBankRowStalePreconditionPort._bank_row_version(row)` 比较当前 row version。比较顺序是：

```text
category_version -> manual_category_version -> version
```

只要前端从 grouped payload 得到的 `categoryVersion` 与后端当前 bank row 的上述版本值不同，就会抛出该错误。

### 高置信根因假设

SQL bank detail -> turnover bank row 的转换口径不一致：

- `Application._turnover_bank_transaction_row_from_bank_detail(...)` 会把 bank detail SQL row 转成 turnover row。
- 当前转换会写入 `category_code`、`category_label`、`category_path`、`turnover_role`、`turnover_action_type`、`turnover_family` 等字段。
- 但当前代码没有显式把 `manual_category_version` 或 `version` 归一成 `category_version`。
- `TurnoverLedgerService` 构建 grouped flow row 时读取 `bank_row.get("category_version") or 0`。
- 因此当 SQL bank detail row 只有 `manual_category_version=真实版本` 而没有 `category_version` 时，页面 grouped payload 暴露 `category_version=0`。
- 但写前 stale precondition 仍会从同一 row 的 `manual_category_version` fallback 到真实版本。
- 结果是前端提交 `0`，后端当前版本为真实值，稳定触发“银行流水状态已变化”。

这解释了截图中的行为：页面已经在提交前刷新并重绑，但仍然被后端判断为 stale。

### 需要在实现阶段验证

实现前先写失败测试，不直接改代码：

- 构造 SQL bank detail row：
  - 有 `manual_category_version=9`
  - 没有 `category_version`
  - 有有效外部往来 `effective_*` 字段
- 调用 `_turnover_bank_transaction_row_from_bank_detail(...)`
- 期望 turnover row 带 `category_version=9`
- 当前预期应失败，从而证明 bug。

补充验证：

- `manual_category_version` 缺失但 `version` 存在时也应归一。
- `category_version` 已存在时优先使用 `category_version`。
- 前端 `closureExpectedVersions(...)` 应保持只从 fresh flow rows 的 `categoryVersion` 生成 expected versions。

## 关联台闭环状态展示研究

### 不能用的来源

- 不能用前端事件直接设置 chip。
- 不能用 `deterministic` Turnover relation 判断已闭环。
- 不能用 grouped summary row 推断全部 flow rows 已闭环。
- 不能直接读旧 pair service snapshot 作为页面事实。

### 应使用的来源

- Workbench active relation / `workbench_relation` read model。
- `WorkbenchRelationReadFacade` 读取 relation distribution 或 canonical relation 详情。
- `turnover_ledger` read model 在 fresh 状态下携带 derived relation status。

### 建议 payload 字段

需要在 L2 实施时确认是否已有等价字段；如果没有，建议新增在 turnover grouped flow rows 上：

```json
{
  "workbench_relation_id": "case:...",
  "workbench_relation_mode": "turnover_manual_closure",
  "workbench_relation_status": "active",
  "workbench_relation_row_ids": ["txn_1", "txn_2"],
  "workbench_relation_closed_row_count": 2,
  "workbench_relation_source": "turnover_manual_closure"
}
```

组级可以由 flow rows 聚合出：

- `none`
- `partial`
- `closed`
- `mixed_relations`
- `refreshing`

### UI 设计约束

- 行级 chip 标注具体 row 是否在 active relation。
- 组级 chip 标注闭环覆盖范围。
- 多个 relation 混在同组时，不能一个按钮撤全部；必须 relation-scoped 选择。
- 已闭环 row 的会影响 relation 的编辑入口应禁用或要求先撤回。

## 撤回研究

### 外部往来页撤回

只允许撤回仍是 bank-only `turnover_manual_closure` 的 relation：

- manual/source 合法。
- Workbench relation 仍未升级为 OA + bank + invoice paired。
- expected relation version 当前。
- canonical write safety 通过。

撤回入口应按 relation/case，不按任意 row ids。

### 关联台撤回反向同步

关联台撤回同一 Workbench relation 后，外部往来款管理必须通过 `turnover_ledger` refresh 体现变化。

关键风险：

- 如果关联台撤回只刷新 `workbench_relation/workbench`，但不刷新 `turnover_ledger`，外部往来页 chip 会滞后。
- 如果只靠 domain event 移除 chip，会造成跨 tab / worker / stale 状态不一致。

## 旧逻辑风险

- `TurnoverLedgerClosureLegacyFallbackFacade` 仍存在；新增功能不得扩大 legacy fallback 职责。
- 涉及 Workbench relation 的写入缺 command service 时必须 fail fast。
- read model stale 时页面可以展示诊断，但不能用 stale payload 做最终闭环判断。
- 系统生成或 deterministic relation 不允许被当作 manual closure 撤回。

## 待确认问题

- Workbench relation 投影到 turnover payload 的最佳位置：projection builder 直接 join，还是 query service 通过 relation facade enrichment。
- 关联台撤回 `turnover_manual_closure` 时当前 refresh targets 是否已经包含 `turnover_ledger`；如果没有，需要补齐。
- 已闭环 row 的编辑限制是否只禁用 relation-impacting fields，还是禁用整条 row 的 extra 编辑。
- 导出是否需要新增 `关联台闭环状态`、`relation_id`、`闭环来源`、`闭环时间`。
