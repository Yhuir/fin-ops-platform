# OA Expense Claim Aggregation Design

## Goal

关联台中的 OA 行必须代表 OA 流程整单，而不是 OA `schedule` 明细行。日常报销中一条 OA 流程可能包含多条付款/报销明细、多个附件和多张发票；关联台应显示为一条 OA，对应多张发票和一条或多条银行流水。

## Current Problem

`MongoOAAdapter._build_expense_claim_records()` 当前遍历日常报销 `schedule`，每条明细生成一条 `OAApplicationRecord`，row id 形如 `oa-exp-1994-0`、`oa-exp-1994-1`。这会把同一个 OA 流程拆成多条 OA 行，导致关联台误以为每条 OA 行只对应一张发票。

## Target Behavior

- 日常报销 OA 每个 OA document 只生成一条 `OAApplicationRecord`。
- 新 row id：`oa-exp-{external_id}`。
- OA 金额口径：
  - 优先使用 OA 主表总金额，例如 `amount=1549.00`。
  - 主表金额缺失或非法时，使用 schedule 明细金额合计。
  - 如果主表金额和明细合计不一致，保留结构化差异信息和详情字段，不静默覆盖。
- schedule 明细只作为整单 OA 的详情来源：
  - 明细数量
  - 明细金额合计
  - 项目集合
  - 费用类型集合
  - 费用内容摘要
  - 报销日期范围
  - 附件文件集合
  - 附件发票集合
- 附件发票继续展开为独立 invoice rows：
  - `oa_rows: [一条 OA]`
  - `invoice_rows: [多张附件发票]`
  - `bank_rows: [一条或多条流水]`

## Reset Scope

“清除所有 OA 数据并重新写入”应只清理 OA 相关工作台状态，并保留纯银行流水-人工导入发票的非 OA 配对关系。必须清理：

- OA row overrides
- 包含 OA row 的 pair relations
- 包含 OA 附件发票派生 row 的 pair relations
- workbench read models

不得清理：

- OA 源库 `form_data_db.form_data`
- app settings
- 纯银行流水-人工发票 pair relations
- 人工导入的银行流水和发票

## Compatibility

- `list_application_records_by_row_ids()` 必须支持新 id `oa-exp-{external_id}`。
- 短期兼容旧 id `oa-exp-{external_id}-{row_index}`，映射到新整单 OA row，避免旧缓存、旧链接或旧操作参数直接 404。
- Workbench read model schema version 必须升级，强制旧缓存失效。
- 搜索和详情应能看到明细摘要、附件发票摘要、金额来源和金额差异。

## Acceptance Criteria

- OA 1994 类场景只显示一条 OA，金额 `1549.00`。
- 这条 OA 可以和多张发票同行显示。
- 设置页重置 OA 后，关联台不会重新生成拆分 OA。
- 纯银行流水-人工发票配对不会因为 OA 重置丢失。
- 后端和前端测试覆盖聚合、旧 id 兼容、附件发票展开、reset 范围和详情展示。

