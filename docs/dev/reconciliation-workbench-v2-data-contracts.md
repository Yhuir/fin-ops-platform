# 关联工作台 V2 数据契约

## 1. 工作台总响应

```json
{
  "month": "2026-03",
  "summary": {
    "oa_count": 286,
    "bank_count": 412,
    "invoice_count": 305,
    "paired_count": 198,
    "open_count": 127,
    "exception_count": 21
  },
  "paired": {
    "oa": [],
    "bank": [],
    "invoice": []
  },
  "open": {
    "oa": [],
    "bank": [],
    "invoice": []
  }
}
```

## 2. OA 行 DTO

日常报销 OA 行按 OA 流程整单建模，而不是按 `schedule` 明细行拆分。整单 row id 使用
`oa-exp-{external_id}`；历史旧 id `oa-exp-{external_id}-{row_index}` 只作为查询兼容入口，
会映射回同一条整单 OA 行。多明细、多附件发票通过 `detail_fields`、`tags` 和派生发票行表达。

```json
{
  "id": "oa-exp-1994",
  "type": "oa",
  "case_id": "MKT-001",
  "applicant": "刘晨",
  "project_name": "品牌广告投放；市场活动项目",
  "project_name_display": "多个项目",
  "project_names": ["品牌广告投放", "市场活动项目"],
  "apply_type": "市场费用",
  "amount": 6000,
  "counterparty_name": "杭州张三广告有限公司",
  "reason": "3月品牌投放尾款",
  "oa_bank_relation": {
    "code": "pending_match",
    "label": "待找流水与发票",
    "tone": "warn"
  },
  "available_actions": ["detail", "confirm_link", "mark_exception"],
  "tags": ["多明细"],
  "detail_fields": {
    "明细数量": "4",
    "明细金额合计": "1549.00",
    "金额来源": "主表总金额",
    "项目名称汇总": "品牌广告投放；市场活动项目",
    "项目名称列表": ["品牌广告投放", "市场活动项目"],
    "费用内容摘要": "ETC通行费；停车费",
    "附件发票摘要": "25532000000191043884（1月ETC.pdf）"
  }
}
```

`project_name` 始终是真实项目名称汇总，用于匹配、搜索和统计，不能写入显示占位值。
`project_names` 是从日常报销 `schedule` 明细解析出的去重真实项目名列表。`project_name_display`
只用于列表展示：真实项目名数量大于 1 时为 `多个项目`，只有一个真实项目时为该项目名，没有真实项目时为 `--`。
`summary_fields["项目名称"]` 使用 `project_name_display`；`detail_fields` 保留
`项目名称汇总` 和结构化 `项目名称列表`，确保详情和搜索仍能命中真实项目名。

OA 附件发票仍展开为独立 invoice rows，row id 为 `oa-att-inv-{oa_row_id}-{index}`，
用于和整单 OA、银行流水共同配对。

## 3. 银行行 DTO

```json
{
  "id": "bk-o-1",
  "type": "bank",
  "case_id": "MKT-001",
  "trade_time": "2026-03-20 09:15",
  "debit_amount": 6000,
  "credit_amount": null,
  "counterparty_name": "杭州张三广告有限公司",
  "payment_account_label": "招行基本户 8821",
  "invoice_relation": {
    "code": "pending_invoice_match",
    "label": "待关联广告票",
    "tone": "warn"
  },
  "pay_receive_time": "2026-03-20 09:15",
  "remark": "应付6000，候选OA-051",
  "repayment_date": null,
  "available_actions": ["detail", "view_relation", "cancel_link", "handle_exception"]
}
```

## 4. 发票行 DTO

```json
{
  "id": "iv-o-1",
  "type": "invoice",
  "case_id": "MKT-001",
  "seller_tax_no": "91330102MA8T32A2X7",
  "seller_name": "杭州张三广告有限公司",
  "buyer_tax_no": "91330106589876543T",
  "buyer_name": "杭州溯源科技有限公司",
  "issue_date": "2026-03-20",
  "amount": 5660.38,
  "tax_rate": "6%",
  "tax_amount": 339.62,
  "total_with_tax": 6000,
  "invoice_type": "进项专票",
  "invoice_bank_relation": {
    "code": "pending_collection",
    "label": "待匹配付款",
    "tone": "warn"
  },
  "available_actions": ["detail", "confirm_link", "mark_exception"]
}
```

## 5. 详情响应 DTO

```json
{
  "id": "bk-o-1",
  "type": "bank",
  "case_id": "MKT-001",
  "summary_fields": {
    "交易时间": "2026-03-20 09:15",
    "借方发生额": "6000.00",
    "对方户名": "杭州张三广告有限公司"
  },
  "detail_fields": {
    "账号": "6214 8350 0000 8821",
    "账户名称": "杭州溯源科技有限公司",
    "余额": "451220.56",
    "币种": "CNY",
    "对方账号": "6222 9033 1200",
    "对方开户机构": "中国银行杭州分行",
    "记账日期": "2026-03-20",
    "摘要": "广告投放尾款",
    "备注": "候选 OA-202603-051",
    "账户明细编号-交易流水号": "B202603200019",
    "企业流水号": "ENT202603200051",
    "凭证种类": "转账支付",
    "凭证号": "VCH-95112"
  }
}
```

## 6. 税金抵扣响应 DTO

```json
{
  "month": "2026-03",
  "output_items": [
    {
      "id": "to-1",
      "buyer_name": "上海辰屹商贸有限公司",
      "issue_date": "2026-03-24",
      "invoice_no": "90342011",
      "tax_amount": 509.43,
      "total_with_tax": 9000,
      "invoice_type": "销项普票"
    }
  ],
  "input_items": [
    {
      "id": "ti-1",
      "seller_name": "杭州张三广告有限公司",
      "issue_date": "2026-03-20",
      "invoice_no": "11203490",
      "tax_amount": 339.62,
      "total_with_tax": 6000,
      "risk_level": "中"
    }
  ],
  "default_selected_output_ids": ["to-1"],
  "default_selected_input_ids": ["ti-1"],
  "summary": {
    "output_tax": "509.43",
    "input_tax": "339.62",
    "deductible_tax": "339.62",
    "result_label": "本月应纳税额",
    "result_amount": "169.81"
  }
}
```

## 7. 动作请求 DTO

### 7.1 确认关联

```json
{
  "month": "2026-03",
  "case_id": "MKT-001",
  "row_ids": ["oa-o-1", "bk-o-1", "iv-o-1"]
}
```

### 7.2 标记异常

```json
{
  "month": "2026-03",
  "row_id": "bk-o-2",
  "exception_code": "bank_fee",
  "comment": "系统自动识别为网银服务费"
}
```

### 7.3 税金抵扣计算

```json
{
  "month": "2026-03",
  "selected_output_ids": ["to-1", "to-2"],
  "selected_input_ids": ["ti-1", "ti-2"]
}
```

## 8. 动作响应 DTO

```json
{
  "success": true,
  "action": "confirm_link",
  "month": "2026-03",
  "affected_row_ids": ["oa-o-1", "bk-o-1", "iv-o-1"],
  "updated_rows": [
    {
      "id": "oa-o-1",
      "type": "oa"
    }
  ],
  "message": "已确认 3 条记录关联。"
}
```

## 9. 契约原则

- 字段名在接口层统一使用英文蛇形
- 状态显示文案由后端产出，前端只做渲染
- `case_id` 是前端做同组联动的唯一依据
- `available_actions` 决定每行显示哪些按钮
- 主表字段与详情字段必须分层返回，避免一个响应既大又难维护
- 所有 V2 动作统一返回 `success / action / month / affected_row_ids / updated_rows / message`

## 10. 自动配对候选 Read Model

自动寻找 OA、银行流水、发票配对项时，后端先写候选 read model，再由关联台消费。前端不直接运行配对规则。

候选结构：

```json
{
  "candidate_id": "candidate:2026-03:oa_bank_multi_invoice_exact_sum:...",
  "candidate_key": "candidate:2026-03:oa_bank_multi_invoice_exact_sum:...",
  "scope_month": "2026-03",
  "candidate_type": "oa_bank_invoice",
  "status": "auto_closed",
  "confidence": "high",
  "rule_code": "oa_bank_multi_invoice_exact_sum",
  "row_ids": ["oa-1", "bk-1", "iv-1", "iv-2"],
  "oa_row_ids": ["oa-1"],
  "bank_row_ids": ["bk-1"],
  "invoice_row_ids": ["iv-1", "iv-2"],
  "amount": "1549.00",
  "amount_delta": "0.00",
  "explanation": "OA、流水、发票金额闭环。",
  "conflict_candidate_keys": [],
  "generated_at": "2026-05-07T10:00:00+00:00",
  "source_versions": {
    "workbench_read_model_schema_version": "2026-05-07-invoice-etc-unified-identity"
  }
}
```

状态契约：

- `auto_closed`：系统安全闭环，进入已配对。
- `incomplete`：缺 OA、流水或发票任一侧，留在未配对。
- `needs_review`：可解释但需要人工确认，留在未配对。
- `conflict`：同一 row 被多个候选占用或存在多个等价组合，留在未配对。

消费顺序：

1. 人工 `workbench_pair_relations` 优先。
2. 再应用自动候选，把同一候选的 `row_ids` 写成同一 `case_id`。
3. 候选组内 row 不再作为 standalone 行重复展示。
4. `auto_closed` 组序列化时保留系统标签，例如“自动匹配”“已匹配：工资”“已匹配：内部往来款”“冲”。

触发链路：

- 发票导入确认：按发票日期提取月份，并扩展上一月、当前月、下一月。
- 银行流水导入确认：按交易日期提取月份，并扩展上一月、当前月、下一月。
- OA hot rebuild / OA reset / `/integrations/oa/sync`：按可用 OA 月份触发。
- 同一月份已有自动配对任务运行时，新任务合并为 dirty scope，不并发删除和写入候选。

可观测性：

- 自动配对结构化日志事件为 `workbench_matching.run.started`、`workbench_matching.run.finished`、`workbench_matching.run.failed`。
- 日志字段至少包含 `request_id`、`scope_months`、`duration_ms`、`candidate_count`、`auto_closed_count`、`conflict_count`。
- `/api/app-health` 的 `workbench_read_model` 节点会返回 `matching_running_scopes`、`matching_dirty_scopes`、`last_matching_error`。
- dirty scope 后台 worker 会定时重试；失败时保留月份、原因、错误和尝试次数。

## 11. 三栏上下文搜索

关联台三栏搜索是前端 display model 行为，不改变后端 `GET /api/workbench` payload、候选 read model 或人工 pair relation。

## 12. 进项发票与 ETC 统一身份

ETC 发票也是进项发票。普通进项发票导入和 ETC zip 导入必须写入同一套 canonical `Invoice` 身份，避免关联台、税金抵扣、成本统计重复计算。

`Invoice` 额外字段：

- `tags`: 来源和业务标签，例如 `["ETC"]`。
- `source_links`: 多来源追踪，`source_type` 可为 `manual_invoice_import`、`etc_invoice_import`、`oa_attachment`。
- `etc_invoice_id`: 对应 ETC service 内部发票 ID。
- `etc_import_batch_id`: 对应 ETC 导入批次 ID。
- `etc_submission_batch_id`: 对应 ETC OA 提交批次 ID。
- `etc_submission_status`: ETC 提交状态。
- `workbench_visibility`: `visible` 或 `hidden_after_etc_submission`。

关联台 invoice row 额外字段：

```json
{
  "source_kind": "etc_invoice",
  "tags": ["ETC", "进"],
  "etc_invoice_id": "etc_invoice_0001",
  "etc_import_batch_id": "etc_import_batch_0001",
  "etc_submission_batch_id": "etc_batch_0001",
  "etc_submission_status": "submitted"
}
```

显示规则：

- ETC 未提交 OA：作为普通发票行进入关联台发票栏，带 `ETC` tag，参与自动配对。
- ETC 已确认提交 OA：canonical invoice 保留，但 `workbench_visibility=hidden_after_etc_submission`，关联台发票栏默认隐藏散票。
- ETC 导入批次只能整批提交 OA；部分提交必须返回业务错误。

导入预览审计：

- 普通进项 / 销项发票导入和 ETC zip 导入必须使用同一套 canonical invoice 身份口径。
- 预览 payload 返回 session/file 级 `audit`，至少包含 `original_count`、`unique_count`、`duplicate_count`、`existing_duplicate_count`、`importable_count`、`update_count`、`merge_count`、`suspected_duplicate_count`、`error_count`。
- ETC zip 命中已存在普通进项发票时归为 `merge_count`，确认后补 `ETC` tag、ETC 来源、批次关系，不新增发票。
- 普通进项发票导入命中已存在 ETC 发票时同样归为 `merge_count`，只合并来源和标签。
- 确认导入前后端必须重算 audit；关键计数变化时返回 `409 preview_stale`，要求用户重新预览。

搜索口径：

- 每个栏的搜索框状态独立保存为 `searchQueryByPane.oa / bank / invoice`。
- 在任意一栏输入关键词时，该栏搜索框显示该关键词，另外两栏搜索框不显示该值。
- 搜索计算使用当前关键词扫描同一 zone 内所有 group 的三栏 rows。
- 来源栏命中的 group 会完整显示，同行 OA / 银行流水 / 发票上下文 rows 保留。
- 另外两栏自身命中同一关键词的 group 也会作为补充行显示，便于人工比对和处理异常。
- 同一 group 被多栏命中时只显示一次，并保持原 group id 和 row id。
- 已配对 zone 和未配对 zone 的搜索状态互不影响。

筛选和排序：

- column filter / time filter 仍按各自 pane 裁剪 rows。
- 搜索上下文只影响 display groups，不生成临时业务 id。
- 详情、确认关联、异常处理等动作继续使用原始 row id 和 group id。
