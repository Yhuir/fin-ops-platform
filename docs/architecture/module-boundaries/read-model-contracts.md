# Legacy Read Model 边界合同与下线清单

本文件记录页面级 read model 的 legacy 下线状态和不得恢复的边界。可执行事实源是 `backend/src/fin_ops_platform/services/read_model_manifest.py` 与 `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`：两者当前都必须为空 guard。

2026-06-26 起，目标架构改为页面 direct API，不再新增或扩展页面 read model。新的读路径目标见 `../direct-api-read-architecture.md`，GSD 实施计划见 `.planning/refactors/remove-read-models/`。本文档中的 manifest 表不再代表未来目标态，只用于确认哪些旧路径必须被 direct API 替换后才能删除。

扫描日期：2026-06-26。

## Legacy 约束

当前页面读取目标是 direct API。剩余 read-model 相关约束只作为删除和防回归规则：

- 不得新增页面 read model、freshness/status/enqueue 边界、page refresh worker、readiness proof 或 `.read_model.refresh` event。
- 不得把 Redis、RabbitMQ、App Status readiness 或旧 projection 状态作为页面可读证明。
- 写操作应返回业务状态、affected ids/months/source metadata 或 updated DTO，前端通过 direct API 重读。
- 真实异步任务只保留 import、OA sync、file migration、settings reset、Workbench matching 等后台任务；这些任务不是页面 read-model refresh worker。

迁移目标是继续删除历史 PSCIP/readiness/freshness 体系残留，而不是修复或扩展它。

## Manifest 合同表

| Read model | Scope | Projection | `all` 语义 | Partition / Scope 说明 | Worker | Query owner | Repository owner | 权限边界 | 核心测试 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 无 | 无 | 无 | 无 | `READ_MODEL_MANIFEST` 当前为空；页面级 active read-model worker/manifest/App Status lane 不得回流 | 无 | 页面 direct API | 无 | 各页面 session owner | `tests/test_read_model_manifest.py` |

`no_oa_bank_batch` read-model runtime 已删除；免 OA 页面当前由 `NoOaBankBatchApplicationService` / `NoOaBankBatchService` direct API 读取业务事实。

`cost_statistics` 与 `tax_offset` read-model worker lane 已删除；页面当前由 `CostStatisticsQueryService` / `TaxOffsetQueryService` direct API 读取业务事实，历史 SQL projection/repository 只作为兼容存储和受控清理对象。

`invoice_lifecycle` read-model worker lane、SQL projection、read facade、repository port 和 `read_model.invoice_lifecycle_rows/scopes` storage 已删除；待找发票、进项使用、销项收款、OA 待付款、税金和成本页面当前由各自 direct API 组装生命周期状态，写后直接重读页面业务 GET，不等待 `invoice_lifecycle.read_model.refresh`、dirty scope 或 readiness 收敛。

`workbench_relation` read-model worker lane 已删除；`WorkbenchRelationReadFacade` 在 app runtime 中优先通过 canonical `WorkbenchRelationCommandService` 读取 active relation facts 并组装 relation context，旧 SQL read-model repository 仅作为 legacy fallback。不得恢复 `workbench-relation` worker、manifest/App Status 绑定、deploy env 或 `workbench_relation.read_model.refresh` event。

`workbench` read-model worker lane 已删除；关联台页面、summary、groups、group-detail 和 row-detail 均不得依赖 `workbench.read_model.refresh`、`worker-workbench`、dirty scope、App Status read-model readiness 或 rehydrate/backfill 脚本。历史 `read_model.workbench_*` 存储只作为迁移/审计对象，不是 active page read model contract。

## 变更规则

- 不再新增页面 read model。确有历史生产修复必须临时触碰旧 read-model storage 时，必须同时记录 direct API 替代路径和删除条件。
- 不再修改页面 projection strategy 或 `all` refresh 语义；发现相关需求时应改 direct query/repository，而不是恢复 scope policy、dirty scope、worker registry 或 freshness/status 查询。
- 删除旧 read model 代码前，必须证明没有页面、API、worker、测试或生产脚本继续读取旧路径。
- `workbench` 的旧 active generation 原子发布模型已经从页面/worker lane 下线；不得以普通 gateway 或新 worker 形式恢复。
- `ReadModelRefreshGateway`、`RuntimeQueueRepository.enqueue_read_model_refresh(...)`、事务内 read-model refresh writer 和 dirty/readiness runtime tables 已删除；不得恢复。
- 真实 background outbox 写入必须使用对应业务 service/repository 边界，并有测试覆盖。

## 验收要求

Read model 下线或防回归变更完成前，至少要完成：

- manifest 与 App Status read-model registry 保持空。
- direct API 不返回 `read_model_status`、`refresh_enqueued`、scope key 或 stale reason。
- 页面能在写后通过 direct API 读取业务数据，或明确显示 direct payload error/unavailable。
- 相关旧链路没有继续被调用；旧代码若保留，必须有明确兼容理由和删除条件。
- 测试覆盖 negative guards、API contract、service orchestration、真实后台任务和受影响业务回归。

已下线 read model：`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`workbench_relation`、`workbench`。这些页面/API 现在通过各自 QueryService、direct Workbench API、import facts、OA projection、WorkbenchRelationReadFacade 和业务 repository 组装 payload；不得恢复 `invoice-usage-collection` worker、三类 `.read_model.refresh` event、repository port、projection builder、`workbench-relation`/`workbench` worker 或 read-model manifest/AppStatus registration。
