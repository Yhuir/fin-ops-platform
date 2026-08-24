# 销项发票收款情况测试矩阵

日期：2026-08-11

## 七类测试适用性

| 类别 | 适用性 | 覆盖 |
| --- | --- | --- |
| 1. 业务核心单元 | 适用 | 红蓝票精确 identity、正负极性、唯一性、日期、歧义拒绝、六种状态、收入金额 |
| 2. Service/repository | 适用 | canonical query、固定查询边界、关系组装、支出流水排除、详情与导出 |
| 3. API contract | 适用 | 七个 GET、权限、非法参数、404、错误映射、旧 mutation route 不存在 |
| 4. Read model/cache/worker | 不新增运行时覆盖 | 页面不使用 read model/cache/worker；boundary guard 保护旧链路不回归 |
| 5. Frontend interaction | 适用 | loading/empty/error、三组居中表头、六种 chip、完整状态候选、原表格局部刷新、内部滚动、详情、导出、旧 UI 缺失 |
| 6. E2E 业务流 | 适用 | canonical rows、自动红蓝票展示、详情、搜索、导出、暂时失败恢复、零 mutation |
| 7. 既有功能回归 | 适用 | Workbench 普通匹配不受影响、红票不误匹配、权限矩阵和其他发票页面合同不变 |

## 关键合同

- 红蓝票匹配同时验证 tax IDs、currency、tax rate、gross/net/tax 绝对值、日期和唯一性。
- 匹配结果写入正式 relation mode `output_invoice_reversal`；重复执行幂等，歧义不写。
- 红票不进入通用自由匹配。
- 蓝票和红票各自保留为独立行，并通过 `invoiceRelations.summaries` 互相引用。
- 列表与关系详情共用唯一 row ID 合同：`output_invoice_collection_row_` 加 `sha1(group_key)` 前 16 位；PostgreSQL `load_row()` 必须能原样读取列表返回的 ID。
- 已收金额只统计 active relation 中的收入流水，支出流水不计入。
- row 顶层只含七个当前字段，不含 OA、receipt、manual status 或 reminder。
- 页面只注册七个 GET route，旧 lifecycle/receipt/manual-red route 返回未匹配。
- 前端只呈现三组表格，不显示旧按钮、旧抽屉、OA 或收据列。
- 主表收款状态只显示状态 chip；待收款、部分收款、已收款额外显示绿色“已收”和橘黄色“待收”金额，不展示 `reason` 或 `canonical` 等内部说明。
- 已被红冲、已冲销蓝票、红票待核对不显示无意义的零收款金额。
- 状态内容布局不得改变 HeroUI `Table.Cell` 的原生 `table-cell` 行为；多条收入流水撑高整行时，状态背景必须覆盖完整行高。
- 表格保持有界内部滚动，HeroUI 分页位于 FinanceTable footer；范围选择与搜索保持同一紧凑行且不重叠。
- 状态筛选后的 `/rows` 仍返回六种完整状态候选；前端交互测试锁定同一 table DOM 节点，防止恢复整表 skeleton/unmount 刷新。
- 发票号码单元格按 API 已有 `isPositiveInvoice` 展示蓝字/红字 chip；顺序固定为开票日期、票面极性、红蓝票关系，前端不得用金额或关系状态反推极性。

## 主要测试入口

- `tests/test_workbench_free_matching_engine.py`
- `tests/test_invoice_usage_collection_canonical_query.py`
- `tests/test_invoice_usage_collection_postgres_integration.py`
- `tests/test_output_invoice_collection_api.py`
- `tests/test_output_invoice_collection_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx`
- `web/e2e/output-invoice-collections-flow.spec.ts`
- `web/e2e/output-invoice-red-relation-fanout.spec.ts`
- `web/e2e/permissions-role-matrix.spec.ts`

## 验证命令

```bash
bash scripts/verify.sh lint

python3 -m pytest -q \
  tests/test_workbench_free_matching_engine.py \
  tests/test_invoice_usage_collection_canonical_query.py \
  tests/test_output_invoice_collection_api.py \
  tests/test_output_invoice_collection_service.py \
  tests/test_platform_runtime_boundary_guards.py

npm --prefix web test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx
npm --prefix web run build
npm --prefix web run e2e -- \
  e2e/output-invoice-collections-flow.spec.ts \
  e2e/output-invoice-red-relation-fanout.spec.ts \
  --project=chromium
```

发布前还必须通过仓库 release gate；部署后执行页面 canonical audit、关键 GET 性能和 T+0/T+60/T+300 延迟复核。

PostgreSQL 集成测试必须覆盖 `load_page() -> row.id -> load_row() -> relation_details()`，不能用固定 mock ID 替代生产 repository 的 row ID 反查合同。

## 剩余风险

- deterministic 测试不等价于生产历史数据分布；生产验证必须检查歧义红蓝票不会被自动关系吞并。
- 历史 lifecycle/receipt 表仍存在但无运行时 reader/writer；本任务不执行不可逆 drop。
