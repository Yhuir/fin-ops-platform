# 销项发票收款情况测试矩阵

日期：2026-08-27

## 七类测试适用性

| 类别 | 适用性 | 覆盖 |
| --- | --- | --- |
| 1. 业务核心单元 | 适用 | 备注精确号码、正负极性、唯一目标、歧义拒绝、六种状态、收入金额 |
| 2. Service/repository | 适用 | canonical query、固定查询边界、关系组装、支出流水排除、详情与导出 |
| 3. API contract | 适用 | 七个 GET、权限、非法参数、404、错误映射、旧 mutation route 不存在 |
| 4. Read model/cache/worker | 不新增运行时覆盖 | 页面不使用 read model/cache/worker；boundary guard 保护旧链路不回归 |
| 5. Frontend interaction | 适用 | loading/empty/error、三组居中表头、六种 chip、完整状态候选、原表格局部刷新、内部滚动、详情、导出、旧 UI 缺失 |
| 6. E2E 业务流 | 适用 | canonical rows、自动红蓝票展示、详情、搜索、导出、暂时失败恢复、零 mutation |
| 7. 既有功能回归 | 适用 | Workbench 普通匹配不受影响、红票不误匹配、权限矩阵和其他发票页面合同不变 |

## 关键合同

- 红蓝票匹配只接受备注中的精确 20 位目标号码，且目标唯一命中正数销项发票；不得按金额、税额、购销方或日期猜测。
- Workbench formal matcher 与页面 canonical query 共用同一精确号码合同；页面不依赖第二条 active relation 才能展示关系。
- 红票不进入通用自由匹配。
- 每个 canonical 销项发票 ID 各自保留为独立行，普通 relation 和红蓝票关系均不得折叠行；蓝票和红票通过 `invoiceRelations.summaries` 互相引用。
- 同一普通 relation 含多张等额蓝票、红票和一条收入流水时，红票及其精确目标蓝票不重复计收款；仅在剩余正票唯一时归属该收入。
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
- 红字发票备注只按精确“被红冲蓝字数电发票号码：20 位号码”合同提取；列表第四列、详情、keyword 和导出共用该结构化结果，非合同自由文本不得猜测发票号。

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

## 日期默认全部回归（2026-09-21）

`OutputInvoiceCollectionsPage.test.tsx` 注入旧年月、起止与日期列缓存，断言首请求全部、无隐藏日期、page=1、非日期筛选/排序/pageSize 保留及旧详情关闭；选择月份后的刷新保留月份，卸载重进重新全部；切回全部后旧月份迟到响应不得覆盖当前结果。正式详情、收款状态和导出既有回归保留。

本次覆盖页面交互与既有功能回归；使用既有 API schema，不新增领域状态、写服务、read model 或 worker。导航、浏览器前后退与整页刷新由 App 进入规则浏览器验证补充。

## 原始流水金额与拆分展示回归（2026-09-24）

`tests/test_bank_split_document_scope_postgres.py` 与 `tests/test_bank_split_consumers_postgres.py` 验证原始金额 1001497.22 与利息业务金额 1497.22 同时成立、同父子项去重、多父金额/标签完整、原始金额筛选、子项金额搜索、持久化第三层及导出。适用业务核心、服务、API/查询合同、跨模块链路与旧功能回归；前端交互由各页面及 BankSplitChips 测试覆盖。本次无缓存/read-model/后台任务变更，验证 canonical 查询与现有写后 GET，无需新增后台测试。
