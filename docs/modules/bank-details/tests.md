# 银行明细测试矩阵

> 银行明细与账户余额都通过 canonical query 读取。旧 `bank_detail`、
> `bank_account_balance` projection/worker/backfill 测试已退出当前矩阵。

## 当前不变量

- accounts、transactions、statistics、category facets、active relation overlap 与 export
  从页面专属 PostgreSQL repository 读取。
- transactions 页面 payload 位于一个 `REPEATABLE READ / READ ONLY` snapshot；分页、
  筛选、排序和聚合在 SQL 完成，没有 per-row relation/category N+1。
- 关系只读 `app.workbench_pair_relations.status='active'`，不读 Workbench 页面 payload
  或 `workbench_relation` distribution。
- GET 不返回 read-model status/version/source/scope/job/barrier，不 enqueue、不 polling。
- 自动标签、人工覆盖和候选确认/撤销保留权限、CAS、审计、幂等；人工覆盖必须原子 supersede/revoke 旧 active facts，并在 direct query、共享 provider 和待找发票 canonical query 中优先于自动规则；成功后只重新 GET 当前 transactions。
- 自动标签规则抽屉使用局部原生语义表格：同名主标签通过 `rowSpan` 合并为单个行组标题，子标签保持逐行编辑；单元格内容完整换行展示，表头固定且滚动限制在表格容器内，不依赖 HeroUI/共享 `FinanceTable` 的行模型。
- 旧 runtime code/env/worker/event/backfill 保持删除；历史 migration/表只供回滚。

## 七类测试

| 类别 | 适用性 | 当前入口 |
| --- | --- | --- |
| 1. 业务核心 | 适用 | `tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_details_service.py`、`tests/test_bank_transaction_effective_category_provider.py`：人工优先、自动恢复、标签、分类、候选、金额和空集 |
| 2. Service/repository | 适用 | `tests/test_bank_transaction_category_postgres_mutation.py`、`tests/test_bank_category_relation_closure_service.py`、`tests/test_bank_details_canonical_query.py`、`tests/test_pending_invoice_canonical_query.py`：active category/confirmation 原子替换、requirement/history 闭环、set-based SQL 和跨页分类一致性 |
| 3. API contract | 适用 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_bank_details_routes.py`、`web/src/test/BankDetailsApi.test.ts`：自动/候选覆盖、内部往来选择、参数、权限和 response shape |
| 4. Read model/cache/worker | 适用（负向） | `tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py`：旧 runtime 不得回归 |
| 5. 前端交互 | 适用 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/AutoTagRulesDrawer.test.tsx`：loading/empty/error、筛选/分页/排序、自动标签撤销后重新分类、同主标签跨行合并、完整换行、规则编辑/校验/保存/停用/重新应用、待确认/待分类内部往来选择和写后 refetch |
| 6. 端到端 | 适用 | `web/e2e/bank-details-auto-tag-rules-flow.spec.ts`、其余 `web/e2e/bank-details-*.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts`：原生规则表格打开/保存/重新应用及导入/分类/导出/canonical 可见 |
| 7. 既有功能回归 | 适用 | 全量 backend/frontend/E2E；重点保护关联台、批量账务、成本、外部往来和 no-OA |

## 必须保留的负向断言

- `bank_detail.read_model.refresh`、`bank_account_balance.read_model.refresh`、对应 scope、
  handler、env、backfill CLI 不存在。
- 页面/API 不引用 `read_model.bank_detail_*`、`read_model.bank_account_balances`、
  Redis freshness cache 或 operation barrier。
- 缺少 canonical repository 时 fail fast，不能回退 broad state snapshot 或旧 projection。
- 写操作不 fan-out retired page dirty scope。

## 验证

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_bank_details_service \
  tests.test_bank_details_canonical_query \
  tests.test_bank_details_export_service \
  tests.test_bank_details_routes -v
cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx
```

真实 PostgreSQL integration 需要 `FIN_OPS_TEST_DATABASE_URL`；无该环境时必须在部署前用
生产只读 smoke 验证 accounts/transactions/export 的结果、查询耗时和执行计划。
