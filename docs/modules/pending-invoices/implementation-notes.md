# 待找发票 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 待找发票行状态由 `InvoiceLifecyclePolicy` / `invoice_lifecycle` read boundary 与 pending invoice read model 表达，页面不得在字段缺失时自行推断状态或 primary action。
- 支出规则版本是 `pending_invoice_tag_groups.version`，收入规则版本是 `pending_output_invoice_tag_groups.version`；二者独立，且都不同于 `bank_transaction_tags.version`。
- `requires_invoice` 是 active tag complement，由后端实时派生；保存规则时即使请求包含该字段也必须忽略。
- rows、filter-options、export-preview 和 export 必须先经过 `PendingInvoiceReadModelService` 的 freshness gate；非 fresh 时不能把空 rows 当真实结果。
- 2026-06-11 测试闭环审计确认：现有 P0/P1 覆盖支出/收入状态、规则保存、人工补票、attach existing、income status、API 契约、SQL read model、worker fan-out、lifecycle fan-out、App Status 和前端交互；本轮不新增重复代码测试，主要补齐模块测试矩阵和状态机文档。

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

## 2026-06-11 - 待找发票测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `pending-invoices` 模块轮次，确认新功能改动不会绕过规则版本、人工补票、选择已有发票、收入状态、read model freshness、invoice lifecycle 或页面交互回归保护。
- 影响范围：`docs/modules/pending-invoices/README.md`、`docs/modules/pending-invoices/tests.md`、`docs/modules/pending-invoices/state-machine.md`、`docs/modules/pending-invoices/implementation-notes.md`；未改变业务代码或测试代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖支出/收入待找发票状态、规则 active complement、支出/收入规则版本隔离、manual preview/confirm、attach existing preview/confirm、income status override、API shape、SQL read model fresh/stale/missing/source mismatch、worker scope fan-out、lifecycle fan-out、App Status 和前端 rules/detail/manual/attach/filter/refreshing 交互；本轮不新增重复测试。
- 文档影响：补齐模块必读事实源、代码入口、七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_search_pending_sql_runtime.py`、`tests/test_pending_invoice_relation_identity.py`、`tests/test_pending_invoice_oa_identity_backfill.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_pending_invoice_api tests.test_invoice_lifecycle_page_integration -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_pending_invoice_relation_identity tests.test_pending_invoice_oa_identity_backfill -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v`；`cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx`。
- 未测风险：未连接真实生产 Postgres 大数据量，不验证真实 SQL projection EXPLAIN、锁等待或长尾分页性能；未跑真实 RabbitMQ/Redis/systemd search-pending 与 invoice-lifecycle worker drain；未做真实浏览器大文件导出和网络中断恢复 smoke。
- 后续事项：下一轮处理 `oa-pending-payments`，重点审计 OA/bank/invoice detail、read model freshness、filter-options 和 invoice lifecycle fan-out。
