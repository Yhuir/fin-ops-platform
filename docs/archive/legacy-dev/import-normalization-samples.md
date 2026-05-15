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

文件导入页使用 `POST /imports/files/preview` 时，还会返回 session 级和文件级 `audit`，用于在用户确认前做导入审计：

```json
{
  "session": {
    "id": "import_session_0001",
    "status": "preview_ready",
    "audit": {
      "original_count": 598,
      "unique_count": 440,
      "duplicate_count": 158,
      "duplicate_in_file_count": 77,
      "duplicate_across_files_count": 81,
      "existing_duplicate_count": 0,
      "importable_count": 440,
      "update_count": 0,
      "merge_count": 0,
      "suspected_duplicate_count": 0,
      "error_count": 0,
      "confirmable_count": 440,
      "skipped_count": 158
    }
  },
  "files": [
    {
      "id": "file_import_0001",
      "file_name": "进项发票查询导出结果-2026年1月.xlsx",
      "row_count": 134,
      "success_count": 120,
      "duplicate_count": 14,
      "audit": {
        "original_count": 134,
        "unique_count": 120,
        "duplicate_count": 14,
        "duplicate_in_file_count": 14,
        "duplicate_across_files_count": 0,
        "existing_duplicate_count": 0,
        "importable_count": 120,
        "error_count": 0
      }
    }
  ],
  "duplicate_groups": [
    {
      "identity_key": "digital:26537000000232963884",
      "record_type": "invoice",
      "duplicate_type": "duplicate_across_files",
      "rows": [
        {"file_id": "file_import_0002", "file_name": "2026年2月.xlsx", "row_no": 12},
        {"file_id": "file_import_0003", "file_name": "2026年3月.xlsx", "row_no": 12}
      ]
    }
  ]
}
```

口径说明：

- `row_count` 和 `success_count` 保留旧接口语义，便于兼容已有页面。
- `original_count` 是原始识别行数。
- `unique_count` 是本次预览 session 内按业务身份去重后的唯一记录数。
- `duplicate_count` 是本次上传集合内重复行数，等于文件内重复和跨文件重复之和。
- `existing_duplicate_count` 是和 app 当前已有记录重复的数量。
- `importable_count` 是现在确认导入会新增的记录数。
- `update_count` 是现在确认导入会更新已有记录的数量。
- `merge_count` 是现在确认导入会合并来源、标签、附件或 ETC 元数据但不新增记录的数量。

因此，“新增”是旧列表字段，主要来自单文件 preview 的 `success_count`；“可导入”是审计字段 `importable_count`，是用户确认导入前应优先看的生产口径。

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

对于文件导入 session，确认前后端会基于当前 app 数据重算 audit。如果关键计数和预览时不一致，接口返回 HTTP 409：

```json
{
  "error": "preview_stale",
  "message": "Preview changed after it was generated. Please refresh preview before confirming."
}
```

前端应提示“预览后数据已变化，请重新预览后再确认。”，用户刷新预览后再确认，避免预览显示可导入数量和最终落库数量不一致。

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
