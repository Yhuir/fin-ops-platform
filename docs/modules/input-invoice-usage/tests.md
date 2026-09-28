# 进项发票使用情况测试矩阵

日期：2026-08-11

## 七类测试适用性

| 类别 | 适用性 | 覆盖 |
| --- | --- | --- |
| 1. 业务核心单元 | 适用 | 支付规则、active relation 聚合、多 OA/流水金额、OA reverse 状态与非法输入 |
| 2. Service/repository | 适用 | canonical query service、RR/RO snapshot、固定查询次数、OA reverse/export、同事务组装 |
| 3. API contract | 适用 | 权限拒绝、非法日期/月/filters、空集、筛选/排序/分页、summary、详情、导出、旧状态字段缺失 |
| 4. Read model/worker cleanup | 适用 | route/frontend 不再依赖 gate、202、polling、filter-options；旧 invoice-usage/lifecycle projection、worker、registry、deploy 保持删除 |
| 5. Frontend interaction | 适用 | loading/empty/error、筛选/排序/分页、详情、导出、OA reverse persistent drawer 的退出 inert/focus、写后 GET、权限 |
| 6. E2E 业务流 | 适用 | 读/导出、支付规则保存后 GET、OA reverse、关系详情、失败恢复 |
| 7. 既有功能回归 | 适用 | OA reverse、支付规则、Workbench relation fanout、permissions/audit |

## 关键合同

- canonical repository 只查询 canonical tables 和 `app.workbench_pair_relations status='active'`。
- 不查询 `read_model.input_invoice_usage_*`、`read_model.workbench_relation_*` 或 `read_model.invoice_lifecycle_*`。
- 一个页面 snapshot 最多 8 条批量 SQL statement，无逐行 N+1；rows/summary/facets 只计算一次 materialized canonical CTE。
- `/rows` 同时返回 rows/summary/statistics/filter options，前端不请求 `/filter-options`；支付状态筛选只约束 rows，不约束自身候选词表，全部规则状态（含零数量）持续可见。
- relation details、export 和 OA reverse preview 不回退旧 page repository。
- OA 详情按 rows DTO 的 canonical `oa.id` 直接读取 completed/in-progress OA projection；测试必须禁止把该 id 送入发票使用行 hash 查询。
- OA summary 从 completed/in-progress canonical source 输出 `workflowStatus`；OA 申请人总览列不显示流程状态，单条和多条 OA 详情只读取 `workflowStatus`，不得回退 relation `status/section`。
- 支付状态 chip 按 canonical `paymentStatus.code` 映射颜色：`paid` 为成功色、`waiting_payment` 为警示色、`pending` 为中性色；现金往来和统一 offset 分类使用信息色，未知 code 保守显示中性色，不按中文 label 推断。
- OA reverse preview 必须区分 `permissions.canCreateDraft` 写能力与顶层 `canCreateDraft` 当前集合业务状态；多销方整组不可创建时，选择同一销方子集仍可触发精确 re-preview 并创建。
- OA reverse 候选表保留选择、发票号码、销方、价税合计和流水关联列；开票日期在发票号码单元格内以 chip 展示，禁用通用说明不占据抽屉头部。
- 写成功响应不含 operation barrier；当前页面随后执行 GET。
- API/frontend 响应不含页面 `read_model_status`、source version、refresh enqueue 或 polling 语义。

## 主要测试入口

- `tests/test_invoice_usage_collection_canonical_query.py`
- `tests/test_input_invoice_usage_api.py`
- `tests/test_input_invoice_usage_service.py`
- `tests/test_input_invoice_usage_export_service.py`
- `tests/test_input_invoice_usage_oa_reverse_service.py`
- `tests/test_input_invoice_usage_payment_rules.py`
- `tests/test_postgres_input_invoice_usage_oa_reverse_repository.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_read_model_runtime_removal.py`
- `web/src/test/InputInvoiceUsagePage.test.tsx`
- `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`
- `web/e2e/input-invoice-usage-flow.spec.ts`
- `web/e2e/drawer-motion.spec.ts`
- `web/e2e/input-invoice-relation-fanout.spec.ts`

## 最小验证命令

```bash
bash scripts/verify.sh lint

python3 -m pytest -q \
  tests/test_invoice_usage_collection_canonical_query.py \
  tests/test_input_invoice_usage_api.py \
  tests/test_input_invoice_usage_service.py \
  tests/test_input_invoice_usage_export_service.py \
  tests/test_input_invoice_usage_oa_reverse_service.py \
  tests/test_input_invoice_usage_payment_rules.py \
  tests/test_postgres_input_invoice_usage_oa_reverse_repository.py

cd web && npm test -- --run \
  src/test/InputInvoiceUsagePage.test.tsx \
  src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx

cd web && npm run e2e -- e2e/input-invoice-usage-flow.spec.ts --project=chromium
cd web && npm run build
```

## 2026-09-15 搜索框双边框修复

- `web/e2e/input-invoice-usage-flow.spec.ts` 增加真实浏览器回归：1440、1280、768px 下检查内部输入无边框/背景、聚焦无重复阴影、图标/输入/清除按钮不遮挡、中文长文本、键盘焦点、Enter 提交、清除及分页参数。输入草稿不得新增查询请求。
- 测试已在修复前因内部 1px 边框失败；修复删除旧页面输入框样式，不改共享组件或 API。
- 本次变更适用七类中的 5（前端交互）、6（搜索 UI 到请求参数）、7（既有搜索回归）；1–4 无新增覆盖，因业务、服务、API、缓存和后台任务均不变。原有模块级测试继续保留。
- 浏览器截图用于人工检查，不引入截图 baseline 或额外发布门禁。

## 剩余风险

- fake transaction 测试保护查询上界、snapshot 命令和 SQL 边界；一次性本地 PostgreSQL 17 测试库另以 20,002 张进项发票验证 20,001 个聚合行：200 行页面请求稳定约 1.0–1.3 秒，精确 20,000 行 DTO 导出约 6.9 秒。
- 本地数据不等价于生产分布；生产 `EXPLAIN (ANALYZE, BUFFERS)`、锁等待、真实 XLSX 下载耗时和 OA 外部草稿联调仍需主控在 staging/生产只读验证。
- 历史 invoice-usage/lifecycle 表仍存在但无运行时 reader/writer；物理 drop 留给单独可回滚 migration。

## 2026-08-10 移动端宽表回归

- `web/src/test/InputInvoiceUsagePage.test.tsx` 锁定表格最小宽度与既有内部滚动容器，避免窄屏把十列压成逐字竖排；桌面列、筛选、分页、详情和 direct API 合同不变。

## 2026-08-11 OA 详情金额合同回归

- `tests/test_invoice_usage_collection_canonical_query.py` 使用生产真实字符串金额，锁定 canonical OA 详情输出 `120.00`。
- `tests/test_input_invoice_usage_api.py` 继续覆盖详情 API 成功/失败映射；生产验收补充真实关联 OA 点击、drawer 内容和无 500 验证。

## 2026-08-25 支付状态 chip 颜色回归

- `web/src/test/InputInvoiceUsagePage.test.tsx` 锁定“已付款/待处理/待付款”分别使用 success/neutral/warning，防止再次回退为统一 warning 色。

## 日期默认全部回归（2026-09-21）

`InputInvoiceUsagePage.test.tsx` 分别注入旧年月/起止与仅日期列过滤缓存，检查所有首请求没有隐藏日期，page=1 且旧详情/导出关闭，非日期偏好保留；已有全部范围 session 保留第 3 页。支付规则、OA 反提、导出与空态回归继续执行。

本次覆盖页面交互与既有功能回归；使用既有 API schema，不新增领域状态、写服务、read model 或 worker。导航、浏览器前后退与整页刷新由 App 进入规则浏览器验证补充。

## 原始流水金额与拆分展示回归（2026-09-24）

`tests/test_bank_split_document_scope_postgres.py` 与 `tests/test_bank_split_consumers_postgres.py` 验证原始金额 1001497.22 与利息业务金额 1497.22 同时成立、同父子项去重、多父金额/标签完整、原始金额筛选、子项金额搜索、持久化第三层及导出。适用业务核心、服务、API/查询合同、跨模块链路与旧功能回归；前端交互由各页面及 BankSplitChips 测试覆盖。本次无缓存/read-model/后台任务变更，验证 canonical 查询与现有写后 GET，无需新增后台测试。


## 2026-09-27 来源详情回归

按[来源详情验证责任](../../dev/source-record-details.md#验证责任)覆盖真实来源保留、内部状态/推断/替代值移除、缺失与零值、权限及读取失败；保留本模块列表、计算、导出和关系回归。公共前端入口包括 `EntityDetailContent.test.tsx`、`DetailDrawer.test.tsx` 与 `BankTransactionDrawer.test.tsx`，后者保护按 ID 读取、切换取消及禁止列表摘要回退。具体后端/浏览器执行及性能结果据实际报告，不以本节表示已通过。

## 2026-09-28 统计与反提闭环验证

新增 `tests/test_input_invoice_usage_candidates_postgres.py`：超过 200 张分页、同组三票、银行关联候选、OA 详情缺失、精确选票、空页总数、错误筛选及行/筛选金额状态一致。新增 `test_input_invoice_usage_payment_rules_postgres.py`：版本并发、幂等、审计回滚和真实配置迁移。新增 `test_oa_reverse_occupancy_postgres.py`：占用并发、释放、事务回滚及已有 OA 的锁后复核。

前端 `InputInvoiceUsagePage`、`InputInvoiceUsageFiltersAndDrawers` 及 `input-invoice-usage-flow.spec.ts` 更新为 HeroUI 分类 Tabs、真实发票张数、服务端候选分页/流水筛选、原生搜索、分页选择、规则增删改和写后回读。

七类中 1/2/3/5/6/7 均适用；第 4 类没有新缓存/read model/worker 行为，继续运行既有架构回归，禁止引回已退休链路。性能在同一生产环境记录列表和 preview 首次/p50/p95/max，张数交叉验证比较 canonical 发票身份集合，不写死历史 385。

## 2026-09-28 反提抽屉完整号码与筛选文案

- 待处理清单标题为“未关联 OA 的发票”，流水筛选为“全部 / 已关联流水 / 未关联流水”，计数沿用 `relationCounts` 的全量发票张数；未关联流水不代表未付款。“全部”包含另外两类，不是第三个互斥分类。
- 候选、暂存和已提交表格的发票号码列只在本抽屉内预留列宽并允许完整换行，保留原字符串与前导零；取消候选号码的 280px 限制和继承省略行为。公共 FinanceTable 的默认样式不改，无新增 API、统计、状态或网络请求。
- 组件测试覆盖完整号码、新文案与三个筛选参数；Playwright 覆盖 20/30 位号码、前导零、桌面/窄屏/150% 缩放的字形边界和分页筛选流程。既有预览、选择、占用及草稿流程回归继续运行。
- 测试责任：前端组件、关键流程集成与既有回归适用；业务规则、service、API 合同未修改，不新增对应测试。列表查询沿用现有合同并验证筛选刷新；独立 read model/cache/worker 不适用。生产只读 preview 与页面视觉核对，不创建或提交真实 OA，无迁移或数据库备份。
