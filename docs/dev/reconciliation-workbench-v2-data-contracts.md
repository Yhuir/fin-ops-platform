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
只有 `source_kind=oa_attachment_invoice` 可进入发票栏；`oa_attachment_payment_receipt`、
`oa_attachment_unknown` 和解析失败附件不得作为 `invoice_rows` 输出，只能保留为 OA 附件审计证据。

### 2.1 Group summary 与完整组

`GET /api/workbench/groups?detail_level=summary` 可以只返回每个 group 每栏的预览行，
但 `source_kind=oa_attachment_invoice` 的 OA 附件发票不得被预览行上限裁剪。OA 附件发票有多少张，
summary 就必须返回多少张，前端直接显示，不做展开/收起。

summary 响应必须带未裁剪的 `row_counts`。如果非 OA 附件栏位的 `row_counts` 大于已返回 rows 长度，
前端必须显示当前行数和总行数，并调用
`GET /api/workbench/groups/detail?zone=...&group_id=...` 获取完整 group 后再展开展示。
前端不能把 summary 预览当作完整附件清单。

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
  "remark": "应付6000，对应OA-051",
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
  "invoice_code": "0330111200",
  "invoice_no": "90342011",
  "digital_invoice_no": "25502000000190342011",
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

发票列表展示、搜索和汇总分页必须使用 row 顶层的 `invoice_no`、`invoice_code`
和 `digital_invoice_no`。`detail_fields` 只用于详情抽屉和审计追溯，汇总列表会裁掉
`detail_fields` 以控制 payload 大小；因此 OA 附件解析出的发票行也必须在读模型中
补齐这些顶层身份字段，不能依赖前端从 `detail_fields` 兜底解析。
发票金额列统一展示 `amount`、`tax_rate` 和 `tax_amount` 三个顶层字段；人工导入发票、
系统发票和 OA 附件解析发票必须输出同一组字段，不能只让某一类来源显示税率/税额。

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
    "备注": "对应 OA-202603-051",
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
  "row_ids": ["oa-exp-1994", "bk-o-1", "iv-o-1"]
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
  "affected_row_ids": ["oa-exp-1994", "bk-o-1", "iv-o-1"],
  "updated_rows": [
    {
      "id": "oa-exp-1994",
      "type": "oa"
    }
  ],
  "message": "已确认 3 条记录关联。"
}
```

## 9. 契约原则

- 字段名在接口层统一使用英文蛇形
- 状态显示文案由后端产出，前端只做渲染
- 工作台展示区只使用 `paired` 和 `open`
- `case_id` 是前端做同组联动的唯一依据
- `available_actions` 决定每行显示哪些按钮
- 主表字段与详情字段必须分层返回，避免一个响应既大又难维护
- 所有 V2 动作统一返回 `success / action / month / affected_row_ids / updated_rows / message`

## 10. 自动决策 Read Model

自动寻找 OA、银行流水、发票配对项时，后端统一写自动决策 read model，再由关联台消费。前端不直接运行配对规则，不根据生命周期状态自行推断配对。该章节描述关联台自动决策重构完成后的目标契约；迁移期旧 `workbench_candidate_matches` 只能作为替换前的现行实现或 shadow 对账来源，不能继续扩展为新的展示事实源。

手工确认关系仍以 `app.workbench_pair_relations` 为事实源；自动决策不复制成手工关系。

自动决策结构：

```json
{
  "decision_id": "decision:2026-03:oa_attachment_invoice_with_bank:...",
  "decision_key": "decision:2026-03:oa_attachment_invoice_with_bank:...",
  "scope_month": "2026-03",
  "display_state": "paired",
  "decision_status": "paired",
  "match_domain": "free",
  "match_shape": "oa_bank_invoice",
  "rule_code": "oa_attachment_invoice_with_bank",
  "rule_version": "2026-05-25",
  "row_ids": ["oa-exp-1994", "bk-o-1", "oa-att-inv-oa-exp-1994-1", "oa-att-inv-oa-exp-1994-2"],
  "oa_row_ids": ["oa-exp-1994"],
  "bank_row_ids": ["bk-o-1"],
  "invoice_row_ids": ["oa-att-inv-oa-exp-1994-1", "oa-att-inv-oa-exp-1994-2"],
  "amount": "6000.00",
  "direction": "expenditure",
  "payment_amount_closed": true,
  "invoice_amount_closed": false,
  "warnings": [
    {
      "code": "invoice_amount_mismatch",
      "message": "OA 与流水金额一致，但 OA 来源附件发票合计金额不一致。"
    }
  ],
  "evidence": {
    "scope_window": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
    "text_tokens": ["杭州张三广告"],
    "uniqueness_scope": "five_month_window"
  },
  "blockers": [],
  "explanation": "OA、流水金额闭合，OA 来源附件发票合计不一致。",
  "generated_at": "2026-05-07T10:00:00+00:00",
  "source_versions": {
    "workbench_read_model_schema_version": "2026-05-07-invoice-etc-unified-identity"
  }
}
```

状态契约：

- `display_state` 是读模型和前端展示状态，只允许 `paired` 和 `open`。
- `decision_status` 是自动决策生命周期状态，只允许 `proposed`、`paired`、`open`、`suppressed`、`consumed`、`expired`。
- `decision_status=paired` 且 `display_state=paired` 时进入已配对区并同组展示。
- `decision_status=open` 且 `display_state=open` 时进入未配对区并独立展示。
- `proposed`、`suppressed`、`consumed`、`expired` 不投影为业务 group，只保留给调试、审计或后续重算。
- Legacy/internal compatibility only: `needs_review` 和 `candidate` 可作为旧表、迁移脚本或调试字段出现，但不得作为当前前端展示状态、zone、筛选值或分组依据。

自动自由匹配契约：

- 首版只覆盖支出方向：普通支出 OA、银行流出、进项或供应商发票。
- 收入方向没有 OA 桥接对象，不进入 OA、流水、发票自由匹配。
- 匹配窗口为 `T-2 / T / T+2`。处理 T 月 dirty scope 时，可读取前后各 2 个月的候选池。
- 唯一性判断必须覆盖完整 5 个月候选窗口；同金额、同证据等级下存在多个可行组合时，全部保持 `open`。
- 跨月自动决策只写一个 `scope_month`：包含银行流水时归属银行交易月份；没有银行流水的 OA+发票关系归属 OA 月份。
- OA 来源附件发票与 OA 强关联。若 OA 金额等于银行流水金额但正式附件发票合计不一致，仍可 `display_state=paired`，同时输出 `invoice_amount_mismatch` warning、`payment_amount_closed=true`、`invoice_amount_closed=false`。

消费顺序：

1. 人工 `app.workbench_pair_relations` 优先形成 `manual_confirmed` group。
2. 再应用自动决策，把同一 `decision_key` 的 `row_ids` 写成同一 `case_id`。
3. 自动 `paired` group 内 row 不再作为 standalone 行重复展示。
4. 自动 `open` 决策只解释未配对原因，不把多个未唯一确定的对象合并成一行。
5. 已被手工关系覆盖的自动决策更新为 `decision_status=consumed`，不得继续投影。

触发链路：

- 发票导入确认：按发票日期提取月份，并扩展到 `T-2 / T / T+2`。
- 银行流水导入确认：按交易日期提取月份，并扩展到 `T-2 / T / T+2`。
- OA hot rebuild / OA reset / `/integrations/oa/sync`：按每个受影响 OA 月份 T 触发，并分别扩展到 `T-2 / T / T+2`。
- 手工确认、撤回关联、异常单创建或关闭、特殊规则配置变化、自由匹配规则版本升级：在同一数据库事务中写入 dirty scope。
- 生产执行机制是 DB-backed dirty scope queue，推荐表为 `job.workbench_matching_dirty_scopes`。
- 同一月份已有自动配对任务运行时，新任务合并为 dirty scope，不并发删除和写入自动决策。
- 进程内 dirty service 只可作为迁移期或单实例 fallback，不能作为生产正确性的依赖。

可观测性：

- 自动配对结构化日志事件为 `workbench_matching.run.started`、`workbench_matching.run.finished`、`workbench_matching.run.failed`。
- 日志字段至少包含 `request_id`、`scope_months`、`duration_ms`、`decision_count`、`paired_decision_count`、`open_decision_count`、`warning_count`。
- `/api/app-health` 的 `workbench_read_model` 节点会返回 `matching_running_scopes`、`matching_dirty_scopes`、`last_matching_error`。
- dirty scope 后台 worker 会定时重试；失败时保留月份、原因、错误和尝试次数。

## 11. 三栏上下文搜索

关联台三栏搜索是前端 display model 行为，不改变后端 `GET /api/workbench` payload、自动决策 read model 或人工 `app.workbench_pair_relations`。

选择状态同样不能依赖 display model。前端只把三栏搜索、列筛选、时间筛选视为可见投影；确认关联、撤回关联、异常处理和选择汇总必须回到未过滤的 zone groups 解析 row id 与关系上下文。

确认关联契约：

- `row_ids` 可以只包含用户显式选中的行，但后端必须在 preview 和 submit 中扩展 active relation 与 read model 中需要保留的上下文行。
- 若显式选择里存在 OA 和银行流水，且该 OA 在 active relation 或缓存 read model 中有正式 OA 附件发票上下文，后端必须只把 `source_kind = "oa_attachment_invoice"` 的 invoice rows 一起纳入 `affected_row_ids` 和最终 pair relation。付款凭证、未知附件、解析失败附件只能作为 OA 附件审计证据，不进入发票栏，也不进入 pair relation。
- preview 与 submit 必须共用同一扩展函数，保证金额校验、备注要求、审计历史和撤回恢复看到同一批 row id。

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
