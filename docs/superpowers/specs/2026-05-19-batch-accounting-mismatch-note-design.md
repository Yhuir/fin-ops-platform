# 批量账务金额不一致差额说明设计

## 背景

`日常报销批量账务管理` 当前要求银行流水金额必须等于所选 OA 金额合计，否则前端禁用提交、后端返回金额不一致错误。实际业务中，财务需要在确认差额原因后仍能完成批量账务关联。

本设计把该能力定义为 `人工差额闭环`：金额不一致时允许提交，但必须填写差额说明。提交后该 `batch_accounting` pair relation 视为已完成关联，不自动生成异常 case 或后续台账；系统必须结构化保存差额事实，并在关联台已配对区持续可见。

## 与既有文档关系

本设计是对 `docs/superpowers/specs/2026-05-18-batch-accounting-design.md` 中“批量账务不允许金额不一致通过备注放行”口径的有范围覆盖，仅适用于 `special_metadata.source == "batch_accounting"` 的日常报销批量账务关系。

该覆盖不改变普通关联台 `confirm-link` 的金额不一致规则，也不改变其他银企核销场景中“未闭环差额进入异常或台账”的产品原则。批量账务金额不一致且填写差额说明后，业务含义是 `人工差额闭环`：财务人员已经确认该差额可接受，系统不再为这笔差额自动生成异常 case、台账、待办或审批流。

## 目标

- 批量账务页面允许银行流水金额与所选 OA 合计不一致时提交。
- 金额不一致时强制填写 `差额说明`。
- 金额不一致提交后仍写入统一 `workbench_pair_relations`，不新增独立事实表。
- 差额事实结构化保存为 relation 级数据，包括银行金额、OA 合计、差额、说明、操作人和时间。
- 关联台已配对区在银行流水金额旁显示警示 icon，hover、focus、点击或触摸时展示差额详情。
- 撤回后恢复提交前关系，差额提示随 batch relation 消失。

## 非目标

- 不生成异常 case、台账、待办或审批流。
- 不新增差额原因类型下拉。
- 不把差额说明拼接进银行流水原始备注。
- 不改变普通关联台 `confirm-link` 的既有金额不一致备注规则。
- 不重做批量账务页面整体布局。

## 业务口径

批量账务提交时，后端重新读取当前银行流水和 OA 行，重新计算金额。

- 金额相等：按现有流程提交，不要求差额说明。
- 金额不等且差额说明为空：拒绝提交。
- 金额不等且差额说明非空：允许提交，视为财务人工确认的差额闭环。

差额说明是 relation 级说明，不属于银行流水原始备注，也不属于 OA 申请事由。

## 后端契约

### POST /api/batch-accounting/submit

Request 新增可选字段：

```json
{
  "bank_year": "2026",
  "oa_year": "2026",
  "bank_row_id": "txn_imported_202601_batch_001",
  "oa_row_ids": ["oa-exp-1", "oa-exp-2"],
  "expected_version": 1,
  "note": "OA合计不含员工餐补扣款，财务确认闭环"
}
```

服务端必须 trim `note`，并始终重新计算：

- `bank_amount`
- `oa_amount`
- `amount_delta = bank_amount - oa_amount`

校验：

- 金额相等时，`note` 非必填。
- 金额不等且 `note.trim()` 为空时，返回 `400 batch_accounting_note_required`。
- 金额不等且 `note.trim()` 非空时，创建 active `batch_accounting` relation。

金额不等但缺少说明的错误响应应包含结构化金额信息：

```json
{
  "error": "batch_accounting_note_required",
  "message": "银行流水金额与所选 OA 金额合计不一致，请填写差额说明。",
  "amount_check": {
    "status": "mismatch",
    "direction": "expense",
    "bank_amount": "3617.41",
    "oa_amount": "3425.41",
    "amount_delta": "192.00",
    "requires_note": true
  }
}
```

成功 relation 保存：

- `pair_relation.note`：差额说明；金额相等且未填说明时可为空或使用现有提交说明。
- `pair_relation.amount_check.status`：`matched` 或 `mismatch`。
- `pair_relation.amount_check.direction`：`expense`。
- `pair_relation.amount_check.bank_amount`。
- `pair_relation.amount_check.oa_amount`。
- `pair_relation.amount_check.amount_delta`。
- `pair_relation.amount_check.requires_note`。
- `pair_relation.special_metadata.source = "batch_accounting"`。
- `pair_relation.special_metadata.bank_row_id`、`oa_row_ids`、`invoice_row_ids`、`bank_year`、`oa_year`、`oa_years` 继续沿用现有字段。

pair relation history 必须记录同一份提交 `note` 和 `amount_check`。撤回时的 `reason` 仍作为 withdraw history 的 `note`，不得覆盖原提交说明。

### GET /api/batch-accounting

`bucket=submitted` 返回的 `relations_by_bank_row_id` 必须保留 relation 的 `note` 和 `amount_check`，供批量账务已提交页刷新后回显。

### GET /api/workbench

已配对区必须输出稳定字段，供前后端 worker 独立实现。后端 payload 使用 snake_case，前端 mapper 使用 camelCase。

后端 group 字段：

```json
{
  "group_id": "case:CASE-BATCH-txn_imported_202601_batch_001",
  "relation_note": "OA合计不含员工餐补扣款，财务确认闭环",
  "amount_check": {
    "status": "mismatch",
    "direction": "expense",
    "bank_amount": "3617.41",
    "oa_amount": "3425.41",
    "amount_delta": "192.00",
    "requires_note": true
  },
  "bank_rows": [
    {
      "id": "txn_imported_202601_batch_001",
      "relation_note": "OA合计不含员工餐补扣款，财务确认闭环",
      "relation_amount_check": {
        "status": "mismatch",
        "direction": "expense",
        "bank_amount": "3617.41",
        "oa_amount": "3425.41",
        "amount_delta": "192.00",
        "requires_note": true
      },
      "tags": ["支", "金额不一致"]
    }
  ]
}
```

前端 display model：

- `WorkbenchCandidateGroup.relationNote`
- `WorkbenchCandidateGroup.amountCheck`
- `WorkbenchRecord.relationNote`
- `WorkbenchRecord.relationAmountCheck`

Tooltip 渲染以银行 row 的 `relationAmountCheck` 和 `relationNote` 为主；如果旧缓存或局部投影缺少 row 字段，前端可以用 group 字段补齐，但实现完成后新 payload 必须同时具备 group 和 bank row 字段。差额说明不得写入 `WorkbenchRecord.note` 或银行 `tableValues["备注"]`。

## 前端交互

### 批量账务未提交页

右侧金额汇总继续显示：

- 银行流水金额。
- 已选 OA 数量。
- 已选 OA 金额。
- 差额。

当已选银行流水、已选 OA 且差额不为 0 时，显示必填输入：

- label：`差额说明`
- helper text：`金额不一致时必须填写，提交后视为人工差额闭环。`

提交按钮规则：

- 金额相等：可提交，不要求说明。
- 金额不等：`差额说明.trim()` 非空才可提交。

状态清理：

- 切换银行流水时清空差额说明。
- 切换 `未提交 / 已提交` 时清空差额说明。
- 切换 OA 勾选时不清空差额说明。

提交 payload 必须带 `note`；后端仍以服务端计算金额为准。

### 批量账务已提交页

已提交页刷新后能从 relation 数据中看到差额状态和差额说明。页面不得依赖提交时的本地状态。

### 关联台已配对区

在已配对区的银行流水金额旁显示警示 icon。

显示条件：

- 当前 row 是银行流水。
- 当前 row 所属 relation 的 `amount_check.status === "mismatch"`。
- relation 有 `note` 或 `amount_check.requires_note === true`。

Tooltip 内容：

```text
金额不一致
银行流水金额：3,617.41
OA合计：3,425.41
差额：192.00
差额说明：OA合计不含员工餐补扣款，财务确认闭环
```

交互要求：

- hover 显示。
- keyboard focus 显示。
- 点击或触摸可打开。
- icon 有 accessible label，例如 `查看金额不一致差额说明`。
- 不新增整行，不改变三栏配对组结构。

## 权限、审计和一致性

- mutation 继续复用 OA session 可写权限。
- 后端不信任前端金额、差额或发票 id。
- 金额不一致提交要能从 pair relation history 中区分出来。
- 撤回必须使用现有 history restore 能力，恢复提交前 OA/附件关系。
- 撤回后已配对区不再显示该差额 icon。
- 持久化失败时不得留下内存已提交但数据库未保存的关系；批量账务提交应尽量对齐普通 `confirm-link` 的回滚策略。

## 验收标准

后端：

- 金额相等时不需要 `note`，现有提交行为不退化。
- 金额不等且 `note` 缺失、空字符串或纯空白时，返回 `400 batch_accounting_note_required`。
- 金额不等且 `note` 非空时提交成功。
- 成功 relation 保存 `note`、`amount_check.status = "mismatch"`、`bank_amount`、`oa_amount`、`amount_delta`、`requires_note = true`。
- history 保存同一份提交说明和金额快照。
- `GET /api/batch-accounting?bucket=submitted` 返回 relation note 和 amount check。
- `GET /api/workbench` 已配对区在 group 和 bank row 上同时投影 `relation_note`、`amount_check` / `relation_amount_check`。
- 金额不一致且有说明的批量账务提交不会创建 `workbench_exception_cases`。
- 金额不一致且有说明的批量账务提交不会创建台账、后续事项、待办或审批流事实。
- 金额不一致且有说明的批量账务关系留在已配对/已完成关系投影中，不进入已处理异常投影。
- 撤回后 active batch relation 消失，撤回 history 的 reason 不覆盖原提交 note。

前端：

- 金额不等且未填说明时不能提交。
- 填写说明后可以提交，request body 包含 `note`。
- 金额相等时不要求说明。
- 批量账务已提交页刷新后能看到 relation 的差额状态和说明。
- 关联台已配对区银行流水金额旁出现警示 icon。
- icon tooltip 支持 hover、focus、点击或触摸。
- tooltip 包含金额不一致、银行金额、OA 合计、差额和差额说明。
- 银行原始备注不被覆盖或拼接。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v
cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx
cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx src/test/WorkbenchApi.test.ts src/test/WorkbenchZone.test.tsx
cd web && npm run build
```
