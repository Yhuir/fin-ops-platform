# 代码扫描摘要 2026-06-22

**命令类型:** 静态扫描、文件行数、文本搜索、CodeGraph context
**修改业务代码:** 否

## Git 工作区状态

扫描时工作区已有未提交变更，集中在 workbench/OA projection 相关文件：

- `backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py`
- `backend/src/fin_ops_platform/services/workbench_amount_check_service.py`
- `backend/src/fin_ops_platform/services/workbench_query_service.py`
- `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- `docs/modules/oa-integration/implementation-notes.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/implementation-notes.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `tests/test_oa_projection_sync_service.py`
- `tests/test_workbench_amount_check_service.py`
- `tests/test_workbench_query_service.py`
- `tests/test_workbench_sql_runtime.py`
- `web/src/features/workbench/api.ts`
- `web/src/test/WorkbenchApi.test.ts`

这些变更未在本次任务中修改。本目录规划需要把它们视为用户已有重构/修复上下文，后续不得无意回滚。

## 环境约束补充

用户确认当前没有本地 `PGSQL_URL` 和 staging 数据库，只有 SSH 进入服务器的密码。后续重构计划必须把验证拆成：

- local static。
- local fake/stub。
- production read-only。
- production controlled-write。

任何真实 PostgreSQL/read model/worker/OA 链路验证都不能默认在本地闭环；也不能要求用户把 SSH 密码或任何 secret 粘贴到聊天、文档、脚本或测试中。

## CodeGraph 状态

CodeGraph 索引正常：

- Files indexed: 899
- Total nodes: 33630
- Total edges: 86070
- Languages: Python、TypeScript、TSX、JavaScript、YAML

## 后端最大文件

| 文件 | 行数 | 风险 |
| --- | ---: | --- |
| `backend/src/fin_ops_platform/app/server.py` | 22849 | legacy route/handler/dependency 中心 |
| `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` | 11329 | read model repository 高耦合中心 |
| `backend/src/fin_ops_platform/services/state_store.py` | 3732 | legacy state/snapshot 兼容中心 |
| `backend/src/fin_ops_platform/services/workbench_write_facade.py` | 3723 | workbench 写编排中心 |
| `backend/src/fin_ops_platform/services/pending_invoice_service.py` | 3688 | pending invoice 业务大 service |
| `backend/src/fin_ops_platform/services/etc_service.py` | 3413 | ETC 业务大 service |
| `backend/src/fin_ops_platform/services/mongo_oa_adapter.py` | 3155 | OA 外部适配大 service |
| `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py` | 2963 | turnover 写适配大 service |
| `backend/src/fin_ops_platform/services/bank_transaction_category_service.py` | 2705 | 银行分类规则大 service |
| `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py` | 2667 | no-OA 批次大 service |

## 前端最大文件

| 文件 | 行数 | 风险 |
| --- | ---: | --- |
| `web/src/test/apiMock.ts` | 7672 | mock contract 过大，API shape 变更容易扩散 |
| `web/src/test/EtcTicketManagementPage.test.tsx` | 4417 | 大型页面测试，维护成本高 |
| `web/src/features/workbench/api.ts` | 3424 | workbench API client 高耦合 |
| `web/src/pages/EtcTicketManagementPage.tsx` | 3129 | ETC 页面状态/交互复杂 |
| `web/src/pages/BankDetailsPage.tsx` | 2822 | 银行明细页面状态/交互复杂 |
| `web/src/pages/ReconciliationWorkbenchPage.tsx` | 2705 | 关联台页面状态/交互复杂 |
| `web/src/test/WorkbenchApi.test.ts` | 2682 | workbench API 测试较大 |
| `web/src/test/WorkbenchSelection.test.tsx` | 2425 | 选择行为测试较大 |
| `web/src/pages/CostStatisticsPage.tsx` | 2209 | 成本统计页面状态复杂 |

## route module 行数

| 文件 | 行数 |
| --- | ---: |
| `routes_turnover_ledger.py` | 602 |
| `routes_output_invoice_collections.py` | 373 |
| `routes_bank_details.py` | 254 |
| `routes_no_oa_bank_batches.py` | 246 |
| `routes_pending_invoices.py` | 245 |
| `routes_cost_statistics.py` | 242 |
| `routes_etc.py` | 220 |
| `routes_tax.py` | 177 |
| `routes_oa_pending_payments.py` | 95 |
| `routes_workbench.py` | 47 |

说明：

- route modules 已存在。
- 但 `server.py` 仍保留大量 dispatch 和 handler，说明 route migration 未闭环。

## 关键边界信号

### service 与 HTTP

扫描未发现 service 大范围直接 import Flask 或 `app.auth`。这是正向信号。

### read model refresh

大量服务直接实例化 `ReadModelRefreshGateway`。这不一定违规，但必须进入登记表，明确 owner/scope/reason/事务边界。

### direct dirty/outbox SQL

扫描显示 direct dirty/outbox 写入主要集中在 repository/runtime queue/repair 工具和测试；后续仍需逐模块确认这些写入是否符合事务内 writer 合同。

## 规划结论

当前系统不是没有模块化，而是处于“半模块化、合同不完整、回归闸门不够硬”的阶段。下一步应该先做模块 IO 合同试点，而不是开始全局拆文件。
