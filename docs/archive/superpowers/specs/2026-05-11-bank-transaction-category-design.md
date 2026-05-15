# 银行流水人工分类与关联台标签优先配对设计

## 目标

在银行明细页面支持用户给每一项银行流水添加、修改、取消业务分类标签，并让该分类实时进入关联台展示、候选生成和特殊配对规则。该功能必须作为银行流水源数据的人工业务元数据实现，而不是前端状态或关联台临时覆盖。

## 标签范围

2026-05-11 更新：银行明细人工分类从四个平铺标签升级为分层 taxonomy。旧 code（`external_turnover`、`internal_transfer`、`offset`、`cash_turnover`）只作为历史数据兼容读取，不再作为银行明细页面的新可选项。

本期银行明细页面只允许选择以下叶子标签：

| 一级 | 二级 | 状态 | code | 最终显示 |
| --- | --- | --- | --- | --- |
| 借入 | 个人往来款 | 待还款 | `borrow_in_personal_pending_repayment` | 个人暂借款：待还款 |
| 借入 | 个人往来款 | 已还款 | `borrow_in_personal_repaid` | 个人暂借款：已还款 |
| 借入 | 公司往来款 | 待还款 | `borrow_in_company_pending_repayment` | 公司暂借款：待还款 |
| 借入 | 公司往来款 | 已还款 | `borrow_in_company_repaid` | 公司暂借款：已还款 |
| 借入 | 银行往来款 | 待还款 | `borrow_in_bank_pending_repayment` | 银行往来款：待还款 |
| 借入 | 银行往来款 | 已还款 | `borrow_in_bank_repaid` | 银行往来款：已还款 |
| 借出 | 个人往来款 | 已借款 | `borrow_out_personal_lent` | 个人往来款：已借款 |
| 借出 | 个人往来款 | 待收款 | `borrow_out_personal_pending_collection` | 个人往来款：待收款 |
| 借出 | 公司往来款 | 已借款 | `borrow_out_company_lent` | 公司往来款：已借款 |
| 借出 | 公司往来款 | 待收款 | `borrow_out_company_pending_collection` | 公司往来款：待收款 |
| 借出 | 货款往来款 | 已借款 | `borrow_out_goods_lent` | 货款往来款：已借款 |
| 借出 | 货款往来款 | 待收款 | `borrow_out_goods_pending_collection` | 货款往来款：待收款 |
| 业务往来 | 质保金 | 待收款 | `business_warranty_pending_collection` | 质保金：待收款 |
| 业务往来 | 投标保证金 | 待收款 | `business_bid_bond_pending_collection` | 投标保证金：待收款 |
| 业务往来 | 履约保证金 | 待收款 | `business_performance_bond_pending_collection` | 履约保证金：待收款 |
| 业务往来 | 已开发票未收款 | 待收款 | `business_invoiced_pending_collection` | 已开发票未收款：待收款 |

标签是人工 evidence，不是自动闭环结论。匹配时可以优先使用标签缩小候选范围和提升证据权重，但仍必须校验金额、方向、主体、日期、账户、唯一性和业务规则。

## 非目标

- 不把标签写进导入文件解析结果本体，不改变导入数据指纹和去重逻辑。
- 不用 UI 或 grouping 临时强行合并关联台行。
- 不新增任意自定义标签。
- 不把银行流水标记 `offset` 等同于自动完成“周洁莹冲”。它只是进入现有冲规则体系的人工线索。

## 后端模型

新增 `BankTransactionCategoryService`，负责银行流水分类元数据：

- 校验 `transaction_id` 是否存在。
- 标准化 category code 和 label。
- 批量保存、修改、清除标签。
- 返回当前版本、更新时间和操作人。
- 为银行明细、关联台、匹配规则批量补齐分类。
- 记录审计字段，支持并发冲突检测。

建议持久化结构：

```json
{
  "transaction_id": "txn_imported_1278",
  "category_code": "borrow_in_company_pending_repayment",
  "category_label": "公司暂借款：待还款",
  "category_path": ["借入", "公司往来款", "待还款"],
  "source": "manual",
  "updated_by": "YNSYLP005",
  "updated_at": "2026-05-11T08:00:00Z",
  "version": 1
}
```

清除标签时不写空字符串，应删除或置空该交易的 category record，并返回最新状态。

## API

### 查询银行明细

`GET /api/bank-details/transactions` 返回值新增：

```json
{
  "rows": [
    {
      "id": "txn_imported_1278",
      "category_code": "borrow_in_company_pending_repayment",
      "category_label": "公司暂借款：待还款",
      "category_path": ["借入", "公司往来款", "待还款"],
      "category_version": 2
    }
  ],
  "category_counts": {
    "borrow_in_company_pending_repayment": 12,
    "business_warranty_pending_collection": 3,
    "uncategorized": 271
  },
  "pagination": {
    "page": 1,
    "page_size": 100,
    "total": 299
  }
}
```

`category_counts` 统计口径是当前 `account_key + date_from + date_to` 下的全部流水，不是当前页。

### 保存标签

新增：

`PATCH /api/bank-details/transactions/categories`

请求：

```json
{
  "updates": [
    {
      "transaction_id": "txn_imported_1278",
      "category_code": "borrow_in_company_pending_repayment",
      "expected_version": 1
    },
    {
      "transaction_id": "txn_imported_1348",
      "category_code": null,
      "expected_version": 3
    }
  ]
}
```

返回：

```json
{
  "updated_transaction_ids": ["txn_imported_1278", "txn_imported_1348"],
  "updated_categories": [
    {
      "transaction_id": "txn_imported_1278",
      "category_code": "borrow_in_company_pending_repayment",
      "category_label": "公司暂借款：待还款",
      "category_path": ["借入", "公司往来款", "待还款"],
      "version": 2
    }
  ],
  "affected_months": ["2026-02", "2026-03"],
  "workbench_rebuild_queued": true
}
```

保存失败必须返回明确错误：

- `unknown_transaction_id`
- `invalid_category_code`
- `category_version_conflict`
- `permission_denied`

后端必须对批量更新做原子处理。若无法原子保存，则返回逐条结果，前端保留失败项 dirty。本期优先实现原子保存。

## 权限与审计

- 只读/只导出用户不能修改标签；后端必须拒绝。
- 全权限用户可以修改。
- 添加、修改、清除都要记录审计字段：交易 id、旧标签、新标签、操作人、操作时间。
- 前端禁用不是权限边界，后端校验是最终边界。

## 缓存与实时更新

保存标签后必须：

1. 持久化 category。
2. 计算受影响月份。
3. 删除这些月份及 `all` 相关的 workbench read model。
4. 标记或重建 workbench candidate matches。
5. 清理 search cache。
6. 返回 `affected_months`。

前端银行明细保存成功后发布全局事件：

```ts
window.dispatchEvent(new CustomEvent("bankTransactionCategoryUpdated", {
  detail: { affectedMonths: ["2026-02", "2026-03"] }
}));
```

关联台页面监听该事件。当前月份为 `all` 或命中 `affectedMonths` 时刷新 `/api/workbench`。

## 银行明细 UI

银行明细页面继续使用 MUI 原生组件：

- DataGrid 新增“类别”列。
- 单元格用 MUI `TextField select` 或 `Select + MenuItem`。
- 已选标签用 MUI `Chip` 展示。
- 表头 toolbar 显示各标签数量和未保存数量。
- `保存` Button 无 dirty 时 disabled；保存中 loading。
- `撤销更改` Button 有 dirty 时可用。
- 保存成功用 `Snackbar + Alert`。

交互状态：

- `savedCategoryByRowId`：当前已保存值。
- `draftCategoryByRowId`：跨页保留的未保存变动。
- 显示值：`draftCategoryByRowId[row.id] ?? savedCategoryByRowId[row.id]`。

切换行为：

- 同一账户、同一日期范围内翻页不提示，dirty 继续保留。
- 切换账户、切换日期、离开页面、刷新页面前，如有 dirty，必须提示：保存并继续、放弃变动、取消。
- 保存提交所有 dirty row，不只提交当前页。

## 关联台 bank row 契约

`LiveWorkbenchService` 生成银行 row 时新增：

```json
{
  "category_code": "borrow_in_company_pending_repayment",
  "category_label": "公司暂借款：待还款",
  "category_path": ["借入", "公司往来款", "待还款"],
  "tags": ["公司暂借款：待还款"],
  "bank_text_fields": [
    { "label": "摘要", "value": "电子转账" },
    { "label": "备注", "value": "代购公车款" },
    { "label": "用途", "value": "货款" }
  ]
}
```

`tags` 只加入合法分类标签，不覆盖系统已有标签。

## 摘要/用途/备注字段

导入阶段需要保留银行文件中的原始文本字段，至少包括：

- 摘要
- 备注
- 用途
- 交易用途
- 客户附言
- 附言

后端统一输出为 `bank_text_fields`，前端关联台银行“备注”列渲染为多行紧凑文本，只显示有值字段。缺失字段不显示，不用 `--` 占位。

历史已导入数据只能从现有 `summary`、`remark` 尽量补齐；未来导入应完整保留原始列名。

## 匹配规则

`WorkbenchSpecialRuleDetector` 需要读取 `category_code` 和 `category_path`：

- 新 taxonomy 叶子标签统一作为人工往来 evidence 进入复核候选，不伪造自动闭环。
- `borrow_in_*`、`borrow_out_*`、`business_*` 的金额、方向、主体、日期仍必须在后续闭环规则中校验。
- 旧 `internal_transfer`、`offset`、`cash_turnover` 只兼容历史数据；内部往来、周洁莹冲、现金往来的既有自动/复核规则仍保持原语义。

如果标签与文本自动识别冲突，候选 evidence 必须保留冲突说明，不静默覆盖。

## 测试与验收

后端：

- `BankTransactionCategoryService` 增删改、非法 code、未知交易、版本冲突。
- `BankDetailsService` 返回 row 分类和全范围 counts。
- API 权限、保存、affected months、缓存失效。
- `LiveWorkbenchService` bank row 带分类 tag 和 `bank_text_fields`。
- `WorkbenchSpecialPairRuleService` 标签优先但不绕过闭环校验。
- `offset` 与现有周洁莹 `oa_invoice_offset_auto_match` 不冲突。

前端：

- 银行明细类别列、MUI select、保存 disabled/loading。
- 标签数量表头、dirty 数即时更新。
- 跨页保留 dirty；翻页不提示。
- 切换账户/日期前提示保存或放弃。
- 保存成功触发 `bankTransactionCategoryUpdated`。
- 关联台接收刷新事件并重新请求数据。
- 关联台备注列显示动态 `摘要/用途/备注` 字段。

回归：

```bash
PYTHONPATH=backend/src:. pytest tests/test_bank_details_service.py tests/test_workbench_special_pair_rule_service.py tests/test_live_workbench_service.py tests/test_workbench_v2_api.py -q
npm --prefix web test -- --run BankDetailsPage WorkbenchApi CandidateGroupGrid
git diff --check
```
