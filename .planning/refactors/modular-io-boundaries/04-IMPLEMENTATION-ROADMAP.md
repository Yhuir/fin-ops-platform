# 模块化 IO 重构路线图

**状态:** Autonomous execution in progress; roadmap state reconciled on 2026-06-23
**原则:** 先试点，后推广；先合同，后实现；先测试，后迁移。

## 进度口径

本文件记录模块化 IO 重构 phase roadmap。它不是根 `.planning/ROADMAP.md` 的页面分析 phase 表，也不是 `autonomous/MODULE-QUEUE.md` 的窄边界执行队列。

后续汇报必须分开列出：

- `.planning/ROADMAP.md`: 页面分析 roadmap 进度。
- 本文件: 模块化 IO phase roadmap 进度。
- `autonomous/MODULE-QUEUE.md`: 自动推进边界队列进度。

如果这些文件的状态互相矛盾，先执行 planning state reconciliation slice，再继续模块实现。

## Phase 0: 架构合同与重构骨架

目标：

- 建立本目录。
- 固化模块化 IO 重构需求。
- 建立合同模板、状态机、影响分析和测试闸门。
- 做当前代码轻量审计。

完成标准：

- [x] `00-REQUIREMENTS.md` 完成。
- [x] `01-CURRENT-STATE-AUDIT.md` 完成。
- [x] `02-MODULE-IO-CONTRACT-TEMPLATE.md` 完成。
- [x] `03-REFACTOR-STATE-MACHINE.md` 完成。
- [x] `04-IMPLEMENTATION-ROADMAP.md` 完成。
- [x] `05-IMPACT-AND-TEST-GATES.md` 完成。
- [x] `06-PILOT-SELECTION.md` 完成。
- [x] prompt 模板完成。
- [x] `08-AUTONOMOUS-RUNBOOK.md` 完成。
- [x] `09-DEV-BRANCH-WORKFLOW.md` 完成。
- [x] `10-AUTONOMOUS-STOP-GATES.md` 完成。
- [x] `11-GO-HOT-PATH-CARVE-OUT.md` 完成。
- [x] `autonomous/STATE.md` 和 `autonomous/MODULE-QUEUE.md` 初始化完成。

不做：

- 不改业务代码。
- 不迁移 route/service/repository。
- 不更新长期事实源，除非发现当前文档事实错误且用户授权。

## Phase 1: 试点模块 IO 审计

目标：

- 选择一个最高收益、可控范围的试点模块。
- 按模板补齐该模块 IO 合同。
- 列出当前实现与目标合同的 gap。
- 明确该模块在“无本地 PGSQL_URL、无 staging 数据库”条件下的验证分层。

候选模块见 `06-PILOT-SELECTION.md`。

完成标准：

- [ ] 试点模块入口清单完成。
- [ ] 试点模块 read model/worker/event/operation barrier 清单完成。
- [ ] 试点模块 force refresh 入口、freshness proof 和跨页面依赖清单完成。
- [ ] 试点模块权限和审计清单完成。
- [ ] 试点模块测试合同完成。
- [ ] 试点模块 legacy path 状态清楚，并标记为 `removed`、`quarantined`、`compat-only` 或 `blocked-by-human-gate`。
- [ ] 试点模块验证被分成 local/fake-only、production read-only、production controlled-write 三类。

不做：

- 不开始迁移代码。

## Phase 2: 试点模块测试闸门补齐

目标：

- 在重构代码前补齐关键测试。
- 覆盖当前行为和预计迁移边界。

完成标准：

- [ ] 业务核心测试覆盖状态/规则/边界。
- [ ] service-layer 测试覆盖写入、审计、幂等、rollback 或说明不适用。
- [ ] API contract 测试覆盖 success/error/permission/response shape。
- [ ] read model/worker 测试覆盖 freshness、dirty/outbox、refreshing/stale/failed。
- [ ] force refresh 测试覆盖 scope normalization、dedupe/idempotency、job/readiness proof 和权限。
- [ ] 跨页面同步回归测试覆盖“页面 A 写入后，页面 B 不能继续把旧 read model 显示为 fresh”。
- [ ] 前端交互测试覆盖 loading/empty/error/refreshing/stale/permissions。
- [ ] 至少一个关键跨模块回归测试。
- [ ] legacy contamination 测试或静态检查覆盖新链路不调用旧模块 internal-only surface。
- [ ] 所有无法在本地无数据库环境运行的测试都有替代 contract/stub 测试或明确标为生产验证待办。

环境限制：

- 当前不能假设存在 `PGSQL_URL` 或 staging 数据库。
- 本地优先补齐 pure unit、API contract fake、repository boundary fake、frontend interaction 和静态检查。
- 涉及真实 PostgreSQL migration、outbox、readiness、worker、Redis/RabbitMQ、OA/MySQL 的验证必须进入生产只读或受控写入 runbook，不得在普通重构步骤中静默执行。

## Phase 3: 试点模块小步迁移

目标：

- 按合同迁移一个模块边界。
- 优先迁移最能降低连锁 bug 的入口，而不是最大文件。

推荐迁移顺序：

1. 固化 public API 和 response shape。
2. 固化 command/query service 边界。
3. 固化 canonical facts 和 repository 边界。
4. 固化 read model refresh 和 operation barrier。
5. 固化 force refresh、freshness proof 和跨页面重读边界。
6. 固化 frontend feature API/types/domain event。
7. 删除或隔离 legacy path。

完成标准：

- [ ] 每个迁移步骤都有测试。
- [ ] 每个 legacy path 删除前有调用点和回归测试证明。
- [ ] 保留的 legacy path 只能是 `compat-only`，不得写 canonical facts、dirty scopes、outbox、read model readiness、cache 或 App Status。
- [ ] 新链路不会通过旧模块 internal-only surface、legacy fallback 或旧 frontend API 污染新链路。
- [ ] force refresh 只能通过统一 gateway/runbook/API contract，不允许页面或业务 service 自行绕过。
- [ ] 不改变业务行为。
- [ ] 如真实 DB/worker 验证未执行，状态只能进入 `Verifying` 或 `ProductionValidationPending`，不能标记全闭环。

生产验证约束：

- 只读生产验证可以通过 SSH 进入服务器后执行 read-only smoke、日志检查、health/readiness 查询，但命令不得包含明文密码。
- 当前已确认 `finops-prod` 可用，但用户是 `finops-deploy`，没有无密码 sudo；因此只能做非特权只读验证。
- 当前 `finops-prod-root` 已可免密公钥登录；root/systemd/log/部署文件级只读验证可纳入 runbook。secret、生产写入、DB 写入、worker 消费/重放仍必须单独审批。
- 任何写入生产数据的验证必须先有备份/回滚方案、影响范围、人工审批和维护窗口。
- 没有 staging 时，优先选择可逆、幂等、只读或 dry-run 工具；避免把生产当作试错环境。

## Phase 4: 试点验收与模板修订

目标：

- 验证试点流程是否真的降低回归风险。
- 把试点经验反向修订模板。

完成标准：

- [ ] 试点模块完成状态进入 `Verified`。
- [ ] 所有文档和测试命令记录完整。
- [ ] 模板中无效、过重或遗漏的部分被修订。
- [ ] 第二批模块选择依据明确。

## Phase 5: 第二批模块推广

目标：

- 同时只推进少量模块。
- 优先选择与试点共享边界的模块，复用刚验证过的合同和测试模式。

建议批次：

1. 与试点强相关模块。
2. read model/worker 共享边界模块。
3. `server.py` legacy handler 较多但测试较完整的模块。
4. 前端大页面/大 API client 模块。

限制：

- 未通过试点前不得开启。
- 每批模块数量建议不超过 2 个。

## Phase 6: 共享边界治理

目标：

- 在多个模块合同稳定后，再治理共享中心。

共享边界包括：

- `server.py` residual route/handler。
- `postgres_repositories/read_models.py`。
- `ReadModelRefreshGateway` usage registry。
- `DerivedDataLifecycleService` event fan-out。
- `OperationFreshnessBarrierService` target mapping。
- `AppStatusOverviewService` / runtime monitoring。
- frontend `domainEvents.ts` 和 `operationBarrier/api.ts`。

完成标准：

- [ ] 每个共享边界有 owner。
- [ ] 每个共享边界有测试。
- [ ] 每个共享边界有禁止绕过规则。

## Phase 7: 全局闭环

目标：

- 所有目标模块达到完成定义。
- 连锁 bug 风险从“靠经验”转为“靠合同和测试”管理。

完成标准：

- [ ] 每个目标模块有 IO 合同。
- [ ] 每个目标模块有测试合同。
- [ ] 所有 read model refresh 调用点有登记。
- [ ] 所有 force refresh 入口有权限、scope、dedupe、freshness proof 和测试登记。
- [ ] 所有页面/domain read model 的 partition key、scope key、scoped incremental projection 策略和 full rebuild fallback 条件已登记。
- [ ] Workbench active generation、month shard、all aggregate、consistency check 和 atomic publish 作为特殊 read model 策略保留。
- [ ] Go hot-path candidates 已完成准入、延期或关闭记录；没有候选列表之外的自动 Go 化。
- [ ] Worker 目标态迁移到 Go Worker + PostgreSQL dual queue 的范围、顺序和 rollback 条件已登记。
- [ ] 所有 legacy handler/service/repository/read model/frontend API 状态明确；能删除的已删除，保留的有 `compat-only` 约束和删除计划。
- [ ] 旧链路不能写新事实源或 refresh 状态的证据已记录。
- [ ] 长期文档更新完成。
- [ ] 全量验证命令可运行或有明确不能运行原因。

## Go Hot Path Overlay: 候选门控迁移

目标：

- 使用 Go / Go Fiber / Go Worker 优化已模块化且性能证据明确的热点模块。
- 所有页面 read model 的目标策略统一为 `Partitioned Scoped Read Model + Scoped Incremental Projection`。
- Worker 目标运行时逐步迁移为 `Go Worker + PostgreSQL Dual Queue`。

非目标：

- 不全量替换 Python 后端。
- 不自动 Go 化候选列表之外的模块。
- 不把 Fiber 当作 Read Model、Worker、durable queue、权限或审计替代品。

推荐执行顺序：

1. Go-0 Performance Baseline: 记录 API p95、SQL p95、worker lag、read model enqueue-to-fresh、CPU、内存、import parse time 和 payload size。
2. Go-1 Workbench Compute Pilot: `workbench:matching-grouping-check` 先 shadow run。
3. Go-2 Scoped Incremental Projection Pilot: 选择一个页面 read model builder，用 Go Worker 实现 partitioned scoped incremental projection。
4. Go-3 Summary Rollup Pilot: 为一个高频 summary 建 precomputed rollup 和 fresh-gated cache，可选 Go builder。
5. Go-4 Import Parser Pilot: Go 化大文件 parse/normalize/preview，canonical confirm 继续 Python-first。
6. Go-5 OA Module Carve-out: OA 模块完成 IO contract 后，再迁移 adapter/sync/parse/cache。

完成标准：

- [ ] Go candidate 必须来自 `11-GO-HOT-PATH-CARVE-OUT.md`。
- [ ] Go candidate 必须通过性能证据、IO contract、legacy isolation、freshness proof、shadow run、rollback 和 Python-vs-Go equivalence gate。
- [ ] Go Worker authoritative 模式前，Python worker 不能同时 ack 或 publish 同一 event/scope。
- [ ] Go shadow mode 不能 ack outbox、mark dirty scope done、publish generation、write readiness 或 update cache。
- [ ] PostgreSQL dual queue 仍是 `job.outbox_events` + `job.read_model_dirty_scopes`；RabbitMQ 只作为未来 wakeup/transport。
- [ ] 没有 staging/`PGSQL_URL` 时，真实 DB/worker 证据只能记录为 `production-evidence-deferred`，不能声明闭环。

## Autonomous Overlay: 无人值守推进

目标：

- 在不依赖 staging 数据库和本地 `PGSQL_URL` 的前提下，尽量自动推进模块化 IO 重构。
- 每个小模块完成后 commit/push 到 `dev`。
- 遇到缺少生产 DB/worker 证据时记录 `production-evidence-deferred`，继续下一个安全模块。

自动推进必须执行：

1. 使用主 repo `/Users/yu/Desktop/fin-ops-platform`，不新建 worktree。
2. 启动前要求工作区干净、`main` 已 push，并将 `origin/main` merge 到 `dev`。
3. 按 `autonomous/MODULE-QUEUE.md` 选择下一个模块边界。
4. 每轮执行 audit -> contract -> tests -> implementation -> verification -> review -> state update -> commit -> push。
5. 每轮必须处理旧链路删除/隔离和 read model force refresh/freshness proof，不允许只新增新链路。
6. 不推送 `main`。
7. 不要求 staging 数据库或 `PGSQL_URL`。
8. 不做生产写入。
9. 只在 `10-AUTONOMOUS-STOP-GATES.md` 定义的 hard gate 停止。

完成标准：

- [x] 至少首个模块边界完成 `closed-autonomous` 或 `production-evidence-deferred`。
- [x] 至少一次 commit/push 到 `origin/dev`。
- [x] `autonomous/STATE.md`、`JOURNAL.md`、`MODULE-QUEUE.md` 更新。
- [x] `autonomous/NEXT-PROMPT.md` 生成下一轮 prompt。
- [x] 每个完成模块记录 legacy 退役/隔离结果和 read model 强制刷新/freshness 结果。
