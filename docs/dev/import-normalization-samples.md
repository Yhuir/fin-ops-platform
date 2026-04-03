# 导入与标准化示例

本文档对应 Prompt 02，说明当前实现的导入方式和样例请求。

## 1. 当前实现范围

当前实现先提供后端接口，不直接做正式导入页：

- `POST /imports/preview`
- `POST /imports/confirm`
- `GET /imports/batches/{batch_id}`

当前输入格式是结构化 JSON 行数据，适合作为现有 UI 的对接层，也适合作为未来 `.xlsx` 解析后的标准中间格式。

## 2. 销项 / 进项发票预览样例

```json
{
  "batch_type": "output_invoice",
  "source_name": "output-demo.json",
  "imported_by": "user_finance_01",
  "rows": [
    {
      "invoice_code": "033001",
      "invoice_no": "9002",
      "counterparty_name": "New Corp Ltd.",
      "amount": "120.00",
      "invoice_date": "2026/03/24",
      "invoice_status_from_source": "valid"
    }
  ]
}
```

规则：

- 数电票优先用 `digital_invoice_no`
- 普票 / 纸票优先用 `invoice_code + invoice_no`
- 无官方唯一号时走数据指纹

## 3. 银行流水预览样例

```json
{
  "batch_type": "bank_transaction",
  "source_name": "bank-demo.json",
  "imported_by": "user_finance_01",
  "rows": [
    {
      "account_no": "62229999",
      "txn_date": "2026-03-24",
      "counterparty_name": "Vendor A",
      "debit_amount": "50.00",
      "credit_amount": "",
      "bank_serial_no": "SERIAL-NEW-001",
      "summary": "purchase"
    }
  ]
}
```

规则：

- `bank_serial_no / voucher_no / enterprise_serial_no` 优先作为唯一业务主键
- 缺失官方唯一号时，用账号、对方名称、日期、方向、金额生成指纹
- 借方金额转为 `outflow`
- 贷方金额转为 `inflow`

## 4. 预览响应重点

预览阶段返回三类信息：

- `batch`
- `row_results`
- `normalized_rows`

其中 `row_results.decision` 会区分：

- `created`
- `status_updated`
- `duplicate_skipped`
- `suspected_duplicate`
- `error`

## 5. 确认导入

预览成功后，用返回的 `batch.id` 调用确认导入：

```json
{
  "batch_id": "batch_import_0001"
}
```

确认导入只会真正写入：

- `created`
- `status_updated`

不会自动写入：

- `duplicate_skipped`
- `suspected_duplicate`
- `error`

## 6. 验证方式

本地运行：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_import_service tests.test_import_api -v
```

如果要手工跑服务：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --host 127.0.0.1 --port 8000
```

然后可调用：

- `POST /imports/preview`
- `POST /imports/confirm`
- `GET /imports/batches/{batch_id}`
