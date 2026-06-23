# Read Model Query Gateway Contract And Status Parity

**日期:** 2026-06-23
**Boundary:** `read-models:query-gateway-contract-and-status-parity`
**状态:** `closed-autonomous`
**范围:** 代码级 manifest/parity guard；不改变业务行为、API shape、SQL repository、worker runtime、Go/Fiber 或生产状态。

## 执行结论

本轮没有直接迁移页面 query path。现有代码已经有三类关键 guard：

- `ReadModelQueryGateway.load(...)` 调用必须传 `expected_source_versions` 或 `expected_schema_version`。
- direct `read_model_status=fresh` 必须进入架构 allowlist 分类。
- direct `source_version_mismatch_reasons(...)` 必须证明 expected contract 非空。

本轮补上的缺口是代码级 read model manifest。此前 14 个 read model 的 owner、scope、event、worker、query contract、projection strategy、`all` scope 语义和测试入口只分散在 App Status registry、runtime worker registry、scope policy、文档和规划分析中。现在 `read_model_manifest.py` 成为后续自动推进的共享合同清单，并由 `tests/test_read_model_manifest.py` 保证它与现有 registry/runtime 事实源一致。

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 模块类型: 共享边界 / 资源模块
- 本次改动类型: read model / worker registry parity / docs
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 read model freshness 语义: 否
- 是否改变 read model partition/scope/incremental projection 策略: 否，本轮只登记当前目标策略
- 是否改变权限或审计: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. 后端影响

| 层 | 是否影响 | 文件/符号 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| route / HTTP mapping | 否 | N/A | 无 API 行为变化 | N/A |
| application service | 否 | N/A | 无运行时调用变化 | N/A |
| domain service / policy | 是，静态只读合同 | `read_model_manifest.py` | manifest 与 registry 漂移 | `tests/test_read_model_manifest.py` |
| repository / SQL | 否 | N/A | 不拆 `read_models.py` | N/A |
| transaction / UoW | 否 | N/A | 不写 dirty/outbox | N/A |
| audit | 否 | N/A | 不新增审计事件 | N/A |
| permission | 否，登记 owner | manifest `permission_owner` | owner 字段漂移 | manifest owner 非空测试 |

### 3. read model / worker 影响

| 项 | 是否影响 | 具体内容 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| read_model_key | 是 | 14 个 App Status key 必须进入 manifest | 新增 key 漏登记 | manifest covers app status registry |
| scope_type/scope_key | 是 | manifest scope 与 scope policy registry parity | scope policy 漏登记 | manifest scope policy parity |
| source/schema version | 否 | 本轮不改 source/schema provider | 无 | 架构 guard 保持 |
| readiness/freshness | 是，合同登记 | `query_status_contract` 分类为 gateway/self-managed/active generation | 自管 freshness 未分类 | owner/allowed value 测试 |
| partition key / scope key | 是，目标策略登记 | projection strategy 与 `all` semantics | 后续迁移误用 `all` | allowed semantics 测试 |
| scoped incremental projection | 是，目标策略登记 | 只登记，不实现 | 文档漂移 | docs + manifest |
| dirty scope | 否 | 不写 queue | 无 | N/A |
| outbox event | 是，refresh event parity | event 必须存在于 worker/RabbitMQ/read_model_event_types | event 漏 worker/dispatch | manifest worker event test |
| worker registry | 是 | primary + auxiliary refresh worker 登记 | 多实例/组合 worker 漏登记 | auxiliary worker event test |
| Go Worker / Python Worker ownership | 否 | 全部保持现有 Python worker | 不进入 Go | N/A |
| App Status | 是 | manifest covers registry | registry/manifest 漂移 | manifest app status parity |
| Operation barrier | 否 | 不改变 barrier | 无 | existing tests |
| force refresh entry | 否 | 下一边界处理 | N/A | N/A |
| Redis/RabbitMQ behavior | 是，RabbitMQ dispatch parity | 只校验 dispatch event | dispatch 漏同步 | manifest worker event test |

### 4. 前端影响

无前端代码变化。页面继续消费现有 `read_model_status` / `refresh_enqueued` / operation barrier 行为。

### 5. Legacy 退役与污染防护

| Legacy path | 当前调用者 | 目标状态 | 删除/隔离证据 | 防污染测试 |
| --- | --- | --- | --- | --- |
| direct fresh/self-managed freshness paths | 多个 query service / legacy server path | compat-only until per-key migration | 本轮只通过 manifest 分类；不删除 | `tests/test_read_model_architecture_guards.py` |
| `read_models.py` shared repository | 各 read model query/save path | deferred to repository-port boundary | 本轮不拆 | 后续 `read-models:repository-port-and-sql-owner-split-plan` |
| direct dirty/outbox producer candidates | 事务内 writer / repository | deferred to legacy guards | 本轮不改写入 | existing architecture/runtime tests |

本轮没有新增旧路径，也没有让新链路调用旧 internals。manifest 会让后续删除/隔离旧路径时具备 read model key 级 owner 和测试入口。

## 代码合同

新增 `ReadModelManifestEntry` 字段：

- `key`
- `scope_type`
- `refresh_event_type`
- `primary_worker_instance`
- `auxiliary_refresh_worker_instances`
- `query_status_contract`
- `projection_strategy`
- `all_scope_semantics`
- `query_owner`
- `repository_owner`
- `permission_owner`
- `test_owner`

索引函数：

- `read_model_manifest_by_scope_type()`
- `read_model_manifest_by_refresh_event_type()`

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改业务规则、金额、状态转换或权限决策 |
| 2. Service-layer tests | 适用 | `tests/test_read_model_manifest.py` 覆盖 manifest 与 registry/worker/scope policy parity |
| 3. API contract tests | 不适用 | 无 HTTP/API shape 变化 |
| 4. Read model/cache/background job tests | 适用 | manifest 覆盖 read model key、refresh event、worker、RabbitMQ dispatch、scope policy |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不跨业务写链路、不触发 worker |
| 7. Existing feature regression tests | 适用 | `tests/test_runtime_worker_registry.py` 和 `tests/test_read_model_architecture_guards.py` 保持通过 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是代码/registry parity。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- Secret handling: 未读取、未记录 secret。

## 验收结果

- `READ_MODEL_MANIFEST` 覆盖所有 `APP_STATUS_READ_MODEL_REGISTRY` key。
- manifest 的 scope/event/primary worker 与 App Status registry 一致。
- manifest 的 refresh event 被 primary worker、auxiliary workers、RabbitMQ dispatch 和 `read_model_event_types()` 覆盖。
- manifest 的 scope type 与 `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY` 一致。
- manifest 的 query/status contract、projection strategy、`all` scope semantics 和 owner 字段已登记。

## 后续边界

下一步应推进 `read-models:refresh-gateway-force-refresh-and-operation-barrier`：

- force refresh 入口、allowed caller、scope source、dedupe、readiness proof。
- operation barrier target registry 与 manifest 对齐。
- 写操作 affected scopes 到 refresh gateway/barrier 的闭环。
- legacy direct refresh / direct dirty/outbox producer 的删除或 compat-only 隔离计划。
