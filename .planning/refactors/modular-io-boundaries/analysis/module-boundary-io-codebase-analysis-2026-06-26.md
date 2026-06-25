# GSD 全量分析：模块边界与 I/O 文档补齐

日期：2026-06-26

## 范围

本轮 GSD 分析用于补齐 `docs/modules/*/boundary-io.md`。分析覆盖：

- `docs/modules/README.md` 中登记的 29 个模块。
- 后端 route：`backend/src/fin_ops_platform/app/routes_*.py`、`server.py`、`worker.py`。
- 后端 service/repository/read model/worker：`backend/src/fin_ops_platform/services/`。
- 前端 page/feature/context/component：`web/src/pages/`、`web/src/features/`、`web/src/components/`、`web/src/contexts/`。
- 测试：`tests/`、`web/src/test/`、`web/e2e/`。
- 现有 read model manifest、scope policy、refresh gateway 和 runtime worker registry。

## 分析方法

- 使用 CodeGraph 确认索引健康：1065 files、36644 nodes、91657 edges。
- 使用 CodeGraph 读取 `READ_MODEL_MANIFEST`、`ReadModelScopePolicyRegistry`、`ReadModelRefreshGateway` 和 manifest 测试合同。
- 解析 `docs/modules/*/README.md` 的“代码入口”作为每个模块的既有文件范围事实基础。
- 对 read model 模块，以 `docs/architecture/module-boundaries/read-model-contracts.md` 和 manifest 合同为准。
- 对非 read model 或部分重构模块，文档标记为 `partial` 或 `legacy`，不伪装成完成态。

## 模块覆盖

本轮补齐 29 个模块的 `boundary-io.md`：

- 页面模块：关联台、税金抵扣、成本统计、银行明细、待找发票、进项发票使用情况、OA待付款核对、销项发票收款情况、免OA流水批量处理、批量账务、外部往来款管理、ETC票据管理、设置、系统状态、三类导入页。
- 资源模块：关联台关系事实源、银行账户余额、搜索索引、Read Model、Runtime Worker、Domain Events 与 Derived Lifecycle、App Shell 与导航、Finance Table System、部署、OA 集成、数据安全与重置、权限与审计。

## Read Model 结论

已确认 manifest 覆盖 14 个 read model：

- `workbench`
- `workbench_relation`
- `bank_detail`
- `bank_account_balance`
- `pending_invoice`
- `search`
- `invoice_lifecycle`
- `input_invoice_usage`
- `output_invoice_collection`
- `oa_pending_payment`
- `cost_statistics`
- `tax_offset`
- `no_oa_bank_batch`
- `turnover_ledger`

所有 read model 均已登记 projection strategy、`all` 语义、partition/scope 合同、query owner、repository owner、permission owner 和核心测试入口。后续实现必须继续以 Partitioned + Scoped + Incremental Projection 为目标；特殊例外仅以 manifest 和 `read-model-contracts.md` 为准。

## 关键边界结论

- `server.py` 仍是依赖组装和部分历史入口；新增业务逻辑不应继续堆在 `server.py`。
- route owner 已拆为多个 `routes_*.py`，页面/API 模块应优先通过 route owner 暴露 HTTP 边界。
- service/facade/gateway 负责业务编排；repository/postgres store 负责 SQL 与持久化细节。
- read model refresh 的非事务入口必须走 `ReadModelRefreshGateway` 和 scope policy registry。
- worker 合同以 `runtime_worker_registry.py` 和 `docs/operations/runtime-worker-governance.md` 为准。
- 前端页面以 `web/src/pages/*Page.tsx` + `web/src/features/<feature>/api.ts` + 相关 components/contexts 形成 UI/API 边界。

## 文档策略

每个 `boundary-io.md` 都必须包含：

- 模块化状态：`completed` / `partial` / `legacy` / `unknown`。
- 当前边界可信度。
- 负责/不负责。
- 输入 I/O、输出 I/O。
- 持久化、read model、worker 或明确“不拥有”。
- 文件范围。
- 依赖方向和禁止绕过。
- 测试与验证入口。
- 当前缺口和旧代码删除条件。

对未完成模块，文档是迁移合同，不是完成证明。
