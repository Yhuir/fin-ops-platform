# 待找发票测试矩阵

> 页面已切换为 canonical query。旧 `pending_invoice`、search-pending、invoice-lifecycle
> 页面 projection/worker 测试只作 Git 历史，不是当前合同。

## 当前不变量

- rows、summary、statistics、facets、筛选、排序和分页来自同一个
  `REPEATABLE READ / READ ONLY` PostgreSQL snapshot。
- 页面只读 canonical bank/invoice/OA/settings/income overrides 与 active formal relations；
  不读取 `pending_invoice`、`bank_detail`、`workbench_relation` 或 `search` projection。
- 支出/收入状态、规则优先级、多 OA/流水/发票聚合、候选发票和导出业务口径保持不变。
- OA summary 覆盖 completed/in-progress workflow status；OA 栏显示 HeroUI workflow chip且不再显示 OA “已配对” chip。
- rules、attach-existing、income status 等 command 保留权限、CAS、idempotency、audit 与
  冲突校验；成功后页面执行一次 normal GET。
- API/frontend 没有 read-model status/source/scope/job/barrier、202、polling 或 fallback。
- 表格仅保留共享 FinanceTable footer 分页；组件与 Browser 测试使用共享分页 summary、HeroUI 页容量选择器和上一页/下一页合同，不允许旧原生分页 class 回归。

## 七类测试

| 类别 | 适用性 | 当前入口 |
| --- | --- | --- |
| 1. 业务核心 | 适用 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_relation_identity.py`：规则、状态、关系、聚合、冲突、幂等 |
| 2. Service/repository | 适用 | `tests/test_pending_invoice_canonical_query.py`、`tests/test_pending_invoice_postgres_integration.py`：snapshot、共享 compiled rule SQL、active relation、固定查询预算、真实 PostgreSQL 命中 |
| 3. API contract | 适用 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts`：rows/detail/rules/candidates/attach/export/权限和 retired 字段缺失 |
| 4. Read model/cache/worker | 适用（负向） | `tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_architecture_guards.py`：页面 worker/runtime 与独立 Search runtime 保持删除 |
| 5. 前端交互 | 适用 | `web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx`：loading/empty/error、筛选/分页/抽屉/批量写/写后 refetch |
| 6. 端到端 | 适用 | `web/e2e/pending-invoices-*.spec.ts`：规则、筛选、attach、收入状态、导出与错误恢复 |
| 7. 既有功能回归 | 适用 | 全量 backend/frontend/E2E；重点保护关联台、发票使用/收款、OA、Search 与正式关系写入 |

## 必须保留的负向断言

- `pending_invoice.read_model.refresh`、search-pending、invoice-lifecycle 页面 worker/event/env
  不存在。
- 页面 SQL 不引用 `read_model.pending_invoice_*`、`read_model.bank_detail_*`、
  `read_model.workbench_relation_*`、`read_model.search_*`。
- GET 不 enqueue；command 不返回 freshness/operation-barrier target。
- 缺少 canonical repository 时 fail fast，不回退旧 service projection 或 broad snapshot。

## 验证

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_pending_invoice_service \
  tests.test_pending_invoice_relation_identity \
  tests.test_pending_invoice_canonical_query \
  tests.test_pending_invoice_api -v
cd web && npm test -- --run \
  src/test/PendingInvoicesApi.test.ts \
  src/test/PendingInvoicesPage.test.tsx \
  src/test/PendingInvoicesRulesSaveTimeout.test.tsx
```

真实 PostgreSQL integration 需要 `FIN_OPS_TEST_DATABASE_URL`；生产验证必须覆盖大数据分页、
筛选/导出上限、规则写后 normal GET 和 active relation 可见性。

```bash
FIN_OPS_TEST_DATABASE_URL=postgresql://localhost/<disposable_db> \
  PYTHONPATH=backend/src python3 -m unittest \
  tests.test_pending_invoice_postgres_integration -v
```
