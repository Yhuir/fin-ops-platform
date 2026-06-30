# Prompt: Workbench Main Closure Controller

**Status:** User-authorized specialized entrypoint
**Use with:** `/goal`
**Purpose:** Run a high-throughput GSD controller to fully close Workbench modularization for `reconciliation-workbench` and `workbench-relations`, including module split, boundary definition, I/O contracts, old-path retirement, tests, docs, state-machine updates, and production validation evidence.

## Core Judgment

Workbench is the next high-risk modularization target because it concentrates route handlers, relation mutations, read/write facade behavior, frontend state, read model freshness, operation barriers, canonical facts, and old compatibility paths.

Treat `reconciliation-workbench` and `workbench-relations` as one Workbench risk cluster:

- `reconciliation-workbench` is the highest-risk module.
- `workbench-relations` is the most urgent modularization module inside the cluster.
- The first queue row to reconcile is `server-py:workbench-pair-relation-row-mutation-audit` unless current evidence proves a different Workbench row is the first unclosed blocker.

This is not a file-splitting exercise. Closure means the Workbench business boundary is proven by code ownership, I/O contracts, tests, static guards, docs, state-machine evidence, and production/runtime validation.

## Throughput Mandate

Optimize for short elapsed time without creating an unreviewable rewrite.

- Work in macro-waves, not one helper or one route at a time.
- Batch all Workbench route-owner extraction that shares the same rollback point.
- Batch relation command/read/history/fan-out boundary work when the same owner and tests cover the surface.
- Batch old-path deletion, static guards, docs, and queue-state updates by boundary class.
- Verification runs at wave gates. Use narrow syntax/import checks during editing only when they prevent wasted work.
- Do not repeatedly stop after analysis. If the analysis identifies a safe implementation wave, execute that wave in the same run.
- Do not generate a static backlog and stop. Generate exactly one next executable prompt from the completed state, then execute it immediately unless a hard stop gate is hit.
- Prefer 2-4 parallel read-only or non-overlapping worker threads when useful. Do not create more than 5 workers in one wave. Do not parallel-edit `server.py`, shared read model runtime files, or shared route wiring.
- Use a single controller as the decision owner. Worker outputs are evidence, not authority, until the controller reviews diffs, tests, and handoff claims.

Recommended macro-wave order:

1. Workbench current-state reconciliation and gap matrix.
2. Workbench route/handler ownership extraction from `server.py`.
3. Relation command/write owner closure.
4. Relation read/history/projection/fan-out owner closure.
5. Workbench read model/freshness/operation barrier I/O closure.
6. Frontend Workbench API/page state boundary closure.
7. Old path deletion or compat-only quarantine with static guards.
8. Docs, module boundary, inventory, queue and state-machine convergence.
9. Local full verification sweep.
10. Production evidence sweep with approved bounded root SSH validation.
11. Final closure audit and completion report.

## Start Prompt

Paste this whole section into Codex as a `/goal` prompt:

```text
/goal

你是 Codex，工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：使用 GSD 闭环工作流，完全关闭 Workbench 模块化重构。目标模块是 `reconciliation-workbench` 和 `workbench-relations`。必须完成：
1. 模块化代码重构；
2. 模块边界定义；
3. 输入/输出 I/O 合同设置；
4. 旧路径、旧模块代码、旧写入/读取/兼容路径的删除、隔离或有证据的 compat-only 退役计划；
5. 测试、静态守卫、文档、GSD 状态机、生产验证证据闭环。

最高风险模块是 `reconciliation-workbench`。
最需要模块化的模块是 `workbench-relations`。
把它们作为同一个 Workbench 风险簇处理。

运行方式：
- 你是 T0 主控，不是普通 worker。
- 一次只生成一个下一步 prompt。
- 每个 prompt 必须由上一次 prompt 的实际完成状态、验证结果、diff、state update 和 blocker 决定。
- 写完 `NEXT-PROMPT.md` 或任意下一步 prompt 后，除非命中 hard stop，必须立即执行它。
- 不要把“生成 prompt”当作完成。prompt 是控制产物，不是交付物。
- 不要一点一点做小改。使用可回滚、可验证的 macro-wave，大批量推进同一边界类。
- 不要做无法审查的一次性全仓重写。每个 wave 必须有清晰 owner、文件范围、回滚点和验证门。

分支和工作树安全：
- 先运行 `git status --short --branch`。
- 如果当前工作树有未提交改动，先分类每个改动是否属于本次 Workbench 重构。
- 不要覆盖用户已有改动。
- 如果存在与 Workbench 重构无关的 dirty files，或者无法证明 dirty files 是本轮产生的，implementation hard stop。只允许写一份阻塞报告和下一步要求，不允许改业务代码。
- 如果工作树干净，切到 `dev` 并同步：
  `git fetch origin --prune`
  `git switch dev`
  `git pull --ff-only origin dev`
- 如果没有本地 `dev` 但存在 `origin/dev`，可在干净工作树上 `git switch -c dev origin/dev`。
- 不要在 `main` 上做 Workbench implementation。
- 不要 force-push、rebase、reset、checkout --、删除分支或 revert 用户改动。
- 每个 macro-wave 结束后，只有验证通过才能 commit。commit 后推送 `origin/dev`。

GSD 主循环：
1. 读取必需上下文。
2. 运行 commit-backed current-state reconciliation，不信任记忆或单个 state 文件。
3. 建立 Workbench gap matrix，覆盖 code/docs/tests/static guards/production evidence。
4. 选择最大的安全 Workbench macro-wave。
5. 写当前 wave 的 pre-implementation analysis，包含 owner、目标 owner、输入、输出、state、events、read model/freshness、operation barrier、permissions、audit、tests、docs impact、old-path deletion/compat criteria、rollback/defer criteria、out-of-scope。
6. 执行该 wave。
7. 运行 wave verification。
8. 更新模块 docs、boundary-io、测试矩阵、GSD state files、`MODULE-QUEUE.md`、`STATE.md`、`JOURNAL.md`、`NEXT-PROMPT.md`。
9. commit/push verified wave。
10. 由刚完成的状态生成 exactly one next prompt。
11. 立即执行下一 prompt。
12. 重复直到本目标完全闭环，或遇到真实 hard stop。

必须先读的仓库事实源：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/index.md
- docs/app-architecture/README.md
- docs/app-architecture/pages.md
- docs/app-architecture/runtime-and-ownership.md
- docs/architecture/module-boundaries/README.md
- docs/architecture/module-boundaries/inventory.md
- docs/architecture/module-boundaries/read-model-contracts.md
- docs/architecture/module-boundaries/canonical-facts.md
- docs/modules/README.md
- docs/modules/reconciliation-workbench/README.md
- docs/modules/reconciliation-workbench/boundary-io.md
- docs/modules/reconciliation-workbench/state-machine.md
- docs/modules/reconciliation-workbench/tests.md
- docs/modules/reconciliation-workbench/e2e-spec.md
- docs/modules/reconciliation-workbench/e2e-coverage.md
- docs/modules/workbench-relations/README.md
- docs/modules/workbench-relations/boundary-io.md
- docs/modules/workbench-relations/state-machine.md
- docs/modules/workbench-relations/tests.md
- docs/modules/read-models/boundary-io.md
- docs/modules/runtime-workers/boundary-io.md
- docs/operations/runtime-worker-governance.md
- .planning/refactors/README.md
- .planning/refactors/modular-io-boundaries/README.md
- .planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md
- .planning/refactors/modular-io-boundaries/01-CURRENT-STATE-AUDIT.md
- .planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md
- .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md
- .planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md
- .planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md
- .planning/refactors/modular-io-boundaries/07-DOCS-GOVERNANCE.md
- .planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md
- .planning/refactors/modular-io-boundaries/autonomous/STATE.md
- .planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md
- .planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md
- .planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md
- 最新的 Workbench/reconciliation/workbench-relations/server-py/read-model/canonical-facts analysis、handoff、final report 文件。

使用 CodeGraph：
- codegraph_status 先确认索引健康。
- codegraph_context 查询 Workbench、Workbench relations、server.py Workbench handlers、relation command/read facades、read model/freshness/barrier flows。
- codegraph_trace 用于关键流：route -> service/facade -> repository/canonical facts -> dirty scope/outbox -> worker/read model -> API/frontend freshness。
- codegraph_impact 用于修改共享 symbol 前的影响面判断。
- rg 只用于 literal strings、routes、test names、状态字段、旧路径标签和文件清单。

Workbench 关闭定义：
- `server.py` 只保留 route registration、dependency assembly、request/session/auth extraction、HTTP response mapping、明确标注的 compat-only wrapper 和删除条件。
- Workbench route behavior 必须进入 Workbench route owner、action owner、service/facade 或等价边界。
- Workbench relation mutation 只能通过明确的 relation command owner；非 owner 不能直接写 relation canonical facts、dirty scopes、outbox、readiness、cache 或 App Status。
- Workbench relation read/history/projection/fan-out 必须有明确 read owner、repository/projection owner、read model/freshness owner 和 tests。
- Workbench I/O 必须定义输入、输出、state、events、read model scope、freshness/readiness、operation barrier targets、permissions、audit、frontend refetch/stale/refreshing/fresh behavior。
- Old paths 必须删除；确实不能删的必须 compat-only，列出 owner、caller inventory、remaining use、deletion condition、static guard 和 next removal prompt。
- 不允许把旧生产路径藏在 wrapper、fallback、test-only branch、dev helper 或未登记 migration script 里继续影响生产链。
- 不允许 stale-as-fresh。
- 不允许绕过 `ReadModelRefreshGateway`、scope policy registry、runtime queue、canonical facts owner 或 relation command owner。
- Worker 不得依赖 `Application`、HTTP、route module、auth internals 或 response object。
- 文档必须与代码一致，尤其是 `docs/modules/reconciliation-workbench/boundary-io.md` 和 `docs/modules/workbench-relations/boundary-io.md`。

第一轮建议目标：
- 从 `server-py:workbench-pair-relation-row-mutation-audit` 做 commit-backed reconciliation。
- 如果它已经被代码和队列证据证明关闭，则选择下一个 Workbench/server-py/workbench-relations 未关闭高风险 row。
- 不要凭 state 文件直接跳过。必须以当前代码、tests、docs、queue 和 git evidence 交叉确认。

允许的高效率并行：
- 可并行做只读分析：route inventory、relation owner inventory、frontend API inventory、tests/static guard inventory、docs gap matrix。
- 可并行做非重叠实现：frontend mocked tests 与 backend static guards；docs matrix 与 route extraction analysis；service tests 与 old-path inventory。
- 不可并行编辑同一个文件或同一共享边界：`server.py`、route wiring、relation command owner、read model runtime shared files、GSD state files。
- Worker 不得创建 worker。
- T0 必须读取每个 worker final answer 和 diff，验证后才能采纳。

测试与验证要求：
- 先定位已有 Workbench/relation/read model/API/frontend tests。
- 每个 wave 至少运行对应最小可靠验证。
- 后端候选验证包括但不限于：
  - `PYTHONPATH=backend/src pytest tests/test_workbench_v2_api.py`
  - `PYTHONPATH=backend/src pytest tests/test_workbench_api.py`
  - `PYTHONPATH=backend/src pytest tests/test_workbench_relation_command_service.py`
  - `PYTHONPATH=backend/src pytest tests/test_workbench_relation_read_facade.py`
  - `PYTHONPATH=backend/src pytest tests/test_workbench_relation_sql_projection.py`
  - `PYTHONPATH=backend/src pytest tests/test_platform_runtime_boundary_guards.py`
  - 任何新增/受影响的 relation、read model、operation barrier、worker、API contract tests。
- 前端候选验证包括 Workbench API/page/component mocked tests；如果 touched frontend，运行相关 npm/vitest target。
- Docs 验证优先运行仓库已有 docs verify，例如 `bash scripts/verify.sh docs`；若命令不存在，记录实际可用的 docs check。
- 最终本地关闭前必须运行一组覆盖 Workbench 后端、前端、static guard、docs 的 full target gate。
- 不要跳过失败测试、不要放松断言、不要用 `ignore_errors=True` 掩盖清理/worker/background job 问题。

生产验证授权：
- 用户已明确批准：为了让 Workbench 模块化重构完全闭环，可以 SSH root 进入生产服务器做生产验证。
- 这不是任意生产修改授权。默认只允许 read-only evidence。
- root SSH 可用于确认 deployed version、systemd/worker 状态、App Status/readiness、read model dirty/outbox 状态、日志中的 Workbench relation/readiness 错误、bounded API/runtime evidence。
- 生产控制类或写入类验证必须满足全部条件：
  1. 本地代码、测试、docs、static guards 已经关闭；
  2. 先写生产验证 runbook 到 `.planning/refactors/modular-io-boundaries/production-evidence/` 或等价现有 evidence 目录；
  3. runbook 写明命令、目标对象选择标准、影响范围、预期证据、回滚/清理、post-check、stop gates；
  4. 操作必须可审计、可回滚、范围有界，不得批量重放、不消费未知队列、不跑无界修复脚本；
  5. 不输出 secrets、tokens、cookies、private credentials。
- 如果 SSH alias、host、credential 或生产入口无法从本机环境/部署文档安全确认，记录为 production evidence blocker，但继续完成所有 local closure。

Hard stop gates：
- 当前工作树有不属于本轮的 dirty files，且 implementation 会有覆盖风险。
- 当前不在 `dev` 且无法在干净工作树切换到 `dev`。
- CodeGraph 或代码证据无法确定关键 owner/caller，且继续会猜 API、DB 字段或 business state。
- 需要生产写入但无法定义可回滚对象、清理方式或 post-check。
- 测试失败且无法归类为无关既有失败。
- 改动需要改变业务口径、权限语义、数据修复策略、生产 migration 或用户可见行为，但没有明确合同支持。
- 需要删除旧路径但 caller inventory 证明仍有生产调用，且不能在同一 wave 迁移调用点。

每轮输出和状态更新：
- 写或更新 Workbench-specific analysis/handoff 文件，文件名含日期或 wave id。
- 更新 `MODULE-QUEUE.md` 对应 Workbench/server-py/workbench-relations rows。
- 更新 `STATE.md`、`JOURNAL.md`、`NEXT-PROMPT.md`。
- 如模块事实变化，更新：
  - `docs/modules/reconciliation-workbench/boundary-io.md`
  - `docs/modules/workbench-relations/boundary-io.md`
  - 相关 tests/state/e2e/implementation notes
  - `docs/architecture/module-boundaries/inventory.md` 或 read-model/canonical-facts docs（仅当事实变化）
- 每个 commit message 简洁说明 wave owner 和 verification。
- 每个 loop 结束必须是以下之一：
  1. 已验证并推送的 Workbench macro-wave；
  2. 已验证并推送的 state/docs-only reconciliation；
  3. local closure 完成后 production evidence precisely deferred；
  4. hard stop 报告，包含证据、完成百分比、阻塞原因、最小下一步。

最终完成标准：
- Workbench 两个模块的模块化代码边界、本地 I/O 合同、旧路径退役、测试、docs、GSD state 全部闭合。
- 没有生产可达旧路径可绕过新 Workbench relation owner 或 Workbench read/freshness owner。
- `server.py` Workbench 相关残留符合 route/http shell 定义，或有删除条件和 static guard。
- 本地 full target gate 通过。
- 生产 read-only evidence 通过。
- 任何生产 control/write evidence 如果确实需要，必须已按 runbook 执行并完成 post-check；如果安全条件不满足，必须记录为真实 blocker，而不是声称完全闭环。
- final report 用中文说明改了什么、删除了什么、保留了什么 compat-only、运行了哪些测试、生产验证证据是什么、剩余风险是否为 0。
```
