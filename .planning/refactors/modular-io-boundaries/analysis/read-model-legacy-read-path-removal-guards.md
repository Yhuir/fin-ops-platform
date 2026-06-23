# Read Model Legacy Read Path Removal Guards

**日期:** 2026-06-23
**Boundary:** `read-models:legacy-read-path-removal-guards`
**状态:** `closed-autonomous`
**范围:** 新增 direct read model refresh enqueue 静态分类守卫；不改 runtime 行为、不删除业务路径、不改 SQL、worker、route、API shape、前端、Go/Fiber、Go Worker 或生产状态。

## 执行结论

本轮审阅了 read-models 模块文档、状态机、测试矩阵、前序 query gateway / refresh gateway / search+no-OA analysis，并通过 CodeGraph/AST 搜索检查：

- `ReadModelRefreshGateway`
- `ReadModelQueryGateway`
- `RuntimeQueueRepository.enqueue_read_model_refresh`
- direct `read_model_status=fresh`
- direct `source_version_mismatch_reasons(...)`
- direct `enqueue_read_model_refresh(...)`
- direct SQL touch points for `job.outbox_events` / `job.read_model_dirty_scopes`

现有架构守卫已经覆盖：

- `ReadModelQueryGateway.load(...)` call site 必须声明 expected source/schema contract。
- direct `read_model_status=fresh` 必须进入 allowlist 分类。
- direct `source_version_mismatch_reasons(...)` 必须证明 expected contract 非空。

本轮补齐缺口：direct `enqueue_read_model_refresh(...)` call site 必须被静态分类。当前仅允许以下受控路径：

- `Application._enqueue_cost_statistics_read_model_refresh`
- `Application._enqueue_tax_offset_read_model_refresh`
- `CostStatisticsQueryService.get_explorer`
- `CostStatisticsRuntimeService.enqueue_refresh_for_months`
- `TaxOffsetQueryService.get_month_payload`
- `TaxOffsetRuntimeService.enqueue_refresh_for_months`

这些路径都属于 legacy/app wrapper 或 runtime service wrapper，并最终委托 `ReadModelRefreshGateway` normalize/validate/dedupe/coalesce 后再触达 queue repository。以后新增非 gateway 的直接 enqueue call site 会让 `tests/test_read_model_architecture_guards.py` 失败，必须先删除、迁移到 gateway，或登记为有 owner/reason 的 compat-only wrapper。

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 子边界: legacy read path / direct refresh enqueue contamination guard
- 本次改动类型: static architecture guard
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 SQL 查询或写入: 否
- 是否改变 worker refresh: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. Legacy 分类

| Path | 分类 | owner | 删除条件 | 禁止事项 |
| --- | --- | --- | --- | --- |
| `Application._enqueue_cost_statistics_read_model_refresh` | compat-only app wrapper | cost statistics legacy route owner | route extraction 后删除 app wrapper | 不得直接写 dirty/outbox |
| `Application._enqueue_tax_offset_read_model_refresh` | compat-only app wrapper | tax offset legacy route owner | route extraction 后删除 app wrapper | 不得直接写 dirty/outbox |
| `CostStatisticsQueryService.get_explorer` | production repository miss wrapper | cost statistics query owner | cost query fully on gateway/query service contract 后可内联 gateway | 不得绕过 scope policy |
| `CostStatisticsRuntimeService.enqueue_refresh_for_months` | runtime cache invalidation wrapper | cost statistics runtime owner | cost runtime wrapper 被统一 refresh gateway adapter 替代 | 不得直接调用 queue repository |
| `TaxOffsetQueryService.get_month_payload` | production repository miss wrapper | tax offset query owner | tax query fully on gateway/query service contract 后可内联 gateway | 不得绕过 scope policy |
| `TaxOffsetRuntimeService.enqueue_refresh_for_months` | runtime cache invalidation wrapper | tax offset runtime owner | tax runtime wrapper 被统一 refresh gateway adapter 替代 | 不得直接调用 queue repository |

## State Machine Impact

- 全局工作流状态: `AutonomousContinue`，当前执行状态为 `autonomous-continue-after-search-and-no-oa-bank-batch-contract`。
- 选中边界进入前状态: `read-models:legacy-read-path-removal-guards` 为 `pending`。
- 已审阅状态机文件:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `docs/modules/read-models/state-machine.md`
- 全局状态机定义: definition unchanged。本轮未新增、重命名或改变 workflow state、transition、guard、stop/defer condition 或 completion criterion；只推进单个 queue boundary 从 `pending` 到 `closed-autonomous`。
- 模块状态机定义: definition unchanged。本轮新增静态污染防护测试，不改变业务状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态定义。
- 成功流转: `pending` -> `closed-autonomous`，自动执行状态更新为 `autonomous-continue-after-legacy-read-path-removal-guards`。
- defer/block 流转: 若静态 guard 发现未分类 direct enqueue 且无法安全分类/迁移，应记录 `deferred-module-failure`；若需要生产写或敏感凭据，应记录 `needs-human-production-gate`。本轮未触发。
- 完成时必须更新: 本 analysis、`tests/test_read_model_architecture_guards.py`、read-models tests/implementation notes、`autonomous/STATE.md`、`autonomous/MODULE-QUEUE.md`、`autonomous/JOURNAL.md`、`autonomous/NEXT-PROMPT.md`。

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改业务规则、金额、状态转换或权限判断 |
| 2. Service-layer tests | 适用 | `test_direct_read_model_refresh_enqueue_calls_are_classified` 锁定 service/app wrapper 的 direct enqueue 分类 |
| 3. API contract tests | 不适用 | 无 HTTP/API shape 变化 |
| 4. Read model/cache/background job tests | 适用 | 静态 guard 防止新增非 gateway refresh producer 绕过 scope policy/gateway |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不触发真实写入、worker 或跨页面刷新 |
| 7. Existing feature regression tests | 适用 | 既有 direct fresh、source mismatch、query gateway expected-contract guards 继续通过 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是静态架构守卫。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- 敏感凭据处理: 未读取、未记录凭据。

## 后续边界

下一步推进 `reconciliation-workbench:amount-check-query-contract`：

- 聚焦 Workbench matching/grouping/check 读侧和计算合同。
- 只做窄范围 amount-check query/compute boundary guard 或 analysis，不做全量 Workbench rewrite，不进入 Go/Fiber 实现，除非后续 Go admission gates 明确通过。
