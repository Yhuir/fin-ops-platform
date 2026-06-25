# Prompt: Read Model Main Branch Closure Controller

**Status:** User-authorized specialized entrypoint
**Use with:** `/goal`
**Purpose:** Run a high-efficiency GSD controller on `main` to complete the Read Model modularization refactor for all page/domain read models. The controller works in waves, generates the next executable prompt from verified state, immediately executes it, and repeats until read model local implementation, tests, docs, legacy retirement and production freshness evidence are closed or a precise hard stop is reached.

## Important Main Branch Override

The repository's existing autonomous workflow documents `dev` as the default implementation branch. For this specific read model closure run, the user explicitly authorized direct `main` work. This prompt is therefore an intentional exception to `.planning/refactors/modular-io-boundaries/09-DEV-BRANCH-WORKFLOW.md`.

Main branch work is allowed only with the safeguards below:

- Start on `main`.
- Ensure `main` is clean and fast-forward synced with `origin/main`.
- Create and push a backup branch before the first implementation commit.
- Never force-push.
- Never rewrite history.
- Never commit unrelated dirty files.
- Commit only verified, reviewable wave results.
- Stop on conflicts, ambiguous ownership, secrets, unbounded production mutation, or failed verification that cannot be repaired in the same wave.

## How To Use

Paste the following prompt into one Codex thread as the only starting prompt:

```text
/goal

你是 Codex，工作目录是 /Users/yu/Desktop/fin-ops-platform，目标分支是 main。

Objective:
完成全量 Read Model 模块化重构闭环。所有页面/domain read model 必须具备清晰模块边界和 I/O 合同，默认目标态是 Partitioned + Scoped + Incremental Projection。例外必须显式登记、测试和证明。完成后不能存在已知 stale-as-fresh、旧链路污染新链路、未登记 dirty/outbox/readiness 写入、未证明 freshness 的页面数据，不能把不 fresh 的 payload 展示成 fresh。

重要现实约束:
- 不要承诺“永远没有 bug”。你必须把目标解释为：零已知 read model bug、零已知 stale-as-fresh、所有合同和验证门禁通过、所有无法本地证明的生产 freshness 证据已实际收集或精确 hard-stop。
- 不允许用状态文件、prompt 或“计划完成”代替代码和验证。
- 不允许只做小修小补。如果分析发现多个模块共享同一个边界问题，应按 wave 批量修复。
- 不允许无边界大爆炸重构。每个 wave 必须有明确 owner、输入、输出、影响范围、测试和回滚点。
- 你必须在 main 上直接推进，这是用户授权的例外策略。不要切到 dev，不要把实现提交推到 dev。

最终完成定义:
1. `READ_MODEL_MANIFEST` 覆盖所有页面/domain read model，并与 App Status registry、worker registry、RabbitMQ dispatch、scope policy、docs 和 tests 保持一致。
2. 每个 read model 都有明确合同:
   - read_model_key
   - scope_type
   - partition key
   - scoped incremental projection strategy
   - all/parent scope semantics
   - source_versions/schema_version proof
   - freshness proof
   - query owner
   - route/API owner
   - service owner
   - repository port owner
   - physical SQL owner
   - refresh producer owner
   - worker owner
   - force refresh entry
   - operation barrier targets
   - frontend stale/refreshing/fresh behavior
   - permission/audit owner
   - tests
   - legacy path status
3. 默认目标态:
   - Partitioned scoped read model.
   - Scoped incremental projection.
   - Full rebuild 只能作为 backfill、repair、cold start 或受控 runbook fallback，不能作为普通写后同步路径。
4. Partitioned + Scoped + Incremental Projection 的精确定义:
   - Partitioned:
     - 页面 read model 的投影存储、readiness、source_versions、schema_version、row_count、generated_at 和错误诊断必须按有界 partition key 切分。
     - partition key 必须来自业务事实边界，例如 month、account、direction/filter/month、project scope、status group、domain object、config version 或明确 all-only scope。
     - 页面热路径查询只能读取目标 partition、目标 scope、或已物化 parent aggregate；不得在生产热路径扫描全量 canonical facts、全量 JSON snapshot、全量 memory state 或无界 legacy collection。
     - SQL/index 必须匹配 scope key 和页面筛选/排序/分页；高行数路径必须能用 query plan 或等价证据证明不是全表热扫描。
   - Scoped:
     - 每个 query、write result、dirty scope、outbox event、worker job、force refresh、operation barrier target 和 frontend refetch 都必须映射到明确 `scope_type + scope_key`。
     - scope 必须先经过 `ReadModelScopePolicyRegistry` normalize/validate/dedupe；非法 scope fail fast，不能降级成 broad `all`。
     - `all` 必须明确是 fan-out command、queryable parent aggregate、active generation aggregate、all-only projection 或 forbidden；禁止 fan-out-only `all` 写假 fresh readiness。
     - parent/aggregate scope 必须等待 child shard fresh，或拥有独立真实 parent freshness proof。
   - Incremental Projection:
     - 普通业务写入只计算 affected scopes，只 dirty 受影响 scope，只重建受影响 projection partition 和必要 parent aggregate。
     - builder/worker 必须是幂等的，能对单个 scope upsert、delete、prune obsolete shard，并能在 partial failure 后 retry/recover。
     - source_versions/schema_version 必须随 projection 一起发布；dependency not fresh 必须 defer/retry，不能写 failed/fresh 假状态。
     - full rebuild 只能由 cold start、backfill、repair、migration 或受控 force refresh runbook 触发；普通写后同步不得全量 rebuild。
5. 最低完成等级:
   - PSCIP-L0 contract-only: 只在 manifest/docs 中登记，不算完成。
   - PSCIP-L1 guarded contract: manifest、scope policy、worker registry、docs、guard tests 对齐；仍不算实现完成。
   - PSCIP-L2 local runtime: route/query/service/refresh/worker 能按 scope 运行，fake/stub/API/contract tests 证明不会 stale-as-fresh；只能算 local implementation。
   - PSCIP-L3 physical modularization: repository port、物理 SQL owner、projection builder、refresh producer、worker/readiness、frontend barrier 都按 read model owner 收敛，旧链路被删除或 compat-only guard 隔离；这是 main implementation closure 的最低要求。
   - PSCIP-L4 production evidence: 在生产或等价真实 runtime 上证明 App Status、dirty/outbox、worker/readiness、关键页面 API 和高行数查询都按 scope fresh/converge；这是 global closure 的最低要求。
   - 本次主控目标是所有非例外 read model 达到 PSCIP-L4；例外 read model 必须达到等价 L4，且例外语义由 manifest/docs/tests/生产证据证明。
6. 高性能门槛:
   - 普通写入复杂度必须接近 `O(affected_scopes * scope_size + affected_parent_aggregates)`，不得接近 `O(all_rows)`。
   - 页面查询复杂度必须随目标 scope、分页大小和已物化 aggregate 缩放，不得随全库事实线性增长。
   - `all` 查询必须使用真实 parent aggregate、受控 shard union + pagination，或明确禁止；不得在请求热路径临时聚合所有 child rows。
   - 每个高行数 read model 必须有索引/查询计划/测试或生产采样证据，证明 scope filter、排序和分页走有界路径。
   - 缓存只能作为 fresh-gated 加速层；缓存 miss 后仍必须走有界 SQL/readiness 路径，不能 fallback 到全量 live scan。
   - 主控必须在 closure report 中列出每个 read model 的性能证据状态: `indexed-and-tested`、`query-plan-proven`、`production-sampled`、`needs-production-evidence` 或 `blocked`。
7. 禁止把以下情况当作完成:
   - 只有 manifest 字段，没有物理 storage/query/worker/freshness 证明。
   - repository port 存在，但底层共享 repository 仍新增未登记跨模块方法。
   - refresh 使用 gateway，但 scope 是 broad `all` 或由页面猜测。
   - API 默认缺失/unknown/stale 为 fresh。
   - worker 成功后没有 readiness/source_versions/schema_version proof。
   - 前端只 refetch 页面但不等待 operation barrier 或 fresh gate。
   - 生产缺 SQL view/repository 时 live rebuild 并返回 fresh。
8. 允许例外，但必须显式证明:
   - `workbench`: 保留 active generation 原子发布，不机械改成普通 projection。
   - `bank_account_balance`: all-only scoped projection。
   - `pending_invoice`: page-first explicit scopes，拒绝裸 `all`。
   - `cost_statistics`: month shards + queryable parent aggregate。
   - 任何新增例外必须先更新 manifest、scope policy、worker/readiness、docs 和 tests。
9. 所有页面读 API:
   - fresh 时必须有 expected source/schema proof 和 current-effective dirty/outbox/readiness proof。
   - stale/missing/failed/unavailable 时必须 fail closed 或返回 refreshing/blocked，不得返回 fresh 空 rows。
   - Redis 只能缓存 fresh gate 后 payload。
   - RabbitMQ 只能是 wakeup/transport，不是 freshness truth。
10. 所有写 API:
   - 写入成功和 read model 可见性分离。
   - 返回 affected scopes/months/version/job 或 operation barrier targets。
   - 前端必须等待或重读对应 read boundary；不能猜测同步完成。
11. 所有 refresh:
   - 非事务 refresh 必须通过 `ReadModelRefreshGateway` + scope policy registry。
   - 事务内 writer 必须承担等价 scope contract。
   - 业务 service 不得直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。
12. 所有 legacy path:
   - 删除，或隔离为 compat-only，或标记 blocked-by-human-gate。
   - 旧路径不得写 canonical facts、dirty scopes、outbox events、readiness、cache、App Status。
   - 保留路径必须有 owner、caller list、删除条件、静态 guard 和测试。
13. 完成后必须有生产 freshness 证据:
   - App Status 当前 read model scope 不应有未覆盖 blocker。
   - 关键页面 API 不返回 stale-as-fresh。
   - worker/outbox/dirty scope/readiness 事实链一致。
   - 没有 staging/local PGSQL_URL 时，使用已授权的 root SSH 生产受控证据，但不得输出 secret。
14. 服务器和数据库操作策略:
   - 默认 code-first。Partitioned、Scoped、Incremental Projection 的边界、I/O、storage owner、builder、worker、gateway、barrier、frontend behavior、tests、docs、migrations 和 runbooks 必须先在代码仓库中完成，不能靠手工进生产库修状态来代替重构。
   - 需要进入服务器/数据库的场景只包括: 应用 migration/schema/index/view/projection table 变更、受控 backfill/repair、读取 App Status/dirty/outbox/readiness/worker health、采集 query plan/latency/performance evidence、执行已写明 scope 的 safe smoke/force refresh。
   - 所有 schema/index/table/view/readiness 结构变化必须以 repo 中的 migration 或等价版本化脚本表达；所有 backfill/repair 必须有 runbook、明确 scopes、前置检查、回滚/清理策略和后置 freshness/performance 检查。
   - 涉及生产 storage/API/worker 切换时，必须使用可回滚 rollout 顺序: expand schema/index/projection storage -> deploy compatible writer/worker -> bounded backfill/repair explicit scopes -> switch read path/fresh gate -> verify App Status/API/performance -> contract/remove legacy。不得在旧 projection 尚未可回退前删除旧链路。
   - 生产 DB 直接操作默认只读；任何写操作必须是 bounded、idempotent、可审计、按 explicit scope 执行，并且来自已提交或已记录的 migration/runbook。禁止手工 update canonical facts、手工改 readiness/outbox/dirty scopes 来伪造 fresh、truncate/rebuild 全库 projection、无界 force refresh、打印 secrets 或导出敏感业务 payload。
   - root SSH 不是实现 PSCIP 的前置条件。如果无法登录 SSH/root，必须先完成代码层 PSCIP-L3: 代码、migration、测试、local/fake/staging verification、性能替代证据和生产验证 runbook。不能因为没有服务器权限而停止代码闭环。
   - PSCIP-L4 仍然要求生产或等价真实 runtime 证据。如果无法登录生产或缺少安全生产验证入口，只能把对应 read model 标为 `local-implementation-closed-production-evidence-needed` 或 hard-stop，不能声明 global closure。
   - 优先使用最小权限生产验证入口，例如只读 DB 用户、App Status API、安全 smoke command 或 systemd/worker health command；只有这些入口不足时才使用 root SSH。

主控职责:
- 你是 T0 controller，不是单个 worker。
- 你负责读取状态、制定 wave、生成 worker prompt、执行 worker prompt、审阅 diff、集成、验证、更新状态，再生成并执行下一轮 prompt。
- 如果 thread tools 可用，可以创建 worker threads；如果不可用，单线程执行，不要因此停止。
- worker 输出不是事实。必须由 T0 审阅代码、测试、状态和风险后才能接受。
- 每一轮必须以 verified commit、verified state-only reconciliation、production evidence defer/hard stop 之一结束。

Branch and git rules:
1. 起始检查:
   - `git status --short --branch`
   - `git fetch origin --prune`
   - `git switch main`
   - `git pull --ff-only origin main`
2. 如果工作区不干净，先分类 dirty files。不得覆盖、stash、reset、checkout、格式化或提交用户无关改动。
3. 第一次实现前创建备份分支:
   - `backup_branch="codex/backup-main-before-read-model-closure-$(date +%Y%m%d-%H%M%S)"`
   - `git branch "$backup_branch"`
   - `git push origin "$backup_branch"`
4. 后续所有实现提交直接落在 `main`。
5. 每个 wave 提交前:
   - review diff
   - no secrets
   - no unrelated staged files
   - targeted tests passed
   - docs impact handled
   - `git diff --check`
   - staged 后 `git diff --cached --check`
6. 推送:
   - `git push origin main`
   - 禁止 `--force` / `--force-with-lease`
7. 如果 push 被拒绝:
   - `git fetch origin main`
   - 只允许 fast-forward / normal merge when safe and conflict-free。
   - 金融、read model、worker、permission、migration 冲突必须 hard stop，不得猜测解决。

必须先读:
- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/index.md`
- `docs/app-architecture/README.md`
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/modules/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- `docs/operations/runtime-worker-governance.md`
- `.planning/refactors/README.md`
- `.planning/refactors/modular-io-boundaries/README.md`
- `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`
- `.planning/refactors/modular-io-boundaries/01-CURRENT-STATE-AUDIT.md`
- `.planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
- `.planning/refactors/modular-io-boundaries/07-DOCS-GOVERNANCE.md`
- `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- all analysis/handoff files relevant to selected read model boundaries.

必须用 CodeGraph:
- `codegraph_status` first.
- `codegraph_context` for read model architecture.
- `codegraph_trace` when tracing write -> dirty/outbox -> worker -> projection -> readiness -> API.
- `codegraph_impact` before modifying shared symbols.
- Use `rg` only for literal strings, routes, fields, env keys, read model keys and legacy labels.

Initial full read model closure reconciliation:
在任何实现前，生成一个新的 commit-backed report:
`.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-<date>.md`

该 report 必须包括:
1. 当前 main commit 和 backup branch。
2. 当前 14 个 read model 的 closure matrix:
   - key
   - page/domain
   - strategy
   - exception status
   - query owner
   - route/API owner
   - repository port owner
   - physical SQL owner
   - refresh producer owner
   - worker owner
   - freshness proof
   - PSCIP level: L0/L1/L2/L3/L4
   - partition storage proof
   - scoped query proof
   - incremental builder proof
   - index/query-plan/performance proof
   - force refresh
   - operation barrier
   - frontend behavior
   - legacy path status
   - production evidence status
3. 每个模块分类:
   - `closed`
   - `local-implementation-closed-production-evidence-needed`
   - `needs-repository-physical-split`
   - `needs-refresh-producer-convergence`
   - `needs-query-fresh-gate-convergence`
   - `needs-operation-barrier-closure`
   - `needs-frontend-freshness-closure`
   - `needs-legacy-removal`
   - `needs-worker-readiness-closure`
   - `blocked`
4. 旧代码污染清单:
   - `server.py`
   - `postgres_repositories/read_models.py`
   - direct `ReadModelRefreshGateway` call sites
   - direct dirty/outbox SQL
   - legacy/local/live scan fallback
   - stale-as-fresh paths
   - frontend default fresh assumptions
5. 高效率 wave plan。

High-efficiency wave policy:
- 不要为每个 read model 单独做一个微小提交。
- 按边界成组推进，每个 wave 可以覆盖多个 read model。
- 推荐 wave 顺序:
  1. Global contract and guard reconciliation.
  2. Physical SQL owner split from `postgres_repositories/read_models.py`.
  3. Refresh producer convergence for every read model.
  4. Query fresh gate convergence and stale-as-fresh removal.
  5. Incremental projection builder and parent/all aggregate convergence.
  6. Operation barrier and write response target convergence.
  7. Frontend freshness UX convergence for all affected pages.
  8. Legacy path retirement/quarantine from `server.py` and old services.
  9. Worker/readiness convergence and production evidence tooling.
  10. Production freshness/performance evidence sweep.
  11. Global closure audit.
- A wave can touch many files if the boundary is coherent and tests are strong.
- A wave must not mix unrelated boundary types just to reduce commit count.
- 每个 wave 必须有 clear rollback point and commit.

Wave acceptance checklist:
每个 wave 完成前必须证明:
- No known stale-as-fresh.
- No new direct dirty/outbox SQL outside allowed owners.
- No new unregistered read model key/scope/event.
- No new broad full rebuild as ordinary write-after-sync path.
- No `all` fake fresh.
- No hot-path full-table/full-snapshot/live-scan fallback for production page reads.
- Every touched read model has a stated PSCIP level and a concrete next action to reach L4.
- Every touched high-row query has an index/query-plan/test/production-sample evidence path.
- No Redis/RabbitMQ freshness truth.
- No worker dependency on `Application`, HTTP, route modules or auth internals.
- No frontend defaulting unknown/stale/missing to fresh.
- Existing API response shape preserved unless explicitly documented and tested.
- Seven test categories evaluated; applicable tests added/updated.
- Docs impact handled.

Testing policy:
Use the smallest reliable tests, but do not under-test shared boundaries.
Required baseline after global/shared changes:
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v`
- targeted service/API tests for touched modules
- targeted frontend tests for touched pages, or explain why frontend unaffected
- targeted repository/query-plan or fake repository contract tests for touched physical SQL owner splits
- performance evidence for touched high-row read paths: local `EXPLAIN` when available, fake query contract when DB unavailable, and production sample after local closure
- `bash scripts/verify.sh docs`
- `git diff --check`
If a command is unavailable or too broad, run the closest targeted substitute and record why.

Production freshness evidence:
After local implementation closure, perform a production evidence sweep using authorized root SSH only when bounded and non-secret:
- inspect App Status read model scopes
- inspect dirty scopes/outbox current-effective blockers
- inspect worker health/heartbeat for read model workers
- inspect query latency or available query-plan evidence for high-row scoped reads
- run deployed safe read-only health/smoke commands if available
- run bounded force refresh / repair only with a written runbook, explicit scopes, rollback/cleanup and post-checks
Do not print env secrets, DSNs, tokens, cookies, private keys, raw sensitive payloads or broad production data.
Do not perform manual production DB writes outside committed migrations or written bounded runbooks. If SSH/root or production DB access is unavailable, complete code-level PSCIP-L3, commit migrations/runbooks/tests, and mark PSCIP-L4 evidence as explicitly deferred or hard-stopped.

Hard stop gates:
Stop and report if:
- main cannot fast-forward sync safely.
- backup branch cannot be created/pushed.
- worktree has unrelated dirty files that make safe commit impossible.
- production operation would require secrets or broad destructive mutation.
- production closure would require manual DB state edits instead of migration/runbook-backed operations.
- SSH/root or DB access is unavailable after code-level closure and no equivalent production-safe verification path exists; report PSCIP-L3 complete with exact PSCIP-L4 evidence gap instead of claiming global closure.
- read model scope contract is ambiguous and cannot be inferred from source/docs/tests.
- tests fail and cannot be fixed without expanding beyond the selected wave.
- a change would alter business behavior/API shape without clear requirement and tests.
- merge conflict touches finance/read model/worker/permission/migration logic.

State updates:
Because this is a main-branch read model closure run, update or create read-model-specific state artifacts instead of corrupting the old dev-oriented queue semantics:
- `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-<date>.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-<N>-<slug>.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
If updating `MODULE-QUEUE.md` or `STATE.md`, explicitly label entries as `main-read-model-closure` and do not imply old dev workflow is still active.

Next prompt loop:
At the end of every wave:
1. Summarize completed wave.
2. Update analysis and journal.
3. Generate the next executable prompt in `NEXT-PROMPT.md`.
4. Immediately execute that next prompt unless a hard stop was hit.
5. Do not stop after writing a plan if safe implementation work remains.

Final answer requirement:
When complete, report in Chinese:
- final main commit
- backup branch
- changed files summary
- per-read-model closure matrix
- tests added/changed
- seven test category coverage
- verification commands
- production evidence collected
- PSCIP L4 evidence per read model, or exact hard-stop reason
- performance evidence and remaining high-row risks
- whether server/DB access was used; if yes, which read-only checks or bounded migration/runbook operations were executed; if no, which production verification runbook remains
- any exact deferred/hard-stop items
- why no known stale-as-fresh path remains
- why old code cannot pollute the new read model chain

Start now with main branch sync, backup branch creation, full read model closure reconciliation, then execute the first high-efficiency wave.
```
