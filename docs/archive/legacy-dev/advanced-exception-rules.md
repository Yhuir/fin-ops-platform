# 高阶异常处理规则

## 范围

Prompt 06 在现有人工核销工作台上补齐三类高阶异常：

- 差额核销
- 红字发票与反向流水核销
- 内部抵扣单

当前入口：

- `POST /workbench/actions/difference`
- `POST /workbench/actions/offset`
- `GET /workbench/prototype` 中右侧操作区的 `差额核销 / 内部抵扣`

## 差额核销

### 适用场景

- 手续费
- 抹零
- 汇率差
- 税差
- 其他尾差

### 结构化原因

后端使用固定枚举 `DifferenceReason`：

- `fee`
- `rounding`
- `fx`
- `tax`
- `other`

同时保留：

- `difference_amount`
- `difference_reason`
- `difference_note`

### 行为

- 发票和流水都按各自剩余金额全部核销
- 差额不再落普通待处理状态
- 生成 `ReconciliationCase(case_type=difference)`
- 写审计日志 `difference_reconciliation_confirmed`

## 红字发票与反向流水

### 规则

- 正销项票 -> 收款流水
- 红字销项票 -> 退款流水
- 正进项票 -> 付款流水
- 红字进项票 -> 收款退款流水

### 实现口径

- 发票剩余金额允许为负数
- 工作台未配对区保留负数发票
- 分配时按绝对值计算可用金额
- 回写发票 `written_off_amount` 时沿用发票原始符号

这样可避免红字发票在核销后出现：

- `written_off_amount` 方向错误
- `outstanding_amount` 被越冲越大

## 内部抵扣单

### 业务边界

- 必须是同一客商
- 必须同时选中销项票和进项票
- 不伪造银行流水

### 核心对象

新增 `OffsetNote`：

- `id`
- `counterparty_id`
- `receivable_amount`
- `payable_amount`
- `offset_amount`
- `reason`
- `note`
- `created_by`
- `created_at`

### 行为

- 默认按双方最小未核销金额抵扣
- 生成 `ReconciliationCase(case_type=offset, biz_side=cross_offset)`
- `ReconciliationLine` 会写入：
  - 应收发票
  - 应付发票
  - `offset_note`
- 写审计日志 `offset_reconciliation_recorded`

## 兼容性

Prompt 06 不替换 Prompt 04/05 的原流程：

- 标准确认核销仍走 `POST /workbench/actions/confirm`
- 异常处理仍走 `POST /workbench/actions/exception`
- 线下核销仍走 `POST /workbench/actions/offline`

只有当用户明确选择：

- `差额核销`
- `内部抵扣`

时，才进入新的高阶异常流程。

## 验证方式

全量测试：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

前端原型脚本校验：

```bash
awk '/<script>/{flag=1;next}/<\\/script>/{flag=0}flag' web/prototypes/reconciliation-workbench-v2.html > /tmp/reconciliation_workbench_v2.js
node --check /tmp/reconciliation_workbench_v2.js
```
