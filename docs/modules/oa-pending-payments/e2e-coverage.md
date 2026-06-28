
> 2026-06-28：invoice usage collection read model runtime 已下线；本文中旧 refresh/worker/port 名称仅作为历史迁移记录，不是当前运行合同。

# OA待付款核对 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的 OA 待付款 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `OA-PENDING-E2E-001` | `covered` | `web/e2e/oa-pending-payments-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx` | Browser 已覆盖 completed 视图首屏、四分组表格、无横向滚动和基本数据展示；也覆盖 rows 首屏暂时 503 时错误 alert、错误态空行、普通空态消失、显式刷新后 rows/pagination 恢复。 |
| `OA-PENDING-E2E-002` | `covered` | `web/e2e/oa-pending-payments-flow.spec.ts`、后端/API tests | Browser 已覆盖搜索、支付状态筛选、项目筛选、发票方筛选和交易时间排序进入 rows query。 |
| `OA-PENDING-E2E-003` | `covered` | `web/e2e/oa-pending-payments-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx` | Browser 已覆盖 OA/流水/发票详情 drawer 和规则 drawer；Vitest 覆盖规则保存成功后直接重新请求 rows，且不再请求 operation barrier。 |
| `OA-PENDING-E2E-004` | `covered` | `web/e2e/workbench-relations-candidate-semantics.spec.ts`、`tests/test_oa_pending_payment_api.py` | Browser 已证明 candidate relation 只展示证据，付款状态保持 `支付少了`，不产生自动写回 mutation。 |
| `OA-PENDING-E2E-005` | `covered` | `web/e2e/workbench-relations-oa-pending-fanout.spec.ts`、`web/e2e/fixtures/apiMocks.ts` | Browser 已证明 Workbench confirm 后返回 OA 待付款重新请求 rows，目标行变为 `已支付`，候选消失并显示 `关联台已确认`。 |
| `OA-PENDING-E2E-006` | `covered` | `web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py` | Browser 已覆盖进行中 OA 切换、页面级 auto-reconcile 单次请求、无人工写回按钮、rows 直接重新请求后 `已写回`、后端 409 失败可见且不半写；Vitest 锁定 auto-reconcile 成功后直接刷新 rows，且不再请求 operation barrier。真实 OA MySQL 写回和 direct rows 收敛仍归入 staging documented-risk。 |
| `OA-PENDING-E2E-007` | `covered` | `web/e2e/oa-pending-payments-bank-link-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_relation_read_facade.py` | Browser 已覆盖进行中 OA 勾选、关联支出流水抽屉已配对/已关联进行中 OA 禁选、relation_status 筛选、提交 body、rows 直接重新请求后 `已写回`、无人工写回按钮，以及 409 失败可见且不半写；Vitest/API/command 测试锁定抽屉候选请求携带已选 `oa_row_ids`，后端按 OA 月份收敛候选池且有 OA id 无月份时不退回全量历史扫描；后端测试锁定 link-bank 创建 OA 待付款独立 pending relation 和 bank claim，不写 Workbench active relation，并锁定 Workbench active generation 和 relation projection 排除 active pending bank claim；Vitest 锁定 link-bank 成功后直接刷新 rows，且不再请求 operation barrier。真实 OA/MySQL/direct rows 收敛仍归入 staging documented-risk。 |
| `OA-PENDING-E2E-008` | `covered` | `web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`、`web/e2e/oa-pending-payments-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | Browser 已覆盖 direct rows 首屏可见且没有页面级 read model 刷新诊断/轮询；Vitest 覆盖 direct rows 自动匹配、空 rows 显示真实空态；detail `detailAvailable=false` 时 drawer 显示“详情暂不可用”。真实 direct rows/detail 恢复仍归入 staging documented-risk。 |

## 下一轮补测建议

1. 补真实基础设施 smoke：真实 OA Mongo/MySQL、PostgreSQL、RabbitMQ/Redis 下的 rows/detail unavailable 恢复、auto-reconcile 写回、link-bank 自动写回闭环。
2. 继续补真实生产大数据、mutation 网络恢复和像素级视觉 smoke；本地 rows 首屏暂时失败恢复已覆盖。
