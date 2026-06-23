# 模块化 IO 边界重构需求文档

**创建日期:** 2026-06-22
**需求状态:** Locked for planning
**实现状态:** Autonomous execution in progress; not global closure
**适用范围:** `backend/`、`web/`、`tests/`、`docs/modules/`、`docs/app-architecture/`、`docs/dev/`、`docs/operations/`

## 目标

把当前“改完一个功能另一个功能出 bug”的高耦合风险，收敛为可验证、可回归、可分阶段迁移的模块化 IO 边界治理体系。

本重构的核心目标不是把文件拆小，而是把业务边界、数据流、状态、事件、read model、权限和测试合同拆清楚。只有当模块的外部合同稳定、内部实现可替换、跨模块影响可预测，并且有回归测试保护时，才算完成。

## 状态口径

本需求文档约束模块化 IO 边界重构，不替代根 `.planning/ROADMAP.md`。

- 根 `.planning/ROADMAP.md` 记录页面分析与页面级 phase roadmap。
- 本目录 `04-IMPLEMENTATION-ROADMAP.md` 记录模块化 IO phase roadmap。
- `autonomous/MODULE-QUEUE.md` 记录无人值守执行的窄边界队列。

后续执行和汇报必须同时识别这些来源。若三者状态不一致，先执行 `planning:state-reconciliation-and-roadmap-alignment` 类型的文档状态同步 slice，再继续代码或模块边界实现。

## 背景

当前仓库已经有模块化基础：

- 后端存在 `backend/src/fin_ops_platform/app/routes_*.py`、`services/`、`services/postgres_repositories/`。
- 前端存在 `web/src/features/*`、`web/src/pages/*`、`web/src/components/*`。
- 模块文档已按 `docs/modules/<module>/` 管理，且大多数模块已经具备 `README.md`、`state-machine.md`、`tests.md`、`e2e-spec.md`、`e2e-coverage.md`、`implementation-notes.md`。
- 架构文档已经要求 route 只做 HTTP 映射、service 承担业务规则、repository 承担 SQL、read model refresh 走统一 gateway/queue。

但当前仍存在高风险信号：

- `backend/src/fin_ops_platform/app/server.py` 仍约 22849 行，且保留大量 `/api/*` dispatch 和 handler。
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` 仍约 11329 行，是 read model 持久化和刷新相关高耦合中心。
- 多个 service 仍超过 2000 行，业务边界和编排边界需要继续收敛。
- 前端存在大页面和大 API client，例如 `web/src/features/workbench/api.ts`、`web/src/pages/EtcTicketManagementPage.tsx`、`web/src/pages/BankDetailsPage.tsx`、`web/src/pages/ReconciliationWorkbenchPage.tsx`。
- route 拆分处于半完成状态: 多个 `routes_*.py` 已存在，但 `server.py` 仍承担大量路由分发。
- read model refresh 入口较多，不少业务 service 会直接实例化 `ReadModelRefreshGateway`；需要明确哪些是合法边界，哪些应该通过更上层 lifecycle/gateway 统一。
- 当前开发环境没有可用 `PGSQL_URL` 和 staging 数据库；操作者只有 SSH 进入服务器的密码。因此重构计划不能假设存在完整预发数据库验证环境，也不能把生产 SSH 密码或任何 secret 写入文档、脚本或测试。

## 原则

### RQ-01: 不拆文件，先拆业务边界

- Current: 仓库已有文件和目录层面的模块化，但局部仍存在 route、service、repository、read model、UI 和测试责任混杂。
- Target: 每个模块先定义业务边界和 IO 合同，再按合同迁移代码。
- Acceptance: 任意模块重构完成后，能从其 IO 合同判断它的输入、输出、状态、事件、read model、权限、测试和跨模块影响。

### RQ-02: 每个模块必须有完整 IO 合同

- Current: `docs/modules/` 有模块文档，但没有统一格式的 IO 合同要求。
- Target: 每个纳入重构的模块必须补齐 `02-MODULE-IO-CONTRACT-TEMPLATE.md` 中的合同内容。
- Acceptance: 模块合同至少覆盖 public API、command/query、canonical facts、read model、dirty scope、outbox event、frontend event、operation barrier、permissions、audit、tests、docs impact。

### RQ-03: 模块边界必须禁止穿透调用

- Current: 前后端已有模块目录，但模块间仍可能通过内部 service、内部 types、共享大 client 或 legacy handler 穿透。
- Target: 模块之间只能通过明确 public API、domain event、read model contract 或 application service contract 交互。
- Acceptance: 单模块审计能列出 allowed imports、forbidden imports、public surface 和 internal-only surface；新增穿透依赖必须被测试、lint 或审计清单发现。

### RQ-04: 共享事实源必须单一

- Current: canonical write facts、read model、legacy snapshot、queue/outbox、App Status 之间仍存在历史兼容路径。
- Target: 每个业务事实只能有一个 canonical owner；legacy/read model/cache 只能派生，不得反向成为事实源。
- Acceptance: 每个模块合同明确 canonical store、read model store、legacy fallback 状态、迁移/回滚条件和禁止写入路径。

### RQ-05: read model refresh 必须走统一边界

- Current: 架构要求 read model refresh 走 `ReadModelRefreshGateway` / scope policy registry / `RuntimeQueueRepository`，但调用点分散。
- Target: 所有非事务 refresh 请求必须走统一 gateway 和 scope policy；事务内 writer 必须承担等价 scope contract；业务 service 不直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。
- Acceptance: 审计中除 `RuntimeQueueRepository`、事务内 canonical writer、read model scope repair 工具和测试外，不能出现未登记的 dirty/outbox 直接写入；每个 refresh 调用点有 owner、scope、reason、dedupe、freshness 证明。

### RQ-06: 写入成功和读模型可用必须分离

- Current: 架构已要求写 API 返回 canonical write 成功后，前端通过 operation barrier 等待目标 read model fresh。
- Target: 所有跨 read model 的写操作都明确返回 affected scopes/months/version/job，前端不得把写入成功当成页面同步完成。
- Acceptance: 模块合同列出每个写操作的 affected scopes、operation barrier targets、刷新后必须重读的 read boundary 和 blocked/fresh/refreshing UI 行为。

### RQ-07: 权限和审计是模块 IO 的一部分

- Current: 权限、actor、audit 可能散在 route/service 中。
- Target: 每个模块必须声明 actions、roles、read-only/export/admin 差异、audit records 和敏感字段处理。
- Acceptance: API contract 测试覆盖无权限、只读、管理员、导出权限和审计事件；服务层不直接读取 HTTP header/cookie。

### RQ-08: 每次改动必须做影响分析

- Current: `.planning/phases/00-cross-page-dependency-baseline` 已建立跨页依赖基线，但日常改动未强制绑定模块 IO 合同。
- Target: 每次功能、bug fix、API、read model、worker、权限或数据流改动前，必须填写影响分析。
- Acceptance: 影响分析至少覆盖 API、service、repository、read model、worker、frontend、domain event、operation barrier、App Status、permissions、audit、tests、docs。

### RQ-09: 每次改动必须做回归测试映射

- Current: AGENTS 已要求七类测试评估，但模块层没有统一执行模板。
- Target: 每次改动必须按七类测试判断适用性；适用则新增或更新测试，不适用则说明原因。
- Acceptance: 最终实现 summary 必须列出新增/修改测试、覆盖七类中的哪些类别、不适用类别原因、运行命令和剩余风险。

### RQ-10: 先试点，不全局一次性重构

- Current: 高风险模块较多，直接全局迁移会放大回归风险。
- Target: 先选择最高频出 bug 或边界最混乱的模块做试点，验证模板、审计、测试、迁移流程后再推广。
- Acceptance: 试点模块完成后，能证明它的 IO 合同、影响分析、测试闸门和迁移步骤可以复制到其它模块；试点未通过前不得启动全量迁移。

### RQ-11: 保持当前业务行为不变，除非明确立项

- Current: 这次工作是架构治理，不是业务口径重写。
- Target: 模块化迁移不得改变业务含义、API response shape、权限行为、read model freshness 语义或 UI 交互，除非单独记录需求并有测试保护。
- Acceptance: 每个重构 phase 必须有 existing behavior regression tests；旧 API shape、旧页面状态、旧 read model 不得静默变化。

### RQ-12: 文档只沉淀长期事实，不保存原始 prompt

- Current: 仓库要求新的 prompt 不写入主文档树，`.planning/` 只作为工作区。
- Target: 本目录保留 prompt 模板和提炼后的决策；长期事实变化必须同步到 `docs/` 对应事实源。
- Acceptance: 业务/API/架构/read model/worker/权限/测试/运维事实变化时，更新 `docs/modules/<module>/` 和对应长期文档；本目录只保留计划和状态。

### RQ-13: 环境约束必须进入验证计划

- Current: 本地没有 `PGSQL_URL` 和 staging 数据库，只有可 SSH 登录服务器的密码。
- Target: 每个重构 phase 必须显式区分本地可验证项、fake/stub 可验证项、需要生产只读验证项、需要生产受控写入验证项。
- Acceptance: 任何需要真实 PostgreSQL、worker、outbox、read model、OA/MySQL、Redis/RabbitMQ 或生产文件系统的验证，都必须在计划中标注环境要求、风险等级、是否只读、是否需要备份/维护窗口、是否需要人工审批和回滚方式。

### RQ-14: Secret 不进入仓库和规划文档

- Current: 操作者只有 SSH 密码，这容易诱导后续 Agent 把密码写入命令、脚本、env 文件或日志。
- Target: 所有计划只引用 secret 的存放位置和获取方式，不记录具体值。Agent 不要求用户把 SSH 密码贴到聊天中，不把密码写进 `.planning/`、`docs/`、测试或 shell history。
- Acceptance: 文档中只出现占位符、root-only env 路径或交互式登录说明；任何生产命令都不能包含明文密码。

### RQ-15: 旧代码和旧链路必须退役或隔离

- Current: 多个模块存在新旧 route、service、repository、read model、frontend API 或 legacy fallback 并存。只新增新链路但不移除旧链路，会继续让旧逻辑影响新行为。
- Target: 每个模块迁移必须明确旧链路状态: `removed`、`quarantined`、`compat-only` 或 `blocked-by-human-gate`。默认目标是删除旧代码和旧调用路径；只有存在兼容、回滚或生产验证限制时，才允许短期隔离保留。
- Acceptance: 模块关闭前必须证明旧入口没有被新链路调用；保留的 legacy path 必须有 owner、调用者清单、到期条件、禁止写入范围、测试覆盖和删除计划。禁止通过旧模块继续写 canonical facts、dirty scopes、outbox、read model readiness 或缓存。

### RQ-16: Read Model 必须支持强制刷新与可证明 freshness

- Current: 页面之间出现“一个页面更新，另一个页面未同步”的核心原因通常不是页面没刷新，而是写入输出、dirty scope、refresh job、freshness gate、operation barrier 和前端重读边界没有形成闭环。
- Target: 每个写操作必须声明它影响哪些 read model scope，并通过统一边界触发 refresh；每个读操作必须声明 freshness 要求。需要跨页面一致性的模块必须具备强制刷新能力，且强制刷新只能通过受控 gateway/runbook/API contract 进入，不允许页面或业务 service 自己绕路刷新。
- Acceptance: 模块合同必须列出 force refresh 入口、允许调用者、scope normalization、dedupe/idempotency、job/readiness 证明、stale/refreshing/fresh/failed API 行为、前端 operation barrier targets 和回归测试。没有 freshness proof 的页面不得显示为 fresh。

### RQ-17: 所有页面 Read Model 目标态必须是分区化 scope + 增量投影

- Current: 不同页面 read model 的 scope、parent/all 聚合、active generation、cache 和刷新方式不完全一致，容易产生全量 rebuild、跨页面 stale 和局部刷新误判。
- Target: 所有页面 read model 的目标优化方向是 `Partitioned Scoped Read Model + Scoped Incremental Projection`。Partitioned/scoped 负责数据如何切分、存储和读取；incremental projection 负责只刷新受影响 scope。Workbench 保留 active generation、month shard、all aggregate、consistency check 和 atomic publish 特殊模型。
- Acceptance: 每个页面/domain 必须登记 read_model_key、scope_type、partition key、dirty source、affected scopes、parent/aggregate 规则、freshness proof、operation barrier target、Go/Python builder owner 和回归测试。Full rebuild 只能作为 backfill/repair/冷启动 fallback，不能作为普通写后同步路径。

### RQ-18: Go/Fiber 只能作为候选门控的热点模块 carve-out

- Current: Go Fiber 可提升 HTTP/Go runtime 性能，但它不替代 Read Model、Worker、durable queue、权限、审计或 freshness contract。直接全量替换 Python 后端工作量和回归风险过高。
- Target: 本计划接受 Go / Go Fiber / Go Worker 作为热点模块 carve-out 技术路线，不接受自动全局 Go 化。自动推进只能在 `11-GO-HOT-PATH-CARVE-OUT.md` 的候选列表中评估模块；未通过性能证据、IO contract、legacy isolation、shadow run、rollback 和 freshness proof gate 的候选必须标记 `go-candidate-deferred`。
- Acceptance: Go 模块必须有 Go contract、Python facade/API compatibility、shadow run、Python-vs-Go output equivalence tests、per-module rollback、worker/service health/check/version、timeout/retry/resource limits、observability 和生产证据状态。Go Worker 目标运行时是 `PostgreSQL dual queue`，即 `job.outbox_events` + `job.read_model_dirty_scopes`；RabbitMQ 只能作为可选 wakeup/transport，不能作为 job/read model/freshness 事实源。

## 模块完成定义

一个模块只有同时满足以下条件，才算完成模块化 IO 重构：

- 模块有完整 IO 合同。
- 模块 public surface 与 internal surface 清晰。
- 后端 route/service/repository/read model/worker 责任清晰。
- 前端 page/component/feature api/types/domain event 责任清晰。
- canonical facts、read model、cache、legacy fallback 的关系清晰。
- 写操作的 affected scopes、events、operation barrier、App Status 影响清晰。
- 旧代码和旧链路已经删除，或被隔离为有到期条件的 `compat-only` 路径，且不能写入新链路事实源。
- read model 强制刷新入口、freshness proof、operation barrier 和跨页面重读边界清晰。
- 页面 read model 已登记为 partitioned scoped + scoped incremental 目标态，或明确不适用。
- 如模块进入 Go candidate，Go contract、shadow run、rollback 和 Python-vs-Go equivalence 证明清晰。
- 权限和审计合同清晰。
- 七类测试适用性已判断，适用测试已补齐。
- 跨模块回归风险已登记并用测试或明确手工验证覆盖。
- 长期文档已更新或明确 docs 不适用。
- 环境限制已记录；没有 staging/真实 PostgreSQL 验证时，不能把生产 read model/worker 闭环标记为完成。

## 全局验收标准

- [ ] 至少一个试点模块完成 IO 合同、迁移计划、测试合同和回归闸门。
- [ ] 试点模块的现有功能回归测试通过。
- [ ] `server.py` 中该试点模块的 legacy route/handler 边界有明确迁移状态。
- [ ] 试点模块所有 read model refresh 调用点有统一 owner 和 scope contract。
- [ ] 试点模块具备受控 force refresh 合同，或明确说明该模块没有跨页面/read model 同步需求。
- [ ] 试点模块所有写操作返回 affected scopes/months/version/job 或明确说明不适用。
- [ ] 试点模块的前端页面不自行伪造 freshness 或全局 App Status。
- [ ] 试点模块旧 route/service/repository/read model/frontend 链路已删除或隔离，且有测试证明新链路不会调用旧链路。
- [ ] 试点模块 read model 的 partition key、scope key、incremental projection 策略和 full rebuild fallback 条件明确。
- [ ] 如果试点模块进入 Go candidate，必须先通过 `11-GO-HOT-PATH-CARVE-OUT.md` 的准入门槛，不能直接实现 Go 化。
- [ ] 试点模块的权限和审计路径有 API/service 测试保护。
- [ ] 基于试点结果更新模板，再推广到第二批模块。

## 非目标

- 不在本阶段直接执行代码重构。
- 不一次性迁移所有模块。
- 不为了拆文件引入额外抽象层。
- 不改变业务口径、金额计算、状态机、API shape 或 UI 行为。
- 不把 read model cache 当作事实源。
- 不让 RabbitMQ/Redis 成为 read model 状态事实源。
- 不保留能写入 canonical facts、dirty scopes、outbox、read model readiness 或缓存的未登记 legacy path。
- 不允许页面、旧 service 或旧模块绕过统一 gateway 强制刷新 read model。
- 不让 service 直接依赖 HTTP cookie/header、Flask response 或 `app.auth`。
- 不让 worker 依赖 `Application`、HTTP response 或 request/session。
- 不在文档、脚本、测试、commit 或日志中保存 SSH 密码、数据库密码、token、cookie 或生产 secret。
- 不把 Go Fiber 当作 Read Model、Worker、durable queue 或权限审计边界的替代品。
- 不自动 Go 化候选列表之外的模块；候选列表之外的 Go 化必须先更新计划并获得明确确认。
- 不让 Python worker 和 Go worker 同时 ack 同一 durable event 或发布同一 read model generation，除非 Go 路径是 shadow-only 且不能发布、ack 或写 readiness。
