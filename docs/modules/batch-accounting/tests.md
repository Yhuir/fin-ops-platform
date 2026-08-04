# 批量账务测试合同

日期：2026-08-05

## 七类测试映射

| 类别 | 适用性 | 当前覆盖 |
| --- | --- | --- |
| 1. 业务核心单元测试 | 适用 | 金额匹配/差额说明、OA 去重、银行/OA 资格、标签选择/取消、提交时标签与规则 version 二次校验、active relation 冲突、CAS、跨月/跨年 scope、withdraw reason |
| 2. Service/repository 测试 | 适用 | query repository 参数、set-based canonical 分类、规则持久化/audit/no-op、command delegation、缺依赖 fail closed、固定 SQL statement count |
| 3. API contract 测试 | 适用 | tag-rules GET/PUT shape、read-export PUT 拒绝、非法 code/version、409 冲突、503 持久化失败、空集、summary/pagination、旧 freshness 字段不存在 |
| 4. Read model/cache/worker cleanup | 适用（清理） | 静态 guard 证明页面 repository 不读 `read_model.*`/Workbench generation；frontend/page/E2E 不再出现 polling、refresh status 或 barrier；无新 worker/cache |
| 5. Frontend interaction | 适用 | 标签 chip、HeroUI drawer、checkbox/save/loading/error、规则保存后一次 GET、双分页、submit/withdraw、只读权限 |
| 6. E2E 业务流 | 适用 | 页面打开 -> 规则抽屉取消标签 -> 保存 -> 左栏过滤；以及 submit -> submitted -> withdraw 完整路径 |
| 7. 既有功能回归 | 适用 | submitted 不受规则过滤、页面路由/权限、active relation、跨年 OA、已提交详情、关联发票、生产 build |

七类均适用；第 4 类只验证旧 read-model runtime 清理和“不新增”约束，不新增 read model/worker 测试。

## 后端测试

### `tests/test_batch_accounting_api.py`

- canonical 未提交/已提交响应和空集；银行名缺失时不得退回账户户名。
- 银行/OA 双分页、OA search 参数与 summary。
- 最大 200 银行 + 200 OA + 200 附件发票的 route/service DTO assembly guard。
- active batch relation 和 canonical member detail。
- amount/CAS/duplicate/conflict/invoice-only/cross-month 业务规则。
- submit/withdraw command owner。
- route HTTP contract、错误码、权限拒绝和旧状态字段清理。

### `tests/test_batch_accounting_postgres_integration.py`

- 固定 query count：未提交、已提交、submit context 均不超过 5，tag-rules snapshot 不超过 3，均包含 isolation statement。
- SQL 不引用 `read_model.` 或 Workbench generations。
- 配置 `FIN_OPS_TEST_DATABASE_URL` 时验证 canonical bank/OA/attachment/invoice/active relation、筛选、分页、submitted detail 和窄提交上下文。
- 未提交、已提交和 submit context 三条 SQL 链路都必须只提取银行名/尾号标量，不返回完整 `raw_payload`。

### `tests/test_platform_runtime_boundary_guards.py`

- GET route 只委托 route/service/query repository。
- repository 必须引用 canonical 表和 repeatable-read snapshot。
- 页面 runtime 不得恢复旧 Workbench loader、relation facade 或 freshness 字段。
- submit/withdraw route 不得绕过 command service。

## 前端与 E2E

- `web/src/test/BatchAccountingApi.test.ts`：canonical DTO、tag rules GET/PUT、submit rule version、OA search query、mutation DTO 无 barrier。
- `web/src/test/BatchAccountingPage.test.tsx`：标签 chip/规则抽屉/只读保存、loading/empty/error、双分页、搜索、选择、submit/withdraw、写后一次 GET。
- `web/e2e/batch-accounting-flow.spec.ts`：真实 Chromium 规则抽屉筛选、浏览器关键业务路径、临时加载失败恢复、窄屏。
- `web/e2e/fixtures/apiMocks.ts`：batch response 不再模拟 read-model status。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_batch_accounting_api \
  tests.test_batch_accounting_postgres_integration \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_legacy_repair_entrypoint_is_removed -v

npm --prefix web test -- --run \
  src/test/BatchAccountingApi.test.ts \
  src/test/BatchAccountingPage.test.tsx

npm --prefix web run build
npm --prefix web run e2e -- e2e/batch-accounting-flow.spec.ts --project=chromium
bash scripts/verify.sh lint
```

## 性能验收

- query-count guard 是强制门槛，不接受随数据量增长的 statement count。
- page size 最大 200；标签分类只读取精确“批量账务集中处理”候选 ID 集合，附件/成员按当前 ID 集合查询。
- 本地 100 次最大页 route/service assembly：p50 `3.637ms`、p95 `8.056ms`、max `28.213ms`。
- 实库集成测试记录列表查询耗时上限 5 秒；生产 EXPLAIN/端点 SLO 由主控在部署验证阶段执行。

## 当前未测风险

- 本地未提供 `FIN_OPS_TEST_DATABASE_URL` 时，真实 PostgreSQL SQL 语法、执行计划和最大生产数据分布只能由合并后实库测试/生产只读验证确认。
- 本分支不删除共享 Workbench/workbench-relation readers；其最终移除需要主控在所有页面迁移合并后运行 whole-repo 回归。
