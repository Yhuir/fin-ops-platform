# 销项发票收款情况测试矩阵

日期：2026-07-27

## 七类测试适用性

| 类别 | 适用性 | 覆盖 |
| --- | --- | --- |
| 1. 业务核心单元 | 适用 | 收款状态、提醒、红蓝票、收据生命周期、幂等/CAS、多发票净额和负数成员 |
| 2. Service/repository | 适用 | canonical query service、RR/RO snapshot、固定查询次数、同事务 lifecycle overlay |
| 3. API contract | 适用 | 权限拒绝、非法参数、空集、筛选/排序/分页、summary、详情、导出、冲突和旧状态字段缺失 |
| 4. Read model/worker cleanup | 适用 | route/frontend 不再依赖 gate、202、polling、filter-options；共享 worker 只做 HANDOFF |
| 5. Frontend interaction | 适用 | loading/empty/error、筛选/排序/分页、详情、导出、状态/提醒/收据、写后 GET、权限 |
| 6. E2E 业务流 | 适用 | 读/导出、状态/提醒、收据 create/void/reissue、红蓝票 relation、失败恢复 |
| 7. 既有功能回归 | 适用 | 收据幂等、permissions/audit、pending invoice、red relation fanout |

## 关键合同

- canonical repository 只查询 canonical tables 和 `app.workbench_pair_relations status='active'`。
- 不查询 `read_model.output_invoice_collection_*`、`read_model.workbench_relation_*` 或 `read_model.invoice_lifecycle_*`。
- 一个页面 snapshot 最多 11 条批量 SQL statement，无逐行 N+1；rows/summary/facets 只计算一次 materialized canonical CTE，lifecycle overlay 复用同一 transaction。
- linked 多发票 relation 输出一行净额，负数/红字发票保留在 summaries。
- `/rows` 同时返回 rows/summary/statistics/filter options，前端不请求 `/filter-options`。
- lifecycle/receipt 成功响应不含 operation barrier；当前页面随后执行 GET。
- API/frontend 响应不含页面 `read_model_status`、source version、refresh enqueue 或 polling 语义。

## 主要测试入口

- `tests/test_invoice_usage_collection_canonical_query.py`
- `tests/test_output_invoice_collection_api.py`
- `tests/test_output_invoice_collection_service.py`
- `tests/test_output_invoice_collection_lifecycle.py`
- `tests/test_pending_invoice_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_read_model_architecture_guards.py`
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx`
- `web/e2e/output-invoice-collections-flow.spec.ts`
- `web/e2e/output-invoice-red-relation-fanout.spec.ts`

## 最小验证命令

```bash
bash scripts/verify.sh lint

python3 -m pytest -q \
  tests/test_invoice_usage_collection_canonical_query.py \
  tests/test_output_invoice_collection_api.py \
  tests/test_output_invoice_collection_service.py \
  tests/test_output_invoice_collection_lifecycle.py \
  tests/test_pending_invoice_service.py

cd web && npm test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx
cd web && npm run e2e -- e2e/output-invoice-collections-flow.spec.ts --project=chromium
cd web && npm run build
```

## 剩余风险

- fake transaction 测试保护查询上界、snapshot 命令和 SQL 边界；一次性本地 PostgreSQL 17 测试库另以 20,003 张销项发票验证 20,001 个净额聚合行：200 行页面请求稳定约 1.2–1.3 秒，精确 20,000 行 DTO 导出约 3.9 秒。
- 本地数据不等价于生产分布；生产 `EXPLAIN (ANALYZE, BUFFERS)`、锁等待、收据编号并发和真实 XLSX 下载耗时仍需主控在 staging/生产验证。
- 共享 `invoice-usage-collection` / `invoice-lifecycle` worker 与 manifest 清理必须等所有页面直读分支合并后由主控验证。
