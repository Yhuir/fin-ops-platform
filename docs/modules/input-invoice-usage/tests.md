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
- 支付状态 chip 按 canonical `paymentStatus.code` 映射颜色：`paid` 为成功色、`waiting_payment` 为警示色、`pending` 为中性色；现金往来和三种冲销状态使用信息色，未知 code 保守显示中性色，不按中文 label 推断。
- OA reverse preview 必须区分 `permissions.canCreateDraft` 写能力与顶层 `canCreateDraft` 当前集合业务状态；多销方整组不可创建时，选择同一销方子集仍可触发精确 re-preview 并创建。
- OA reverse 候选表只保留选择、发票号码、销方、价税合计和 OA 关联列；开票日期在发票号码单元格内以 chip 展示，禁用通用说明不占据抽屉头部。
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
- `tests/test_read_model_architecture_guards.py`
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
