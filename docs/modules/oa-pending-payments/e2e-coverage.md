# OA 待付款核对 E2E Coverage

日期：2026-07-25

| Spec ID | 状态 | 自动化入口 | 说明 |
| --- | --- | --- | --- |
| `OA-PENDING-E2E-001` | covered | `oa-pending-payments-flow.spec.ts`、`OaPendingPaymentsPage.test.tsx` | 单一 rows首屏、四分组、summary/filter/paging；旧 filter请求为0 |
| `OA-PENDING-E2E-002` | covered | `oa-pending-payments-flow.spec.ts`、API/query tests | 搜索、筛选、排序、分页、view mode进入同一query |
| `OA-PENDING-E2E-003` | covered | `oa-pending-payments-flow.spec.ts`、`oa-pending-payments-nonfresh-flow.spec.ts` | details惰性加载与non-fresh不可用 |
| `OA-PENDING-E2E-004` | covered by component/API | `OaPendingPaymentsPage.test.tsx`、`test_oa_pending_payment_read_model_query.py` | fresh 后零常驻检查；ETag/304服务端合同保留；Playwright网络计数为补充证据 |
| `OA-PENDING-E2E-005` | covered locally | `oa-pending-payments-nonfresh-flow.spec.ts`、`OaPendingPaymentsPage.test.tsx` | 202 隐藏旧 rows、只通过当前 rows normal GET 收敛、operation barrier 为 0、fresh 重读；真实 worker 链待统一部署 |
| `OA-PENDING-E2E-006` | covered locally | `oa-pending-payments-confirm-paid-flow.spec.ts`、command/API/component tests、`tests/test_oa_pending_payment_source_snapshot_repository.py` | 写回成功/409失败、命令零页面 fan-out、本页 normal GET 新 rows；真实 MySQL+PG reconcile 待统一部署 |
| `OA-PENDING-E2E-007` | covered locally | `oa-pending-payments-bank-link-flow.spec.ts`、command/relation/Workbench tests、`tests/test_read_model_architecture_guards.py` | pending relation、候选限制、自动写回、Workbench/其它页面 queue 隔离 |
| `OA-PENDING-E2E-008` | covered by component | `OaPendingPaymentsPage.test.tsx` | hidden 停止且 visible 不自动恢复、unmount/query cancellation |
| `OA-PENDING-E2E-009` | covered by component/API | `OaPendingPaymentAuditIcon.test.tsx`、Audit repository/API tests | OA专属五态文案、issue samples、共享组件隔离 |

## 尚未完成的生产证据

- 真实 `PostgreSQL T0 -> durable queue -> oa-pending-payment worker -> browser T1` 至少200次样本。
- 1000次fresh API和1000次304样本，以及生产数据量 `EXPLAIN (ANALYZE, BUFFERS)`。
- OA sync全量回填、MySQL成功/PG失败故障演练、Page Audit最终pass。

这些证据因用户要求“所有 task 完成后统一部署”而有意延后；本地mock结果不能替代生产SLO。
