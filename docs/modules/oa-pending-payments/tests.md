# OA 待付款核对测试责任

日期：2026-07-28

## 2026-07-31 关联支出流水抽屉回归

- `web/src/test/OaPendingPaymentsPage.test.tsx` 保护共享 `AppDrawer` 复用、560px 宽度、busy close guard、搜索/筛选/分页/选择/提交、候选 503 抽屉内反馈与同查询重试清理、页面 mutation 错误隔离，以及旧自定义 shell 删除。
- `web/e2e/drawer-motion.spec.ts` 通过共享 Workbench 详情实例机械证明 HeroUI right drawer 的进入/退出中间帧、方向、reduced-motion、CLS 严格阈值和关闭零新增业务请求；OA 页面原有 `oa-pending-payments-flow.spec.ts` 继续保护本模块详情/关联业务流。
- 适用第 5 类 frontend interaction 与第 7 类 existing regression；本次没有业务规则、service、API、read model 或跨模块数据流变更，第 1–4 类和新的第 6 类后端链路测试不适用。

## 风险模型

本模块跨 OA integration canonical snapshots、Workbench/pending relations、银行/发票 facts、外部写回、PostgreSQL direct query、权限和前端交互。测试必须证明：

- rows、summary、statistics、facets 和当前页 hydrate 来自同一显式只读 repeatable-read snapshot。
- 正式关系只读取 active canonical Workbench facts；withdrawn/inactive 不可由旧 projection/raw payload 复活。
- `turnover_manual_closure` 等混合收支关系必须可见；只有 outflow 进入支付展示、金额和写回，inflow-only 保持 unpaid。
- Audit 必须发现 active OA+outflow 关系存在但 canonical page consumer 遗漏的情况。
- 页面请求不访问 OA Mongo/MySQL、Redis、queue、worker 或 read-model projection。
- SQL 服务端过滤/排序/分页，查询次数不随 page size 增长。
- 写回/claim/promotion 的权限、审计、幂等、冲突和写后重新 GET 不回归。
- `read_model_status`、source versions、refresh enqueue、`202/304/ETag` 和 frontend polling 不再出现。

## 七类测试

### 1. 业务核心单测：适用

覆盖：

- `paymentStatus` 的 paid/unpaid、金额边界、outflow、candidate/inactive relation。
- 混合收支关系只展示/合计 outflow；inflow-only、missing bank fact fail closed。
- completed/in-progress identity、flow id、duplicate/empty/invalid input。
- grouped OA/bank/invoice row 组装、跨月隔离和 relation row identity。
- writeback already-paid、重复提交、claim/CAS/冲突和部分失败。
- filters/sort/paging/view mode 参数合同。

入口：

- `tests/test_oa_pending_payment_canonical_rows.py`
- `tests/test_oa_pending_payment_command_service.py`
- `tests/test_invoice_lifecycle_policy.py`
- `tests/test_oa_pending_payment_query_service.py`

### 2. Service / repository：适用

覆盖：

- query service 在一个 repository snapshot 中执行 selector + 当前页 hydrate。
- 空页不 hydrate；missing detail 为 `404`。
- repository 显式执行 `REPEATABLE READ READ ONLY`。
- selector SQL 使用 canonical OA/admission/payment status、pending relation、active Workbench relation、bank/invoice tables。
- active OA+outflow relation 与 canonical consumer visibility 的 Audit 对照。
- 当前页 1 与 200 descriptors 的 hydrate 查询次数相同，无 N+1。
- OA authoritative snapshot 幂等 commit、writeback 后 PG reconcile、失败回滚。

入口：

- `tests/test_oa_pending_payment_query_service.py`
- `tests/test_oa_pending_payment_postgres_integration.py`
- `tests/test_oa_pending_payment_source_snapshot_repository.py`
- `tests/test_oa_pending_payment_relation_repository.py`
- `tests/test_oa_pending_payment_command_service.py`

### 3. API contract：适用

覆盖：

- rows `200` shape：rows/pagination/summary/statistics/filterConfig/filterOptions/appliedFilters/sort/viewMode。
- 空集、非法 month/date/range/page/filter/sort、missing detail。
- 未认证/无读取权限/read-only 写入拒绝，identity 每 endpoint 只解析一次。
- tenant 传入 query repository。
- 旧 filter endpoint 保持不存在。
- `If-None-Match` 不触发旧条件语义；响应不含 ETag、`202/304`、read-model/version/refresh fields。
- write 200/400/409/503、幂等重复和 `readModelRefresh` 删除。

入口：

- `tests/test_oa_pending_payment_api.py`
- `tests/test_oa_pending_payment_query_service.py`
- `tests/test_oa_pending_payment_command_service.py`

### 4. Read model / cache / background job cleanup：适用

本页面运行时的目标是“不存在这些依赖”，因此覆盖方式为负向 guard：

- repository SQL 不引用 `read_model.oa_pending_payment_*`、`workbench_relation` projection、dirty/outbox。
- page frontend/API/types 不含 freshness/source version/refresh target/polling。
- 页面 query service 不注入 queue/Redis/worker。
- 旧 OA read-model service/projector/worker 与 invoice-lifecycle 间接依赖已删除；架构守卫锁定不得恢复。

入口：

- `tests/test_oa_pending_payment_query_service.py`
- `tests/test_oa_pending_payment_api.py`
- `web/src/test/OaPendingPaymentsPage.test.tsx`
- whole-repo boundary scans / existing architecture guards

### 5. Frontend component / interaction：适用

覆盖：

- initial loading、ready、true empty、error、手工 refreshing。
- canonical rows 只加载一次，无后台 polling。
- 手工刷新只发一个 normal GET，不带 `If-None-Match`。
- 搜索、筛选、排序、分页、view toggle。
- OA/bank/invoice/relation drawers，detail error。
- 权限隐藏/禁用写操作。
- link/writeback 成功后当前 rows GET；失败反馈与重试。
- 晚响应不能覆盖新 query。
- Audit 单次读取且不调用 page operation barrier。

入口：

- `web/src/test/OaPendingPaymentsPage.test.tsx`
- `web/src/test/OaPendingPaymentAuditIcon.test.tsx`

### 6. End-to-end business flow：适用

需要保护的关键路径：

- canonical OA + active Workbench relation + bank/invoice facts -> rows/details。
- canonical OA + mixed turnover relation + inflow/outflow facts -> 只显示和合计 outflow。
- active relation withdraw -> 下一次 GET 直接不再展示 relation，无 refresh worker。
- in-progress link-bank -> optional paid writeback -> PG snapshot -> current rows GET。
- writeback-paid -> external adapter -> PG snapshot -> current rows GET。

自动化入口：

- `tests/test_oa_pending_payment_postgres_integration.py`
- `web/e2e/oa-pending-payments-flow.spec.ts`
- `web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts`
- `web/e2e/oa-pending-payments-bank-link-flow.spec.ts`

`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts` 已在保留文件名的同时改写为 direct canonical response、无后台 polling、503 错误不伪装空集和单次手工刷新恢复。

### 7. Existing feature regression：适用

影响面：

- OA integration snapshot 与外部 MySQL 写回。
- Workbench relation confirm/withdraw、pending promotion 和 bank claim。
- invoice lifecycle 仍消费的旧 OA read-model repository。
- input/output invoice read models、App Status、runtime worker registry。
- permissions/audit。

回归入口：

- `tests/test_oa_projection_sync_service.py`
- `tests/test_oa_pending_payment_command_service.py`
- `tests/test_workbench_*`
- `tests/test_invoice_lifecycle_*`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_app_status_overview_service.py`

跨页面 cleanup 已删除 OA 专属 registry/deploy/worker；当前共享运行时只保留 `workbench` 与 `workbench_relation`，由各自回归保护。

## 性能验收

### 本地门槛

- selector 固定 1 个 statement，服务端 limit/offset。
- hydrate 查询次数对 1 与 200 descriptors 相同，当前 guard 上限 `<=5` repository reads（不含 selector）。
- 单个 rows 请求使用一个显式 repeatable-read/read-only snapshot。
- 不新增索引、cache 或 materialized view 掩盖慢查询。

### 统一部署后的硬门槛

- 在生产等量级只读副本运行 selector 与 hydrate 的 `EXPLAIN (ANALYZE, BUFFERS)`，记录数据量、plan、rows、buffers 和耗时。
- rows endpoint 至少 1000 次，报告 p50/p95/p99/error rate；目标仍为 server `p95 <=250ms`、`p99 <=500ms`。
- page size 20/50/100/200 各验证查询次数固定，无 N+1。
- active relation confirm/withdraw、pending link 和 paid writeback 后，各测 normal GET 可见性；不等待 worker。
- 同时记录连接获取、snapshot、selector、hydrate、serialization 和 browser render。

索引只有在 EXPLAIN 证明瓶颈后提出，migration 编号由主控统一分配。

## 本地验证命令

```bash
bash scripts/verify.sh lint

pytest -q \
  tests/test_oa_pending_payment_query_service.py \
  tests/test_oa_pending_payment_api.py \
  tests/test_oa_pending_payment_command_service.py \
  tests/test_oa_pending_payment_postgres_integration.py

cd web && npm test -- --run \
  src/test/OaPendingPaymentsPage.test.tsx \
  src/test/OaPendingPaymentAuditIcon.test.tsx

cd web && npm run build
```

配置 `FIN_OPS_TEST_DATABASE_URL` 时，PostgreSQL integration 必须实际执行；未配置时属于 conditional skip，不能冒充 SQL 已验证。

## 当前剩余风险

- 当前环境若没有 disposable `FIN_OPS_TEST_DATABASE_URL`，真实 PostgreSQL SQL parse/plan 与 active-withdraw 集成用例只能在统一验证环境执行。
- 未运行生产等量级 EXPLAIN/endpoint benchmark，无法声明当前 direct-query p95/p99。
- MySQL 与 PostgreSQL 无分布式事务；依赖既有幂等重试与 OA sync，仍需生产故障演练。
- 历史 OA read-model 表仍存在但无运行时 reader/writer；物理 drop 留给单独可回滚 migration。
