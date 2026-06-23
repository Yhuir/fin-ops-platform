---
phase: quick
plan: 260623-pim-pending-invoices-multi-relation-display
type: execution-summary
status: implemented
completed_at: 2026-06-23
---

# 待找发票多关系成员 `+N` 展示闭环总结

## 已完成

- 确认待找发票已接入统一 `workbench_relation` / Workbench canonical relation 事实源；本轮没有新增页面私有事实源。
- rows 新增 `bank_transactions` 分区，和既有 `input_invoices`、`oa` 一起表达 relation members、count、summary 和 detail mode。
- Query service fallback 与 SQL projection 都会把同一多流水 relation 折叠为一条待找发票行，避免其它流水成员再作为 standalone 行重复出现。
- 前端表格在 OA、流水或发票分区 count > 1 时只显示代表全部成员的 `+N`，不再同时展示 primary 成员。
- 点击 `+N` 时按 `kind=bank|invoice|oa` 打开对应类型明细；后端 relation detail 也支持同一 `kind` 参数过滤。
- 同步更新产品/API/模块状态机/测试矩阵/实施记录文档。

## 测试覆盖

- `tests/test_pending_invoice_service.py`
  - 多流水 relation 聚合为一行。
  - relation detail `kind=invoice|bank|oa` 服务端过滤。
- `tests/test_search_pending_sql_runtime.py`
  - SQL projection 多流水 relation 成员去重和 grouped row payload。
  - pending invoice source version helper 跟随生产 `OA_PROJECTION_SYNC_VERSION` 常量。
- `web/src/test/PendingInvoicesApi.test.ts`
  - `bank_transactions` 到 `bankTransactions` mapper。
- `web/src/test/PendingInvoicesPage.test.tsx`
  - 多项 `+N` 显示、primary 去重、分类型 drawer 展开。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests.test_relation_detail_uses_workbench_relation_distribution_for_oa_attachment_invoices -v
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests.test_list_rows_collapses_multi_bank_relation_into_one_grouped_row tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_pending_invoice_sql_projection_collapses_multi_bank_relation_members -v
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_search_pending_sql_runtime tests.test_pending_invoice_api -v
cd web && npm test -- --run src/test/PendingInvoicesPage.test.tsx -t "opens relation"
cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx
cd web && npm run build
bash scripts/verify.sh docs
git diff --check -- backend/src/fin_ops_platform/app/routes_pending_invoices.py backend/src/fin_ops_platform/services/pending_invoice_service.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py tests/test_pending_invoice_service.py tests/test_search_pending_sql_runtime.py web/src/features/pendingInvoices/types.ts web/src/features/pendingInvoices/api.ts web/src/components/pendingInvoices/PendingInvoicesTable.tsx web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx web/src/pages/PendingInvoicesPage.tsx web/src/test/PendingInvoicesApi.test.ts web/src/test/PendingInvoicesPage.test.tsx docs/product-specs/invoice-lifecycle.md docs/dev/api-contracts.md docs/modules/pending-invoices/README.md docs/modules/pending-invoices/state-machine.md docs/modules/pending-invoices/tests.md docs/modules/pending-invoices/implementation-notes.md .planning/quick/260623-pim-pending-invoices-multi-relation-display/GOAL_PROMPT.md .planning/quick/260623-pim-pending-invoices-multi-relation-display/PLAN.md .planning/quick/260623-pim-pending-invoices-multi-relation-display/SUMMARY.md
```

## 未测风险

- 本地未跑真实 Browser E2E 和真实 Postgres/RabbitMQ/Redis/systemd worker drain。
- 如果生产存在同一 relation 横跨多个 month shard 的多流水场景，仍需 staging 样本验证聚合行 owner month 选择，必要时补 owner 规则。
- 导出是否完全镜像 grouped row 明细拼接仍建议后续在导出专项里补测试。
