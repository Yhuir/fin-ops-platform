---
spike: 001
name: architecture-audit
type: standard
validates: "Given current docs/codebase maps and source evidence, when auditing runtime/read-model/worker boundaries, then identify boundary correctness, violations, bug risks, and refactor phases without code changes."
verdict: PARTIAL
related: []
tags: [architecture, read-model, worker, queue, postgres, frontend, risk]
---

# 架构只读审计报告

日期：2026-06-16

结论：目标架构方向是合理的，但当前实现仍处在迁移后半段。PostgreSQL primary、durable queue、read model freshness gate、worker registry、operation barrier 的中心边界已经成型；主要风险来自 `server.py` 仍保留的 legacy request-path fallback、权限 fail-open 语义、direct OA Mongo 兼容路径和部分 read model 状态默认值。这些问题足以造成 stale read model、假 fresh、跨页面状态不同步、权限绕过或生产配置误用。

Verdict 是 `PARTIAL`：架构目标可验证为正确，当前实现还不能证明所有生产路径都强制走目标边界。

## What This Validates

本 spike 验证以下问题：

1. 当前前后端、service、repository、read model、worker、queue、PostgreSQL、Redis、RabbitMQ、OA Mongo 边界是否合理。
2. 哪些边界违反仓库 `AGENTS.md` 的目标架构。
3. 哪些架构问题可能造成真实 bug。
4. 每个风险给出证据文件路径和原因。
5. 按 P0/P1/P2 给出改进建议。
6. 输出分阶段重构路线图，不直接改业务代码。

## Inputs

主要输入：

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/architecture/persistence-and-read-models.md`
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/CONCERNS.md`
- `.planning/codebase/STACK.md`
- `.planning/codebase/STRUCTURE.md`
- 相关源码和测试的只读行号证据

## Boundary Assessment

| Boundary | Assessment | Evidence |
|---|---|---|
| Frontend route/session/status | 基本合理。前端通过 session bootstrap、operation barrier 和 App Status 消费后端事实；风险主要在个别页面/写操作是否始终等待 barrier 后再 refetch。 | `docs/app-architecture/runtime-and-ownership.md:53-62`, `web/src/features/operationBarrier/api.ts:73-129`, `.planning/codebase/ARCHITECTURE.md:281-285` |
| HTTP/App shell | 部分违反目标。`server.py` 仍是超大 composition + legacy handler + fallback surface，容易绕过 service/read model/permission 边界。 | `AGENTS.md:45-48`, `.planning/codebase/CONCERNS.md:7-11`, `backend/src/fin_ops_platform/app/server.py` 约 21,982 行 |
| Service | 方向合理但不均匀。核心 gateway/service 已显式注入依赖；部分 route/service 边界仍允许 `session=None` 或内嵌 SQL/state-store 兼容语义。 | `AGENTS.md:46-48`, `backend/src/fin_ops_platform/services/read_model_query_gateway.py:23-33`, `backend/src/fin_ops_platform/app/routes_bank_details.py:95-107` |
| Repository / PostgreSQL | 目标合理。PostgreSQL 是生产事实、durable queue、read model 的主边界；但旧 snapshot/state fallback 仍需严控在 migration/shadow/test/legacy。 | `README.md:7-10`, `ARCHITECTURE.md:49-55`, `docs/architecture/persistence-and-read-models.md:5-20` |
| Read model | 目标合理但仍有 legacy 绕路。正确路径是 fresh/status/enqueue；当前 workbench 仍有 request-path raw build/stale fallback。 | `AGENTS.md:52-58`, `docs/operations/runtime-worker-governance.md:59-79`, `backend/src/fin_ops_platform/app/server.py:17004-17090` |
| Worker / queue | 边界较强。`RuntimeWorker` 不依赖 HTTP/Application，`RuntimeQueueRepository` 写 PostgreSQL queue/dirty scopes，`ReadModelRefreshGateway` 做 scope normalize/validate/dedupe。 | `backend/src/fin_ops_platform/services/runtime_worker.py:73-168`, `backend/src/fin_ops_platform/services/runtime_queue.py:164-290`, `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py:11-72` |
| Redis | 合理。文档要求 Redis 只缓存 fresh gate 后 payload；`ReadModelQueryGateway` 也在 freshness fresh 后才写 cache。 | `AGENTS.md:56`, `docs/operations/runtime-worker-governance.md:18,63-79`, `backend/src/fin_ops_platform/services/read_model_query_gateway.py:124-136` |
| RabbitMQ | 合理。RabbitMQ 是 optional transport/wakeup，不替代 PostgreSQL durable queue 状态。 | `docs/app-architecture/runtime-and-ownership.md:87-93`, `.planning/codebase/STACK.md:99-103`, `.planning/codebase/INTEGRATIONS.md:19` |
| OA Mongo | 目标合理但兼容路径仍危险。OA Mongo 应只由 worker/migration/shadow/audit 工具只读；App shell 仍有 legacy direct adapter 构造和 adapter 类型分支。 | `docs/architecture/persistence-and-read-models.md:171-180`, `backend/src/fin_ops_platform/app/server.py:703-709,837-844,17765-17830` |

## Findings

### P0-1: Protected route auth can fail open when session dependencies are absent

Risk: 权限绕过。若 `identity_service` 或 `access_control_service` 未注入，`_resolve_fin_ops_read_session(...)` 返回 `(None, None)`，多个 mutation handler 只在 `session is not None and not session.can_mutate_data` 时拒绝。route class 内部也把 `session=None` 当作可保存或可变更。只要未来某个生产配置、轻量启动路径或新 handler 没有正确注入 session 依赖，就可能把受保护写操作放行。

Evidence:

- `AGENTS.md:44-48` 要求生产级需求考虑权限、service 不读 HTTP，HTTP 层负责权限映射。
- `backend/src/fin_ops_platform/app/server.py:10447-10450` 在 identity/access service 缺失时返回 `None, None`，不是 `401/503`。
- `backend/src/fin_ops_platform/app/server.py:12296-12308`, `12314-12323`, `12331-12347`, `12394-12406` 等 mutation handler 只在非空 session 且不可写时拒绝。
- `backend/src/fin_ops_platform/app/routes_bank_details.py:95-107`, `148-155` 把 `session=None` 解释为 `can_save=True` 或 `can_save=True`。
- `backend/src/fin_ops_platform/app/routes_pending_invoices.py:141-145` 使用 `getattr(session, "can_mutate_data", True)`。
- `.planning/codebase/CONCERNS.md:39-49` 已把 session 缺失默认值列为 known bug/coverage risk。

Why this can create real bugs:

- 缺失 auth 依赖本应是 `401/503` 或 blocked 状态，但可能变成允许保存规则、重跑标签、写入分类等。
- 单元测试如果直接调用 route class 并传 `session=None`，会固定一个比生产期望更宽松的权限模型。

Recommendation:

- 所有 protected read/mutation session resolver 缺依赖时 fail closed：read 返回 `503 auth_unavailable`，mutation 返回 `403/503`，不能返回 `(None, None)`。
- mutation route class API 改为要求非空 `OARequestSession` 或显式 `MutationActor`，不要用 `None` 表示允许。
- 增加 HTTP contract tests：缺 auth header、auth service missing、readonly user、admin-only route、direct route class session none。

### P0-2: Workbench request path can still build or return stale/legacy payloads

Risk: stale read model、旧 snapshot、前端假 fresh、跨页面状态不同步。目标架构要求 production miss/stale 只返回 refreshing/unavailable 并 enqueue，不在请求线程同步构造旧 payload；但 `server.py` 仍有 `_get_or_build_workbench_read_model(...)`、`_build_raw_workbench_payload(...)` 和 stale fallback。

Evidence:

- `AGENTS.md:52-56` 要求 read model 查询走 freshness/status/enqueue，不能读旧 read model 伪装 fresh。
- `docs/operations/runtime-worker-governance.md:14-18` 要求 source version guard、请求线程不做高成本 live rebuild。
- `docs/architecture/persistence-and-read-models.md:82-91` 明确 `/api/workbench` production miss/dirty 不调用旧 `_build_raw_workbench_payload()`，不使用 `state:workbench_*` fallback。
- `backend/src/fin_ops_platform/app/server.py:17004-17090` 中 `_get_or_build_workbench_read_model(...)` 会读取 cached read model、接受无 source_versions 的 legacy read model、必要时调用 `_build_raw_workbench_payload(month)`，并在不可持久化时返回 fallback stale read model。
- `backend/src/fin_ops_platform/app/server.py:17023-17027` 可把无 source_versions 的 legacy read model 判定为可用。
- `backend/src/fin_ops_platform/app/server.py:17046-17069` 可在不能持久化新 payload 时返回 stale fallback。
- `backend/src/fin_ops_platform/app/server.py:17102-17106` bank details relation tag 路径在缺 persisted read model 时直接构造 `all` raw payload。
- `backend/src/fin_ops_platform/app/server.py:17739-17756` raw builder 会从 live/OA payload 拼装、同步关系修复和 override，不是纯 SQL read model 读取。

Why this can create real bugs:

- OA 临时不可用或 projection miss 时，页面可能拿到旧 payload，而不是明确 `refreshing/blocked`。
- 无 source_versions 的旧 read model 被视作 fresh，会掩盖 schema/source mismatch。
- 下游页面如果从自己的 read model 看到 fresh，而 bank/workbench 另一路 fallback 拼旧 payload，会产生跨页面状态不同步。

Recommendation:

- 在 production/PostgreSQL bootstrap 下禁止 request path 调 `_build_raw_workbench_payload(...)`；miss/stale 只返回 `read_model_status=refreshing/unavailable` 并通过 `ReadModelRefreshGateway` enqueue。
- 将 legacy fallback 限制到 `FIN_OPS_BOOTSTRAP_MODE=legacy`、migration/shadow/test 工具，并增加 production guard test。
- 增加回归测试：生产 PG mode 中 repository missing、dirty pending、source_version mismatch、OA unavailable 都不能返回 grouped payload 或 stale fallback。

### P1-1: Workbench refresh status has an implicit fresh default

Risk: 前端假 fresh。`_workbench_refresh_status_payload_for_scope(...)` 如果 repository 返回一个 dict 但缺少 `status/read_model_status`，会把 fallback status 设为 `"fresh"`。这和治理文档要求的统一 response fields、missing/dirty/schema mismatch 返回 refreshing 不一致。

Evidence:

- `docs/operations/runtime-worker-governance.md:59-79` 要求统一 response 至少包含 `read_model_status`、scope、source_versions、stale_reasons、refresh_enqueued，missing/dirty/source mismatch 返回 refreshing。
- `backend/src/fin_ops_platform/app/server.py:3905-3921` 当 `payload` 是 dict 时传入 `fallback_status="fresh"`。
- `backend/src/fin_ops_platform/app/server.py:3923-3937` 用 `payload.get("read_model_status") or payload.get("status") or fallback_status` 得出 raw status。

Why this can create real bugs:

- 仓储层或查询层的 partial payload 会被解释为 fresh，页面可以释放 overlay 或展示旧数据。
- 状态字段缺失属于 contract violation，本应 fail closed 或 blocked/refreshing。

Recommendation:

- dict payload 缺少 status 时 fail closed 为 `unavailable` 或 `refreshing`，并记录 `reason=missing_status_contract`。
- 加 contract test：repository 返回空 dict、缺 `read_model_status`、缺 source_versions 时不可 fresh。

### P1-2: App shell still contains direct OA Mongo compatibility paths

Risk: worker 与 API/OA source 边界混淆。文档要求 production API 读取 PostgreSQL OA projection，不构造 direct `MongoOAAdapter`；当前代码大体用 `bootstrap_mode == "legacy"` 保护 direct adapter，但 App shell 仍存在 fallback wiring 和 `MongoOAAdapter` 类型分支。

Evidence:

- `docs/architecture/persistence-and-read-models.md:171-180` 要求 OA Mongo 只由独立 worker 拉取，API server 默认不构造 direct `MongoOAAdapter`。
- `backend/src/fin_ops_platform/app/server.py:703-709` `_build_legacy_direct_oa_mongo_adapter()` 在 legacy mode 构造 direct adapter。
- `backend/src/fin_ops_platform/app/server.py:837-844` 如果没有 OA projection repository，`oa_adapter` fallback 到 `source_oa_adapter`。
- `backend/src/fin_ops_platform/app/server.py:17765-17830` workbench row payload 构造仍根据 `MongoOAAdapter` 类型进入不同路径。
- `tests/test_platform_runtime_boundary_guards.py:939-963` 当前通过 allowlist 管理 `MongoOAAdapter` direct use，并把 `cost_tax_sql_projection.py` 标成 known violation。
- `.planning/codebase/CONCERNS.md:152-155` 把 OA MongoDB 仍为外部只读依赖列为风险。

Why this can create real bugs:

- 生产配置误把 bootstrap 切到 legacy 或缺失 projection repo 时，API 可能重新依赖 direct OA source，导致请求超时、数据口径和 worker projection 不一致。
- 类型分支让 read model/source boundary 难以静态证明。

Recommendation:

- production startup 检查：PostgreSQL mode 缺 OA projection repository 时 fail fast，不 fallback 到 direct adapter。
- 将 `MongoOAAdapter` parser/version pure helper 抽到独立 utility，缩小 allowlist。
- 保留 legacy direct adapter 但只允许工具/legacy mode，通过 tests 明确生产 request path 不实例化。

### P1-3: `server.py` is still a high-blast-radius route/business/fallback module

Risk: 新功能容易绕过目标架构。`server.py` 仍同时做 HTTP dispatch、auth/session、dependency wiring、legacy read model/fallback、worker-ish hot rebuild 和多个业务 handler。任何小改动都可能跨越权限、read model、queue、audit 边界。

Evidence:

- `AGENTS.md:45` 明确 `server.py` 只做路由、依赖组装和 HTTP 映射；业务逻辑放 services，SQL 放 repository，后台任务放 worker/service。
- `.planning/codebase/CONCERNS.md:7-11` 指出 `server.py` 约 22k 行并承载大量 fallback facades。
- `.planning/codebase/ARCHITECTURE.md:257-273` 把业务逻辑进入 `server.py`、service 依赖 HTTP/Application、直接写 queue SQL列为 anti-pattern。
- `backend/src/fin_ops_platform/app/server.py:719-880` 一次性初始化大量 repositories/services/adapters，并根据 legacy/projection 条件分支。
- `backend/src/fin_ops_platform/app/server.py:8482-8518` hot rebuild 直接在 App shell 中 raw build/persist workbench read model。

Why this can create real bugs:

- 新 handler 很容易复用已有 fallback helper，而不是走 `ReadModelQueryGateway`、operation barrier、service/repository contract。
- 权限检查、dirty scope enqueue、read model freshness、audit 可能分散在不同层，产生遗漏。

Recommendation:

- 采用 strangler 迁移：每次只抽一个 route family 到 `app/routes_*.py` + explicit application service。
- 对每个抽离的 route family 先加 characterization tests，再删除 server fallback。
- 建静态 guard：新代码不得在 `server.py` 增加业务规则、raw read model builder、direct OA source 分支。

### P1-4: Operation barrier is solid, but correctness depends on every write path using it

Risk: 写成功后页面提前恢复操作，导致局部 stale。当前 barrier 的实现是合理的，但如果新增页面/写操作只用 domain event 或本地 loading，而不等待 `/api/operation-barrier/status` 和 refetch，就会展示旧 read model。

Evidence:

- `docs/app-architecture/runtime-and-ownership.md:53-62` 规定写 API 成功只代表 canonical write，前端必须轮询 operation barrier，fresh 后重新读取 read boundary。
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py:42-71` barrier 只读 runtime snapshot 并返回 fresh/refreshing/blocked。
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py:120-152` 结合 read model scope 与 outbox pending/failed 状态判定。
- `web/src/features/operationBarrier/api.ts:73-129` 前端 helper 会轮询、blocked 抛错、timeout 抛错。
- `tests/test_operation_freshness_barrier.py:41-99` 覆盖 dirty scope refreshing 与 outbox failure blocked。
- `.planning/codebase/CONCERNS.md:191-201` 指出缺少完整 browser business flow 和 fallback removal readiness。

Why this can create real bugs:

- 已覆盖页面较安全；新页面或未迁移写流如果只 refetch 当前页面，不等 impacted scopes fresh，会出现 workbench、bank details、pending invoice 等页面之间状态不同步。

Recommendation:

- 为每个写 API response 标准化 `affected_months/scope_keys/read_model_targets`，前端强制用 helper 构造 barrier targets。
- 增加 E2E 或 integration tests：confirm relation -> barrier -> workbench display，import -> worker refresh -> page display。

### P2-1: Read model repository is too broad

Risk: 维护风险和跨域回归。read model repository 聚合多个 unrelated read model writer/status/query 动态行为，一个状态改动可能影响银行明细、发票、OA 待付款、搜索、成本、税金。

Evidence:

- `.planning/codebase/CONCERNS.md:25-29` 记录 `postgres_repositories/read_models.py` 约 10.8k 行，含多类 read model writers/status calculations。
- `.planning/codebase/STRUCTURE.md:151-153` 把 `read_model_refresh_gateway.py`、`runtime_queue.py`、`runtime_worker_registry.py` 作为关键边界文件。
- `docs/operations/runtime-worker-governance.md:81-92` 要求 refresh 链路通过统一 gateway/dirty scope/outbox contract。

Why this can create real bugs:

- 某个 read model family 的 status/scopes 修复，可能改变其它 family 的 `fresh/refreshing/failed` 解释。

Recommendation:

- 按 read model family 拆 repository 文件，保留公共 gateway、scope policy、freshness resolver 不变。
- 每拆一个 family，补对应 SQL runtime test、fresh/stale/source mismatch test、App Status scope test。

### P2-2: SQL/persistence details still appear outside strict repository modules

Risk: 边界理解不一致。大部分直接 SQL 位于 state-store、migration、operations/preflight，属于可解释例外；但仍会让“service 不应散落 SQL”的规则变得模糊。

Evidence:

- `AGENTS.md:48` 要求 repository 可以知道 SQL，业务 service 不应散落 SQL。
- `backend/src/fin_ops_platform/services/input_invoice_usage_payment_rules.py:280-295` 在 service 文件里定义 `PostgresInputInvoiceUsagePaymentRulesStateStore` 并直接查询 `app.app_settings`。
- `backend/src/fin_ops_platform/services/cutover_preflight.py:115-154` preflight service 直接做 PostgreSQL health/count SQL。
- `backend/src/fin_ops_platform/services/file_object_migration.py:127-305` migration service 直接读取/更新 `app.file_objects`。

Why this can create real bugs:

- 对 operational/migration state-store 来说可以接受；对业务 service 来说，SQL 分散会让事务边界、测试替身、权限/audit 链路难以统一。

Recommendation:

- 明确例外清单：`*_state_store.py`、migration/preflight、repository packages 可以直接 SQL；普通 application/business service 不新增 direct SQL。
- 将 `PostgresInputInvoiceUsagePaymentRulesStateStore` 迁到 repository/state-store 模块或纳入 allowlist。

### P2-3: Production readiness and fallback removal are not covered by one executable gate

Risk: 架构债被测试固定为“兼容行为”。当前有不少边界 guard，但还缺一个能证明 production PG mode 不使用 snapshot/direct OA/request rebuild fallback 的整体验证。

Evidence:

- `.planning/codebase/CONCERNS.md:197-201` 指出缺少证明 fallback 未用于 production PostgreSQL mode 的单一 gate。
- `.planning/codebase/CONCERNS.md:167-169` 指出缺少真实浏览器业务流标准验证目标。
- `tests/test_platform_runtime_boundary_guards.py:939-1009` 已有 allowlist guard，但仍保留若干 allowed/known violation。
- `README.md:40-46` 标准验证目前是 backend unittest、frontend test、frontend build。

Why this can create real bugs:

- 单测覆盖可能证明 legacy 行为仍工作，却不能证明生产不会走 legacy。
- 发布前无法一眼看出 fallback 是否已被重新引入。

Recommendation:

- 新增 `scripts/verify.sh runtime-boundary` 或类似入口：扫描/运行 production-mode guard tests、operation barrier smoke、worker manifest/deploy env consistency、no request-path raw build assertions。
- 将 allowlist 每项写 owner/exit condition，逾期 fail 或至少 yellow。

## P0/P1/P2 Improvement Summary

P0:

- Auth boundary fail closed：session dependency missing 不得放行 protected read/mutation；mutation route class 不接受 `session=None` 为 allowed。
- Workbench production read path fail closed：禁止 request-path raw build/stale fallback；miss/stale/source mismatch 返回 refreshing/unavailable 并 enqueue。

P1:

- Workbench status payload 缺 status 时不能默认 fresh。
- Production PG mode 缺 OA projection repo 时 fail fast，不 fallback direct Mongo adapter。
- `server.py` 按 route family 小步拆分，禁止新增业务规则/fallback。
- 标准化写 API affected scopes 和前端 operation barrier 使用。

P2:

- 按 read model family 拆分超大 repository。
- 收紧 direct SQL 例外清单。
- 建 production boundary verification gate 和真实浏览器关键业务流。

## Refactor Roadmap

### Phase 0: Freeze and Guard

Goal: 先不重构大块代码，先把风险入口封住。

Work:

- 加 production-mode guard tests：auth dependency missing fail closed、workbench miss/stale 不 raw build、不 stale fallback。
- 为 `MongoOAAdapter` allowlist 增加 owner/exit condition。
- 增加 runtime-boundary verify 命令或 CI target。

Acceptance:

- 生产 PG mode 下无法通过缺失 auth/identity service 放行写操作。
- 生产 PG mode 下 `_build_raw_workbench_payload` 不能出现在 workbench API read path。

### Phase 1: Workbench Read Path Convergence

Goal: 把 workbench 生产读取收敛到 SQL read model/generation/freshness 边界。

Work:

- 将 `_get_or_build_workbench_read_model(...)` 的 production 分支改为 query gateway/freshness resolver。
- legacy raw build 只保留在 explicit legacy/test/migration 工具。
- bank details relation tag 改为消费 `WorkbenchRelationReadFacade` 或对应 read model，不 raw build `all` payload。

Acceptance:

- missing/dirty/source mismatch/OA unavailable 都返回明确 `refreshing/blocked/unavailable`。
- 页面不再收到未证明 fresh 的 grouped payload。

### Phase 2: Auth and Permission Boundary Cleanup

Goal: 把权限从“可选 session”改成显式 actor/session contract。

Work:

- protected route resolver 缺依赖 fail closed。
- mutation service 入参统一为 `actor_id` + permission facts，route class 不再默认 `session=None` allowed。
- 为 bank details、pending invoices、tax、output collection 等 route family 增加 missing-auth/read-only/admin negative tests。

Acceptance:

- direct route class tests 也不能用 `session=None` 通过 mutation。
- HTTP 和 service test 的权限语义一致。

### Phase 3: OA Source Boundary and Worker Ownership

Goal: API 只读 PostgreSQL OA projection；OA Mongo 只属于 worker/tool。

Work:

- Production startup 强制 OA projection repository 存在。
- 抽出 OA attachment parser version/pure helpers，减少 `MongoOAAdapter` import。
- `POST /integrations/oa/sync` 只 enqueue durable event，不触发 in-process sync/rebuild。

Acceptance:

- production request path 不实例化 direct `MongoOAAdapter`。
- worker/source sync、projection builder、API reader 的依赖方向可由静态 guard 验证。

### Phase 4: Route and Repository Strangler

Goal: 降低 `server.py` 和 read model repository 的 blast radius。

Work:

- 每次迁移一个 route family 到 `app/routes_*.py` + application service。
- 按 read model family 拆 `postgres_repositories/read_models.py`。
- 保持 public response shape 和 status semantics 不变。

Acceptance:

- `server.py` 新业务逻辑不再增长，只保留 composition 和 legacy adapter glue。
- 每个 read model family 有独立 freshness/source mismatch/worker refresh tests。

### Phase 5: Full Flow Verification

Goal: 用端到端流程证明架构约束在真实业务链路中成立。

Work:

- 增加浏览器或高层 integration：import -> preview -> confirm -> worker refresh -> page display。
- 增加 relation confirm/withdraw -> operation barrier -> workbench/bank/pending invoice display。
- 增加 App Health/App Status worker missing/stale/backlog smoke。

Acceptance:

- 发布前能证明关键页面不会假 fresh、不会跨页面状态不同步。
- fallback removal readiness 有可执行 gate，而不是人工记忆。

## How To Run / Reproduce

只读复查命令：

```bash
find .planning/codebase -maxdepth 1 -type f -print | sort
rg -n "read model|worker|queue|fallback|legacy|MongoOAAdapter|session is None|can_mutate_data" AGENTS.md docs backend/src web/src .planning/codebase
PYTHONPATH=backend/src python3 -m unittest tests/test_operation_freshness_barrier.py tests/test_platform_runtime_boundary_guards.py -v
cd web && npm test -- OperationBarrierApi
```

本 spike 本身不要求运行全量测试，因为没有修改业务代码。

## What To Expect

- 本报告只创建 `.planning/spikes/001-architecture-audit/README.md` 和更新 `.planning/spikes/MANIFEST.md`。
- 不修改 `backend/`、`web/`、`docs/` 的长期事实源。
- 后续如果按路线图执行，应从 P0 guard tests 和 fail-closed 行为开始，而不是先做大重构。

## Investigation Trail

- 读取 GSD spike 工作流：`/Users/yu/.codex/skills/gsd-spike/SKILL.md`、`/Users/yu/.codex/gsd-core/workflows/spike.md`。
- 读取仓库入口和长期架构文档：`AGENTS.md`、`README.md`、`ARCHITECTURE.md`、`docs/app-architecture/runtime-and-ownership.md`、`docs/operations/runtime-worker-governance.md`、`docs/architecture/persistence-and-read-models.md`。
- 读取 `.planning/codebase/` 映射结果，尤其是 `ARCHITECTURE.md`、`CONCERNS.md`、`STACK.md`、`STRUCTURE.md`。
- 使用 CodeGraph 查询 read model freshness、operation barrier、runtime worker 的结构上下文。
- 用 `rg` 和 `nl -ba` 定位风险证据行号。

## Results

Validated:

- PostgreSQL primary + durable queue + read model freshness + worker registry + operation barrier 的目标架构是合理的。
- Redis/RabbitMQ 的目标定位正确：Redis 只做 fresh-gated cache，RabbitMQ 只做 optional transport/wakeup。
- Worker/queue/gateway 的核心实现较符合目标边界。

Partially validated / remaining risk:

- App shell、Workbench legacy fallback、permission session defaults、direct OA Mongo compatibility paths 仍会削弱目标架构。
- 这些风险不是抽象洁癖；它们可直接导致 stale payload、假 fresh、权限绕过、跨页面状态不同步或生产误配置。

Not performed:

- 未修改业务代码。
- 未运行全量测试。
- 未启动本地服务或浏览器验证。
