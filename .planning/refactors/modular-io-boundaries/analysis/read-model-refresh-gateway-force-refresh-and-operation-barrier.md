# Read Model Refresh Gateway Force Refresh And Operation Barrier

**日期:** 2026-06-23
**Boundary:** `read-models:refresh-gateway-force-refresh-and-operation-barrier`
**状态:** `closed-autonomous`
**范围:** 代码级 manifest contract guard；不改变 API shape、SQL、worker runtime、Go/Fiber、Go Worker 或生产状态。

## 执行结论

本轮先审阅了 `ReadModelRefreshGateway`、`OperationFreshnessBarrierService`、`read_model_slo_smoke`、operation barrier API、runtime dirty/outbox 入口和相关测试。当前代码已经具备三条关键边界：

- 非事务 read model refresh 通过 `ReadModelRefreshGateway` 做 scope normalize、validate、dedupe 和 active refresh coalescing，再委托 queue repository。
- `/api/operation-barrier/status` 只读 App Health runtime snapshot，把 read model readiness、dirty/outbox 和 worker 状态合成为 `fresh` / `refreshing` / `blocked`，不写状态、不重建 read model。
- 受控 force refresh 入口是 `read_model_slo_smoke` / deploy-control runbook；apply 时通过 `ReadModelRefreshGateway.enqueue_many_events(...)` 入队，并等待 outbox、dirty scope 和 readiness 收敛。

本轮补上的缺口是把 force refresh contract 和 operation barrier target contract 写入代码级 `READ_MODEL_MANIFEST`，并用 `tests/test_read_model_manifest.py` 守住：

- 每个 manifest entry 必须声明 force refresh 合同。
- 每个 manifest entry 必须声明 operation barrier 合同。
- operation barrier target 必须能从 `read_model_key` 推导到 manifest 对应的 `scope_type`。
- workbench 和 pending invoice 这类特殊 force refresh scope source 必须在 manifest 中显式分类。
- 每个 read model 的 refresh event 仍必须是 `{scope_type}.read_model.refresh`，由 gateway / queue / worker 使用同一 scope 语言。

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 模块类型: 共享边界 / 资源模块
- 本次改动类型: force refresh contract / operation barrier contract / manifest parity
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 read model freshness 语义: 否
- 是否改变 worker 投递或执行: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. 后端影响

| 层 | 是否影响 | 文件/符号 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| route / HTTP mapping | 否 | `/api/operation-barrier/status` 只读现状保持 | 无 shape 变化 | existing app-health / barrier tests |
| service | 是，静态只读合同 | `ReadModelManifestEntry.force_refresh_contract`、`operation_barrier_contract` | manifest 与 force refresh / barrier 入口漂移 | `tests/test_read_model_manifest.py` |
| repository / SQL | 否 | N/A | 不拆 `read_models.py` | N/A |
| transaction / UoW | 否 | N/A | 不写 dirty/outbox | N/A |
| worker | 否 | N/A | 不改消费者 | N/A |
| runbook / force refresh | 是，合同登记 | `read_model_slo_smoke.PAGE_FIRST_SCREEN_SCOPE_KEYS` | 特殊 scope source 漏登记 | manifest force refresh smoke contract test |

### 3. read model / worker 影响

| 项 | 是否影响 | 具体内容 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| refresh gateway | 否 | 现有 normalize/validate/dedupe/coalesce 保持 | 后续新增 read model 绕过 manifest | manifest parity tests |
| force refresh entry | 是，合同登记 | `gateway_force_refresh` / `gateway_force_refresh_active_generation_scope` / `gateway_force_refresh_with_page_first_screen_scope` | 特殊 page-first scope 或 active generation scope 未登记 | `test_manifest_declares_force_refresh_smoke_contract` |
| operation barrier | 是，合同登记 | `app_status_registry_target` | barrier target 与 read model scope 漂移 | `test_manifest_declares_operation_barrier_targets` |
| dirty scope / outbox | 否 | 不新增、不修改 | 无 | existing runtime queue tests |
| App Status | 否 | 仍由 registry/snapshot 提供事实 | 无 | existing parity tests |
| RabbitMQ / Redis | 否 | RabbitMQ 只 transport，Redis 只 fresh-gated cache | 无 | existing registry/env tests |

### 4. Legacy 退役与污染防护

| Legacy path | 当前状态 | 本轮处理 | 后续 |
| --- | --- | --- | --- |
| non-transactional direct refresh producer | 大多已通过 `ReadModelRefreshGateway`，调用点仍分散 | 本轮不移动调用点，只固化 force-refresh 合同 | 后续 page/module slice 收口 owner |
| transaction dirty/outbox writer | 允许作为 canonical writer 例外 | 本轮不改 | repository/UoW 边界单独处理 |
| operation barrier 前端自推 fresh | 不应存在 | 本轮以 manifest target 测试强化后端推导事实 | 页面切片继续检查 UI overlay |
| 生产 force refresh 临时脚本 | 不应绕过 gateway | 本轮以 `read_model_slo_smoke` 合同登记为唯一受控入口 | runbook 继续由 operations 文档管理 |

## 代码合同

`ReadModelManifestEntry` 新增字段：

- `force_refresh_contract`
- `operation_barrier_contract`

允许值：

- `force_refresh_contract`
  - `gateway_force_refresh`
  - `gateway_force_refresh_active_generation_scope`
  - `gateway_force_refresh_with_page_first_screen_scope`
- `operation_barrier_contract`
  - `app_status_registry_target`

特殊分类：

- `workbench`: force refresh smoke scope 来自 active generation / readiness direct scope。
- `pending_invoice`: force refresh smoke 额外覆盖页面首屏 aggregate scope，例如 `expense:all`。
- 其他 read model: 标准 gateway force refresh。

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改业务规则、状态转换、金额或权限决策 |
| 2. Service-layer tests | 适用 | manifest 强制登记 force refresh / operation barrier contract |
| 3. API contract tests | 不适用 | `/api/operation-barrier/status` shape 不变 |
| 4. Read model/cache/background job tests | 适用 | refresh event、force refresh smoke source、barrier target 与 manifest 绑定 |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不触发真实 worker 或生产写操作 |
| 7. Existing feature regression tests | 适用 | refresh gateway、operation barrier、SLO smoke 现有测试保持通过 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是代码/registry parity。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- Secret handling: 未读取、未记录 secret。

## 验收结果

- 14 个 App Status read model 都有 force refresh 合同和 operation barrier 合同。
- operation barrier target 能从 read model key 推导到对应 scope type。
- `read_model_slo_smoke` 的 page-first-screen 特殊 scope 已被 manifest 显式覆盖。
- Workbench active generation 特殊 force-refresh scope source 已被 manifest 显式覆盖。
- 目标测试集通过。

## 后续边界

下一步推进 `read-models:repository-port-and-sql-owner-split-plan`：

- owner-map `postgres_repositories/read_models.py` 中各 read model SQL owner。
- 明确 repository port 和 SQL ownership，先做分析和 guard，不一次性拆大文件。
- 删除或隔离可污染新链路的 legacy read path / live scan / direct refresh path。
