# Phase 01 Bug Log

## BUG-001 确认闭环时报“银行流水状态已变化”

### 状态

- Status: `analyzed`
- Implementation: `not-started`
- Priority: P1
- Reported from: 用户截图，2026-06-16

### 复现步骤

1. 打开 `外部往来款管理`。
2. 展开同一对方/同一往来类型的流水组。
3. 选择一条收入和一条支出，金额相等，差额为 `0.00`。
4. 点击 `确认闭环`。
5. 在确认抽屉中点击 `确定`。

### 实际结果

弹窗：

```text
操作失败
银行流水状态已变化，请刷新后重试。
```

### 期望结果

如果所选 flow rows 在提交前重新加载后仍然：

- 同组。
- 至少一收一支。
- 差额 `0.00`。
- 未被其他 active Turnover relation 或 Workbench relation 占用。
- `categoryVersion` 与当前银行流水版本一致。

则应成功写入：

- Turnover manual relation。
- Workbench bank-only `turnover_manual_closure` active relation。
- dirty/outbox refresh。
- operation freshness targets。

### 当前证据

错误文案来源：

- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `TurnoverLedgerBankRowStalePreconditionPort.assert_current(...)`

前端提交版本来源：

- `web/src/pages/TurnoverLedgerPage.tsx`
- `closureExpectedVersions(rows)` 使用 fresh flow row 的 `categoryVersion` 生成 `turnover_bank_row:{id}`。
- `handleConfirmClosure` 在 POST 前已经等待 `turnover_ledger:all` fresh，并重新加载 grouped ledger / rebind flow rows。

后端当前版本来源：

- `TurnoverLedgerBankRowStalePreconditionPort._bank_row_version(row)`
- 比较顺序：`category_version` -> `manual_category_version` -> `version`。

高置信假设：

- SQL bank detail row 有 `manual_category_version` 但没有 `category_version`。
- `_turnover_bank_transaction_row_from_bank_detail(...)` 没有把 `manual_category_version` 归一成 `category_version`。
- grouped payload 暴露 `category_version=0`，前端提交 `0`。
- 后端 stale precondition fallback 读到 `manual_category_version=真实版本`。
- 两者不一致，导致误判 stale。

### 实现前必须加的失败测试

后端最小测试：

```text
Application._turnover_bank_transaction_row_from_bank_detail(row)
  row.category_version missing
  row.manual_category_version = 9
  expect result.category_version == 9
```

建议测试文件：

- `tests/test_turnover_ledger_api.py`

补充测试：

- `category_version` 存在时优先使用。
- `manual_category_version` 缺失但 `version` 存在时 fallback。
- 前端 closure confirm request 继续提交 fresh reload 后的 latest `expected_versions`。

### 预计修复方向

在 SQL bank detail -> turnover bank row 转换边界归一化版本字段，而不是移除 stale precondition。

候选位置：

- `backend/src/fin_ops_platform/app/server.py`
- `Application._turnover_bank_transaction_row_from_bank_detail(...)`

原则：

- 保留后端 stale precondition。
- 保留前端提交前 fresh/rebind 逻辑。
- 不让 UI 忽略 expected_versions。
- 不绕过 Workbench relation command service。

### 回归风险

- 如果直接移除 expected_versions，会丢失并发保护。
- 如果只改前端用 `manualCategoryVersion`，可能扩大 API contract 且绕过已有 grouped payload 口径。
- 如果只捕获错误后自动重试，可能掩盖真实并发修改。
- 如果改错 source version，可能让 stale `turnover_ledger` payload 被当 fresh。
