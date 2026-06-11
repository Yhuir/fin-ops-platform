# OA待付款核对 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- OA 待付款列表以 OA application 为主行；银行流水、进项发票和 relation 只是付款证据或详情证据。
- Workbench active relation 是 OA/支出流水/进项发票关联关系的唯一事实源；多 OA、流水或发票在同一 relation 中必须聚合成一条核对行，并通过 `relationCount`/`summaries` 展开详情。
- `paymentStatus` 由 `InvoiceLifecyclePolicy` / `OaPendingPaymentQueryService` 判定，前端不得按金额字段自行推断。
- `paymentStatus` 不输出 `overpaid` 或 `merged_paid`；支出流水合计大于 OA 合计进入 `pending_review`，多 OA 合并付款先按 relation group 合计后再判定。
- 生产 rows、filter-options 和 detail 必须走 `OaPendingPaymentReadModelService` 的 freshness/source-version gate；非 fresh 返回 refreshing/unavailable 并入队 `oa_pending_payment.read_model.refresh`，不能 live scan。
- `invoice-usage-collection` worker 同时负责 `input_invoice_usage`、`output_invoice_collection` 和 `oa_pending_payment` read model；OA all scope 只 fan-out month shards，不同步重建全量历史。
- pending invoice rules 对 OA 待付款的刷新当前由执行层 workbench invalidation 间接入队 invoice usage collection，已有 `tests/test_pending_invoice_api.py` 回归保护；dry-run plan 的 domain 名称不直观，暂记为 documented-risk。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-11 - OA待付款关联台分组关系闭环

- 目标：修复多条 OA/支出流水/进项发票在关联台已清晰配对时，OA 待付款页拆成多行并误显示“支付多了”或“多条OA合并支付”的问题。
- 影响范围：`InvoiceLifecyclePolicy`、`OaPendingPaymentQueryService`、OA pending payment read model detail builder、SQL projection 复用路径、`/api/oa-pending-payments/rows/{row_id}/relation-details`、`OaPendingPaymentsTable`、前端 OA pending payments 类型、模块/API 文档和相关测试。
- 关键决策：关联关系完全来自 Workbench active relation；同一 relation 下的 OA、有效 outflow 支出流水和进项发票分别汇总为一条核对行，列表只显示合计金额和 `+N`，点击 `+N` 分别以 `kind=oa|bank|invoice` 查看明细。
- 文档影响：更新模块状态机、测试矩阵、实施记录、产品口径和 API 合同。
- 测试覆盖：新增/更新 lifecycle policy、query service、API/read model detail、SQL projection runtime 和前端交互回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_invoice_lifecycle_policy tests.test_oa_pending_payment_api tests.test_invoice_usage_collection_sql_runtime -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未连接真实 OA/Mongo、生产 Postgres 大数据、真实 RabbitMQ/Redis/systemd worker drain 和真实浏览器截图 smoke。
- 后续事项：如需发布前进一步验证，使用截图中的真实月份在 staging 触发 relation 确认/撤回、`oa_pending_payment` scope refresh 和页面浏览器 smoke。

## 2026-06-11 - OA待付款测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `oa-pending-payments` 模块轮次，确认 OA 单据、支出流水、进项发票、Workbench relation、SQL read model、worker 和前端交互的回归保护。
- 影响范围：`docs/modules/oa-pending-payments/README.md`、`docs/modules/oa-pending-payments/tests.md`、`docs/modules/oa-pending-payments/state-machine.md`、`docs/modules/oa-pending-payments/implementation-notes.md`；未改变业务代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖付款状态、缺失证据、API shape、权限、read model freshness、detail stale/missing、SQL projection/repository、worker fan-out、App Status registry 和前端交互；本轮不新增重复测试。
- 文档影响：补齐模块必读事实源、代码入口、七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_invoice_lifecycle_page_integration -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/TableAlignmentStyles.test.ts`。
- 未测风险：未连接真实 OA/Mongo，不验证真实 OA sync 字段变体和权限菜单；未在真实生产 Postgres 跑大数据 EXPLAIN/锁等待/长分页；未跑真实 RabbitMQ/Redis/systemd `invoice-usage-collection` 与 `invoice-lifecycle` worker drain；未做真实浏览器大数据表格和网络中断 smoke。
- 后续事项：下一轮处理 `turnover-ledger`，重点审计手动闭环、extra、relation stale precondition、read model freshness 和前端筛选/抽屉交互。
