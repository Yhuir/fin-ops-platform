# Phase 01 外部往来款管理 L2 Context

## 目标

本 phase 目标是完善 `外部往来款管理` 页面围绕外部往来闭环的可见性、撤回能力和跨页一致性，并先分析一个当前已观察到的闭环确认 bug。

本阶段进入实现前必须保持两个约束：

- 不重复造轮子：已有统一事实源和统一写边界，必须复用现有 Turnover / Workbench relation 架构。
- 不绕过 GSD：实现前先完成本 L2 context / research / plan，并用测试矩阵保护后再改代码。

## 用户需求

### 完善 1：展示关联台闭环状态

当一组外部往来流水已经通过关联台/Workbench canonical relation 闭环时，`外部往来款管理` 页面需要明确表达：

- 哪个组已经存在关联台闭环关系。
- 哪几条具体流水已经属于该闭环关系。
- 当前状态是全部闭环、部分闭环、未闭环，还是状态刷新中。

建议表达：

- 组级 chip：`关联台已闭环 · N笔` 或 `部分已闭环 X/Y`。
- 行级 chip：每条已进入 active Workbench relation 的流水显示 `关联台已闭环`。
- 不使用泛化文案 `已关联`，避免和候选、Turnover 本地 relation、读侧归属混淆。

### 完善 2：在外部往来款管理中撤回关联台闭环

已在关联台闭环的外部往来关系，需要在外部往来款管理中提供撤回入口。

关键设计约束：

- 撤回必须按 relation/case 关系执行，不按任意 row ids 半撤回。
- 用户选中任意一条已闭环流水时，应高亮同一 active relation 内全部相关流水。
- 组级操作区、行级菜单或顶部 selection toolbar 可以出现 `撤回关联台闭环`。
- 确认弹窗需要展示 relation 包含的全部流水、影响说明和可选撤回备注。

### 完善 3：关联台撤回应同步反馈到外部往来款管理

如果用户在关联台中选中外部往来流水并撤回，效果必须等同于在外部往来款管理撤回同一 canonical relation。

要求：

- 关联台撤回后，后端通过 canonical relation command boundary 写事实。
- 返回 freshness targets 应覆盖 `workbench_relation`、`workbench`、`workbench:all` 和 `turnover_ledger:all` 或等价 turnover affected scope。
- 外部往来款管理当前打开时，只能把前端 domain event 当刷新提示；最终 chip/按钮变化必须来自 fresh `turnover_ledger` payload。

## 当前 Bug

复现路径来自用户截图：

1. 在 `外部往来款管理` 页面选中同组两条外部往来流水。
2. 点击 `确认闭环`。
3. 抽屉展示收入/支出合计一致，差额 `0.00`。
4. 点击 `确定`。
5. 页面弹出 `操作失败`，错误文案：`银行流水状态已变化，请刷新后重试。`

这不是 UI 表达问题，而是后端 stale precondition 拒绝写入。当前 L2 只记录根因分析和计划，不做实现。

## 统一事实源判断

现有架构已经有统一事实源和统一写边界，不需要另造状态表或前端本地闭环状态：

- Turnover 读侧：`turnover_ledger` SQL read model。
- Turnover 写侧：`TurnoverLedgerWriteFacade` / `TurnoverLedgerWriteUnitOfWork`。
- 银行流水版本检查：`TurnoverLedgerBankRowStalePreconditionPort`。
- Turnover 本地 relation 写入：`TurnoverLedgerRelationWritePort` / relation repository。
- Workbench canonical relation 写入：`TurnoverLedgerWorkbenchPairPort` -> `WorkbenchRelationCommandService`。
- Workbench relation 读侧：`WorkbenchRelationReadFacade` / `workbench_relation` read model。
- 后台刷新事实源：PostgreSQL `job.outbox_events`、`job.read_model_dirty_scopes`。

因此新增 chip 和撤回功能的方向应是：

- 把 Workbench active relation 状态投影到 `turnover_ledger` payload。
- 撤回复用现有 Workbench relation command boundary。
- 页面只消费 fresh payload 和 operation freshness targets。

## 非目标

- 不新增外部往来专用的第二套闭环事实源。
- 不用前端 domain event 直接改变 chip 作为事实。
- 不把 `deterministic` 零差额候选当成已闭环。
- 不允许从外部往来页撤回已经升级为 OA + 银行 + 发票三栏 paired 的完整关系；这类关系应从关联台撤回。
- 不在旧 fallback 路径上堆新业务逻辑。

## 验收标准草案

- 已在 Workbench active relation 中的外部往来流水，在外部往来页面显示组级和行级闭环状态。
- 同一组部分流水闭环时，显示 `部分已闭环 X/Y`，未闭环流水仍可参与合法闭环选择。
- 选中已闭环流水时，选择语义按 relation 自动扩展到同一 relation 内全部流水。
- 外部往来页撤回时调用 canonical relation withdraw/cancel 边界，不半写 Turnover 本地 relation。
- 关联台撤回同一 relation 后，外部往来页刷新到 fresh payload 后 chip 消失或变成部分闭环。
- 当前确认闭环 bug 的根因被测试复现，并以最小改动修复。
