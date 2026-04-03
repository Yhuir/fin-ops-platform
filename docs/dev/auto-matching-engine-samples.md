# 自动匹配引擎示例

本文档对应 Prompt 03，说明当前自动匹配引擎支持的规则、接口和结果流转。

## 1. 当前实现范围

当前匹配引擎基于 Prompt 02 已确认导入的数据运行，先落成：

- 匹配计算
- 结果持久化到应用内状态
- 结果查询接口

当前接口：

- `POST /matching/run`
- `GET /matching/results`
- `GET /matching/results/{result_id}`

## 2. 已实现规则

### 2.1 标准一对一自动匹配

命中条件：

- 同客商
- 金额一致
- 方向一致
  - 销项发票对应收款流水
  - 进项发票对应付款流水

输出：

- `automatic_match`
- `high` 置信度
- 规则码：`exact_counterparty_amount_one_to_one`

### 2.2 多票一付 / 一票多付建议

命中条件：

- 同客商
- 同方向
- 多个对象金额求和后等于另一侧金额

输出：

- `suggested_match`
- `medium` 置信度
- 规则码：
  - `same_counterparty_many_invoices_one_transaction`
  - `same_counterparty_one_invoice_many_transactions`

### 2.3 部分核销 / 溢收 / 缺票建议

命中条件：

- 同客商
- 同方向
- 只有一个主要候选，但金额不一致

输出：

- `suggested_match`
- `low` 置信度
- 规则码：`same_counterparty_partial_amount_match`
- 返回 `difference_amount`

### 2.4 待人工处理

命中条件：

- 无法形成高置信度或中置信度建议

输出：

- `manual_review`
- `low` 置信度
- 规则码：`no_confident_match`

## 3. 结果如何流转到工作台

Prompt 04 的人工核销工作台可直接消费：

- `result_type`
- `confidence`
- `rule_code`
- `explanation`
- `invoice_ids`
- `transaction_ids`
- `difference_amount`

建议用法：

- `automatic_match`：默认展示在已自动匹配区
- `suggested_match`：展示在候选建议区，等财务确认
- `manual_review`：直接进入人工处理池

## 4. 运行示例

先准备并确认导入数据，再运行匹配：

```json
{
  "triggered_by": "user_finance_01"
}
```

调用：

```text
POST /matching/run
```

返回内容包含：

- `run`
- `results`

其中 `run` 会给出：

- `result_count`
- `automatic_count`
- `suggested_count`
- `manual_review_count`

## 5. 查询示例

### 查询所有匹配结果

```text
GET /matching/results
```

### 查询单条匹配结果

```text
GET /matching/results/match_result_00001
```

## 6. 验证方式

运行：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_matching_service tests.test_matching_api -v
```

全量回归：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```
