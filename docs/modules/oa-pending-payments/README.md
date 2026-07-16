# OA 待付款核对模块维护入口

- Module key：`oa-pending-payments`
- Route：`/oa-pending-payments`
- Page key：`oa-pending-payments`
- 当前状态：本地实现已闭环，等待统一部署、回填和生产性能验收

## 修改前必读

- `docs/modules/oa-pending-payments/boundary-io.md`
- `docs/modules/oa-pending-payments/state-machine.md`
- `docs/modules/oa-pending-payments/tests.md`
- `docs/modules/oa-pending-payments/performance-integrity-design.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- 前端：`web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/components/oaPendingPayments/*`、`web/src/features/oaPendingPayments/*`
- API：`backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
- 查询合同：`oa_pending_payment_query_contract.py`、`oa_pending_payment_read_model_service.py`、`oa_pending_payment_read_model_repository.py`
- 投影：`oa_pending_payment_sql_projection.py`、`oa_pending_payment_read_model_refresh.py`
- 命令：`oa_pending_payment_command_service.py`、`oa_pending_payment_relation_promotion_service.py`
- PostgreSQL owner：`postgres_repositories/oa_pending_payment_source_snapshot.py`、`postgres_repositories/oa_pending_payment_relation.py`、`postgres_repositories/oa_pending_payment_admission.py`
- OA integration：`oa_projection_sync.py`、`mongo_oa_adapter.py`、`oa_payment_status_service.py`
- Audit：`postgres_repositories/page_business_audit.py`、`web/src/components/oaPendingPayments/OaPendingPaymentAuditIcon.tsx`

## 当前有效链路

```text
OA Mongo / t_payment_simple
  -> OA integration sync
  -> PostgreSQL completed OA + admission + payment-status snapshot + source watermark
  -> 同事务先写 workbench_relation:<month> 依赖 dirty/outbox，再写 oa_pending_payment:<month> dirty/outbox
  -> oa-pending-payment 专属 worker（仅 PostgreSQL）
  -> 月份 read model 原子发布/CAS
  -> fresh gate
  -> 单一 rows 聚合 API（rows + summary + filterOptions + ETag）
  -> 页面 500ms 条件检查 / 202 barrier / fresh 重读
```

页面热路径和 read model worker 都不得访问 Mongo/MySQL。外部系统变化尚未进入 PostgreSQL 时，属于 OA sync lag；一旦 PostgreSQL canonical snapshot 已提交，dirty/outbox、动态 source version、CAS 和 fresh gate 必须阻止旧 rows 被伪装成 fresh。

月份 shard 只能包含该月份的 OA 主行。跨月正式 relation 可以继续为各月提供 relation evidence，但不得把其它月份的 OA 成员复制进当前月份 rows；relation group row identity 同时包含 month scope。`month=all` 不做隐藏去重，freshness gate 与 Page Audit 会把跨 scope 重复 `row_id` 明确判为阻断错误。

## 页面合同

- 页面只有 `GET /api/oa-pending-payments/rows` 一个首屏聚合入口；旧 `filter-options` endpoint 已删除。
- `200` 返回 rows、pagination、summary、`filterConfig`、`filterOptions`、freshness proof 和 `ETag`。
- 同一 normalized query 在版本未变且仍 fresh 时返回 `304`，不得执行 rows/facet 聚合。
- dirty、source mismatch、scope missing 或 queue 活跃时返回 `202` 和精确月份 `operationBarrierTargets`，不返回旧 rows。
- 可见页面每 500ms 最多发起一个条件 GET；tab 隐藏时停止，恢复可见时立即检查。收到 `202` 后立即隐藏旧 rows，等待 barrier fresh 再完整读取一次。
- `paymentStatus` 只有 `paid` / `unpaid`，由后端 lifecycle/read model 判定；页面不得按金额或候选关系自行推断。

## Completed 与 in-progress

- `completed` 主行来自 `app.oa_applications` completed/legacy projection。
- `in_progress` 主行来自 integration sync 已写入 `app.oa_pending_payment_admissions` 的准入快照；准入身份是 `t_payment_simple.flow_id` 对应的 OA Mongo `form_data._id`，不是 `t_payment_simple.id`。
- completed relation 证据来自 Workbench active relation；in-progress relation 证据来自 OA 待付款 active pending relation。pending relation promotion 前不得写入 Workbench active relation。
- 银行流水和发票是 relation evidence，不替代 OA 主行；付款写回仍须后端复核 active relation、outflow、金额相等和 flow id。

## 写回一致性

`writeback-paid` 和金额匹配后的 `link-bank-transactions` 先完成幂等 MySQL `pay_status=1` 写回，再通过窄 PostgreSQL snapshot writer 更新对应 flow 的支付状态、月份 source watermark 和精确月份 outbox。PostgreSQL 三项写入同事务；失败时命令返回可安全重试错误，重试即使发现 MySQL 已经是 paid，也必须继续修复 PostgreSQL snapshot。

Mongo/MySQL 与 PostgreSQL 之间不做分布式事务。若外部写成功而 PostgreSQL 提交失败，页面继续基于最后一个可证明的 PostgreSQL snapshot，不把外部状态猜成 fresh；幂等重试或下一次 OA sync 完成修复。

## Audit 文案

OA 页面通过专属 wrapper 隔离共享 `PageAuditIcon`，其它页面文案不变：

- `Audit 通过 · App 内部数据一致`
- `Audit 校验中 · 新数据正在生成`
- `Audit 未通过 · 发现 N 个一致性问题`
- `Audit 未通过 · Read model 未在时限内更新`
- `Audit 无法完成 · 请查看诊断`

禁止展示 `integrity issues_found`、`blocking samples` 等内部枚举拼接文案。Audit 只证明同一 PostgreSQL repeatable-read snapshot 内部一致性；外部同步 lag 单独表达。

## 明确不做

- 不新增 CDC、通用 event bus、SSE/WebSocket、Redis 页面 payload cache或新 worker framework。
- 不增加 stale-while-revalidate、live fallback、兼容 filter endpoint 或双读路径。
- 不修改其它页面 read model、共享 Page Audit 默认文案或 input/output invoice worker 责任。
- 不在没有生产 `EXPLAIN` 和压测证据时增加索引、分区、cursor pagination 或 worker pool。

## 本目录文件

- `performance-integrity-design.md`：性能、一致性、删除和统一部署验收设计。
- `boundary-io.md`：模块边界、I/O、事实所有权和 writer inventory。
- `state-machine.md`：业务、UI、read model、worker 和 Audit 状态机。
- `tests.md`：七类测试责任、命令和剩余生产风险。
- `e2e-spec.md` / `e2e-coverage.md`：浏览器合同与覆盖映射。
- `implementation-notes.md`：提炼后的实施记录，不保存原始 prompt。
