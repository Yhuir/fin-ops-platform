---
phase: 08-oa-pending-payments-improvements
status: master_prompt
created: 2026-07-16
scope: oa-pending-payment-performance-integrity-closure
---

# OA 待付款核对性能与完整性闭环：主控 `/goal` Prompt

把下面整段作为 Codex 主控 `/goal` objective。它必须一次只生成并执行一个 bounded execution prompt；下一 prompt 只能由上一轮的真实完成状态决定。

```text
/goal

完全闭环 fin-ops-platform 的“OA 待付款核对”性能、read model 新鲜度、Audit 和旧链路清理任务。

仓库：/Users/yu/Desktop/fin-ops-platform
工作方式：直接使用当前 main worktree，不创建或切换分支。

一、目标

实现并验证以下设计：

- docs/modules/oa-pending-payments/performance-integrity-design.md

最终必须达到：

1. PostgreSQL 统一事实源的普通单条/单月变化提交后，已打开且可见的 OA 待付款页面显示新 read model 的生产目标为 p95 <= 1s；500ms 仅为挑战目标。
2. fresh 首屏聚合 API 目标为 p95 <= 250ms、p99 <= 500ms；ETag 304 快路径目标为 p95 <= 30ms。
3. 页面不使用 stale-while-revalidate。可见页面用原 rows endpoint 的 ETag 条件请求检测版本；检测到 dirty/source mismatch 后立即隐藏旧 rows，等待精确月份 operation barrier，再读取新 payload。
4. OA read model worker 只读取 PostgreSQL canonical/integration facts，不访问 Mongo/MySQL，不写其它页面 read model。
5. completed OA、in-progress admission、payment status、relation、银行、发票和规则变化都有 tenant-aware dynamic source version、精确 OA 月份 invalidation、durable outbox 和 CAS 闭环。
6. query gate 在 dirty/outbox、missing scope、expected/actual version mismatch 时 fail closed，返回 202 和精确 operationBarrierTargets；不能 live scan 或返回 falsely-fresh rows。
7. Page Audit 正确区分 App 内部 integrity、freshness、queue 和外部 sync evidence；不再显示原始英文 enum/重复计数，并且 OA 的文案变化不得影响其它页面的共享 PageAuditIcon。
8. 设计文档第 8 节列出的旧 route/client/service/repository/worker/read-model/fallback/pickle/snapshot/shared-worker 路径全部从 production runtime 删除；不保留并行旧路径、隐藏 fallback 或 compatibility endpoint。
9. input/output invoice、Workbench relation、bank detail、invoice detail、权限和其它页面 read model/API/worker 不受影响。
10. 适用的七类测试、文档、运维配置、回滚说明和验证证据全部闭环。

二、锁定决策：不得自行更改

以下决策已经通过 Grill-me 与用户确认：

1. 直接在当前 main worktree 实施。
2. 禁止创建或切换分支。
3. 禁止 git stage、commit、push、merge、rebase、reset、checkout、clean、stash 和任何会改写用户工作树/索引/历史的操作。
4. 允许只读 git status、diff、log、show，用于保护既有修改和审阅本任务 diff。
5. 禁止部署。不得调用 scripts/deploy-oa.sh，不得 SSH 到生产执行变更，不得操作 systemd，不得发布 release，不得对生产运行 migration、refresh、queue drain、repair 或业务写入。
6. 本地修复和验证完成后必须停在 READY_FOR_UNIFIED_DEPLOYMENT；此时总体 /goal 仍未完成，不得调用 complete，也不得因为等待统一部署而标记 blocked。
7. 只有用户明确回复“统一部署已完成，可以恢复验证”后，才允许恢复同一个 /goal 进入生产终验。
8. 统一部署由本 /goal 外部完成。即使恢复验证，主控也永远不会自行部署。
9. 生产终验默认只读：先使用自然发生的 canonical changes、现有 trace/source version、worker 日志、Audit 和只读 API 探针。
10. 如果自然样本不足以证明 commit-to-visible SLO，停止在 NEEDS_PRODUCTION_WRITE_AUTHORIZATION，列出 exact test record、正式业务 API、影响范围、回滚和验证方式，等待用户单独明确授权。部署或一般性“继续”不等于生产写入授权。
11. 禁止直接修改生产数据库制造性能样本。
12. 部署前允许本地/测试数据库做 SQL EXPLAIN、生产等量级数据基准、worker 构建耗时和 ETag 304 压测；这些只作为性能守门，不能冒充生产性能结论。
13. 不使用 subagent/orchestrator；本目标由主控在当前 worktree 内串行执行，避免并行写入和上下文所有权冲突。

三、工作树隔离

1. 开始第一轮前记录 git status --short 和目标文件 diff 基线。
2. 当前 worktree 可能同时存在其他 thread 的 tracked/untracked 修改；全部视为用户资产，不得删除、覆盖、格式化、移动或纳入本任务。
3. 只修改 OA 性能与完整性闭环直接需要的文件，以及被明确证明必须同步的 read-model/runtime-worker/module/docs/tests 配置。
4. 禁止全仓批量格式化、机械 rewrite 或无关 cleanup。
5. 每次修改目标文件前先检查它是否已被其他 thread 改动：
   - 能安全保留双方语义时，做最小合并。
   - 存在语义冲突或无法确定所有权时，停止在 WORKTREE_CONFLICT，列出文件、冲突事实和所需用户协调；不得覆盖。
6. 验证失败若来自其它 thread 的已知无关修改，只记录证据，不擅自修复或回滚对方工作。
7. 不创建 GSD workspace/worktree，不生成临时 prompt、临时导出、截图、数据库 dump 或仓库根目录垃圾文件。

四、事实源与必读顺序

每轮按当前子任务读取最小必要上下文，但第一轮必须完成以下事实核对：

1. AGENTS.md
2. README.md
3. ARCHITECTURE.md
4. docs/index.md
5. docs/app-architecture/README.md
6. docs/modules/README.md
7. docs/architecture/module-boundaries/README.md
8. docs/architecture/module-boundaries/inventory.md
9. docs/architecture/module-boundaries/read-model-contracts.md
10. docs/modules/oa-pending-payments/README.md
11. docs/modules/oa-pending-payments/boundary-io.md
12. docs/modules/oa-pending-payments/state-machine.md
13. docs/modules/oa-pending-payments/tests.md
14. docs/modules/oa-pending-payments/implementation-notes.md
15. docs/modules/oa-pending-payments/performance-integrity-design.md
16. docs/modules/oa-integration/README.md 和 boundary-io.md
17. docs/modules/read-models/README.md 和 boundary-io.md
18. docs/modules/runtime-workers/README.md 和 boundary-io.md
19. docs/operations/runtime-worker-governance.md
20. docs/dev/api-contracts.md

`.planning/phases/08-oa-pending-payments-improvements/08-SPEC.md` 和 `08-PLAN.md` 是早期历史计划，包含已被当前代码和长期文档替代的 SSE、confirm-paid 等旧决策。它们不能覆盖当前模块文档和 performance-integrity-design.md；只有仍被当前代码/长期合同证明有效的内容才能复用。

结构问题优先使用 CodeGraph：context、trace、callers、callees、impact、explore。只有 literal text、配置、日志、文件发现或 CodeGraph 未覆盖的精确细节才使用 rg/read。不要用 grep/read 循环重复 CodeGraph 已经证明的调用关系。

五、GSD + Grill-me 闭环算法

主控必须维护以下状态：

- Objective
- Current phase and bounded prompt number
- Known facts and authoritative source files
- Assumptions
- Dirty-worktree baseline and protected unrelated files
- Affected modules and dependency direction
- Affected APIs/services/repositories/read models/workers/pages/docs/tests
- Dependency writer inventory
- Legacy runtime path inventory and deletion status
- Files changed by this goal
- Tests added or changed
- Seven-category test coverage decision
- Verification commands and results
- Local performance evidence
- Open risks/blockers
- Deployment-gate status
- Next action

循环执行：

1. Analyze
   - 审阅当前状态和上一轮证据。
   - 用 Grill-me 检查目标、模块、输入 I/O、输出 I/O、事实源、scope/version、旧路径、测试责任、权限、回滚、性能和 worktree 冲突是否清楚。
   - 能从代码、文档、测试或安全只读证据发现的事实自行查明，不向用户提问。
   - 只在答案会实质改变业务行为、生产权限或与其他 thread 所有权时向用户提一个问题并等待。
   - 选择当前最高风险、可以独立完成的唯一下一步。

2. Generate exactly one bounded execution prompt
   每轮只生成一个 prompt，格式必须包含：

   [BOUNDED EXECUTION PROMPT <N>]
   - Goal
   - Why this is the highest-risk next gap
   - Evidence/source files to inspect
   - Allowed files/modules
   - Protected/forbidden files and operations
   - Architecture/I-O constraints
   - Existing helpers/services/repositories/tests to reuse first
   - Exact task actions
   - Tests/docs impact to decide
   - Verification commands
   - Stop condition and expected evidence

   不得预先生成 future prompt backlog。生成后必须在同一轮立即执行，不能只把 prompt 交给用户。

3. Execute
   - 只完成当前 bounded prompt。
   - 先查现有 helper/service/repository/manifest/fixture/test pattern，再新增代码。
   - 使用 apply_patch 编辑文件；不使用 shell 写文件技巧。
   - 保持模块边界和显式 I/O。
   - 行为变化必须同步适用测试和 docs impact。
   - 不部署、不写生产、不操作 git 索引或历史。

4. Review
   - 审阅实际 diff 和 worktree 状态。
   - 检查架构边界、API contract、事务、并发、幂等、fresh gate、权限、Audit、回滚、性能、旧路径删除、其它页面隔离和文档。
   - 检查是否引入重复 abstraction、parallel fallback、dead code、unused dependency、temporary artifact 或 speculative index/cache。
   - 先跑最小可靠验证，再按风险扩大。
   - 若失败，分类为 implementation defect、test defect、environment blocker、unrelated worktree failure 或 design contradiction。

5. Decide
   - CONTINUE：还有可安全执行的闭环工作，生成唯一下一 prompt。
   - WORKTREE_CONFLICT：目标文件与其它 thread 存在不可安全合并的语义冲突，停止请求协调。
   - READY_FOR_UNIFIED_DEPLOYMENT：本地实现、测试、文档、旧代码删除和本地性能守门全部完成，但尚未统一部署。停止，不 complete、不 blocked、不部署。
   - NEEDS_PRODUCTION_WRITE_AUTHORIZATION：统一部署后只读/自然样本不足，需要用户授权 exact 生产测试写入。停止，不自行写入。
   - CONTINUE_AFTER_PRODUCTION_FINDING：生产终验发现缺陷；返回本地实现循环，修复后再次停在新的 READY_FOR_UNIFIED_DEPLOYMENT。
   - DONE：只有统一部署已由用户确认，且生产只读/自然样本终验通过，才允许完成目标。

6. Derive next prompt from evidence
   - 测试失败：下一 prompt 只诊断/修复该失败及其 root cause。
   - 性能未达本地 guard：下一 prompt 先用 EXPLAIN/query-count/timing 定位，不盲加索引或 cache。
   - 发现 source/version/scope 缺口：下一 prompt 先闭合 writer inventory 和事务合同。
   - 发现旧调用者：下一 prompt 先迁移/删除调用者并加 guard，再删除符号。
   - 发现设计与代码事实冲突：先更新设计和验收，再实现；重大业务变化请求用户确认。

不得机械按预设阶段推进，不得为了“完成”跳过失败证据。

六、架构与 Ponytail 硬门

1. server.py 只负责 route wiring、依赖组装和 HTTP mapping。
2. 业务逻辑放 services；SQL/schema 放 repository；worker 不依赖 Application/HTTP/auth/route。
3. service 构造函数接收明确依赖，不接收整个 Application。
4. transactional writer 在同一 PostgreSQL 事务写 canonical fact、owner version、OA dirty scope 和 durable outbox。
5. 非事务 refresh 只能走 ReadModelRefreshGateway/scope policy registry。
6. Redis 只能位于 fresh gate 后；RabbitMQ 只是可选 wakeup，不是事实源。
7. 普通变化只刷新精确 OA 月份；all 仅用于初始化、回填、显式修复和可观测的 scope_resolution_failed safety path。
8. read model scope rows replace、scope metadata、actual version 必须原子 publish；旧 event 不能清新 dirty scope。
9. all 查询和 ETag token 从 expected canonical months、scope versions、dirty/outbox 的并集批量证明；不能扫描全量 rows 来证明 freshness。
10. 只允许设计中三个有当前证据的新组件：
    - OA payment-status PostgreSQL snapshot。
    - OA PostgreSQL-only projector。
    - 复用 RuntimeWorker 的 OA 专属进程/配置。
11. ETag、条件 GET、queue coalescing 和 operation barrier 复用标准/既有能力，不创建第二状态 API。
12. 禁止 SSE/WebSocket、新 event bus、新 CDC 平台、新通用 version service、Redis payload cache、预计算 filter-options 表、cursor pagination、预建 worker pool和无 EXPLAIN 证据的索引/分区。
13. 删除优先于兼容。禁止 parallel old path、live fallback、stale payload fallback、兼容 filter endpoint 和 feature flag 双读。
14. 如果当前设计无法在不增加上述复杂度的情况下达标，必须先提供生产/本地证据和最小替代方案，再请求用户决定。

七、必须闭合的实现合同

主控不能把下面内容机械拆成预生成 prompts；它们是最终 completion checklist，下一 prompt 仍由当前证据决定。

1. Dependency writer inventory
   - completed OA、admission、payment status、Workbench relation、pending relation、银行、发票、规则全部写入口。
   - 每个入口的 tenant、input/output、owner version、受影响 OA 月份、事务和 outbox 责任。
   - whole-repo guard 不允许未登记 direct canonical write。

2. OA integration boundary
   - 外部 Mongo/MySQL I/O 移出 RM worker。
   - payment-status snapshot 使用 tenant + flow_id 唯一身份。
   - 完整读取成功后才允许同事务 upsert、删除上游已消失记录、更新 watermark/version、enqueue months。
   - timeout、分页不完整、schema/response completeness unknown 时整轮不提交。
   - 重复/非法 flow_id 复用已验证业务规则，不猜优先级。

3. Exact scope and versions
   - tenant-aware dynamic source-version vector 覆盖设计列出的全部依赖。
   - 银行/发票/跨月 relation 用一次 indexed batch owner lookup 解析 OA 月份，不按事实自身月份猜测。
   - query expected provider 只读小型 version/watermark，不扫描业务事实。

4. OA-only projector and worker
   - PG-only、常数级批量 query，不存在 per-row I/O/N+1。
   - stale event admission check、并发新版本 CAS、空 scope 清理、原子 publish、崩溃幂等。
   - OA 从 invoice-usage-collection shared builder/handler/registry/manifest 中移除。
   - OA-only worker 使用现有连接预算，不挤压其它 worker。

5. Query/API/UI hot path
   - rows route 返回 rows、pagination、summary、view counts、filter config/options、freshness proof 和精确 operationBarrierTargets。
   - 删除 filter-options route/client、all_rows() 和 Python 全量分页。
   - 一次 compact gate/version query + 不超过两个有界 set-based data statements；以实际 EXPLAIN 决定，不强求单 SQL。
   - 200 ETag 包含 tenant、normalized query、contract revision、read-model version；正确 Cache-Control/Vary。
   - 304 只查有索引的 scope/version/dirty/outbox，不做 count/sort/JSON/facet aggregation。
   - 可见 tab 每 500ms 最多一个条件请求；隐藏时停止，恢复立即检查；query/contract 变化取消旧请求，晚到响应不能覆盖新 query。
   - 202 时立即隐藏旧 rows，等待精确月份 barrier；不等待 all，不显示旧快照。
   - detail endpoints 保持 lazy，并使用同一 dynamic fresh gate。

6. Audit
   - OA 文案：通过时明确“App 内部数据一致”；dirty/outbox 时显示校验中；fresh 后 integrity failure 展示去重中文样本；证据不足不能显示通过。
   - 外部 sync watermark/lag/reconciliation 与 App 内部证明分开。
   - OA 通过可选 formatter/wrapper 实现，shared PageAuditIcon 和其它页面默认输出不变。
   - Audit admin-only、repeatable-read、strict read-only，不 refresh/repair/write。

7. Legacy removal
   - 全量落实 performance-integrity-design.md 第 8 节清单。
   - 用 CodeGraph impact + whole-repo symbol/text scan 找入口、调用方、client、service、repository、worker、read model、tests、docs。
   - 迁移调用者后删除 production executable code；保留 immutable migrations/history/audit evidence。
   - 增加 boundary guards 防止旧 route/symbol/fallback 回流。

八、七类测试责任

实现工作必须逐类判断并报告：

1. Business core unit tests
   - tenant-aware scope、跨月 owner resolution、version vector、stale event/CAS、empty/tombstone、duplicate/invalid flow_id、idempotency。
2. Service-layer tests
   - snapshot replace/delete + version + outbox 原子性；partial external failure 无半写/误删；projector publish rollback；Audit read-only。
3. API contract tests
   - rows 聚合 payload、ETag/304、Cache-Control/Vary、auth before 304、202 exact targets、非法 query、权限、旧 filter route 不存在。
4. Read model/background worker tests
   - invalidation、pending/processing coalescing、PG-only dependencies、constant query count、empty scope、low-priority all、CAS、dedicated claim isolation。
5. Frontend interaction tests
   - loading/empty/error/refreshing、visible/hidden tab、ETag lifecycle、single in-flight request、late response、202 hide rows、barrier、filter/sort/page、OA Audit copy/samples。
6. End-to-end tests
   - open page -> canonical change -> month outbox -> OA worker -> conditional detection -> new rows -> Audit pass。
7. Existing feature regression
   - input/output invoice、Workbench relation、bank/invoice detail、shared Audit、permissions、other workers/pages/API latency and behavior。

不适用的类别必须给出理由；不能只覆盖 happy path。禁止 skip/xfail、弱 assertion、扩大 allowlist、删除旧测试或 ignore_errors 来伪造闭环。

九、验证顺序

每个 bounded prompt 运行最小相关验证；接近本地 closure 时按风险执行：

1. 目标 Python unit/service/API/read-model/worker tests。
2. 目标 Vitest/Playwright 和 TypeScript build。
3. bash scripts/verify.sh lint。
4. bash scripts/verify.sh backend。
5. bash scripts/verify.sh frontend。
6. bash scripts/verify.sh docs。
7. bash scripts/verify.sh runtime-check。
8. 在 worktree 状态允许且不会把其它 thread 的无关失败误归本任务时，运行 bash scripts/verify.sh all。
9. git diff --check。
10. 关键 SQL 的 EXPLAIN (ANALYZE, BUFFERS)、query-count 断言和生产等量级本地基准。

性能守门：

- fresh payload 至少 1000 次本地/测试请求样本。
- 普通 canonical mutation 至少 200 次本地端到端样本。
- 覆盖代表性月份、当前生产峰值并发和两倍数据/写入余量。
- 报告 p50/p95/p99、错误率、warm/cold-start。
- timeout、error 和 202 不得静默剔除。
- 本地结果只能标记 local performance gate，不得标记 production SLO proven。

十、部署门

满足以下全部条件后才进入 READY_FOR_UNIFIED_DEPLOYMENT：

1. 请求行为已实现，设计合同未被静默削弱。
2. 适用七类测试完成并通过，或环境性未运行风险明确。
3. 目标 lint/backend/frontend/docs/runtime/local performance gate 通过。
4. 旧 production runtime 路径按清单清零并有 guard。
5. input/output invoice 和其它页面隔离回归通过。
6. docs/modules、boundary-io、read-model contracts、worker governance、API contracts、state machine、tests、implementation notes 按事实同步。
7. worktree 无本任务产生的临时文件、dead code、unused imports/dependencies 或未解释修改。

达到后输出：

- Status: READY_FOR_UNIFIED_DEPLOYMENT
- Result
- Exact files changed by this goal
- Preserved unrelated worktree changes
- Tests added/changed，按七类映射
- Verification commands/results
- Local performance evidence
- Docs impact
- Required migration/env/worker/release changes for the future unified deployment
- Rollback instructions
- Production validation runbook
- Remaining risks

然后停止。不得部署，不得 complete，不得 blocked，不得继续生成 prompt。

十一、统一部署后恢复

只有用户明确确认统一部署已完成后，恢复同一个 goal，并生成唯一下一 prompt：验证 deployed release identity、migration/schema、OA-only worker、shared worker OA exclusion、dirty/outbox 和版本合同。不要部署。

之后按真实证据一次一个 prompt：

1. 只读生产 Audit、App Status、worker heartbeat、dirty/outbox、source versions、sync watermark/reconciliation。
2. 只读 fresh rows/ETag 304/API latency 探针。
3. 用自然发生的 canonical changes 和 trace/source version 采集 commit-to-visible 样本。
4. 若自然样本不足，停在 NEEDS_PRODUCTION_WRITE_AUTHORIZATION，不自行制造数据。
5. 若生产发现缺陷，返回本地修复循环，完成后再次停在 READY_FOR_UNIFIED_DEPLOYMENT，等待下一次外部统一部署。

生产只读探针必须从低频、单并发开始，观察错误率和其它页面延迟后再采样；不得把性能验证变成未经授权的压力测试。样本量不足以支持 p95/p99 时明确标记 evidence insufficient，不用少量样本宣称通过。

只有以下全部满足才 DONE：

- 用户确认目标修复 release 已统一部署。
- migration、env、worker registration/manifest/systemd 状态与文档一致。
- OA worker 不访问 Mongo/MySQL；shared invoice worker 不 claim OA event。
- queue drained、read model fresh、source versions current、Audit integrity pass。
- fresh API production p95 <= 250ms、p99 <= 500ms，ETag 304 p95 <= 30ms。
- 普通变化 commit-to-visible production p95 <= 1s；失败/超时/202 未被剔除。
- 其它页面无生产回归。
- 无未授权生产写入、未披露风险或待执行部署动作。

十二、首个 bounded execution prompt

[BOUNDED EXECUTION PROMPT 1]

Goal:
在不修改代码、不部署、不访问生产的前提下，完成 implementation readiness、dirty-worktree conflict、dependency writer 和 legacy runtime path 的事实审计，为第一个安全实现 slice 生成唯一下一 prompt 所需证据。

Why this is the highest-risk next gap:
当前设计跨 OA integration、canonical writers、read model、worker、API、frontend 和 Audit；在多个 thread 共用 main worktree 时，先确认真实调用图、文件重叠、版本/outbox 责任和旧路径调用者，才能避免覆盖用户修改或在错误边界打补丁。

Evidence/source files:
- 本 prompt 第四节必读文档。
- docs/modules/oa-pending-payments/performance-integrity-design.md。
- CodeGraph 对 OaPendingPaymentsPage、OaPendingPaymentApiRoutes、OaPendingPaymentReadModelService、OaPendingPaymentQueryService、OaPendingPaymentReadModelRepositoryPort、InvoiceUsageCollectionSqlProjectionBuilder、InvoiceUsageCollectionReadModelRefreshService、RuntimeWorker、RuntimeQueueRepository、PageAuditIcon、OA sync/payment status/relation writers 的 context/impact/explore。
- 当前 tests、worker registry/manifest/deploy config 和 literal legacy symbol scan。

Allowed files/modules:
- 只读全仓。
- 本轮结论只维护在 /goal 内部 cycle state 和输出中；不得修改 runtime code、tests、长期 docs 或共享 .planning/STATE.md/ROADMAP.md，也不得新建临时 readiness 文件。

Protected/forbidden:
- 所有当前 worktree 修改。
- 不编辑、不格式化、不 stage/commit、不切分支、不部署、不访问生产。

Exact actions:
1. 记录 git status --short、目标文件 existing diffs 和可能冲突的其它 thread 修改。
2. 建立 affected module/I-O/dependency map。
3. 建立 dependency writer inventory，标明 version/scope/outbox/transaction 当前状态与缺口。
4. 建立 design 第 8 节 legacy runtime inventory，标明 symbol、调用者、替代边界、删除条件。
5. 核对 queue pending/processing coalescing、stale event admission、complete CAS 和 publish transaction 真实合同。
6. 核对 combined rows/ETag、all-token、exact barrier targets 和 OA-only Audit formatter 的最小实现边界。
7. 判断第一个实现 slice：必须独立、可验证、不会与其它 thread 冲突，并优先关闭最高风险一致性缺口。

Verification:
- CodeGraph/rg evidence complete。
- git diff --check（只检查现有状态，不修改）。
- 不运行会写文件或访问生产的命令。

Stop condition:
输出结构化 readiness report：known facts、conflicting files、writer inventory、legacy inventory、architecture gaps、test/docs impact、first safe implementation slice、exact allowed files、verification plan。然后 REVIEW 并根据证据生成且立即执行唯一下一 bounded prompt；若存在不可安全合并的语义冲突，停在 WORKTREE_CONFLICT。
```

## 主控每轮审阅模板

```text
上一轮 bounded prompt：
- Prompt number:
- Goal:

执行结果：
- Completed:
- Files changed:
- Tests/docs changed:
- Verification:

审阅：
- Architecture/I-O gates:
- Worktree isolation:
- Seven-category coverage:
- Legacy deletion status:
- Performance evidence:
- New facts/deviations:
- Remaining risks:

Decision:
- CONTINUE | WORKTREE_CONFLICT | READY_FOR_UNIFIED_DEPLOYMENT | NEEDS_PRODUCTION_WRITE_AUTHORIZATION | CONTINUE_AFTER_PRODUCTION_FINDING | DONE

唯一下一 bounded execution prompt：
“仅在 Decision=CONTINUE 时生成并立即执行。”
```
