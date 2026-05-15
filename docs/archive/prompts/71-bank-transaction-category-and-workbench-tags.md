# Codex 多任务子代理执行 Prompt：银行流水人工分类与关联台标签优先配对

## 背景

仓库：`/Users/yu/Desktop/fin-ops-platform`

用户要求新增银行流水分类标签功能：

1. 银行明细页面每条流水可选择标签：外部往来款、内部往来款、冲、现金往来。
2. 有变动才允许保存；无变动保存按钮不可交互。
3. 添加、更新、取消标签后，关联台必须实时更新。
4. 关联台做外部往来款、内部往来款、冲、现金往来配对时，优先使用标签。
5. 关联台银行流水备注列增加 `摘要`、`用途` 等来自导入文件的文本字段，缺失不显示。
6. 银行明细页面右栏表头需要显示各标签数量。
7. 切换账户/切换日期前，如有未保存变动，提示保存或放弃；同一账户下翻页不提示，跨页保留选择，最后统一保存。
8. `冲` 必须沿用现有“周洁莹冲”语义，即 `oa_invoice_offset_auto_match` / `OA_INVOICE_OFFSET_TAG = "冲"`。
9. 禁止救急/临时方案；必须生产级整合进现有服务。

完整设计文档：`docs/superpowers/specs/2026-05-11-bank-transaction-category-design.md`

## 总体架构

实现为“银行流水人工分类元数据”：

`银行明细保存标签 -> 后端持久化 -> BankDetailsService/LiveWorkbenchService 补齐 category -> WorkbenchSpecialPairRuleService 优先读取标签 -> candidate/read model 失效重建 -> 关联台刷新`

不要把标签只放前端，不要写入导入数据指纹，不要用关联台 grouping 临时合并。

## 任务拆分

### 71A 总控与文档

负责人：主线程。

职责：

- 固化设计文档。
- 创建本 prompt。
- 派发 71B、71C、71D、71E 子代理。
- 合并冲突。
- 补齐跨模块集成。
- 跑最终回归。

### 71B 后端分类持久化/API

建议子代理类型：worker。

文件范围：

- 新增：`backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- 修改：`backend/src/fin_ops_platform/services/state_store.py`
- 修改：`backend/src/fin_ops_platform/services/bank_details_service.py`
- 修改：`backend/src/fin_ops_platform/app/server.py`
- 测试：`tests/test_bank_transaction_category_service.py`
- 测试：`tests/test_bank_details_service.py`
- 测试：`tests/test_workbench_v2_api.py`

要求：

1. 新增 canonical 分类：
   - `external_turnover` -> `外部往来款`
   - `internal_transfer` -> `内部往来款`
   - `offset` -> `冲`
   - `cash_turnover` -> `现金往来`
2. `BankTransactionCategoryService` 支持：
   - `from_snapshot`
   - `snapshot`
   - `get(transaction_id)`
   - `bulk_get(transaction_ids)`
   - `apply_updates(updates, actor)`
   - `category_counts(transaction_ids)`
3. 保存时校验：
   - transaction 必须存在。
   - category code 必须合法或为 null。
   - expected_version 冲突要报错。
4. `BankDetailsService` 返回每条 row 的：
   - `category_code`
   - `category_label`
   - `category_version`
5. `BankDetailsService.list_transactions` 返回全查询范围 `category_counts`，不是当前页 counts。
6. 新增 `PATCH /api/bank-details/transactions/categories`。
7. API 成功后返回 `updated_transaction_ids`、`updated_categories`、`affected_months`、`workbench_rebuild_queued`。
8. 保存后必须触发 workbench read model invalidation、candidate dirty scope/search cache 清理。
9. 只读/只导出用户不能保存，后端拒绝。

验证：

```bash
PYTHONPATH=backend/src:. pytest tests/test_bank_transaction_category_service.py tests/test_bank_details_service.py tests/test_workbench_v2_api.py -q
```

### 71C 银行明细 MUI UI

建议子代理类型：worker。

文件范围：

- 修改：`web/src/features/bankDetails/types.ts`
- 修改：`web/src/features/bankDetails/api.ts`
- 修改：`web/src/pages/BankDetailsPage.tsx`
- 测试：`web/src/test/BankDetailsPage.test.tsx`
- 如需 mock：`web/src/test/apiMock.ts`

要求：

1. 使用 MUI 原生组件：
   - DataGrid
   - TextField select 或 Select/MenuItem
   - Chip
   - Button
   - Snackbar/Alert
   - Dialog
2. DataGrid 新增“类别”列。
3. 标签选项包括“无”、外部往来款、内部往来款、冲、现金往来。
4. 表头 toolbar 显示服务端 category counts，并叠加本地 dirty 后的即时数量。
5. 显示“未保存 N”。
6. 保存按钮无 dirty 时 disabled；保存中 loading。
7. 翻页不弹提示，dirty 跨页保留。
8. 切换账户、切换日期、离开页面、刷新页面前，如有 dirty，弹 Dialog 选择：
   - 保存并继续
   - 放弃变动
   - 取消
9. 保存提交全部 dirty row。
10. 保存成功触发：
    ```ts
    window.dispatchEvent(new CustomEvent("bankTransactionCategoryUpdated", {
      detail: { affectedMonths }
    }));
    ```
11. 保存失败保留 dirty，并显示错误。

验证：

```bash
npm --prefix web test -- --run BankDetailsPage
```

### 71D 关联台 row 契约、备注列与特殊规则

建议子代理类型：worker。

文件范围：

- 修改：`backend/src/fin_ops_platform/services/live_workbench_service.py`
- 修改：`backend/src/fin_ops_platform/services/workbench_special_rule_detectors.py`
- 修改：`backend/src/fin_ops_platform/services/workbench_special_pair_rule_service.py`
- 修改：`backend/src/fin_ops_platform/app/server.py`
- 修改：`web/src/features/workbench/types.ts`
- 修改：`web/src/features/workbench/api.ts`
- 修改：`web/src/features/workbench/tableConfig.ts`
- 修改：`web/src/components/workbench/WorkbenchRecordCard.tsx`
- 测试：`tests/test_live_workbench_service.py`
- 测试：`tests/test_workbench_special_pair_rule_service.py`
- 测试：`web/src/test/WorkbenchApi.test.ts`
- 测试：`web/src/test/CandidateGroupGrid.test.tsx`

要求：

1. `LiveWorkbenchService` 输出 bank row 分类字段：
   - `category_code`
   - `category_label`
   - `category_source`
   - `tags` 中加入分类 label，但不覆盖系统标签。
2. 输出 `bank_text_fields`，历史数据至少由 `summary`、`remark` 生成；未来导入字段预留。
3. 前端 `ApiWorkbenchRow` / `WorkbenchRecord` 增加分类和 `bankTextFields`。
4. 关联台银行“备注”列改为动态显示：
   - 摘要
   - 备注
   - 用途
   - 交易用途
   - 客户附言
   缺失不显示。
5. `WorkbenchSpecialRuleDetector` 读取 `category_code`：
   - `internal_transfer` 优先内部往来规则，但仍校验金额、方向、账户。
   - `cash_turnover` 直接作为现金往来 evidence。
   - `offset` 接入现有 `OA_INVOICE_OFFSET_AUTO_MATCH` 语义，不另造规则码。
   - `external_turnover` 作为外部往来 evidence，若当前外部往来闭环规则未完整实现，至少要把 evidence 写入候选/特殊 metadata，不允许假闭环。
6. `冲` 必须与现有“周洁莹冲”共用 `OFFSET_TAG = "冲"`。

验证：

```bash
PYTHONPATH=backend/src:. pytest tests/test_live_workbench_service.py tests/test_workbench_special_pair_rule_service.py -q
npm --prefix web test -- --run WorkbenchApi CandidateGroupGrid
```

### 71E 导入文本字段保留

建议子代理类型：worker。

文件范围：

- 修改：`backend/src/fin_ops_platform/domain/models.py`
- 修改：`backend/src/fin_ops_platform/services/import_file_service.py`
- 修改：`backend/src/fin_ops_platform/services/imports.py`
- 修改：`tests/mock_import_files.py`
- 测试：相关 import / bank details / live workbench 测试。

要求：

1. `BankTransaction` 支持结构化 `bank_text_fields` 或等价字段。
2. 导入解析时保留银行文件原始文本字段，至少：
   - 摘要
   - 备注
   - 用途
   - 交易用途
   - 客户附言
   - 附言
3. 不改变 source unique key/data fingerprint 逻辑，除非现有规范明确包含这些字段。
4. 历史数据没有该字段时，`LiveWorkbenchService` 从 `summary/remark` fallback。

验证：

```bash
PYTHONPATH=backend/src:. pytest tests/test_import_api.py tests/test_bank_details_service.py tests/test_live_workbench_service.py -q
```

### 71F 总体验收

负责人：主线程。

要求：

1. 检查所有任务是否满足设计文档。
2. 跑后端回归：
   ```bash
   PYTHONPATH=backend/src:. pytest tests/test_bank_transaction_category_service.py tests/test_bank_details_service.py tests/test_live_workbench_service.py tests/test_workbench_special_pair_rule_service.py tests/test_workbench_v2_api.py -q
   ```
3. 跑前端回归：
   ```bash
   npm --prefix web test -- --run BankDetailsPage WorkbenchApi CandidateGroupGrid
   ```
4. 跑：
   ```bash
   git diff --check
   ```
5. 如有 dev server，给出可测试 URL。

## 执行约束

- 不允许临时方案。
- 不允许绕过后端权限。
- 不允许只改前端。
- 不允许标签直接决定闭环。
- 不允许破坏现有“周洁莹冲”规则。
- 不允许污染导入去重指纹。
- 有行为变化必须补测试。
