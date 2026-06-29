# OA待付款核对模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：OA 待付款页面读取 `oa_pending_payment` read model；确认付款、银行关联、OA 状态同步通过 command/service 边界触发 scoped refresh。
- 当前缺口：OA Mongo、银行关联、invoice usage collection 和 relation promotion 依赖较多，变更必须覆盖生产级写后恢复。
- 旧代码删除条件：旧 OA projection/read path 不再被 API 直接调用，nonfresh e2e 和 API tests 通过。

## 职责边界

### 负责

- OA 待付款核对页面、银行关联、确认付款、状态展示和 OA projection read model。
- `oa_pending_payment` read model。
- OA 付款关系 promotion 和银行流水匹配入口。

### 不负责

- 不拥有 OA 登录/菜单权限事实。
- 不直接维护银行明细 read model。
- 不替代 workbench relation 事实源。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/过滤 | `OaPendingPaymentsPage.tsx`、`features/oaPendingPayments/api.ts` | 进入 read model service/fresh gate |
| 确认付款/银行关联 | command service | 写操作必须审计并触发 read model scopes |
| OA projection sync | OA sync/projection services | 输入必须带 source version |
| Refresh scope | `oa_pending_payment` manifest | month or `all`；`all` 是 fan-out command |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| OA 待付款 rows/details | 前端页面 | fresh/status 可见 |
| 关系 promotion/确认付款结果 | relation/downstream/frontend | 可审计、可恢复；返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`，目标覆盖 `oa_pending_payment` 与受影响 `workbench_relation` scope |
| Dirty scope | runtime queue | `oa_pending_payment.read_model.refresh` |

## 持久化与投影

- Read model：`oa_pending_payment`
- Projection：`scoped_incremental`
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
- 禁止绕过：直接操作数据库确认付款；直接读取 OA Mongo 作为页面 fresh payload。

## 测试与验证

- `tests/test_oa_pending_payment_api.py`
- `tests/test_oa_pending_payment_command_service.py`
- `tests/test_oa_projection_sql_runtime.py`
- `web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`

## 当前缺口和删除条件

- 确认付款/撤回类变更必须通过业务 API 验证，不直接改数据库。
- 删除旧 projection 路径前必须验证 nonfresh、银行关联和确认付款恢复。

## Canonical facts ownership

- Owned facts: `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims`、`app.oa_pending_payment_bank_relation_events`。
- Allowed writes: OA pending payment relation service、明确 application/UoW boundary。
- Allowed reads: OA pending payment read/query ports、relation claim read ports。
- Downstream outputs: oa_pending_payment、bank_detail、turnover_ledger、workbench_relation dirty scopes 或 owner producer 输出。
- Forbidden paths: 其它模块不得直接 claim 银行流水关系；workbench relation migration 不得保留为 normal write path。
- Old code deletion: legacy workbench-pair based OA pending relation fallback、direct bank claim write 和 snapshot relation inference 必须删除；migration/audit/rollback 工具保留不算 closure。
