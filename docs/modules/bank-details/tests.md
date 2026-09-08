# 银行明细测试矩阵

> 银行明细与账户余额都通过 canonical query 读取。旧 `bank_detail`、
> `bank_account_balance` projection/worker/backfill 测试已退出当前矩阵。

## 当前不变量

- accounts、transactions、statistics、category facets、active relation overlap 与 export
  从页面专属 PostgreSQL repository 读取。
- transactions 页面 payload 位于一个 `REPEATABLE READ / READ ONLY` snapshot；分页、
  筛选、排序和聚合在 SQL 完成，没有 per-row relation/category N+1。
- 内容筛选仅用于定位候选组；排序前按时间/账户 WITH TIES 选择覆盖本页前缀的完整时间组，从 classifier base 补齐完整候选日期检测时间歧义，再判定目标组。已确认组的 page keys、最终 rows 与 export 同序；每事实最多连接一条结果，不放大 summary/facets/金额，不丢弃 unresolved 行。
- `same_time_order_status` 与 `balance_status` 独立；可靠终点不等于已确认完整顺序。null 合计、最后已知值、真实零和未知状态必须分别保护。
- 关系只读 `app.workbench_pair_relations.status='active'`，不读 Workbench 页面 payload
  或 `workbench_relation` distribution。
- GET 不返回 read-model status/version/source/scope/job/barrier，不 enqueue、不 polling。
- 自动标签、人工覆盖和候选确认/撤销保留权限、CAS、审计、幂等；人工覆盖必须原子 supersede/revoke 旧 active facts，并在 direct query、成本统计/Workbench matching 规范投影、仍合法的共享 provider 和待找发票 canonical query 中优先于自动规则；成功后只重新 GET 当前 transactions。
- 自动标签规则抽屉使用局部原生语义表格：同名主标签通过 `rowSpan` 合并为单个行组标题，子标签保持逐行编辑；单元格内容完整换行展示，表头固定且滚动限制在表格容器内，不依赖 HeroUI/共享 `FinanceTable` 的行模型。
- 旧 runtime code/env/worker/event/backfill 保持删除；历史 migration/表只供回滚。

## 七类测试

| 类别 | 适用性 | 当前入口 |
| --- | --- | --- |
| 1. 业务核心 | 适用 | `tests/test_bank_same_time_ordering_postgres.py` 通过真实 SQL 保护顺序/终点与精度/歧义；`tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_details_service.py`、`tests/test_bank_transaction_effective_category_provider.py` 保护人工优先、自动恢复、标签、分类、候选、金额和空集 |
| 2. Service/repository | 适用 | `tests/test_bank_same_time_ordering_postgres.py`、`tests/test_bank_details_canonical_query.py` 保护完整组、账户聚合、同序导出与固定查询数；`tests/test_bank_transaction_category_postgres_mutation.py`、`tests/test_bank_category_relation_closure_service.py`、`tests/test_pending_invoice_canonical_query.py` 保护分类/关系原子写和跨页分类一致性 |
| 3. API contract | 适用 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_bank_details_routes.py`、`web/src/test/BankDetailsApi.test.ts`：参数/权限/response shape、必填状态、nullable 金额/币种/总额、来源 ID 可空与原字段 |
| 4. Read model/cache/worker | 本次不新增正向测试；保留负向回归 | `tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py`：排序是请求内派生，不新增或恢复 runtime；导入/撤回后重读由业务集成测试覆盖 |
| 5. 前端交互 | 适用 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/AutoTagRulesDrawer.test.tsx`：loading/empty/error、余额/顺序提示、null 不转零、真实零、切账户晚返回、账户失败不被流水成功清除、旧刷新不覆盖新规则读取、四类独立请求错误、筛选分页、规则抽屉、人工分类与写后 refetch |
| 6. 端到端 | 适用 | `tests/test_bank_same_time_ordering_postgres.py` 保护正式 import owner→canonical query→export snapshot→withdrawal owner→重读；`web/e2e/bank-details-*.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts` 保护浏览器流程。真实 PostgreSQL 的 owner 集成与带 mock 的 Browser E2E 不能相互替代，完整文件预览/确认到下载的实际验收结果另行记录 |
| 7. 既有功能回归 | 适用 | 全量 backend/frontend/E2E；重点保护关联台、批量账务、成本、外部往来和 no-OA |

## 必须保留的负向断言

- `bank_detail.read_model.refresh`、`bank_account_balance.read_model.refresh`、对应 scope、
  handler、env、backfill CLI 不存在。
- 页面/API 不引用 `read_model.bank_detail_*`、`read_model.bank_account_balances`、
  Redis freshness cache 或 operation barrier。
- 缺少 canonical repository 时 fail fast，不能回退 broad state snapshot 或旧 projection。
- 写操作不 fan-out retired page dirty scope。
- 共享分类映射及 Workbench 等分类消费者不要求页面顺序字段、不产生排序 I/O；新增状态仅在银行页面/导出映射边界添加。

## 同时间修复重点用例

`tests/test_bank_same_time_ordering_postgres.py` 使用匿名合成数据，不依赖生产账号或本地 Excel。必须保护：两组截图金额、逆序 ID/serial、三笔混合收支、负/零余额、分支但终点确定、断链/断开环、闭合组有无紧邻单笔起点、部分缺余额、最后已知及不越过冲突历史组、同日缺时间且被搜索隐藏、单笔日期、较晚完整日期、亚秒精度、同尾号不同账号、多币种与空币种沿用 CNY、signed amount/方向冲突、分页大小 1、金额搜索、导入防重及撤回后重读。

`tests/test_bank_details_export_service.py` 保护原列名称/相对顺序/金额与 sheet 分组、末列未确认说明及正常留空、20000 + 1 超限；导出权限和下载审计由 route/service 现有合同测试保护。固定查询数只验证无 N+1；真实 SQL 执行与 EXPLAIN、冷/热查询及尾延迟由[修复计划](../../dev/bank-same-time-ordering-repair-plan.md)记录实际结果，不因测试通过宣称性能或发布完成。

旧 `BankDetailsService.list_accounts/_latest_balance_transaction`、core accounts reader、state-store wrapper 及独占 fake 已删除；最新余额来源、日期仅影响笔数、范围外无余额账户、真实账号与 metadata 一致性等有效旧断言迁入 `tests/test_bank_same_time_ordering_postgres.py`。该文件当前 29 项，包含空库、全收入精确金额和既有账户合同，不能因旧方法删除而丢掉其业务保护。

2026-09-08 已有一轮前端全量 96 文件/1249 项通过；最后一项规则响应竞态回归加入后，银行专项 75 项、前端 build 和 6 项相关浏览器测试通过。真实 PostgreSQL 29 项已有一轮通过，后续 SQL 调整与重跑状态以修复计划为准；本记录不将此前通过外推为最终性能验收或发布完成。

## 验证

```bash
PYTHONPATH=backend/src:tests python3 -m unittest \
  tests.test_bank_same_time_ordering_postgres \
  tests.test_bank_details_postgres_integration \
  tests.test_bank_details_service \
  tests.test_bank_details_canonical_query \
  tests.test_bank_details_export_service \
  tests.test_bank_details_routes -v
npm --prefix web test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx
bash scripts/verify.sh docs
git diff --check
```

真实 PostgreSQL integration 需要本机独占 `FIN_OPS_TEST_DATABASE_URL`，运行前核对隔离测试库并 unset 生产/runtime DSN；不能把 truncate/migration 测试指向正式库。无测试库时明确记为未运行，生产只读 smoke 不代替业务集成测试。发布与性能验收尚未完成时必须保留该限制；导出 smoke 会写下载审计，不能称为零写入。
