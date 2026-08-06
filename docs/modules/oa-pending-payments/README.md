# OA 待付款核对模块维护入口

- Module key：`oa-pending-payments`
- Route：`/oa-pending-payments`
- Page key：`oa-pending-payments`
- 当前状态：页面通过 PostgreSQL canonical facts 直读；无页面 read model。

## 修改前必读

- `docs/modules/oa-pending-payments/boundary-io.md`
- `docs/modules/oa-pending-payments/state-machine.md`
- `docs/modules/oa-pending-payments/tests.md`
- `docs/modules/oa-pending-payments/performance-integrity-design.md`
- `docs/modules/oa-integration/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/input-invoice-usage/boundary-io.md`
- `docs/modules/permissions-and-audit/boundary-io.md`

## 代码入口

- 前端：`web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/components/oaPendingPayments/*`、`web/src/features/oaPendingPayments/*`
- API route：`backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
- 页面 query service：`backend/src/fin_ops_platform/services/oa_pending_payment_query_service.py`
- 页面 PostgreSQL repository：`backend/src/fin_ops_platform/services/postgres_repositories/oa_pending_payment_query.py`
- 查询合同与纯组装：`oa_pending_payment_query_contract.py`、`oa_pending_payment_canonical_rows.py`、`oa_pending_payment_details.py`
- 命令：`oa_pending_payment_command_service.py`、`workbench_relation_command_service.py`
- Canonical snapshot owners：`postgres_repositories/oa_pending_payment_source_snapshot.py`、`oa_pending_payment_admission.py`、`oa_projection.py`
- Audit：`postgres_repositories/page_business_audit.py`、`web/src/components/oaPendingPayments/OaPendingPaymentAuditIcon.tsx`

## 当前有效读链路

```text
browser
  -> GET /api/oa-pending-payments/rows
  -> route：单次鉴权、参数转交、HTTP 映射
  -> OaPendingPaymentQueryService
  -> PostgresOaPendingPaymentQueryRepository
  -> REPEATABLE READ / READ ONLY snapshot
     -> completed OA + in-progress admission + payment-status snapshots
     -> app.workbench_pair_relations(status=active)
     -> canonical bank/input-invoice facts
     -> SQL filters/sort/paging/summary/facets + 当前页批量 hydrate
  -> 200 canonical JSON
```

页面请求不访问 OA Mongo/MySQL、对象存储、Redis、RabbitMQ、read-model queue、Workbench 页面 payload 或 `workbench_relation` projection。`rows`、`summary`、`statistics`、`filterOptions` 和当前页 descriptors 在同一个显式数据库快照内读取；详情和银行候选分别使用同一 repository 的只读快照。

前端只保留 loading、empty、error、手工刷新和写后重新 GET。页面不解释 `read_model_status`、source versions、refresh enqueue、`202`、`304` 或 ETag，也不做 polling。

## 页面合同

- 首屏和所有列表查询只调用 `GET /api/oa-pending-payments/rows`；旧 `filter-options` endpoint 保持不存在。
- 成功响应固定为 `200`，公开字段为 `rows`、`pagination`、`summary`、`statistics`、`filterConfig`、`filterOptions`、`appliedFilters`、`sort`、`viewMode`。
- 不返回 `readModelStatus`、`read_model_status`、source versions、refresh target、job、cache/version metadata。
- 筛选、排序、分页、summary、facets 均由 SQL set-based 执行；最大 `page_size=200`，禁止浏览器或 Python 全量分页。
- OA、银行、发票和 relation detail 继续惰性读取；未找到返回结构化 `404`，非法查询返回 `400`。
- `bank-transaction-candidates` 直接从 PostgreSQL bank facts 与 active formal relations 做状态筛选、排序和分页；不再经 command service 全量加载。
- `paymentStatus` 仍由既有纯业务组装和 lifecycle policy 计算，前端不得自行推断。

## Completed 与 in-progress

- `completed` 主行来自 `app.oa_applications`。
- `in_progress` 主行来自 `app.oa_pending_payment_admissions`。
- completed 正式关系读取 `app.workbench_pair_relations` 中全部 `status='active'` 的事实。
- `turnover_manual_closure` 等混合收支关系中，只有成功解析的 outflow bank member 是本页支付证据；inflow 只保留为周转上下文，不进入页面流水、已付金额或写回金额。
- completed 与 in-progress 关系统一读取 `app.workbench_pair_relations.status='active'`；workflow status 只决定关联台 paired/unpaired gate，不产生 pending owner 或 promotion。
- 银行流水和发票只是 relation evidence，不替代 OA 主行。

## 写回一致性

`writeback-paid` 和金额匹配后的 `link-bank-transactions` 保留原有单次鉴权、tenant、active formal relation、outflow、金额、CAS/冲突、审计和幂等语义。link-bank 只通过正式 relation command 创建或扩展唯一 active case；已有混合收支关系的写回只合计 outflow，inflow 不参与金额校验。外部 MySQL 写回仍走既有 command/adapter；成功或 already-paid 后必须幂等更新 PostgreSQL payment-status canonical snapshot。响应不再返回页面 read-model refresh metadata，前端成功后立即重新调用当前 rows GET。

Mongo/MySQL 与 PostgreSQL 之间没有分布式事务。若外部写成功而 PostgreSQL canonical commit 失败，命令必须返回可安全重试错误；重试或后续 OA sync 收敛，不允许页面请求回退读取外部系统。

## 旧链清理结果

`oa_pending_payment` 旧 read model、projector、worker、manifest、App Status registry、deploy env 和 invoice-lifecycle 间接依赖已删除。invoice lifecycle 页面也已切换为 canonical direct read。历史 migration/表暂留作回滚证据，没有运行时 reader/writer。

旧 pending relation repository、bank claim、promotion service 及关联台 claim 排除链已删除；migration `0136` 后旧关系表只读审计，不参与页面或写命令。

## 明确不做

- 不新增 cache、worker、queue、materialized view、统一大而全 service、双读或 fallback。
- 不在 route/server 堆 SQL 或业务组合，不把 `Application` 传入 service。
- 不读取 Workbench page read model 或 `workbench_relation` projection 作为正式关系事实。
- 不因缺少生产 `EXPLAIN` 证据新增索引；索引建议和 migration 编号由主控统一处理。

## 本目录文件

- `boundary-io.md`：模块边界、直接/上下游 I/O、事实所有权和旧链删除状态。
- `state-machine.md`：业务、UI、写回和错误状态。
- `tests.md`：七类测试责任、命令和剩余风险。
- `performance-integrity-design.md`：查询次数、快照和生产性能门槛。
- `e2e-spec.md` / `e2e-coverage.md`：浏览器合同与覆盖映射。
- `implementation-notes.md`：历史实施记录；历史 read-model 设计不覆盖本页当前合同。
