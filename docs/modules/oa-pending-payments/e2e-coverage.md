# OA待付款核对 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的 OA 待付款 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `OA-PENDING-E2E-001` | `covered` | `web/e2e/oa-pending-payments-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx` | Browser 已覆盖 completed 视图首屏、四分组表格、无横向滚动和基本数据展示；也覆盖 rows 首屏暂时 503 时错误 alert、错误态空行、普通空态消失、显式刷新后 rows/pagination 恢复。 |
| `OA-PENDING-E2E-002` | `covered` | `web/e2e/oa-pending-payments-flow.spec.ts`、后端/API tests | Browser 已覆盖搜索、支付状态筛选、项目筛选、发票方筛选和交易时间排序进入 rows query。 |
| `OA-PENDING-E2E-003` | `covered` | `web/e2e/oa-pending-payments-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx` | Browser 已覆盖 OA/流水/发票详情 drawer 和规则 drawer；Vitest 覆盖规则保存成功后等待 `oa_pending_payment` operation barrier，再刷新 rows。 |
| `OA-PENDING-E2E-004` | `covered` | `web/e2e/workbench-relations-candidate-semantics.spec.ts`、`tests/test_oa_pending_payment_api.py` | Browser/后端回归已证明未正式化 decision 或历史 candidate 兼容值不能驱动 `已支付`，不产生自动写回 mutation；只有 active linked relation 会进入已关联付款证据。 |
| `OA-PENDING-E2E-005` | `covered` | `web/e2e/workbench-relations-oa-pending-fanout.spec.ts`、`web/e2e/fixtures/apiMocks.ts` | Browser 已证明 Workbench confirm 后返回 OA 待付款重新请求 rows，目标行变为 `已支付`，候选消失并显示 `关联台已确认`。 |
| `OA-PENDING-E2E-006` | `covered` | `web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py` | Browser 已覆盖进行中 OA 切换、首屏不自动写、支付状态为 `已支付` 且写回状态为 `未写回` 时显示行内“写回”、点击后单次 `writeback-paid` 请求、rows/read model 重新请求后 `已写回` 并隐藏按钮、后端 409 失败可见且不半写；Vitest 锁定写回成功后等待 `oa_pending_payment` operation barrier 再刷新 rows。真实 OA MySQL/worker drain 仍归入 staging documented-risk。 |
| `OA-PENDING-E2E-007` | `covered` | `web/e2e/oa-pending-payments-bank-link-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_relation_sql_projection.py` | Browser 已覆盖进行中 OA 勾选、关联支出流水抽屉已配对/已关联进行中 OA 禁选、relation_status 筛选、提交 body、rows/read model 重新请求后 `已写回`、无人工写回按钮，以及 409 失败可见且不半写；Vitest/API/command 测试锁定抽屉候选请求携带已选 `oa_row_ids`，后端返回全部支出流水候选池并按全部、未配对、已配对、已关联进行中 OA 分类筛选；Vitest 锁定候选超过首屏时可分页浏览且翻页不丢 `oa_row_ids` / relation status；后端测试锁定 link-bank 创建 OA 待付款独立 pending relation 和 bank claim，不写 Workbench active relation，并锁定 Workbench active generation 和 relation projection 排除 active pending bank claim；Vitest 锁定 link-bank 成功后等待 `oa_pending_payment` operation barrier 再刷新 rows。真实 worker drain 仍归入 staging documented-risk。 |
| `OA-PENDING-E2E-008` | `covered` | `web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`、`web/e2e/oa-pending-payments-flow.spec.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | Browser 已覆盖 rows `refreshing` 不显示真实空态、不泄露 stale reason，以及 detail 202 时 drawer 显示“详情暂不可用”；也覆盖 rows 暂时 503 时错误态不伪空态、手动刷新恢复 fresh rows。真实 worker drain 仍归入 staging documented-risk。 |

## 下一轮补测建议

1. 补真实基础设施 smoke：真实 OA Mongo/MySQL、PostgreSQL、RabbitMQ/Redis 和 `invoice-usage-collection` worker drain 下的 rows/detail non-fresh 恢复、逐行 `writeback-paid` 写回、link-bank 自动写回闭环。
2. 继续补真实生产大数据、mutation 网络恢复和像素级视觉 smoke；本地 rows 首屏暂时失败恢复已覆盖。
