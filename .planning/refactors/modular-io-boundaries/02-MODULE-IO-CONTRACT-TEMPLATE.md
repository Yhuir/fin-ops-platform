# 模块 IO 合同模板

**用途:** 每个纳入模块化 IO 重构的模块必须按此模板填写。
**落点:** 试点阶段可先写在 `.planning/refactors/modular-io-boundaries/analysis/`；一旦进入实现，应同步到 `docs/modules/<module>/`。

## 模块基本信息

| 字段 | 内容 |
| --- | --- |
| Module key |  |
| 模块名称 |  |
| 模块类型 | 页面模块 / 资源模块 / 共享运行时模块 |
| Route |  |
| 前端入口 |  |
| 后端入口 |  |
| 文档入口 |  |
| 当前 owner |  |
| 重构状态 | Not started / Auditing / Contracted / Pilot migrating / Verified / Rolled back |

## 业务边界

### 模块职责

- 本模块负责:
  - 
- 本模块不负责:
  - 

### Canonical facts

| 事实 | Canonical owner | 存储位置 | 写入入口 | 是否可由其它模块写入 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Derived facts / read models

| 派生数据 | read_model_key | scope_type | partition key | scope_key 规则 | builder/refresh owner | freshness proof | projection strategy |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  | partitioned scoped + scoped incremental / active generation / not applicable |

## 输入合同

### HTTP/API 输入

| Endpoint | Method | Request fields | Auth/permission | Command/query owner | Validation |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

### Command 输入

| Command | Caller | Required fields | Idempotency | Version/conflict | Invalid input behavior |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

### Query 输入

| Query | Caller | Filters | Pagination/sort | Freshness requirement | Empty behavior |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

### 外部输入

| Source | Adapter/boundary | Trust level | Timeout/retry | Normalization owner | Failure behavior |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## 输出合同

### API response

| Endpoint | Success shape | Error shape | Required fields | Compatibility constraints |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### 写操作输出

| Operation | Canonical write result | affected scopes/months | version/job | audit event | frontend action after success |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

### 事件输出

| Event | Type | Producer | Payload contract | Consumer modules | Retry/dedupe |
| --- | --- | --- | --- | --- | --- |
|  | Domain event |  |  |  |  |
|  | Dirty scope |  |  |  |  |
|  | Outbox event |  |  |  |  |
|  | Frontend domain event |  |  |  |  |

## 状态合同

### 业务状态

| State | Meaning | Allowed transitions | Forbidden transitions | Owner |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### UI 状态

| State | Trigger | User-visible behavior | Recovery | Test coverage |
| --- | --- | --- | --- | --- |
| initial_loading |  |  |  |  |
| empty |  |  |  |  |
| error |  |  |  |  |
| refreshing |  |  |  |  |
| stale |  |  |  |  |
| blocked |  |  |  |  |

### Read model / worker 状态

| State | Source of truth | UI behavior | API behavior | Recovery |
| --- | --- | --- | --- | --- |
| fresh |  |  |  |  |
| refreshing |  |  |  |  |
| stale |  |  |  |  |
| missing |  |  |  |  |
| failed |  |  |  |  |
| schema_mismatch |  |  |  |  |
| source_mismatch |  |  |  |  |

## 权限与审计合同

| Action | Required permission | Read-only behavior | Admin behavior | Audit record | Sensitive data rules |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

要求：

- route 可以读取 HTTP/session 并映射 actor。
- service 只接收 actor/permission 结果，不直接读取 HTTP header/cookie。
- audit 不记录 secrets、tokens、原始敏感 payload。

## 模块边界

### Public surface

允许其它模块调用：

- 

### Internal-only surface

禁止其它模块直接调用：

- 

### Allowed dependencies

- 

### Forbidden dependencies

- service 不直接 import Flask、HTTP response、`app.auth`。
- worker 不依赖 `Application`、HTTP response、request/session。
- 页面不绕过 feature API 直接拼接后端路径，除非模块合同登记。
- 模块不直接读写其它模块 canonical facts，除非通过明确 application service contract。
- 业务 service 不直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。
- 新链路不调用旧 route、旧 service、旧 repository、旧 frontend API 或 legacy fallback，除非在本合同登记为 `compat-only`。

## Legacy 退役与隔离合同

| Legacy path | 类型 | 当前调用者 | 目标状态 | 删除/隔离条件 | 禁止行为 | 测试证明 |
| --- | --- | --- | --- | --- | --- | --- |
|  | route / service / repository / read model / frontend API / worker |  | removed / quarantined / compat-only / blocked-by-human-gate |  |  |  |

要求：

- 默认删除旧链路；只有兼容、回滚或生产验证限制明确时，才允许短期保留。
- `compat-only` 旧链路必须只读或只做兼容映射，不得写 canonical facts、dirty scopes、outbox、read model readiness、cache 或 App Status。
- 新链路不得从旧模块读取内部状态来决定业务结果；只能读取 canonical facts 或登记过的 read model contract。
- 每个保留旧链路必须有 owner、删除触发条件、最长保留范围和回归测试。
- 模块关闭前必须有 import/call graph、API route、frontend API 或测试证据，证明新链路不会误走旧链路。

## Read model refresh 合同

| Operation/event | scope_type | scope_key normalization | Gateway owner | Transaction boundary | Dedupe key | Operation barrier target |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

### Partitioned scoped incremental projection 合同

| read_model_key | Partition key | Incremental trigger | Full rebuild fallback | Parent/aggregate scope | Builder owner | Go candidate |
| --- | --- | --- | --- | --- | --- | --- |
|  | month/account/domain/object/status | dirty scope / outbox event / config version | backfill / repair / cold start only | none / all / active generation aggregate | Python / Go Worker / mixed | yes/no |

### 强制刷新合同

| Force refresh entry | Allowed caller | Scope source | Idempotency/dedupe | Readiness proof | API states | UI behavior |
| --- | --- | --- | --- | --- | --- | --- |
|  | operator/API/job/service boundary | canonical write result / explicit scope / repair runbook |  | job id / generation / source version / refreshed_at | stale / refreshing / fresh / failed | blocked / reload / background refresh |

要求：

- 非事务 refresh 必须走 `ReadModelRefreshGateway`。
- 事务内 writer 必须写清等价 scope contract。
- Redis 只能缓存 fresh gate 后 payload。
- RabbitMQ 只能作为 wakeup/transport，不作为状态事实源。
- Workbench active generation 保留特殊边界，不机械套普通 read model gateway。
- 强制刷新必须受权限、scope validation、dedupe 和审计保护；不能作为页面随意触发的“刷新所有”按钮。
- 写 API 不能只返回成功；涉及跨页面一致性时必须返回 affected scopes/months、version/job 或明确说明不适用。
- 读 API 必须暴露或内部使用 freshness/readiness 状态，不能把 stale payload 标为 fresh。
- 前端必须通过 operation barrier 或登记的重读边界等待目标 read model，不得自行伪造 fresh。

## Go / Fiber / Go Worker carve-out 合同

仅当模块在 `11-GO-HOT-PATH-CARVE-OUT.md` 的 candidate list 中，且通过 admission gates，才填写为 active。

| 项 | 内容 |
| --- | --- |
| Candidate key |  |
| Go shape | Go Worker / Go Processor / Go compute service / Go Fiber internal API / not applicable |
| Fiber 是否需要 | no / internal API only / frontend-facing not allowed |
| Python facade owner |  |
| Python reference implementation |  |
| Go candidate implementation |  |
| Shadow run mode | yes/no |
| Rollback switch |  |
| Deployment unit | binary / service / worker / sidecar |
| Worker instance / event types |  |
| PostgreSQL dual queue contract | `job.outbox_events` + `job.read_model_dirty_scopes` / not applicable |

### Go admission checklist

- [ ] Candidate listed in `11-GO-HOT-PATH-CARVE-OUT.md`.
- [ ] Performance evidence recorded.
- [ ] IO contract complete.
- [ ] Legacy retirement/quarantine complete.
- [ ] Freshness/force refresh/operation barrier contract complete or not applicable.
- [ ] Shadow run possible.
- [ ] Python-vs-Go equivalence tests possible.
- [ ] Per-module rollback possible.
- [ ] Basic verification does not require staging DB or local `PGSQL_URL`.

### Python-vs-Go equivalence tests

| Contract area | Required comparison | Test |
| --- | --- | --- |
| rows | row count, identity, stable fields |  |
| summary | totals, grouped counts, signs, amounts |  |
| ordering/pagination | stable sort and page boundaries |  |
| freshness | source_version, schema_version, readiness metadata |  |
| affected scopes | scope_type/scope_key/reason/dedupe |  |
| errors | error code/message/status shape |  |
| empty state | empty vs refreshing vs unavailable |  |

### Go double-write prevention

- Go shadow mode cannot ack outbox, mark dirty scope done, publish read model generation, write readiness or update cache.
- Python worker and Go worker cannot both own the same event type/scope in authoritative mode.
- Go implementation cannot bypass registered repository/queue contracts to write canonical facts, dirty scopes, outbox, readiness or cache.
- RabbitMQ, if used later, is wakeup/transport only and cannot be the job/read model/freshness source of truth.

## 测试合同

| 测试类别 | 是否适用 | 需要覆盖的行为 | 现有测试 | 新增/修改测试 |
| --- | --- | --- | --- | --- |
| 1. Business core unit tests |  |  |  |  |
| 2. Service-layer tests |  |  |  |  |
| 3. API contract tests |  |  |  |  |
| 4. Read model/cache/background job tests |  |  |  |  |
| 5. Frontend component/interaction tests |  |  |  |  |
| 6. End-to-end business-flow integration tests |  |  |  |  |
| 7. Existing feature regression tests | Always evaluate |  |  |  |

## 验证命令

| Scope | Command | When to run |
| --- | --- | --- |
| 后端模块测试 | `PYTHONPATH=backend/src python3 -m unittest ...` |  |
| 后端全量测试 | `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v` |  |
| 前端模块测试 | `cd web && npm test -- ...` |  |
| 前端 build | `cd web && npm run build` |  |
| smoke/check | `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` |  |

## 环境约束

| 项 | 当前可用性 | 对本模块验证的影响 | 替代方案 |
| --- | --- | --- | --- |
| 本地 `PGSQL_URL` | 不可用 / 可用 |  |  |
| staging 数据库 | 不可用 / 可用 |  |  |
| 生产 SSH | 需要人工交互，不记录密码 |  |  |
| Redis/RabbitMQ | 不可用 / 可用 |  |  |
| OA Mongo/OA MySQL | 不可用 / 可用 |  |  |

验证分层：

- Local static:
- Local fake/stub:
- Production read-only:
- Production controlled-write:

要求：

- 不把 SSH 密码、数据库密码、token、cookie 或生产 secret 写入合同。
- 没有真实数据库验证时，不能把 read model/worker 生产闭环标为完成。
- 生产写入验证必须有备份、审批、影响范围和回滚路径。

## Docs impact

| 变更类型 | 是否影响 | 需要更新的文档 |
| --- | --- | --- |
| 产品/业务口径 |  | `docs/product-specs/` |
| 页面/API/运行时 |  | `docs/app-architecture/`、`docs/dev/` |
| 模块事实/状态/测试 |  | `docs/modules/<module>/` |
| read model/worker/队列 |  | `docs/modules/read-models/`、`docs/modules/runtime-workers/`、`docs/operations/` |
| 权限/审计 |  | `docs/modules/permissions-and-audit/` |
| 部署/运维 |  | `docs/operations/`、`deploy/oa/README.md` |

## 完成证明

- [ ] IO 合同已填完整。
- [ ] 当前实现与合同差异已登记。
- [ ] 迁移计划只覆盖本模块或明确共享边界。
- [ ] Legacy 退役与隔离合同已填完整；旧链路已删除或明确隔离。
- [ ] Read model 强制刷新合同已填完整，或明确不适用。
- [ ] Partitioned scoped incremental projection 合同已填完整，或明确不适用。
- [ ] 如进入 Go candidate，Go / Fiber / Go Worker carve-out 合同已填完整；否则明确 not applicable。
- [ ] 测试合同已补齐。
- [ ] 验证命令已运行或明确不可运行原因。
- [ ] 环境限制已说明；真实 DB/worker 验证缺口已登记。
- [ ] docs impact 已处理。
