---
phase: quick-260812-roj-workbench-generation-scope-generation-st
plan: "01"
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
  - backend/src/fin_ops_platform/tools/prune_workbench_generations.py
  - deploy/oa/bin/finops-prune-workbench-generations.sh
  - tests/test_workbench_sql_runtime.py
  - tests/test_deploy_runtime_examples.py
  - docs/modules/reconciliation-workbench/boundary-io.md
  - docs/operations/runtime-worker-governance.md
autonomous: true
requirements:
  - QUICK-260812-ROJ
must_haves:
  truths:
    - "一次 Workbench generation retention 运行最多选择 500 个候选，并且候选先按 scope_key 隔离，再按每批 1～100 个 generation 删除。"
    - "每个同 scope generation 小批次使用独立事务；一个批次的锁等待或失败不会把全部 scope 候选捆绑在同一个长事务中。"
    - "CLI 在构造 repository 前为专用 PostgreSQL connection 设置默认 60 秒 statement timeout，并把默认 delete batch size 1 传入 repository。"
    - "版本化 wrapper 通过两个受控环境变量传递 delete batch size 与 statement timeout，默认分别为 1 和 60 秒。"
    - "active generation 保护、发布热路径不清理、keep_recent 至少为 1、默认 dry-run 和无生产数据库动作的合同保持不变。"
  artifacts:
    - path: backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
      provides: "按 scope 分组、按 generation 小批次独立事务执行的 retention repository"
      contains: "delete_batch_size"
    - path: backend/src/fin_ops_platform/tools/prune_workbench_generations.py
      provides: "专用 statement timeout 与 delete batch size CLI 合同"
      contains: "--statement-timeout-seconds"
    - path: deploy/oa/bin/finops-prune-workbench-generations.sh
      provides: "版本化运行 wrapper 的两项环境变量和参数透传"
      contains: "FINOPS_WORKBENCH_PRUNE_DELETE_BATCH_SIZE"
    - path: tests/test_workbench_sql_runtime.py
      provides: "repository 事务隔离、边界归一化、active 保护及 CLI 参数回归测试"
    - path: tests/test_deploy_runtime_examples.py
      provides: "部署 wrapper 默认值与参数透传合同测试"
    - path: docs/modules/reconciliation-workbench/boundary-io.md
      provides: "Workbench generation retention 模块边界事实"
    - path: docs/operations/runtime-worker-governance.md
      provides: "retention timer 的运维批量与 timeout 合同"
  key_links:
    - from: backend/src/fin_ops_platform/tools/prune_workbench_generations.py
      to: backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
      via: "prune_workbench_generations(delete_batch_size=...)"
      pattern: "delete_batch_size=args\\.delete_batch_size"
    - from: backend/src/fin_ops_platform/tools/prune_workbench_generations.py
      to: backend/src/fin_ops_platform/services/postgres_connection.py
      via: "repository 构造前调用 set_statement_timeout_ms(seconds * 1000)"
      pattern: "set_statement_timeout_ms"
    - from: deploy/oa/bin/finops-prune-workbench-generations.sh
      to: backend/src/fin_ops_platform/tools/prune_workbench_generations.py
      via: "--delete-batch-size 与 --statement-timeout-seconds 参数"
      pattern: "--delete-batch-size"
---

<objective>
修正 Workbench superseded generation 定时清理的事务粒度与专用 SQL 超时：候选按 `scope_key` 分组，同一 scope 内按 generation 小批次删除，每批独立提交；CLI 和版本化 wrapper 显式配置 batch size 与 statement timeout。

Purpose: 避免最多 500 个跨 scope generation 被绑定在一个长事务中而造成锁等待、statement timeout 和大范围回滚，同时保持 active generation 原子发布与 retention 安全边界。
Output: repository 小批次事务实现、CLI/wrapper 参数链、定向回归测试，以及模块/运维长期事实文档。

锁定决策映射：
- LD-01：repository 新增 `delete_batch_size`，默认 1，归一化范围 1～100。
- LD-02：preview candidates 按 `scope_key` 分组；每个 scope 的 generation ids 分块；每块独立事务。
- LD-03：总 candidate limit 保持 500，不把一次运行扩成无界清理。
- LD-04：CLI 新增 `--delete-batch-size`（默认 1）和 `--statement-timeout-seconds`（默认 60），并在 repository 使用前调用现有 `PostgresConnection.set_statement_timeout_ms(...)`；默认调用值为 `60000`。
- LD-05：wrapper 使用 `FINOPS_WORKBENCH_PRUNE_DELETE_BATCH_SIZE:-1` 与 `FINOPS_WORKBENCH_PRUNE_STATEMENT_TIMEOUT_SECONDS:-60`，并传递两个 CLI flags。
- LD-06：保留 active-generation protection；不执行生产/数据库操作。

范围围栏：本计划不实现 `keep_recent_generations_per_scope=0`，不把 retention 接入 generation 发布后异步清理，不新增 worker/queue/cache/schema/migration/dependency，也不触碰用户现有无关 dirty worktree edits。
</objective>

<execution_context>
@/Users/yu/.codex/gsd-core/workflows/execute-plan.md
@/Users/yu/.codex/gsd-core/templates/summary.md
</execution_context>

<context>
@AGENTS.md
@.planning/STATE.md
@backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
@backend/src/fin_ops_platform/tools/prune_workbench_generations.py
@backend/src/fin_ops_platform/services/postgres_connection.py
@deploy/oa/bin/finops-prune-workbench-generations.sh
@tests/test_workbench_sql_runtime.py
@tests/test_deploy_runtime_examples.py
@docs/architecture/module-boundaries/read-model-contracts.md
@docs/modules/reconciliation-workbench/boundary-io.md
@docs/modules/read-models/boundary-io.md
@docs/modules/runtime-workers/boundary-io.md
@docs/operations/runtime-worker-governance.md

执行前先运行 `git status --short --untracked-files=all`，确认用户已有 dirty edits。只对本计划列出的七个文件做局部修改；其中 `docs/modules/reconciliation-workbench/boundary-io.md` 当前已有用户修改，必须保留并在现有内容上精确合并，禁止覆盖或回退任何无关 diff。
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: 按 scope 和 generation 小批次拆分 retention 事务</name>
  <files>backend/src/fin_ops_platform/services/postgres_repositories/read_models.py, tests/test_workbench_sql_runtime.py</files>
  <behavior>
    - Test 1: preview 返回多个 scope 的候选时，删除调用绝不把不同 `scope_key` 的 generation ids 放进同一批次；每个同 scope chunk 恰好进入一次独立 transaction。
    - Test 2: `delete_batch_size` 缺省为 1，传入小于 1 的值归一为 1，传入大于 100 的值归一为 100；chunk 顺序沿用 preview 的稳定 `scope_key`/时间顺序。
    - Test 3: 一次 prune 最多处理 500 个 preview candidates；dry-run 或无候选时不打开删除 transaction，`deleted_count=0`。
    - Test 4: 每个删除 chunk 只处理 preview 判定为 terminal `failed|superseded` 的 generation，最终 generation delete SQL 保留 `tenant_id='default'` 与 terminal-status 防护；`active|building` generation 不被删除。
    - Test 5: generation publish 路径继续不调用 retention；`keep_recent_generations_per_scope=0` 仍归一为 1，不能表示删除所有历史版本。
  </behavior>
  <action>
先扩展 `WorkbenchGenerationRetentionConnection` 测试 double，使其记录每次 transaction 的进入/退出和该事务收到的 generation ids；增加跨两个 scope、单 scope 多 generation、边界 batch size、dry-run/空候选、500 candidate 上限与 active 防护测试，再实现 LD-01、LD-02、LD-03、LD-06。

在 `PostgresReadModelRepository.prune_workbench_generations(...)` 增加 keyword-only `delete_batch_size: int = 1`。使用现有 `int_value` 做单一规范化，结果限定为 `1..100`，并把规范化值纳入返回 report，便于 dry-run/execute 都能观察实际策略。保留 preview 作为唯一候选 owner；候选总数限制为 500，不增加第二次候选查询或无界循环。按 preview 行的 `scope_key` 建立稳定分组，scope 之间不混批；每个 scope 内按规范化 batch size 对 generation ids 分块，并对每个 chunk 分别调用一次 `run_in_transaction(self._connection, delete_chunk)`，复用 `_delete_workbench_generations(...)` 的既有表删除顺序。`deleted_count` 只在所有 chunks 成功后按本次实际提交目标数报告；异常继续向上抛出，不能伪装整批成功或追加 fallback 重试路径。

不得移动 retention 到 `save_workbench_read_models`、generation activation/publish、worker 或 queue；不得删除/放宽 preview 和 final generation delete 的 terminal `failed|superseded`、scope 与 tenant guard；不得改变 keep-days、scope-key normalization、默认 dry-run 或 generation 表结构。明确不接受 `keep_recent=0` 语义。
  </action>
  <verify>
    <automated>PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_workbench_generation_retention_chunks_per_scope_in_independent_transactions tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_workbench_generation_retention_bounds_delete_batch_size tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_workbench_generation_retention_never_deletes_active_generations tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_retention_preview_allows_zero_keep_days tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_publish_leaves_generation_retention_to_the_timer -v</automated>
  </verify>
  <done>repository 默认逐 generation 独立事务；可配置 1～100 个 generation 的同-scope chunk；跨 scope 不混批；候选总量不超过 500；active generation、keep_recent>=1、dry-run 与 publish-path 隔离合同均有自动测试保护。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: 贯通 CLI、版本化 wrapper、合同测试与长期文档</name>
  <files>backend/src/fin_ops_platform/tools/prune_workbench_generations.py, deploy/oa/bin/finops-prune-workbench-generations.sh, tests/test_workbench_sql_runtime.py, tests/test_deploy_runtime_examples.py, docs/modules/reconciliation-workbench/boundary-io.md, docs/operations/runtime-worker-governance.md</files>
  <behavior>
    - Test 1: CLI 无参数运行仍为 dry-run，并向 repository 传 `delete_batch_size=1`；fake connection 在 repository 构造/调用前收到 `set_statement_timeout_ms(60000)`。
    - Test 2: CLI 显式 `--delete-batch-size 20 --statement-timeout-seconds 15` 时分别传给 repository 和 connection（`15000` ms），其他 keep/limit/execute 参数保持原合同。
    - Test 3: wrapper 文本包含 `DELETE_BATCH_SIZE="${FINOPS_WORKBENCH_PRUNE_DELETE_BATCH_SIZE:-1}"` 与 `STATEMENT_TIMEOUT_SECONDS="${FINOPS_WORKBENCH_PRUNE_STATEMENT_TIMEOUT_SECONDS:-60}"`，并把两值传给对应 flags。
    - Test 4: wrapper 仍通过 active release source、现有 env/lock/log/health 边界运行，既有 `KEEP_RECENT=1`、`KEEP_DAYS=0`、`LIMIT=500` 和 `--execute` 不被改写为 `keep_recent=0` 或发布后触发。
  </behavior>
  <action>
先扩展现有 CLI default test，并在 `DeployRuntimeExampleTests` 增加 Workbench generation prune helper 的精确默认值/flag 断言，然后实现 LD-04、LD-05、LD-06。

在 CLI parser 添加 `--delete-batch-size`（int，default 1）与 `--statement-timeout-seconds`（int，default 60）。构造一次 `PostgresConnection` 后，立即按秒转毫秒调用其现有 `set_statement_timeout_ms(...)`，默认必须是 `60000`；随后才构造 `PostgresReadModelRepository`，并把 delete batch size 传给 `prune_workbench_generations(...)`。对非正 statement-timeout seconds 在 CLI 边界 fail fast，使用 argparse 可观察错误，不允许静默退回通用 connection timeout；不新增连接、线程、signal timeout 或 SQL 级 `SET LOCAL` 分支。

在版本化 wrapper 定义 LD-05 的两个变量，保持用户指定的精确环境变量名和默认值，并在现有 Python invocation 中传 `--delete-batch-size "$DELETE_BATCH_SIZE"` 与 `--statement-timeout-seconds "$STATEMENT_TIMEOUT_SECONDS"`。日志 policy 行应包含实际 batch/timeout，便于运维定位，但不得打印 secrets 或 database URL。

Docs impact assessment：这是 retention repository 事务 I/O 和版本化运维入口合同变化，必须局部更新两处长期事实源。将 `docs/modules/reconciliation-workbench/boundary-io.md` 的 `superseded generation retention` 行补充为：最多 500 候选、按 scope 分组、每 scope generation 小批次独立事务、active 不删、publish 热路径不清理。将 `docs/operations/runtime-worker-governance.md` 的 Workbench generation runtime 段补充 CLI flags、wrapper env、1/60 默认值、1～100 batch 约束及专用 statement timeout；同时写明 `keep_recent` 下限仍为 1，且没有发布后异步清理。保留这些文档里用户已有的无关修改，不重排整段。

不得安装依赖、改 systemd service/timer/deploy-control、执行 helper、连接真实 PostgreSQL、部署或运行任何生产 smoke。本计划只做本地纯测试、lint、docs 和 diff 检查。
  </action>
  <verify>
    <automated>PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_prune_workbench_generations_cli_defaults_to_dry_run tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_prune_workbench_generations_cli_applies_custom_batch_and_statement_timeout tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_prune_workbench_generations_cli_allows_zero_keep_days_for_emergency_cleanup tests.test_deploy_runtime_examples.DeployRuntimeExampleTests.test_workbench_generation_prune_helper_uses_bounded_batch_and_statement_timeout_defaults -v</automated>
  </verify>
  <done>CLI 默认先设置 60000 ms 专用 statement timeout 并传 batch size 1；自定义秒数和批量参数正确贯通；wrapper 精确暴露两个环境变量和 flags；模块/运维文档反映实际合同且没有引入 keep_recent=0、post-publish cleanup 或生产动作。</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| timer/wrapper → CLI | 环境变量和 CLI 数字参数属于运维输入，必须有确定默认值和合法边界。 |
| CLI → PostgreSQL connection | 专用 statement timeout 必须在任何 repository SQL 之前应用，避免继承不适合 maintenance delete 的通用默认。 |
| preview candidates → destructive repository transaction | preview 输出控制删除目标；必须限制总量、隔离 scope、保留 active/tenant 防护并避免跨 scope 长事务。 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-ROJ-01 | Tampering | `_delete_workbench_generations` | mitigate | preview 和 final generation delete 均只接受 terminal `failed|superseded`，final delete 继续限定 default tenant 与 scope；自动测试证明 `active|building` generation 不进入删除结果。 |
| T-ROJ-02 | Denial of Service | retention delete transactions | mitigate | candidate 总量 500；按 scope 隔离；每批 1～100 generation 且独立事务；CLI 在 repository 使用前配置默认 60 秒 statement timeout。 |
| T-ROJ-03 | Repudiation | wrapper/CLI report | mitigate | dry-run/execute JSON 保留候选与删除数并新增规范化 batch size；wrapper policy log 记录非敏感 batch/timeout 实值。 |
| T-ROJ-04 | Elevation of Privilege | versioned wrapper | accept | 本次不改变既有 systemd 身份、env 文件权限、数据库凭据或 deploy-control 安装边界。 |
| T-ROJ-SC | Tampering | package supply chain | accept | 本计划没有 npm/pip/cargo install 或新依赖。 |
</threat_model>

<test_coverage>
## 七类测试适用性

| Category | Applicability | Coverage |
|----------|---------------|----------|
| 1. Business core unit | 适用 | batch size 1～100、candidate 500、按 scope 分组、keep_recent>=1、active 不删。 |
| 2. Service-layer | 适用 | transaction 次数/边界、dry-run 零事务、CLI→connection→repository 调用顺序与参数。 |
| 3. API contract | 不适用 | 不新增或修改 HTTP/API contract。 |
| 4. Read model/cache/background job | 适用 | generation retention timer 合同、publish 路径不清理、无新 worker/queue/cache。 |
| 5. Frontend interaction | 不适用 | 无 frontend 文件或用户交互变化。 |
| 6. End-to-end business flow | 不适用 | 本次禁止生产/数据库动作，且不改变业务写入或页面消费链；用 repository/CLI/wrapper 合同测试覆盖。 |
| 7. Existing regression | 适用 | 默认 dry-run、keep-days=0、active protection、publish-path isolation、版本化 runtime assets 保持。 |
</test_coverage>

<verification>
按以下顺序执行，全部为本地无数据库动作：

1. `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime tests.test_deploy_runtime_examples -v`
2. `bash scripts/verify.sh lint`
3. `bash scripts/verify.sh docs`
4. `git diff --check`
5. `git status --short --untracked-files=all`，确认仅计划内文件新增了本任务 diff，用户原有 dirty edits 均被保留。

不要运行 `deploy/oa/bin/finops-prune-workbench-generations.sh`、`scripts/deploy-oa.sh`、`infra-smoke`、任何 `psql` 命令或 production/database smoke。
</verification>

<source_audit>
| SOURCE | ID | Feature/Requirement | Plan | Status | Notes |
|--------|----|---------------------|------|--------|-------|
| GOAL | — | 修正 generation 清理超时与批量事务策略 | 01 | COVERED | Task 1 repository + Task 2 timeout chain |
| REQ | QUICK-260812-ROJ | 单一、原子、自包含 quick task | 01 | COVERED | 两个聚焦任务、同一执行 wave |
| RESEARCH | — | 无独立 RESEARCH.md | — | EXCLUDED | 现有 repository/CLI/wrapper 模式足够，未引入依赖或外部集成 |
| CONTEXT | LD-01 | delete_batch_size 默认 1、上限 100 | 01 | COVERED | Task 1 |
| CONTEXT | LD-02 | 按 scope 分组、generation chunk 独立事务 | 01 | COVERED | Task 1 |
| CONTEXT | LD-03 | candidate limit 保持 500 | 01 | COVERED | Task 1 |
| CONTEXT | LD-04 | CLI batch/timeout flags 与 60000 ms connection override | 01 | COVERED | Task 2 |
| CONTEXT | LD-05 | wrapper 两项 env 默认与 flags | 01 | COVERED | Task 2 |
| CONTEXT | LD-06 | active protection；无生产/数据库动作 | 01 | COVERED | 两任务与 verification fence |
| CONTEXT | DEFERRED-01 | keep_recent=0 | — | EXCLUDED | 明确不实现；测试保护下限 1 |
| CONTEXT | DEFERRED-02 | 发布后异步清理 | — | EXCLUDED | 明确不实现；保留 timer-only 边界 |
</source_audit>

<success_criteria>
- repository 的 deletion transaction 数量等于所有 scope chunks 数量，且任一 chunk 不跨 scope、大小不超过 100。
- 默认每个 generation 独立事务；一次运行候选总数不超过 500。
- active generation 防护、`keep_recent>=1`、默认 dry-run 与 timer-only retention 均未回归。
- CLI 默认在 repository 使用前调用 `set_statement_timeout_ms(60000)`，并传 `delete_batch_size=1`。
- wrapper 的两个环境变量、默认值、CLI flags 与非敏感日志均有静态合同测试。
- 两处长期事实文档同步，所有定向测试、lint、docs gate 与 diff check 通过。
- 没有生产访问、数据库动作、部署、新依赖、migration、worker/queue/cache 或用户无关 dirty diff 覆盖。
</success_criteria>

<output>
完成后创建 `.planning/quick/260812-roj-workbench-generation-scope-generation-st/260812-roj-SUMMARY.md`，记录修改文件、七类测试覆盖、验证命令、未测风险，并明确 `production/database action: not run by scope`。
</output>
