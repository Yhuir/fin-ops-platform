# Phase 40: 关联台自收敛补充范围 - Research

**Researched:** 2026-08-06  
**Domain:** Bank-flow canonical mutation、Workbench freshness/status、durable refresh queue、active generation、浏览器轮询  
**Confidence:** HIGH（代码、长期架构文档、现有测试与生产记录交叉核对）

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 架构
- D-01 PostgreSQL canonical facts 继续作为业务事实源；普通页面保持 direct canonical query。
- D-02 Workbench active-generation 与 `workbench_relation` 是保留例外，不删除 worker/read model/freshness/version/atomic publish。
- D-03 禁止新增 Worker、页面 Read Model、Redis cache、Search projection、通用 Bootstrap API 或第三方压测框架。

#### 性能
- D-04 先测量再优化；索引、普通列、cursor 和高基数筛选远程搜索只能由目标规模证据触发。
- D-05 页面首屏/API p95 目标保持 `<=1000ms`；写后可见性继续遵循现有 p99 `<=3000ms` 合同。
- D-06 精确 total、金额、统计、红冲、退款、关系和状态口径不得为性能降级。

#### 关联台自收敛
- D-10 流水规则批量处理及其他普通页面写成功后只提交 canonical facts、version/audit，并刷新本页面；禁止向关联台做同步/异步页面 fan-out、operation barrier 或刷新目标通知。
- D-11 关联台 freshness/status 查询边界负责比较 source proof；发现 `stale` 时必须复用现有 `ReadModelRefreshGateway`，只 enqueue 已归一化、校验和去重后的精确 scope，由现有 Workbench worker 原子发布 active generation。
- D-12 关联台进入页面或重新获得焦点时立即检查；只要关联台页面可见，无论 `fresh/stale/refreshing`，每次 status 请求完成后等待 1 秒再发下一次。隐藏页面暂停，前端请求必须 single-flight；generation version 变化后只 reload 一次。
- D-13 禁止新增 endpoint、Worker、read model、数据库表/trigger、Redis、RabbitMQ 强依赖、跨页事件总线、BroadcastChannel、SSE 或第三方轮询依赖；每秒检查只允许调用现有有界 refresh-status，不得并发、积压或退化为重复完整 payload GET，并须以目标并发证明数据库/API 容量后才可发布。
- D-14 删除或继续保持删除已退休的普通写侧 Workbench refresh、operation barrier、targets 和 fallback；显式 maintenance/repair/rehydrate 以及独立 domain jobs 不属于页面 fan-out，不得误删。
- D-15 流水规则提交到关联台可见的生产合同保持 p99 `<=3000ms`；必须分别测量 canonical commit、status proof/enqueue、queue/worker publish 和浏览器 reload，不能用单个最快样本代替。
- D-16 该变更只能落在关联台查询/前端轮询边界；流水规则批量提交 API、事务、正式关系写入和本页 reload I/O 保持不变，其他页面的写/读合同不得被污染。

#### 安全与发布
- D-07 目标规模数据只写隔离 performance/test 数据库；生产只做有界登录态 GET、health、dashboard、pg_stat 和现有 release gate。
- D-08 旧链删除必须先扫描 caller/consumer；无 hidden fallback、双读、旧 route alias 或退休 event 残留。
- D-09 每个根修复都有测试保护；全量回归通过后才 commit/push main、部署和生产验证。

### the agent's Discretion

CONTEXT.md 未声明额外 discretion；实现只能在上述锁定边界内选择最小代码路径。

### Deferred Ideas (OUT OF SCOPE)

- 历史 projection 表物理 DROP 只在所有受支持 rollback release 均无 reader/writer/backlog 后另立 migration；本 Phase 只删除当前运行入口与旧事实描述。
- 若目标规模基准未证明 JSONB、索引或 cursor 必要，则不实施对应结构变更。
</user_constraints>

## Summary

当前流水规则批量提交链路已经符合 D-10/D-16：写侧只提交 canonical batch/event、正式 relation、版本/审计，并让本页做一次 normal GET；`PostgresStateStore.save_bank_flow_rule_batch_mutation(...)` 明确不消费 `changed_scope_keys`，同一事务只保存 relation/history 与 batch/events，没有写 `job.read_model_dirty_scopes` 或 `job.outbox_events`。[VERIFIED: `BankFlowRuleBatchPage.tsx:469-533`, `routes_bank_flow_rule_batches.py:142-205`, `bank_flow_rule_batch_application_service.py:545-640,929-973`, `postgres_state_store.py:748-787`, `tests/test_postgres_repositories_boundaries.py:1324-1351`]

确认的根缺口不在流水规则提交侧，而在 Workbench 查询侧：`WorkbenchQueryFacade.refresh_status()` 已调用同一 canonical source freshness proof，但只 normalize/return；它没有复用 `_groups_refresh_status_payload(..., enqueue_non_fresh=True)` 已有的精确 scope enqueue 逻辑。持续打开的关联台如果只剩 `/api/workbench/refresh-status` 轮询，可以看到 `stale`，却不一定启动 worker；直到另一次 initial/groups GET 才会 enqueue。[VERIFIED: `workbench_query_facade.py:980-1041`; `WorkbenchQueryFreshnessService.apply:27-69`]

生产者/消费者完全解耦还有一个不可省略的正确性前提：**每个能改变 Workbench 投影结果的 canonical writer，都必须改变 Workbench source proof 中对应 exact scope 的可比较值**。当前 proof 已覆盖正式关系、异常决定、row override、pending-payment claim、银行流水/分类/确认、发票、OA、ETC submission/business/invoice/link，以及设置与schema/rule/parser版本；bank-flow正式关系写通过 `workbench_pair_relations.updated_at` 与跨月member proof进入该集合。实施计划必须增加 writer→proof 覆盖审计和契约测试；发现漏项时修 source proof，不在 writer 侧补 Workbench 通知。[VERIFIED: `workbench_sql_projection.py:445-849`; read-model contracts]

最小生产级修复是把公开 refresh-status 接入同一个现有 helper/gateway，并把前端固定 `setInterval(5000)` 改为单一 self-scheduling、visibility-aware、single-flight 轮询：进入/重新聚焦立即检查；页面可见时无论状态，每次请求完成后等待 1000ms 再检查；隐藏时暂停；新 generation 只 reload 一次。无需新增 endpoint、worker、read model、表、cache、消息总线、依赖或写侧通知。[VERIFIED: `ReconciliationWorkbenchPage.tsx:199-205,932-946,1139-1182`; `ReadModelRefreshGateway.enqueue_many:45-114`; Phase 40 D-10..D-16]

**Primary recommendation:** 用八个小计划执行同一范围：`40-01` probe/FinanceTable、`40-02` proven SQL、`40-03` 已证明的 import batch-row、`40-04` Search/no-OA facts + local candidate，随后 `40-05` backend self-heal、`40-06` frontend poller、`40-07` writer-proof/legacy/E2E、`40-08` docs/capacity/browser p99/唯一发布。拆分只修正执行粒度，流水规则写链与 runtime 架构零改动。[VERIFIED: scope analysis against Phase 40 plans and D-16]

**Release-blocking performance gate:** 更新后的 D-12 把可见关联台的检测等待压到“前一请求完成 + 1000ms”，因此 commit-to-visible p99 `<=3000ms` 在逻辑上不再被 5 秒定时器直接否定；但它仍是 **NOT YET MEASURED**。completion-driven 调度将每个持续可见客户端的上限控制在约 1 QPS（实际为 `1 / (请求耗时 + 1s)`，focus 触发仍由 single-flight 合并），发布前必须按目标可见客户端并发实测 refresh-status API、canonical proof SQL、连接池与 PostgreSQL 容量，并完成四段端到端 p99 证据；容量或时延不达标即阻断发布，不新增架构补偿。[VERIFIED: updated D-12/D-13; scheduling bound]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| 流水规则 canonical commit | API / Backend | Database / Storage | 现有 application service + caller-owned transaction 持有 relation/batch/event 原子写；本补充计划禁止修改。[VERIFIED: bank-flow boundary docs and code] |
| 判断 Workbench stale 与精确 scope | API / Backend | Database / Storage | `WorkbenchQueryFreshnessService` 比较 canonical proof 与 active generation proof；`all` 返回真实 mismatch month shards。[VERIFIED: `workbench_query_freshness_service.py:27-134`] |
| writer→source-proof 完整性 | Database / Storage | API / Backend tests | 每个影响 Workbench 的 canonical mutation 都必须推进 exact-scope proof；由test-owned覆盖矩阵审计，writer保持零通知。[VERIFIED: decoupling invariant and current proof query] |
| enqueue / dedupe / durable truth | API / Backend | Database / Storage | 现有 `ReadModelRefreshGateway` normalize/validate/dedupe 后写 PostgreSQL queue。[VERIFIED: `read_model_refresh_gateway.py:45-114`; read-model contract] |
| generation rebuild / publish | API / Backend worker | Database / Storage | 现有 Workbench worker 重建精确 month scope，完整保存后原子激活 generation。[VERIFIED: `workbench_sql_projection.py:198-257`; runtime worker docs] |
| 轮询、visibility、reload once | Browser / Client | API / Backend | 浏览器决定何时请求 status；服务端决定 freshness/enqueue，不让页面构造 scope 或写 queue。[VERIFIED: current Workbench page/API boundaries] |
| 生产 SLO 证据 | Operations | API / Database / Browser | 四段时延必须分别记录并汇总，生产 mutation 仍受 test-owned、bounded、可逆约束。[VERIFIED: Phase 40 D-07/D-15; runtime-worker governance] |

## Exact Current Chain

### A. 流水规则提交链（当前正确，计划必须保持字节级行为边界）

```text
BankFlowRuleBatchPage.handleSubmitSelected / handleSubmitBatch
  -> POST /api/bank-flow-rule-batches/submit-selection 或 /{batch_id}/submit
  -> BankFlowRuleBatchRoutes
  -> BankFlowRuleBatchApplicationService.submit_selected_rows / submit_batch
  -> BankBatchService 复核 candidate、分类、scope、占用、CAS
  -> WorkbenchRelationCommandService.confirm_relation
  -> _mutation_result -> persist_mutation
  -> PostgresStateStore.save_bank_flow_rule_batch_mutation
  -> 单一事务：save_workbench_pair_relations + save_bank_flow_rule_batch_items/events
  -> HTTP 200
  -> 流水规则页面一次 GET /api/bank-flow-rule-batches
```

[VERIFIED: CodeGraph node/call trail and module code cited in Summary]

写链中的 `changed_scope_keys` 仍是 mutation receipt/affected-month 信息输入；PostgreSQL writer 用 `_ = changed_scope_keys` 明确不把它变成 Workbench dirty/outbox。这个“忽略”是目标架构，不是遗漏。[VERIFIED: `postgres_state_store.py:758-760`; D-10]

### B. Workbench source proof 组装（bank-flow覆盖已验证；全writer审计待执行）

`WorkbenchSqlProjectionBuilder._load_source_versions_for_scopes(...)` 把 relation `status`、`updated_at`、`month_scope`、member rows、跨月 member 对象与各 canonical source 版本纳入 month proof；新 bank-flow relation 会让真实受影响月份 mismatch。[VERIFIED: `workbench_sql_projection.py:445-703`, especially relation members/scoped relation ids/relation versions]

`WorkbenchQueryFreshnessService.apply(...)` 对 month 返回该 exact month；对 `all` 一次 bulk 枚举 active shards、一次 canonical bulk proof、一次 active-generation bulk proof，只返回 mismatch month shards。[VERIFIED: `workbench_query_freshness_service.py:27-134`]

### C. Producer → source-proof coverage contract

| Canonical dependency family | Current proof key/input | Writer audit obligation |
|---|---|---|
| 正式关系与跨月成员 | `workbench_pair_relations_updated_at`，relation status/month/member rows及member对象 `updated_at` | 所有confirm/withdraw/batch relation writer必须改变relation `updated_at`；跨月member所属月份也必须mismatch。[VERIFIED: projection proof SQL] |
| 银行流水、分类、确认/撤销 | `bank_transactions_updated_at`、`bank_transaction_categories_updated_at`、`bank_transaction_category_confirmations_updated_at` | bank import/edit/tag/confirm/revoke writer必须推进对应事实时间；金额/日期变化还要覆盖新旧受影响scope。[VERIFIED: projection proof SQL and read-model contract] |
| 发票与OA | `invoices_updated_at`、`oa_projection_updated_at`，active cross-month relation member updates | invoice/OA import/edit/sync/attachment-derived changes必须推进exact scope；跨月正式成员变化不能只覆盖对象本月。[VERIFIED: projection proof SQL] |
| Workbench控制事实 | `workbench_exception_cases_updated_at`、`workbench_row_overrides_updated_at`、`oa_pending_payment_bank_claims_updated_at` | ignore/restore/override/claim writer必须更新可比较时间并只影响真实scope。[VERIFIED: projection proof SQL] |
| ETC canonical facts | submission/business batch、ETC invoice、batch-invoice link各自 `updated_at` proof | submit/link/unlink/import writer必须推进owner或link时间；不能依赖写侧refresh event兜底。[VERIFIED: projection proof SQL] |
| 设置与代码语义 | settings payload aliases、builder/rule/parser/OA sync version | 设置writer必须改变被proof读取的payload；投影语义变更必须bump既有schema/rule/parser version owner。[VERIFIED: projection proof payload assembly] |

**Required audit/test shape:** 建立一个窄的、test-owned writer→proof矩阵（优先放在 `tests/test_workbench_source_proof_contract.py`，不新增runtime registry）。对每个生产writer类别记录 canonical mutation入口、被改变的表/字段、expected old/new scope、proof key；在事务型 PostgreSQL integration test 中先取proof、执行writer、再断言受影响scope proof变化、无关scope不变、`WorkbenchQueryFreshnessService`由fresh变stale。bank-flow用例还必须同时断言writer事务零 Workbench dirty/outbox/target。未来新增或修改任何参与Workbench投影的writer或source table时，必须更新矩阵，否则contract test/review gate失败。[VERIFIED: resolved decoupling design; AGENTS read-model test requirements]

这个矩阵只保护“canonical change可被consumer观察”的合同，不成为生产代码manifest，也不向writer注入gateway依赖。若审计发现当前writer没有推进现有proof，修复点是canonical时间/version或projection proof query；禁止添加写侧 Workbench notification、barrier、target或fallback。[VERIFIED: D-10/D-11/D-13/D-16]

### D. 当前能自愈的 GET 与不能自愈的 status

| 入口 | proof | stale enqueue | 结果 |
|---|---:|---:|---|
| combined initial / groups | 是 | 是，经 `_groups_refresh_status_payload` | 能自愈。[VERIFIED: facade callers and helper] |
| write precondition | 是 | 按现有写门禁合同 | 不属于本问题。[VERIFIED: facade caller map] |
| `/api/workbench/refresh-status` | 是 | **否** | 能报告 stale，但可能不启动 refresh。[VERIFIED: `refresh_status:980-1009`] |

### E. 当前浏览器轮询链

- active 时立即 status GET，之后固定每 5000ms 一次；focus 再立即 GET。[VERIFIED: `ReconciliationWorkbenchPage.tsx:1139-1182`]
- 每次 tick 会 abort 上一次请求；若把固定间隔机械改成 1 秒，而 proof 超过 1 秒，可能连续 abort、永远没有完成响应。[VERIFIED: same effect implementation]
- 没有 `visibilitychange`/`document.visibilityState` 处理，隐藏页面仍轮询。[VERIFIED: same effect; whole-file literal scan]
- status 变 fresh 且 generation version 改变时，现有 300ms debounce reload；version ref 已避免相同 version 重复 reload。[VERIFIED: `ReconciliationWorkbenchPage.tsx:932-946`]

## Confirmed Root Gap

根因是同一 facade 内出现了两条近似 freshness 流程：`initial/groups` 通过 `_groups_refresh_status_payload` 完成 proof + exact enqueue，而 `refresh_status` 手写了 repository read + proof + normalize，漏了 enqueue。修复点应在共享查询边界，不应在每个普通 writer 补通知。[VERIFIED: `workbench_query_facade.py:980-1041`]

症状的“十几秒后才刷新”可由多个现有延迟叠加解释：等下一次能 enqueue 的 initial/groups GET、normal-priority durable queue 等待、worker rebuild/publish、前端最多 5 秒 status poll 和 300ms reload debounce。该解释是从已验证链路作出的因果推断，不代表每次都由同一段耗时主导。[VERIFIED: inference from code paths and documented queue/poll configuration]

## Minimal Architecture

```text
普通页面 POST
  -> canonical facts/version/audit + current-page GET
  -> （零 Workbench 通知）

关联台 status GET（进入/聚焦/定时）
  -> lightweight repository status
  -> existing canonical source proof
  -> fresh --------------------------> return fresh
  -> refreshing ---------------------> return refreshing（不重复 enqueue）
  -> stale + exact mismatch scopes
       -> existing _groups_refresh_status_payload
       -> existing ReadModelRefreshGateway
       -> PostgreSQL dirty/outbox dedupe
       -> existing Workbench worker
       -> exact month generation rebuild
       -> atomic active generation publish
       -> next 1s status sees fresh + new version
       -> frontend reload once
```

[VERIFIED: existing components; only missing edge is refresh-status -> existing helper]

### Backend recommendation

让 `refresh_status()` 在现有异常/timeout 映射内直接复用 `_groups_refresh_status_payload(scope_key, enqueue_non_fresh=True)`，然后继续使用现有 payload normalizer。不要复制 enqueue loop，不要新增 service/repository/gateway/endpoint。若调整 reason，只使用一个 endpoint-neutral `api_workbench_source_versions_stale`，不要创造第二套策略。[VERIFIED: recommendation based on existing helper and gateway]

必须保留 `_refresh_scope_keys(...)` 的当前 fail-closed 行为：month 只回自身；`all` 优先 exact mismatch/failed month；active refresh in progress 返回空；只有 active generation missing 的冷启动/显式恢复才允许 `all`。[VERIFIED: `workbench_query_facade.py:1044+`; module contracts]

### Frontend recommendation

用一个 self-scheduling timeout 替代固定 `setInterval`：请求 settle 后等待 1000ms 再排下一次，因此天然 single-flight，不需要并行 controller/重复 abort。只要页面可见，所有返回状态都使用相同完成后 1 秒节奏；hidden 清 timer/abort，visible 或 focus 时立即检查，并由 in-flight guard 合并紧邻触发。[VERIFIED: recommendation constrained by updated D-12/D-13 and current implementation]

该调度每个持续可见客户端至多约 1 QPS，目标并发为 `C` 时 refresh-status 总请求上限约为 `C QPS`，且每次请求会执行有界 status/source proof。这个成本比当前 5 秒轮询高，必须在目标并发下验证 API p95、数据库 query p95、连接池等待、CPU/IO 与错误率；验证不通过时阻断发布，不通过新增 cache、bus、endpoint 或 writer notification 绕过。[VERIFIED: completion-driven scheduling math and D-13]

复用现有 `applyWorkbenchRefreshStatus` 与 300ms generation reload debounce；不在 stale 时主动打 combined initial，不重复执行 full payload proof，不在 status response 到达前先 reload。[VERIFIED: recommendation based on existing version-key logic]

### Explicit non-goals

- 不改 bank-flow POST、route、application service、relation command、transaction、receipt、本页 GET。[VERIFIED: D-16]
- 不新增 endpoint、worker、read model、表、trigger、cache、RabbitMQ 依赖、BroadcastChannel、SSE、跨页 event bus、第三方 poller。[VERIFIED: D-13]
- 不把 `workbench_relation` distribution 当成 Workbench page dependency；page generation 直接读 canonical relations。[VERIFIED: read-model contracts]
- 不恢复 `workbench:all` 作为普通 stale fallback。[VERIFIED: current exact-scope contract]
- 不删除 maintenance/repair/rehydrate、Workbench matching、OA/import 等独立 domain job。[VERIFIED: D-14 and runtime docs]

## Boundary I/O Contract

| Boundary | Input | Output / side effect | Must not do |
|---|---|---|---|
| Bank-flow write API | 现有 payload/session/idempotency/CAS | 现有 receipt + canonical relation/batch/event + 本页一次 GET | 不返回 Workbench target，不写 page dirty/outbox，不等待 barrier。[VERIFIED: current boundary] |
| Any Workbench-affecting canonical writer | domain payload + current canonical state | canonical fact/version/audit；其真实受影响scope的既有source proof必须变化 | 不import/call Workbench gateway，不发refresh event/target/barrier，不把漏proof隐藏成writer side effect。[VERIFIED: resolved producer/consumer decoupling contract] |
| Workbench refresh-status API | `month=all|YYYY-MM` + authenticated read session | 保持现有 status shape；stale 时额外产生 existing gateway exact enqueue side effect | 不返回 rows，不跑 App Health full diagnostic，不构造 `all` fallback。[VERIFIED: current route/facade contracts + recommendation] |
| Workbench freshness service | repository status + canonical/active proof | `fresh|stale|refreshing|failed|unavailable` + exact `refresh_scope_keys` | 不写 SQL、不直接 enqueue。[VERIFIED: current service responsibility] |
| Refresh gateway | scope type `workbench`, exact month keys, reason/metadata | normalized/validated/deduped PostgreSQL durable event | 不接受非法 scope，不把 transport 当 truth。[VERIFIED: gateway code/docs] |
| Workbench worker | registered exact refresh event | complete generation save + atomic activation + dirty completion | 不读 HTTP/session，不发布 partial generation。[VERIFIED: worker/read-model docs] |
| Browser poller | active/visibility/focus/current status | one status request at a time；fresh version change后 one reload | 不在 hidden 状态轮询，不因 tick abort 正常慢请求，不主动通知其它页面。[VERIFIED: recommendation] |

## Standard Stack

### Core

| Component | Current version/contract | Purpose | Why Standard Here |
|---|---|---|---|
| Python service layer | Python 3.11.5 available | facade/freshness/gateway orchestration | Existing owner; no new abstraction。[VERIFIED: local runtime + repository] |
| PostgreSQL durable queue | `job.outbox_events` + `job.read_model_dirty_scopes` | refresh truth、dedupe、claim、completion | Repository-authoritative contract。[VERIFIED: AGENTS.md and runtime docs] |
| React/TypeScript browser lifecycle | existing React hooks + browser `focus`/`visibilitychange`/`setTimeout` | all-status completion-driven 1s poll、single-flight、reload once | Native platform suffices。[VERIFIED: current frontend stack] |
| Existing Workbench active generation | current v20+ contract as deployed code decides | stable old generation + atomic new publish | Explicit retained exception。[VERIFIED: Workbench boundary docs] |

### Validation

| Tool | Version/contract | Purpose |
|---|---|---|
| pytest | 8.0.1 | backend service/API/repository/integration tests。[VERIFIED: local `pytest --version`] |
| Vitest | package range `^2.1.4` | frontend fake-timer/lifecycle tests。[VERIFIED: `web/package.json`] |
| Playwright | package range `^1.60.0` | browser visibility/focus/E2E chain。[VERIFIED: `web/package.json`] |
| Existing SLO/production tools | repository scripts + deploy gate | bounded production evidence without new framework。[VERIFIED: Phase 40 and operations docs] |

**Installation:** none. No external package is needed or allowed.[VERIFIED: D-03/D-13; existing native/runtime capabilities]

## Package Legitimacy Audit

Not applicable: this addition installs zero packages and uses only existing project code plus browser native APIs.[VERIFIED: proposed architecture]

## Architecture Patterns

### Pattern 1: Query-owned self-healing

The consumer that can prove staleness owns exact enqueue; producers only advance canonical facts. This keeps dependency direction `page query -> freshness -> gateway -> queue -> worker`, avoiding N writers each knowing Workbench internals.[VERIFIED: repository target architecture and D-10/D-11]

### Pattern 2: Stable-while-refreshing generation

Non-fresh status may expose the last stable generation with write operations disabled; only complete new generation becomes active. Browser reloads after version change, not when stale is first observed.[VERIFIED: Workbench boundary/state docs]

### Pattern 3: Completion-driven polling

```typescript
// Planning sketch only; source pattern is current Workbench effect + browser native APIs.
async function pollOnce() {
  if (document.visibilityState !== "visible" || inFlight) return;
  inFlight = true;
  try {
    const status = await fetchWorkbenchRefreshStatus("all");
    applyWorkbenchRefreshStatus(status);
  } finally {
    inFlight = false;
    if (document.visibilityState === "visible") schedule(1_000);
  }
}
```

The executor should adapt this inside the existing effect, not create a generic polling hook.[VERIFIED: recommendation based on Ponytail/YAGNI]

### Pattern 4: Proof-complete producer decoupling

Writer只负责canonical fact/version/audit；Workbench通过source proof识别变化。这个模式只有在“投影依赖集合 ⊆ proof依赖集合”且每个writer会推进对应proof时才正确。用test-owned writer→proof矩阵和真实mutation integration tests保护该包含关系，不建立runtime producer registry。[VERIFIED: resolved design and current projection proof]

### Anti-Patterns to Avoid

- 在 bank-flow writer 加 Workbench target/outbox：恢复 N-writer fan-out，违反 D-10/D-16。[VERIFIED: locked decision]
- 只验证bank-flow writer而不审计其它canonical writers：某个漏proof writer会让关联台继续显示`fresh`，每秒轮询也永远不会重建。[VERIFIED: decoupling invariant]
- stale 后让前端再打 combined initial 触发 enqueue：重复 canonical proof和payload I/O，根修仍遗漏在 status boundary。[VERIFIED: inference from current facade]
- 机械地把固定 `setInterval` 从 5s 改成 1s：慢请求可能被下一 tick abort，并造成并发或积压。必须改成请求完成后再等待 1 秒的 single-flight 调度，并以目标并发验证约 1 QPS/visible client 的 API/DB 容量。[VERIFIED: updated D-12/D-13 + current effect]
- `stale -> all` fallback：把 exact mismatch 扩成全月 fan-out。[VERIFIED: current scope contract]
- 新建 coordinator/poller abstraction：这里只有一个 Workbench effect，现有 helper 已覆盖后端逻辑。[VERIFIED: code inventory]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| scope normalize/dedupe | 新 scope parser/锁/cache | `ReadModelRefreshGateway` + policy registry | 已有原子 active coalescing/orphan recovery。[VERIFIED: gateway/runtime docs] |
| refresh transport | SSE/WebSocket/RabbitMQ-required | existing HTTP status + PostgreSQL queue | 锁定架构且 durable truth 已存在。[VERIFIED: D-13] |
| frontend scheduler | 第三方 polling library/generic hook | one local `setTimeout` effect | 单页面、状态少、原生足够。[VERIFIED: scope] |
| generation publish | frontend merge/partial publish | existing worker atomic generation | 防止半新半旧数据。[VERIFIED: active-generation contract] |
| cross-page notification | BroadcastChannel/event bus | focus/entry/status self-check | 普通 writers 保持零依赖。[VERIFIED: D-10/D-13] |

## Legacy Removal Inventory

| Candidate | Evidence | Classification | Required action |
|---|---|---|---|
| `bank_flow_rule_batch.read_model.refresh` | 生产源码/worker/deploy无匹配；只剩 migration/负向测试。[VERIFIED: whole-repo literal scan] | 已退休且当前不可达 | 保留/加强 zero-reference guard；不要恢复 event/handler/env。 |
| bank-flow read-model files/worker/replay | `rg --files` 无当前实现。[VERIFIED: whole-repo file scan] | 已删除 | 无代码可删；文档继续写明退役。 |
| bank-flow operation barrier/targets | 页面/route tests明确断言不存在，生产页面只一次GET。[VERIFIED: bank-flow tests/code] | 已删除 | 保持负向回归。 |
| Workbench exception DTO `operationBarrierTargets` 与 `operationBarrierTargets || freshnessTargets` fallback | 只有 type/mapper/tests，页面无 consumer。[VERIFIED: whole-repo scan + CodeGraph impact] | 可证明的 Workbench 局部旧 DTO residue | 在 Workbench frontend边界删除字段、fallback和对应正向旧断言；保留零 barrier E2E。 |
| `web/src/features/operationBarrier/api.ts` | 无生产 import；只被自身测试/历史 timeout test直接引用。[VERIFIED: production import scan] | 全局退休 helper，但超出 D-16 行为边界 | 不在本补充计划改其它页面；登记为单独 cleanup 候选，除非 planner 将“无运行调用的纯删除”判为 D-14 明确授权。 |
| backend `/api/operation-barrier/status`、runtime monitoring、migration/index | 仍有运维/runtime tests与潜在外部 operator consumer。[VERIFIED: caller/text inventory] | 不是 bank-flow 页面 fan-out residue，删除证据不足 | 保留；不得因名称相似误删。 |
| rehydrate/repair/backfill | 现有 scripts/gateway/ops入口。[VERIFIED: file/runtime docs] | 显式 maintenance | 必须保留。 |
| `workbench-matching`、OA/import jobs | registry登记的独立domain jobs。[VERIFIED: runtime registry] | 非页面 fan-out | 必须保留。 |

### Runtime State Inventory

| Category | Items Found | Action Required |
|---|---|---|
| Stored data | 历史 retired projection/outbox/dirty 表由 migration 0127 保留回滚；当前 runtime 不读不 claim。[VERIFIED: read-model contracts] | 本阶段零 migration、零 DROP、零数据改写。 |
| Live service config | 当前 required workers六个；read models仅 `workbench`/`workbench_relation`。[VERIFIED: registry/docs] | 不新增/改名 unit；release gate继续核对 exact inventory。 |
| OS-registered state | systemd worker由registry与release helper管理；未知 unit由门禁 stop/disable。[VERIFIED: runtime governance] | 无新 unit，无手工 systemd 操作。 |
| Secrets/env vars | 本变更无新 secret/env。[VERIFIED: proposed files/architecture] | none。 |
| Build artifacts / installed packages | frontend bundle会因轮询代码/死DTO删除重建；无新依赖。[VERIFIED: web build contract] | 正常 `npm build`；不做包安装。 |

## Common Pitfalls

### Pitfall 1: status 报 stale 但没有推进者

**What goes wrong:** 页面一直显示旧 generation，等待其它 GET 偶然触发。  
**Why:** `refresh_status()` 与 groups helper重复 proof 流程，漏 enqueue。  
**Avoid:** facade复用同一 helper，并测试 stale exact enqueue。[VERIFIED: confirmed root gap]

### Pitfall 2: 1秒 setInterval 反而永不完成

**What goes wrong:** proof超过tick时被下一次poll abort。  
**Why:** 当前实现每个tick先 abort上一 controller。  
**Avoid:** 请求完成后 self-schedule；同一时刻最多一个 status GET。[VERIFIED: current effect]

### Pitfall 3: hidden/focus 事件造成双请求

**What goes wrong:** visibilitychange与focus紧邻触发两次。  
**Avoid:** 两个事件都调用同一 `pollNow`，由in-flight guard合并；隐藏时清 timer/abort。[VERIFIED: recommendation]

### Pitfall 4: enqueue 后仍返回 stale 被误认为失败

**What goes wrong:** 第一次 stale响应在 enqueue 后仍可能是 stale；前端若要求立即 refreshing会误报。  
**Avoid:** 第一次 stale 响应允许保持 stale；所有状态仍按完成后 1 秒轮询，下一次 durable status 才可能显示 refreshing。[VERIFIED: inference from helper order and updated D-12]

### Pitfall 5: failed/unavailable 状态形成容量风暴

**What goes wrong:** 可见客户端仍按锁定合同每秒检查；若 status/proof 失败路径昂贵，目标并发会持续放大 API/DB 压力。  
**Avoid:** 保持 completion-driven single-flight 和 gateway active coalescing/orphan recovery；失败状态不得绕过 1 秒合同改打 full payload，也不得重复 enqueue。以目标并发验证失败路径容量，并保留 retryable/运维 repair 合同。[VERIFIED: updated D-12/D-13; gateway/tests/status normalizer]

### Pitfall 6: canonical writer漏出source proof

**What goes wrong:** writer成功提交且关联台每秒检查，但canonical proof与active generation proof仍相同，页面永久错误显示fresh。  
**Why:** projection读取了新表/字段，或writer没有推进proof读取的`updated_at`/version；旧写侧通知曾掩盖该缺口。  
**Avoid:** writer→proof覆盖矩阵 + 每类真实mutation测试；断言affected scope变stale、unaffected scope不变、writer零Workbench fan-out。漏项只修canonical version/proof。[VERIFIED: decoupling invariant]

### Pitfall 7: D-15 或容量被错误“证明”

**What goes wrong:** 用最后一次快速 GET、单个最佳样本、单客户端结果或从 focus 后才计时，宣称 commit-to-visible p99 和容量均达标。  
**Avoid:** 报告四段时延、样本量、commit 起止点，并在目标可见客户端并发下测 API/DB/连接池；证据不足保持 `NOT YET MEASURED`，不发布。[VERIFIED: D-13/D-15]

## Performance Acceptance Evidence

### Required segment timestamps

| Segment | Start | End | Evidence owner |
|---|---|---|---|
| canonical commit | bank-flow POST request start | HTTP commit response | access log / existing action timing；写链不改。[VERIFIED: D-15] |
| detection + proof/enqueue | canonical commit | 首个证明该 commit 影响的 status response + outbox `available_at` | correlated browser/API timing + queue row。[VERIFIED: D-15 measurement contract] |
| queue/worker publish | outbox `available_at` | `processed_at` + active generation version | existing queue/worker/generation facts。[VERIFIED: runtime docs] |
| browser reload | first fresh status with new version | combined initial installed/业务identity可见 | browser performance mark/E2E assertion。[VERIFIED: recommendation] |

### Gates

- `/api/workbench/refresh-status` 仍属于页面API p95 `<=1000ms`；历史生产记录显示该 endpoint p95 `138.925ms`，只能作为基线，不是新版本保证。[VERIFIED: Workbench tests.md Phase 34 evidence + D-05]
- stale proof一次只enqueue真实 mismatch month，active pending/processing时零重复 enqueue；job amplification应为每个exact scope最多一个active event。[VERIFIED: gateway/freshness contracts]
- 所有状态下，可见浏览器均在前一次 status 请求完成后等待 1000ms 再检查；hidden时业务请求增量为0，focus/visible时首个检查立即发起且不得突破 single-flight。[VERIFIED: updated D-12 acceptance]
- generation version只触发一次combined initial reload；相同version重复fresh status零reload。[VERIFIED: existing version-key logic]
- completion-driven 1秒调度的单客户端上限约为1 QPS；以目标可见客户端并发验证 refresh-status/API、source-proof SQL、连接池、PostgreSQL CPU/IO和错误率，容量证据未通过即阻断发布。[VERIFIED: D-13 + scheduling math]
- 端到端 commit-to-visible p99 `<=3000ms` 必须用四段足量样本证明；当前结论是 `NOT YET MEASURED`，不能把 correctness timeout、最后一次 GET 或单客户端最佳样本代替。[VERIFIED: D-15]
- 生产只做一次已批准、test-owned、bounded、可逆scenario和有界只读采样；要声称统计p99，需prod-equivalent重复样本或足量被动生产样本。生产样本不足时不宣称p99。[VERIFIED: D-07 and runtime smoke governance]

### Target-concurrency capacity evidence

| Load point | Input | Required observation | Release decision |
|---|---|---|---|
| Normal visible concurrency | 从生产会话/访问日志得出的正常同时可见Workbench客户端数 `C_normal`；每客户端completion+1s | refresh-status RPS/latency/error、source-proof SQL latency/rows、pool wait/timeout、PostgreSQL CPU/IO | API p95仍`<=1000ms`且无积压/容量异常才通过。[VERIFIED: D-05/D-13] |
| Peak visible concurrency | 生产峰值或批准的保守峰值 `C_peak`；同一节奏 | 同上，并观察durable queue active dedupe与worker publish不被status reads饿死 | 未得到峰值证据或任一资源饱和则阻断发布。[VERIFIED: D-13] |
| End-to-end mutation samples | 隔离prod-equivalent中的足量bank-flow提交样本 | canonical commit、proof/enqueue、worker publish、browser reload四段与总体p99 | 总体p99`<=3000ms`才通过；单个最佳样本无效。[VERIFIED: D-07/D-15] |

不增加第三方压测框架；优先复用Phase 40既有测量脚本、访问日志、PostgreSQL statement/连接池指标和浏览器E2E marks。若现有工具不能生成批准的目标并发，只补最小test/ops脚本，不新增runtime service。[VERIFIED: D-03/D-13 and project constraints]

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Backend | pytest 8.0.1；existing unittest-compatible tests。[VERIFIED: local runtime] |
| Frontend | Vitest `^2.1.4` + Testing Library。[VERIFIED: package.json] |
| Browser | Playwright `^1.60.0` Chromium。[VERIFIED: package.json] |
| Quick backend | `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_workbench_query_facade.py tests/test_workbench_routes.py` |
| Quick frontend | `npm --prefix web test -- --run src/test/WorkbenchSelection.test.tsx src/test/WorkbenchApi.test.ts` |
| Phase gate | existing lint/backend/frontend/build/Browser/docs/diff gates + bounded release evidence。[VERIFIED: AGENTS/Phase 40] |

### Seven-category assessment

| Category | Applies | Planned coverage |
|---|---:|---|
| 1. Business core unit | No new business rule; regression only | Rerun bank-flow candidate/relation/frozen metadata/core tests to prove zero semantic change。No new core test unless executor accidentally changes business code。[VERIFIED: D-16] |
| 2. Service layer | Yes | `refresh_status` stale exact enqueue；fresh/refreshing zero enqueue；failed exact retry；active refresh no all fallback；timeout unchanged；gateway dedupe/orphan recovery；writer→proof contract保持service零Workbench依赖。[VERIFIED: affected service] |
| 3. API contract | Yes | `/api/workbench/refresh-status` auth/month/status/error/shape unchanged；side effect only on stale exact scope；bank-flow POST receipt仍无read_model/barrier fields。[VERIFIED: affected APIs] |
| 4. Read model/cache/background job | Yes | 对每个Workbench canonical dependency family执行真实writer mutation，断言affected proof变化/unaffected不变/fresh->stale；再验证exact dirty/outbox -> worker publish -> fresh。active generation stable while refreshing；Redis non-fresh no write；no duplicate/out-of-scope jobs。[VERIFIED: core change and decoupling invariant] |
| 5. Frontend interaction | Yes | immediate entry/focus/visible、hidden pause、single-flight、所有状态完成后1s、focus与timer合并、new version reload once、unmount abort；断言没有full payload polling。[VERIFIED: affected UI lifecycle] |
| 6. E2E business flow | Yes | bank-flow submit -> zero write-side outbox/targets -> Workbench status detects exact stale -> worker publishes -> active Workbench reloads once and shows relation。[VERIFIED: cross-module flow] |
| 7. Existing regression | Yes | bank-flow current-page one GET/candidate conflict；writer→proof矩阵覆盖当前所有投影source families；Workbench search/pagination/detail/write gate；no-OA/turnover/bank-details/cost isolation；maintenance/domain jobs preserved。[VERIFIED: blast radius] |

### Wave 0 gaps

- [ ] `tests/test_workbench_query_facade.py` lacks a public `refresh_status` stale->exact enqueue test; existing test only proves fast port and timeout.[VERIFIED: test inventory]
- [ ] 缺少test-owned writer→proof完整矩阵及真实PostgreSQL mutation contract tests，无法机械证明所有Workbench-affecting writer都会使exact scope stale；新增`tests/test_workbench_source_proof_contract.py`，不新增runtime manifest。[VERIFIED: resolved decoupling requirement + test inventory]
- [ ] `web/src/test/WorkbenchSelection.test.tsx` lacks fake-timer assertions for visibility pause、all-status completion+1s cadence、single-flight、focus coalescing、zero full-payload polling and one reload after external generation change.[VERIFIED: frontend scan]
- [ ] No single automated integration currently protects bank-flow submit -> status self-enqueue -> worker publish -> visible Workbench reload.[VERIFIED: test inventory]
- [ ] Performance harness/evidence must cover target visible-client concurrency and commit-to-visible four-segment p99 before release.[VERIFIED: D-13/D-15]

### Recommended execution waves for planner

1. **Wave 1 / Plans 40-01..03 — Independent proven hotspots:** probe/FinanceTable、三个 proven SQL owners、import batch-row only.  
2. **Wave 2 / Plan 40-04 — Legacy facts + local candidate:** Search/no-OA guard/docs and full local handoff; no push/deploy.  
3. **Wave 1 / Plans 40-05..06 — Workbench backend/frontend roots:** existing facade helper and local completion-driven poller.  
4. **Wave 2 / Plan 40-07 — Writer→proof + local legacy + correctness E2E:** real PostgreSQL matrix and deterministic Browser flow.  
5. **Wave 3 / Plan 40-08 — Docs/capacity/browser p99/one release:** Playwright Node monotonic t0..t4, derived capacity, official deploy and rollback evidence.  

[VERIFIED: recommendation based on dependencies; Wave 2 depends only on response contract, Wave 3/4 validate whole loop]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---:|---|
| V2 Authentication | No behavior change | Existing Workbench session auth remains route owner。[VERIFIED: D-16/current routes] |
| V3 Session Management | No behavior change | Poller uses same authenticated fetch path；no token storage/change。[VERIFIED: current API client] |
| V4 Access Control | Yes regression | refresh-status read permission unchanged；bank-flow read/write permissions unchanged。[VERIFIED: route/module contracts] |
| V5 Input Validation | Yes regression | existing month -> `all|YYYY-MM` scope normalizer and gateway policy fail closed。[VERIFIED: scope policy contract] |
| V6 Cryptography | No | No cryptographic operation or secret introduced。[VERIFIED: proposed scope] |

### Threat model

| Threat | STRIDE | Mitigation |
|---|---|---|
| 每个visible client约1 QPS放大canonical proof | Denial of Service | completion-driven、hidden暂停、single-flight、只调用有界status；目标并发API/DB容量门禁不通过不发布。[VERIFIED: updated D-12/D-13] |
| forged/invalid scope写入queue | Tampering | route normalization + gateway policy validate；业务service不直接SQL。[VERIFIED: gateway contract] |
| duplicate enqueue/worker write amplification | Denial of Service | gateway active coalescing + PostgreSQL durable dedupe；tests assert one active event。[VERIFIED: gateway/runtime queue] |
| stale generation用于写操作 | Tampering | non-fresh write gate保持禁用，version conflict fail closed。[VERIFIED: Workbench contract] |
| 删除显式repair/domain job导致不可恢复 | Availability | legacy inventory逐项分类；maintenance/matching/import保留。[VERIFIED: D-14] |

## Risks and Rollback

| Risk | Prevention / detection | Rollback |
|---|---|---|
| status endpoint queue amplification | exact-scope tests、active-event dedupe、queue counters | 回滚应用release；无数据migration。 |
| 某canonical writer未被source proof覆盖，关联台错误保持fresh | test-owned writer→proof矩阵；真实mutation断言affected stale/unaffected fresh；projection dependency变更review gate | 修canonical `updated_at`/version或proof query并重建受影响scope；禁止添加writer通知兜底。 |
| 约1 QPS/visible client导致API/DB负载放大 | 目标并发下status endpoint p95/error、source-proof SQL p95、连接池等待、PostgreSQL CPU/IO、visible request count | 容量门禁未过不发布；若发布后异常则回滚frontend poll change，writer零改动。 |
| hidden timer仍运行 | fake timers + visibility browser test + network count | 回滚frontend bundle。 |
| generation重复reload/selection丢失 | same-version zero reload + one-version-change test | 回滚frontend change。 |
| stale enqueue错误退化为`all` | month/all exact tests + static assertion | 回滚facade change；durable queue按现有ops检查/收敛。 |
| legacy删除误伤operator | 只删CodeGraph/whole-repo证明无consumer的Workbench局部字段；backend ops endpoint保留 | 恢复previous release/source；无schema rollback。 |
| 3秒SLO或目标并发容量无法满足 | 四段p99与API/DB容量测量阻断发布 | 回滚frontend/facade change；保持旧稳定版本，不扩大架构。 |

[VERIFIED: no schema/dependency/runtime topology change makes release rollback sufficient]

## Plan Recommendations

### Recommended Workbench plan set: `40-05-PLAN.md` through `40-08-PLAN.md`

**Goal:** 在零普通写侧fan-out前提下，让公开 Workbench freshness/status 成为完整自愈入口，并用最小 browser scheduler 在访问时快速收敛。[VERIFIED: research conclusion]

**Files expected to change (minimum):**

- `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- `backend/src/fin_ops_platform/services/workbench_sql_projection.py`（仅当writer→proof契约测试证明现有proof漏项时修改；不改writer）
- `tests/test_workbench_query_facade.py`
- `tests/test_workbench_source_proof_contract.py`（test-only writer→proof matrix；不建立runtime registry）
- `tests/test_workbench_routes.py` 或已有API owner test（只在需要锁HTTP shape时）
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/features/workbench/api.ts`、`exceptionTypes.ts`（仅删除已证明死的 Workbench target fallback）
- `web/e2e/fixtures/operationLatency.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`（existing Playwright Node monotonic owner + real-backend t0..t4 case）
- `.planning/phases/40-performance-contract-hot-path-closure/40-workbench-visibility-p99.json`（redacted per-sample/aggregate report）
- affected long-term Workbench/read-model/runtime docs and Phase 40 summary/verification

[VERIFIED: recommendation; bank-flow production files intentionally absent]

**Plan 40-05 — Backend self-heal:** 先写 stale/exact/fresh/refreshing/failed/timeout tests，再让 `refresh_status()` 复用 `_groups_refresh_status_payload`；禁止新增方法层、repo port或endpoint。[VERIFIED: root gap]

**Plan 40-06 — Frontend 1秒 completion-driven poll:** 用局部 self-scheduling effect替换setInterval；写fake-timer/visibility/focus/single-flight/all-status completion+1s/zero full-payload/version reload tests；保留现有状态banner/write gate。[VERIFIED: frontend gap and updated D-12]

**Plan 40-07 — Writer→proof audit, closed-loop regression and legacy guard:** 盘点所有Workbench projection canonical dependencies及其生产writer，建立test-owned矩阵；每类执行mutation并断言affected exact proof变化、unaffected不变、fresh->stale、writer零fan-out。再添加bank-flow status enqueue + worker publish + relation visible integration；删除Workbench局部dead target fallback；whole-repo guard禁止refresh event/operation barrier回归；保留maintenance/domain jobs。[VERIFIED: resolved decoupling contract + D-14/D-16]

**Plan 40-08 — Capacity/browser SLO evidence and release:** 先从命名生产 session/access evidence window 或批准 capacity contract 推导 `C_normal/C_peak`，再用 `max(4,C_normal)`/`max(8,C_peak)` 做容量门禁；由现有 Playwright spec/helper 的单一 Node monotonic clock记录 t0 POST、t1 commit、t2 exact status enqueue-observed、t3 fresh generation、t4 payload install/DOM identity，逐样本四段和等于 total；最后执行 official deploy/T+0/T+60/T+300/read-only audit/queue drain。前一个 release 保留回滚；容量或 p99 未通过不得发布。[VERIFIED: AGENTS and Phase 40 D-13/D-15]

### Acceptance truths

1. Bank-flow submit SQL/HTTP/frontend current-page I/O完全不变，写事务零 Workbench dirty/outbox。[VERIFIED: target D-10/D-16]
2. 所有能改变Workbench结果的canonical writer均在test-owned writer→proof矩阵中；真实mutation使affected exact scope proof变化、unaffected不变，writer零Workbench通知。[VERIFIED: resolved producer/consumer decoupling contract]
3. 任何公开 refresh-status stale proof都确保同一批exact mismatch scope进入existing gateway；fresh/refreshing零重复enqueue。[VERIFIED: target D-11]
4. active/focus immediate；hidden零poll；所有状态均在请求完成后等待1s；single-flight；new version只reload once。[VERIFIED: target D-12]
5. 每秒只调用现有有界refresh-status，零并发/积压/full-payload polling，目标并发API/DB容量证据通过；无新增runtime architecture或dependency，零`all`普通fallback。[VERIFIED: target D-13]
6. retired bank-flow/Workbench target residue有负向guard，显式ops/domain jobs保留。[VERIFIED: target D-14]
7. 四段commit-to-visible性能证据完整且p99 `<=3000ms`；未测量或目标并发不足时不得宣称PASS或发布。[VERIFIED: target D-15]
8. 七类测试适用性按上表执行，全量跨页回归和production release gate通过。[VERIFIED: target D-09]

## State of the Art

| Old approach | Current target | Impact |
|---|---|---|
| ordinary write fan-out / barrier / targets | canonical commit + consumer access-time proof | writer不认识消费者，减少耦合和写放大。[VERIFIED: Phase 27/40 contracts] |
| status只观察不推进 | status proof发现stale即existing gateway exact enqueue | 完成自愈闭环。[VERIFIED: recommendation] |
| fixed 5s setInterval + abort previous | all-status completion-driven 1s timeout | 检测窗口有界、single-flight、慢proof不被下一tick饿死；代价约1 QPS/visible client并受容量门禁。[VERIFIED: recommendation] |
| stale时重复full payload GET | lightweight status等待 + generation change后一次reload | 减少DB/payload/browser成本。[VERIFIED: existing Phase 29 pattern] |

## Assumptions Log

No `[ASSUMED]` claims. Code behavior、contracts、tests、runtime topology and historical timing cited here were verified from the repository; future production latency remains an acceptance measurement, not an assumption.

## Open Questions

1. **(RESOLVED) 是否在本计划删除全局无生产caller的frontend operationBarrier helper？**  
   - Known: runtime production imports为0，但backend endpoint和ops contract仍有潜在external consumers。[VERIFIED: scan]  
   - Resolution: Phase 40 只删除 Workbench-local dead target DTO fallback；global helper与backend operator endpoint均不在本次删除范围，避免把D-14扩大为跨模块清理。[VERIFIED: 40-07 locked scope]

2. **(RESOLVED) 生产p99如何取得足量样本而不重复写真实财务关系？**  
   - Known: production write smoke必须bounded/test-owned/reversible；单样本不是p99。[VERIFIED: D-07/D-15 and operations docs]  
   - Resolution: 隔离prod-equivalent PostgreSQL通过现有 Playwright harness 执行至少100个test-owned/reversible样本并计算p99；production只做一次批准的bounded reversible smoke和被动/只读佐证。不足100个同钟完整样本即`NOT_MEASURED`并阻断发布。[VERIFIED: 40-08 measurement gate]

3. **(RESOLVED) 目标“可见关联台客户端并发数”取什么容量档位？**  
   - Known: 每个持续可见客户端至多约1 QPS；总请求上限随可见客户端数近似线性增长。[VERIFIED: completion-driven scheduling math]  
   - Resolution: 候选冻结前最近14个完整自然日的production authenticated refresh-status session/access evidence为首选来源；以rolling 60-second bucket匿名unique clients计算`C_normal=p95`、`C_peak=max`，并测试`N_normal=max(4,C_normal)`、`N_peak=max(8,C_peak)`。若日志不能区分client/session，只允许改用有来源/版本/批准人的capacity contract；两者都没有则`NOT_MEASURED`并阻断发布。4/8仅是压测下限，不是生产实际计数。[VERIFIED: 40-08 blocking derivation]

## Environment Availability

This is a code/config-only change with no new external dependency. Local Node v26.3.0、Python 3.11.5、npm 11.16.0、PostgreSQL CLI and `rg` are available; actual disposable/production database credentials remain execution-time gated.[VERIFIED: local command probes and repository policy]

## Project Constraints (from AGENTS.md)

- GSD is mandatory for cross-module read-model/worker work; long-term facts must return to `docs/`.[VERIFIED: AGENTS.md]
- Read-model refresh must use `ReadModelRefreshGateway`/scope policy and PostgreSQL durable queue；business service cannot SQL dirty/outbox。[VERIFIED: AGENTS.md]
- Workbench active generation is a retained exception；do not mechanically replace it。[VERIFIED: AGENTS.md]
- Before deleting old paths, scan route/API client/service/repository/worker/test/docs callers and consumers；no hidden fallback/double path。[VERIFIED: AGENTS.md]
- Production work must consider permission、audit、rollback、consistency and verification；official deploy entry is `./scripts/deploy-oa.sh`。[VERIFIED: AGENTS.md]
- Applicable seven test categories and regressions are mandatory；failure/stale/refreshing/idempotency paths cannot be skipped。[VERIFIED: AGENTS.md]
- Prefer existing boundary/helper/gateway and minimum reversible diff；no new dependency or speculative abstraction。[VERIFIED: AGENTS.md + Ponytail mode]

## Sources

### Primary (HIGH confidence)

- Phase 40 `40-CONTEXT.md` D-01..D-17 and `40-01-PLAN.md` through `40-08-PLAN.md` — locked scope/performance/release constraints.[VERIFIED: repository planning artifacts]
- `AGENTS.md` and module boundary/read-model/worker governance documents listed in the task — architecture, I/O, test and release authority.[VERIFIED: repository docs]
- CodeGraph index: 981 files / 35,741 nodes / 88,203 edges, no pending staleness banner; symbols and call trails cited above.[VERIFIED: CodeGraph status/context/node/explore]
- Bank-flow page/route/application/state-store code and tests — current zero-fanout transaction chain.[VERIFIED: repository code/tests]
- Workbench query facade/freshness/projection/gateway/frontend code and tests — root gap and existing reusable path.[VERIFIED: repository code/tests]

### Secondary (historical production evidence, HIGH for recorded sample only)

- `docs/modules/reconciliation-workbench/tests.md` — refresh-status p95 138.925ms, combined initial/groups historical samples and access-to-fresh test ownership.[VERIFIED: repository production evidence]
- `docs/operations/monitoring.md` and `runtime-worker-governance.md` — p95/p99 measurement semantics, queue timestamps, bounded production write policy.[VERIFIED: repository operations docs]

### External sources

None. No framework/library behavior or package choice changed, so external documentation lookup and package legitimacy checks were not applicable.[VERIFIED: scope]

## Metadata

**Confidence breakdown:**
- Current bank-flow chain: HIGH — code, CodeGraph and transaction tests agree.[VERIFIED: code and transaction tests]
- Root gap: HIGH — sibling facade methods directly demonstrate missing enqueue.[VERIFIED: facade source]
- Minimal architecture: HIGH — all required components already exist and are tested.[VERIFIED: code and tests]
- Performance result: NOT YET MEASURED — updated all-status completion-driven 1s polling removes the former deterministic 5s detection conflict, but target-concurrency API/DB capacity and four-segment commit-to-visible p99 remain release-blocking measurements.[VERIFIED: updated D-12/D-13/D-15]

**Research date:** 2026-08-06  
**Valid until:** code changes to the cited Workbench/bank-flow boundaries or 30 days, whichever occurs first.
