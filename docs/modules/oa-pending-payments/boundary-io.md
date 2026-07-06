# OA待付款核对模块边界与 I/O

日期：2026-07-06

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：OA 待付款页面读取 `oa_pending_payment` read model；已支付行写回、银行关联、OA 状态同步通过 command/service 边界触发 scoped refresh。
- 当前缺口：无模块化边界缺口；真实 OA Mongo/MySQL、PostgreSQL/RabbitMQ/Redis/systemd worker drain 仍属于 staging/生产 smoke 风险，不作为模块边界未闭合项。
- 旧代码删除状态：旧 `Application` rebuild/live read helper 已移除；生产 rows/filter/detail 不再回退 live query；后端手工 `/api/oa-pending-payments/confirm-paid` route 与 `OaPendingPaymentCommandService.confirm_paid(...)` 已移除；旧 `/api/oa-pending-payments/auto-reconcile-bank-transactions` route、前端 toolbar 按钮和 command service 自动匹配写回逻辑已移除；候选接口不再输出 `monthScopes` 旧月份收敛诊断字段。

## 职责边界

### 负责

- OA 待付款核对页面、已支付未写回行的写回、银行关联、状态展示和 OA projection read model。
- `oa_pending_payment` read model。
- OA 付款关系 promotion 和银行流水匹配入口。

### 不负责

- 不拥有 OA 登录/菜单权限事实。
- 不直接维护银行明细 read model。
- 不替代 workbench relation 事实源。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/过滤 | `OaPendingPaymentsPage.tsx`、`features/oaPendingPayments/api.ts` | 必须进入 `OaPendingPaymentReadModelService` fresh gate；read model service 未配置或 payload 不 fresh 时 fail closed，不回退 live query |
| 关联支出流水候选查询 | `GET /api/oa-pending-payments/bank-transaction-candidates` | `oa_row_ids` 只作为后续提交关联的目标 OA 上下文；候选读取全部支出流水，不按 OA 月份收敛 |
| 已支付写回/银行关联 | command service | 写操作必须审计并触发 read model scopes；逐行写回只能由 `writeback-paid` 触发，且后端必须重新校验已存在的 Workbench active relation 或 in-progress active pending relation、outflow、金额合计和 `flow_id`；`link-bank-transactions` 成功创建关系后仍可自动写回 |
| OA projection sync | OA sync/projection services | 输入必须带 source version |
| Refresh scope | `oa_pending_payment` manifest | month or `all`；`all` 是 fan-out command；SQL all 读取跨月物理行时必须按 `row_id` 去重后再计算 rows/summary/viewCounts |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| OA 待付款 rows/details | 前端页面 | fresh/status 可见 |
| 支出流水候选 rows | 前端右侧抽屉 | 输出分页后的全部支出流水候选，并由后端标注 `unmatched` / `matched` / `linked_in_progress` 分类；只有 `unmatched` 可被提交关联 |
| 关系 promotion/写回结果 | relation/downstream/frontend | 可审计、可恢复；返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`，目标覆盖 `oa_pending_payment` 与受影响 `workbench_relation` scope |
| Dirty scope | runtime queue | `oa_pending_payment.read_model.refresh` |

## 持久化与投影

- Read model：`oa_pending_payment`
- Projection：`scoped_incremental`；月份 refresh 必须使用月份 OA projection、context 级事实索引复用、payment-admitted 准入边界、批量支付状态 map 和 admitted OA record cache，避免同一 refresh 重复全量读取 completed OA、进项发票、支付状态表或 OA source adapter。
- Worker：`invoice-usage-collection`
- Query owner：`OaPendingPaymentReadModelService`
- Repository owner：`OaPendingPaymentReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/OaPendingPaymentsPage.tsx` |
| Frontend feature/components | `web/src/features/oaPendingPayments/*`、`web/src/components/oaPendingPayments/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py` |
| Backend service | `oa_pending_payment_service.py`、`oa_pending_payment_command_service.py`、`oa_pending_payment_relation_promotion_service.py`、`oa_pending_payment_read_model_*`、`oa_payment_*` |
| Repository / SQL | `oa_pending_payment_read_model_repository.py`、`postgres_repositories/oa_pending_payment_relation.py`、`invoice_usage_collection_sql_projection.py` |
| External/OA | `mongo_oa_adapter.py`、`oa_projection_sync.py` |
| Tests | `tests/test_oa_pending_payment*.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-*.spec.ts` |

## 依赖方向

- 允许依赖：OA projection adapter, bank relation services, invoice usage collection projection。
- 必须通过：OaPendingPayment command/read model service。
- 禁止绕过：直接操作数据库写回付款；恢复人工 `confirm-paid` route/command；直接读取 OA Mongo 作为页面 fresh payload。

## 测试与验证

- `tests/test_oa_pending_payment_api.py`
- `tests/test_oa_pending_payment_command_service.py`
- `tests/test_oa_projection_sql_runtime.py`
- `tests/test_invoice_usage_collection_sql_runtime.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`

## 当前缺口和删除条件

- 确认付款/撤回类变更必须通过业务 API 验证，不直接改数据库。
- 删除旧 projection/read 路径前必须验证 nonfresh、银行关联、确认付款恢复和 all-scope 去重；当前生产 rows/filter/detail API 不允许直接调用 live query fallback。

## Canonical facts ownership

- Owned facts: `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims`、`app.oa_pending_payment_bank_relation_events`。
- Allowed writes: OA pending payment relation service、明确 application/UoW boundary。
- Allowed reads: OA pending payment read/query ports、relation claim read ports。
- Downstream outputs: oa_pending_payment、bank_detail、turnover_ledger、workbench_relation dirty scopes 或 owner producer 输出。
- Forbidden paths: 其它模块不得直接 claim 银行流水关系；workbench relation migration 不得保留为 normal write path。
- Old code deletion: legacy workbench-pair based OA pending relation fallback、direct bank claim write 和 snapshot relation inference 必须删除；migration/audit/rollback 工具保留不算 closure。
