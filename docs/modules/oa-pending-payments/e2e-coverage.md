# OA 待付款核对 E2E Coverage

日期：2026-07-27

| Spec ID | 状态 | 自动化入口 | 说明 |
| --- | --- | --- | --- |
| `OA-PENDING-E2E-001` | covered | `oa-pending-payments-flow.spec.ts`、`OaPendingPaymentsPage.test.tsx` | 单一 rows 首屏、summary/filter/paging；旧 filter 请求为 0 |
| `OA-PENDING-E2E-002` | covered | page/API/query tests | 搜索、筛选、排序、分页、view mode |
| `OA-PENDING-E2E-003` | covered | page tests、query service/API tests | details 惰性加载、missing/error |
| `OA-PENDING-E2E-004` | covered | `OaPendingPaymentsPage.test.tsx`、`oa-pending-payments-nonfresh-flow.spec.ts` | 页面保持打开后无后台请求；手工刷新无条件 header |
| `OA-PENDING-E2E-005` | covered | `OaPendingPaymentsPage.test.tsx`、`oa-pending-payments-nonfresh-flow.spec.ts` | loading/empty/error/manual refresh；response 无旧 runtime metadata |
| `OA-PENDING-E2E-006` | covered locally | confirm-paid flow、command/API/component tests | 写回、冲突、失败、写后 GET；真实 MySQL+PG 待统一验证 |
| `OA-PENDING-E2E-007` | covered locally | bank-link flow、command/relation tests | pending relation、claim、自动写回、冲突 |
| `OA-PENDING-E2E-008` | covered conditionally | `test_oa_pending_payment_postgres_integration.py` | active -> withdrawn 后 direct GET；需 `FIN_OPS_TEST_DATABASE_URL` |
| `OA-PENDING-E2E-009` | covered | `OaPendingPaymentAuditIcon.test.tsx` | 单次 Audit、中文文案、无 barrier |

## 尚未完成的生产证据

- 生产等量级 selector/hydrate `EXPLAIN (ANALYZE, BUFFERS)`。
- 1000 次 rows endpoint p50/p95/p99/error rate，覆盖 page size 20/50/100/200。
- 真实 active confirm/withdraw、pending link、promotion、MySQL paid writeback 后 normal GET 可见性。
- 当前环境未配置 disposable PostgreSQL 时，真实 SQL parse/plan 集成用例为 conditional skip。

这些证据由主控统一部署后执行；本地 mock 和静态 query-count guard 不能替代生产 SLO。
