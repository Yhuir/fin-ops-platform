# 当前代码边界审计

**审计日期:** 2026-06-22
**审计类型:** 规划前静态扫描
**是否修改业务代码:** 否

## 审计范围

本次只做全局重构前的轻量体检，目标是识别规划必须覆盖的热点，不判定每一处代码是否错误。

读取和扫描范围包括：

- `AGENTS.md`
- `.planning/README.md`
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`
- `backend/src/fin_ops_platform/app/`
- `backend/src/fin_ops_platform/services/`
- `backend/src/fin_ops_platform/services/postgres_repositories/`
- `web/src/features/`
- `web/src/pages/`
- `web/src/components/`
- `docs/modules/`

## 已有基础

当前代码并非完全没有模块化，已有基础包括：

- 后端已有多个 route module: `routes_bank_details.py`、`routes_cost_statistics.py`、`routes_etc.py`、`routes_no_oa_bank_batches.py`、`routes_oa_pending_payments.py`、`routes_output_invoice_collections.py`、`routes_pending_invoices.py`、`routes_tax.py`、`routes_turnover_ledger.py`、`routes_workbench.py`。
- 后端已有大量 application service、domain service、read facade、read model refresh service、runtime worker 和 repository。
- 前端已有 `features/*/api.ts` 和 `features/*/types.ts` 的模块化入口。
- `docs/modules/` 已覆盖主要页面模块和资源模块，且大多数模块具备 state machine、tests、e2e spec 和 implementation notes。
- service 中未发现大范围直接 import Flask 或 `app.auth` 的明显违规信号。
- `ReadModelRefreshGateway` 已存在，并被多个服务使用。

## 高风险热点

### H-01: `server.py` 仍是最大中心

扫描结果：

- `backend/src/fin_ops_platform/app/server.py`: 约 22849 行。
- 文件内仍有大量 `/api/*` route dispatch 和 `_handle_api_*` handler。
- 虽然多个 `routes_*.py` 已存在，但 `server.py` 仍承担大量路由分发、依赖组装和 legacy handler。

风险：

- route owner 不清晰。
- 新旧入口并存，容易导致同一业务行为有多个响应路径。
- 修改一个模块时可能误触共享 helper、shared dependency 或 legacy handler。

规划要求：

- 每个模块合同必须列出 canonical route module 和 legacy server.py handler 状态。
- 后续重构必须按模块小步迁移，不能直接全局清理 `server.py`。

### H-02: read model repository 过大

扫描结果：

- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`: 约 11329 行。
- 是 repository 层最大文件，可能承载多个 read model 的 SQL、metadata、freshness、dirty/readiness 逻辑。

风险：

- 多个 read model 的 SQL 和状态更新耦合在同一文件。
- 小改动可能影响多个页面或 App Status。
- 事务、source version、schema version 和 freshness proof 容易被重复实现。

规划要求：

- 每个 read model owner 必须登记 key、scope、builder、refresh service、repository 方法和 readiness proof。
- 拆分前先写合同和测试，不能先机械拆文件。

### H-03: 多个 service 文件仍然过大

扫描显示以下文件超过 2000 行：

- `workbench_write_facade.py`: 约 3723 行。
- `pending_invoice_service.py`: 约 3688 行。
- `etc_service.py`: 约 3413 行。
- `mongo_oa_adapter.py`: 约 3155 行。
- `turnover_ledger_write_adapters.py`: 约 2963 行。
- `bank_transaction_category_service.py`: 约 2705 行。
- `no_oa_bank_batch_service.py`: 约 2667 行。
- `runtime_monitoring.py`: 约 2275 行。
- `app_settings_service.py`: 约 2063 行。

风险：

- service 可能同时承担 command、query、policy、projection、export、audit 或 compatibility 责任。
- 单个 service 的构造依赖和副作用过多，重构风险难以评估。

规划要求：

- 每个大 service 先做责任切片分析。
- 只在测试覆盖足够时迁移调用点。
- 禁止为了行数拆分而增加无意义 wrapper。

### H-04: read model refresh 调用点分散

扫描发现多个位置直接实例化 `ReadModelRefreshGateway`，包括但不限于：

- `bank_details_application_service.py`
- `cost_statistics_runtime_service.py`
- `cost_statistics_read_model_refresh.py`
- `invoice_lifecycle_read_facade.py`
- `invoice_usage_collection_read_model_refresh.py`
- `no_oa_bank_batch_application_service.py`
- `oa_pending_payment_read_model_service.py`
- `output_invoice_collection_lifecycle_service.py`
- `output_invoice_collection_receipt_service.py`
- `pending_invoice_read_model_service.py`
- `tax_offset_runtime_service.py`
- `workbench_read_model_refresh.py`
- `workbench_relation_read_facade.py`
- `workbench_relation_read_model_refresh.py`
- `oa_projection_sync.py`

风险：

- gateway 使用本身不一定错误，但调用点过多会让 scope normalize、dedupe、reason、source version、operation barrier 影响难以集中审计。
- 业务 service 和 read model refresh service 的边界需要明确。

规划要求：

- 每个调用点必须登记 owner、scope_type、scope_key 规则、reason、事务边界、是否允许非事务 enqueue。
- 新增调用点必须通过模块 IO 合同和测试。

### H-05: 事务内 dirty/outbox 写入需要明确授权

扫描结果显示，dirty/outbox 直接 SQL 写入集中在 repository/runtime queue/contract repair 等区域：

- `RuntimeQueueRepository` 是标准队列边界。
- `postgres_repositories/workbench_relation.py` 存在事务内写入。
- `postgres_repositories/read_models.py` 存在 read model 相关写入。
- `read_model_scope_contracts.py` 存在 repair/cleanup 语义。

风险：

- 事务内 writer 可以是合法路径，但必须有等价 scope contract。
- 如果业务 service 绕过 gateway 直接写 SQL，会破坏统一边界。

规划要求：

- 允许清单和禁止清单必须写入 `05-IMPACT-AND-TEST-GATES.md`。
- 每次新增事务内 dirty/outbox 写入必须配套 contract test。

### H-06: 前端 feature 已拆分，但页面仍较大

扫描显示以下前端文件较大：

- `web/src/features/workbench/api.ts`: 约 3424 行。
- `web/src/pages/EtcTicketManagementPage.tsx`: 约 3129 行。
- `web/src/pages/BankDetailsPage.tsx`: 约 2822 行。
- `web/src/pages/ReconciliationWorkbenchPage.tsx`: 约 2705 行。
- `web/src/pages/CostStatisticsPage.tsx`: 约 2209 行。

风险：

- 页面同时承担 fetching、view model、操作编排、dialog/drawer 状态、operation barrier 和 domain event 发射。
- API client 过大时，API response shape 变化容易影响多个组件。

规划要求：

- 每个前端模块合同必须列出 page owner、feature API、types、domain events、operation barrier usage、loading/error/stale/refreshing 状态。
- 拆前先补组件/交互测试，不先抽组件。

### H-07: 模块文档已经完整，适合作为长期落点

扫描显示 `docs/modules/` 下主要模块均已有：

- `README.md`
- `state-machine.md`
- `tests.md`
- `e2e-spec.md`
- `e2e-coverage.md`
- `implementation-notes.md`

机会：

- 不需要另建长期事实源格式。
- 可以在试点通过后，把模块 IO 合同长期沉淀到对应模块目录。

规划要求：

- 本目录先设计模板。
- 真正改模块时，同步更新 `docs/modules/<module>/`，而不是只更新 `.planning/`。

## 当前未完成判断

根据本次扫描，已有部分重构方向是正确的：route modules、application services、read model gateway、module docs 都已经存在。

但还不能认为“全局模块化 IO 闭环”已经完成，原因是：

- 模块 IO 合同不是统一必填项。
- `server.py` 仍是大规模 legacy 入口。
- `read_models.py` 仍是 read model 高耦合中心。
- 多个大 service 的职责边界尚未完全可审计。
- read model refresh 调用点虽大多使用 gateway，但缺少统一登记和模块级验收。
- 每次改动的影响分析和七类测试映射还没有被固化成模块闸门。

## 后续审计任务

- [ ] 为试点模块建立完整 IO 合同。
- [ ] 列出试点模块所有 route/API/service/repository/read model/worker/frontend entry。
- [ ] 列出试点模块所有 dirty/outbox/read model refresh 调用点。
- [ ] 列出试点模块所有 operation barrier 和 frontend domain event。
- [ ] 列出试点模块所有权限动作和审计事件。
- [ ] 按七类测试补齐测试合同。
- [ ] 确认 legacy path 迁移/保留/删除规则。

