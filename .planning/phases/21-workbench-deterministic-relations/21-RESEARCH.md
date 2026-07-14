# Phase 21: Workbench Deterministic Relations - Research

**Researched:** 2026-07-14
**Domain:** 关联台确定性正式关系、跨月 N:M:K 匹配、active-generation read model、旧候选链迁移
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### D-01 — Exactly two user-visible relation states

The Workbench exposes only:

1. Paired: the fact is a member of one active canonical relation.
2. Unpaired: the eligible fact is not in an active relation and appears as its own row.

Candidate, proposed, automatic-decision, automatic-match, source-linked and auto-closed are not user-visible or persisted business relation states.

### D-02 — Exact visibility partition

Let `C` be eligible canonical facts, `R` active relation members, `P` visible paired facts and `U` visible unpaired facts. The invariant is `P = R`, `U = C - R`, `P ∩ U = ∅`, `P ∪ U = C`, and each canonical fact appears exactly once.

### D-03 — Safe automatic results become formal immediately

A deterministic safe match must call the existing `WorkbenchRelationCommandService`/relation UoW and create or extend an active formal relation in the same orchestration path. No candidate or decision row is written first. Results that do not pass the safe rule create no relationship and leave every fact visible as an unpaired singleton.

### D-04 — Formal relation origin is audit metadata only

Manual confirmation, historical creation and system automatic creation share the same lifecycle, visibility and downstream behavior. Origin/rule/version/evidence may remain in immutable audit metadata, but must not branch relation status, projection or API behavior. Existing `manual_confirmed` storage may be treated as the generic confirmed mode rather than adding `automatic_confirmed`.

### D-05 — Existing active relations are preserved

Every pre-migration active canonical relation remains active and unchanged. Historical group IDs such as `case:decision:*` do not control visibility. If the current canonical state is active, the group is paired.

### D-06 — Cross-month matching

Matching must not stop at the selected month. Explicit unique business references may search all retained history. Strong composite evidence may search a bounded 365-day window. Amount-only, fuzzy-only or date-only similarity never creates a formal relation.

### D-07 — Arbitrary N:M:K shapes

The business model supports one-or-many OA rows, one-or-many bank rows and one-or-many invoices, including legitimate two-pane shapes such as OA+invoice or bank+invoice. There is no business cardinality cap. Computation must cluster by evidence first, remain resource-bounded and fail closed when limits are reached.

### D-08 — Deterministic safety and ambiguity

Inferred formalization requires currency/direction compatibility, exact amount closure across the participating panes, connected strong-evidence graph, a unique valid partition, no active-row overlap and no withdrawal block. Multiple valid partitions, conflicts or incomplete evidence create no relation. Explicit unique source references may create or extend a formal partial relation before amount closure when the reference itself proves ownership.

### D-09 — Negative/refund/reversal safety

Generic inferred matching applies to compatible positive flows. Red invoices, refunds and reversals auto-formalize only when an explicit unique original-reference link proves the relationship; otherwise they remain unpaired.

### D-10 — Simple lifecycle

An active relation persists until an explicit audited withdraw/cancel. Source-version changes do not automatically withdraw it. Hard corruption is an internal audit/repair condition, not a third relation state. An explicit user withdrawal blocks automatic recreation of the same canonical row set.

### D-11 — Projection is relation-only

Projection reads canonical facts plus active relations. Active relations become paired groups; every remaining eligible fact becomes one unpaired singleton. Projection must not infer, promote, demote, merge or hide candidate groups.

### D-12 — All-scope composition

`month=all` must union every active month-shard member by canonical object identity. It must aggregate group headers without choosing only the latest shard, and list/detail/Audit must share the same active-generation boundary. The known 13 omitted active input invoices are a required regression fixture.

### D-13 — One modular I/O chain

The target flow is: bulk canonical fact reader -> pure deterministic matcher -> orchestrator -> existing formal relation command/UoW -> history/outbox -> read-model workers. SQL stays in repositories; routes/pages never infer relationships; services do no per-row I/O; refresh uses the existing gateway and durable PostgreSQL queue. No replacement candidate service/table is allowed.

### D-14 — Full legacy removal

After a whole-repository caller scan and porting still-valid deterministic rules, remove both legacy systems: `workbench_candidate_matches`/`WorkbenchCandidateMatchService` and `workbench_reconciliation_decisions`/`WorkbenchReconciliationDecisionStore`, including models, protocols, adapters, orchestrator dual mode, projection hooks/stubs, grouping heuristics, repository automatic-group filters, API/frontend states, tests, tools, grants and indexes. Use a forward migration; never rewrite historical migrations. Unrelated UI selection variables named `candidate` and exception evidence are not relation states and are out of this deletion scope.

### D-15 — Manifest-driven migration and rollback

Before backfill, capture canonical fact hashes, active relations/history, visibility sets, queue/freshness state and old candidate/decision inventories. Re-evaluate old candidate material from current canonical facts; never trust old status/confidence. Only `promote_safe` groups create formal relations. Rollback may withdraw only relation IDs created by the migration manifest. Existing relations and canonical facts are never rewritten.

### D-16 — Required counterexamples and closure evidence

The Yunnan Lifu invoice `26532000000716859331` (`inv_imported_0369`), OA `oa-pay-2169`, amount 520.00 already exists in an active canonical relation and must display as paired without recreation. The 13 active input invoices previously omitted by all-scope composition, totaling 1709.49, must display as unpaired singleton rows unless a canonical active relation exists. Data hashes, active relation preservation, no overlap, no hidden facts, worker drain, freshness and System Audit must all pass.

### the agent's Discretion

No separate discretion section was provided.

### Scope Fence

- Preserve unrelated relation modes such as ETC, batch accounting, turnover closure and no-OA/bank-flow batches; they encode business ownership rather than creation origin.
- Do not create a new universal fact service, a new relation status hierarchy or a replacement candidate table.
- Do not deploy to or mutate a real production environment without passing repository safety gates and using the authorized operational entry points. Local and disposable-PostgreSQL verification must complete first.
- No raw user prompt is copied into long-term `docs/`; only approved business and architecture facts are promoted after implementation review.

### Deferred Ideas (OUT OF SCOPE)

None. The phase must close implementation, legacy deletion, migration, tests, docs and controlled data verification together.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|---|---|---|
| RELVIS-01 | Every eligible canonical Workbench fact appears exactly once: as a member of one active formal relation or as one standalone unpaired row; no fact is hidden or duplicated. | Relation-only projection、集合恒等式 Audit、all-scope logical-member union。 |
| RELVIS-02 | A deterministic safe automatic match creates or extends the canonical active relation in the same orchestration path; candidate/proposed/open/paired decision records are not persisted or exposed as business relation state. | 纯 matcher 输出 formalization plan，orchestrator 直接调用现有 command/UoW。 |
| RELVIS-03 | Matching supports cross-month OA, bank and invoice facts and arbitrary N:M:K cardinality without a business-size cap, while computation remains bounded and fails closed. | 全历史显式引用、365 日复合窗口、证据聚类、状态预算而非业务基数上限。 |
| RELVIS-04 | Amount-only, fuzzy-only, date-only, ambiguous, conflicting, resource-limited and unsafe negative/refund results never create a formal relation; their facts remain visible as standalone unpaired rows. | 强证据图、唯一分区、正向流规则、红冲显式原始引用、fail-closed 矩阵。 |
| RELVIS-05 | Legacy candidate-match and reconciliation-decision runtime paths, projection hooks, repository filters, frontend states, tests and database objects are removed after a whole-repository caller scan; no compatibility fallback remains on the new chain. | 全仓删除/移植/保留清单和 forward drop 迁移。 |
| RELVIS-06 | Existing active relations remain unchanged and visible regardless of historical group-id prefix or creation origin; relations persist until an explicit audited withdraw/cancel, and an explicit withdrawal blocks automatic recreation of the same row set. | active relation 唯一可见性依据、历史 row-set fingerprint 拦截、迁移 preserve set。 |
| RELVIS-07 | `month=all` composes the union of every active month shard by canonical member identity and cannot drop source-linked or otherwise repeated group members; list, detail and Audit use the same generation boundary. | 当前 latest-shard 根因、logical group/member CTE 和 active-generation-set version。 |
| RELVIS-08 | Relation writes use `WorkbenchRelationCommandService`/UoW, SQL remains in repositories, matching is pure over bulk inputs, and read-model refresh uses the existing gateway/durable queue with no page/route/service/repository/worker I/O pollution. | I/O contracts、依赖方向、事务 advisory row locks、既有 outbox 链复用。 |
| RELVIS-09 | Migration/backfill is manifest-driven, idempotent, preserves canonical fact hashes and pre-existing active relations, refreshes only affected scopes, and can withdraw only newly created migration relations on rollback. | 两阶段 cutover、manifest 分类、relation-ID allowlist rollback。 |
| RELVIS-10 | Applicable seven-category tests and controlled data verification prove the Yunnan Lifu 520 invoice/OA relation is paired, the known 13 omitted invoices are recovered as unpaired, queues/read models converge, and canonical data is unchanged. | 七类测试矩阵、本地/disposable PG/受控生产三级 gate。 |
</phase_requirements>

## Summary

当前缺陷由两条仍然相互影响的旧语义造成。第一，matching worker 同时支持 legacy candidate 表与 reconciliation decision 表；新 decision 路径虽然随后可能调用正式 relation command，但仍先持久化 proposed/open/paired decision，并由 projection/grouping/filter 再解释。第二，Workbench projection 把 active relation 的“是否进入 paired 区”与三 pane 完整性、relation code、历史 group type 绑定，而 `month=all` 又对同一逻辑组使用 `distinct on` 只选最新月份分片，所以正式二 pane 关系仍可能进入 open，较旧分片独有成员会完全消失。[VERIFIED: local code `workbench_matching_orchestrator.py`, `workbench_reconciliation_engine.py`, `workbench_candidate_grouping.py`, `postgres_repositories/read_models.py`]

520 元立孚数据不是事实或正式关系缺失：仓库内已归档的只读诊断证明 invoice `inv_imported_0369`、OA `oa-pay-2169` 和 active `manual_confirmed` relation 均存在；旧状态机因为缺 bank 将 OA+invoice 正式关系留在 open。Phase 21 的新决策明确覆盖该旧口径：所有 active relation 都进入 paired，不能再由 pane 数量、case 前缀或创建来源降级。[VERIFIED: local evidence `.planning/debug/resolved/input-invoice-520-oa-missing.md`; locked decision D-16]

**Primary recommendation:** 保留现有 `workbench-matching` worker、dirty-scope queue、`WorkbenchRelationCommandService`、UoW、history/outbox 和 active-generation 发布模型；将 matcher 改为纯内存 formalization plan，删除两套 candidate/decision persistence 与 candidate grouping，用“active relation group + unclaimed singleton”构建投影，并把 all-scope 改成对全部 active month shards 的 logical member union。[VERIFIED: local architecture docs and code]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| canonical matching facts bulk read | Database / repository | API / worker | SQL、结构化引用、365 日范围和 active relation anchors 由 repository 一次批量返回；service 不逐行读。 |
| deterministic matching | Domain/service pure computation | — | 输入快照、输出 formalization plan；零 SQL、零 queue、零 clock/network I/O。 |
| formal relation creation/extension | Backend command/UoW | Database | 复用 command、history、idempotency、transactional outbox。 |
| matching scheduling/retry | Worker | PostgreSQL durable queue | 保留 `job.workbench_matching_dirty_scopes` 和 required worker。 |
| paired/unpaired projection | Read-model projection service | Read-model repository | service 只做集合映射；repository 持有 SQL 和 active-generation publication。 |
| all-scope union/list/detail | Read-model repository | API DTO | logical group/member CTE、筛选、分页和版本边界属于 repository。 |
| exact visibility/system proof | Audit repository | Operations API/tool | 在一个 read-only repeatable-read snapshot 内证明集合恒等式。 |
| rendering | Browser/client | API | 只显示 paired/unpaired；不推断、不升级、不隐藏。 |

[VERIFIED: local docs `ARCHITECTURE.md`, module boundary docs, runtime worker governance]

## Project Constraints (from AGENTS.md)

- 代码修改前必须读取受影响模块及上下游 `boundary-io.md`；read model/worker 还必须更新 read-model contracts、runtime-workers 和 worker governance。[VERIFIED: repository `AGENTS.md`]
- 后端 route 只做 HTTP 映射，service 不读 cookie/header、不构造 response、不散落 SQL；repository 才知道 SQL。[VERIFIED: repository `AGENTS.md`]
- 非事务 refresh 必须走 `ReadModelRefreshGateway`；事务 writer 通过 UoW 等价写入 durable queue；Redis/RabbitMQ 不是状态事实源。[VERIFIED: repository `AGENTS.md`]
- 旧链替换前必须扫描入口、调用方、API client、service、repository、worker、read model、测试、文档，并删除 fallback/重复路径。[VERIFIED: repository `AGENTS.md`]
- 行为变更必须评估七类测试；生产级改动同时覆盖权限、审计、回滚、数据一致性与验证。[VERIFIED: repository `AGENTS.md`]
- 采用 Ponytail：复用既有 command/UoW/queue/audit，删除旧逻辑优先，不新建 universal fact service 或候选状态层。[VERIFIED: repository `AGENTS.md` and locked scope]

## Standard Stack

本阶段不安装外部包，也不需要 package legitimacy audit。现有标准能力已经覆盖事务、SQL、测试与 UI。[VERIFIED: local dependency manifests]

| Component | Verified local version/contract | Purpose |
|---|---|---|
| Python | 3.13.9 | backend service、matcher、migration/audit tools |
| PostgreSQL client/server contract | psql 17.10；本机 socket 可接受连接 | canonical facts、relations、queue、read models |
| `unittest` / pytest | repository primary unittest；pytest 9.0.2 installed | backend deterministic/integration checks |
| Node.js / npm | Node 26.3.0 / npm 11.16.0 | frontend build/tests |
| Vitest | 2.1.9 installed | frontend contract/component tests |
| Playwright | 1.60.0 installed | deterministic business-flow browser tests |
| Existing services | relation command/UoW, refresh gateway, durable queue, Audit | 不重复实现事务、幂等、fan-out、freshness |

### Do not introduce

| Instead of | Required choice | Reason |
|---|---|---|
| new candidate/proposal table | pure in-memory plan + formal command | 非安全结果无需持久状态；用户只需要 paired/unpaired。 |
| new relation status hierarchy | existing active/withdrawn lifecycle | origin 仅审计 metadata。 |
| new all-scope materialized truth | compose active month generations | `workbench` 已有原子 generation model。 |
| per-row repository calls | bulk seed/reference/window query | I/O 清晰且避免 N+1。 |
| custom queue/cache | existing PostgreSQL queue/gateway | durable fact 已存在。 |

## Current Root Causes

### 1. Automatic chain persists false relationship states

`WorkbenchMatchingOrchestrator.run` currently has two branches: legacy mode deletes/upserts `workbench_candidate_matches`; decision mode calls `WorkbenchReconciliationEngine`, which expires/upserts `workbench_reconciliation_decisions` and only then may auto-create or extend a formal relation. `WorkbenchWriteUnitOfWorkContext` also exposes `candidate_matches`, so exception/write flows consume/suppress a state that should not exist.[VERIFIED: local CodeGraph impact and code in `workbench_matching_orchestrator.py`, `workbench_reconciliation_engine.py`, `workbench_uow.py`]

`WorkbenchFreeMatchingEngine` outputs `WorkbenchDecision` with proposed/open/paired/consumed concepts and searches only `T-2..T+2`. It hard-caps each subset at six rows, keeps at most two results per sum, and aborts after 20,000 subset states. Currency is not part of its normalized row, OA rows are forced to expenditure, and negative amounts are excluded rather than handled through an explicit original-reference rule.[VERIFIED: local code `workbench_free_matching_engine.py`]

### 2. Projection still decides whether a formal relation is “complete enough”

`WorkbenchCandidateGroupingService` first labels rows paired, then calls `_split_valid_and_incomplete_paired_groups`. Its default policy requires three panes; bank relations use a requirement policy; OA+invoice is paired only for a special code allowlist. It then performs source-linked grouping, candidate merging, amount aggregation, promotion/demotion and auto-close classification.[VERIFIED: local code `workbench_candidate_grouping.py:115-184,270-293,1390-1467`]

This directly violates D-01/D-11: active relation membership, not pane completeness, must determine paired. Exception/ignored metadata may remain orthogonal, but may not become a third relation state.[VERIFIED: locked decisions D-01, D-11]

### 3. All-scope chooses a shard instead of unioning members

`_workbench_active_month_groups_sql()` computes a logical ID and then executes `distinct on (zone, all_scope_group_id)`, ordered by descending `scope_month` and `updated_at`. The selected row retains one `source_group_id`. `_materialize_workbench_group_payloads` subsequently loads members only for that one `(scope_key,generation_id,zone,group_id)`; older active shards in the same logical group are not read.[VERIFIED: local code `postgres_repositories/read_models.py:54-105,6543+`]

`get_workbench_group_detail` repeats the latest-shard choice, so list and detail can both omit older members. Current Workbench page Audit proves canonical month projection membership and active relation edges, but does not prove that the composed all-scope member set equals the union of every active month generation member set.[VERIFIED: local code `postgres_repositories/read_models.py:7174+`, `workbench_page_audit.py`, `workbench_projection_audit.py`]

## Target I/O Contracts

### A. Bulk canonical fact reader

**Input**

- tenant, dirty scope month(s), current rule version;
- all active relation members touching the seed/reference/window facts;
- retained-history explicit reference keys and a 365-day composite evidence window.

**Output**

- immutable facts with `row_type`, canonical row ID, object identity, amount in minor units, normalized currency, direction, event date, typed explicit references, strong structured evidence fields and source version;
- active relation anchors and exact audited withdrawal row-set fingerprints;
- affected month scopes.

**Boundary**

- SQL remains in a focused PostgreSQL repository; one query per fact class/reference batch, never per row.
- Reuse `FinancialObjectIdentityPolicy`, `WorkbenchObjectIdentityArbitrationService`, `oa_attachment_matches_oa`, canonical invoice/bank/OA columns and active relation repository. Do not build a universal fact service.

[VERIFIED: local canonical schemas and identity services]

Canonical columns already include invoice and bank `currency`; OA projection writes `currency='CNY'`. Invoice source links and `oa_form_id` carry direct OA ownership identity. The current Workbench SQL reader simply omits several of these columns, so the fix is to extend the bulk repository projection rather than invent fields.[VERIFIED: migrations `0002_core_imports_invoices_bank.sql`, OA projection repository, `oa_attachment_invoice_linking.py`]

### B. Pure deterministic matcher

**Input:** complete immutable fact batch + active relation anchors + withdrawal fingerprints + explicit budgets.
**Output:** zero or more immutable `FormalRelationPlan` values containing canonical row IDs/types, create-or-extend target, amount check, rule/version, evidence, affected scopes and deterministic idempotency key.
**Forbidden output:** candidate ID, decision status, display state, repository call, clock read, log write or queue mutation.

The smallest implementation is to refactor/rename the useful algorithms in `workbench_free_matching_engine.py` into one pure matcher module and define the plan dataclass beside it. Do not add a generic rule framework or replacement model package.[VERIFIED: current engine is already mostly pure; Ponytail constraint]

### C. Orchestrator

**Input:** claimed dirty scope.
**Flow:** bulk read → matcher → for each deterministic plan call transaction-bound `WorkbenchRelationCommandService.confirm_relation` through the existing UoW → complete/fail dirty scope.
**Output:** run summary with created/extended relation IDs, skipped reason counts, affected scopes and outbox IDs; no candidate/decision inventory.

Use `relation_mode='manual_confirmed'` as generic confirmed storage. Put `origin=system_deterministic`, rule/version/evidence and run/manifest IDs only in audit metadata/history.[VERIFIED: command signature supports relation mode, evidence, rule version, actor, history operation and idempotency]

### D. Formal write concurrency

`WorkbenchRelationCommandService.confirm_relation` checks active conflicts and supports idempotency, while `WorkbenchWriteUnitOfWork.run` atomically persists relation/history/idempotency/outbox. The current check loads a snapshot before save and no canonical active-member uniqueness constraint exists on the array column, so two concurrent, different idempotency keys can race.[VERIFIED: local CodeGraph node for `confirm_relation` and UoW; relation migrations]

Add one repository port operation that acquires sorted PostgreSQL transaction advisory locks for normalized canonical row IDs before reloading active relations. Every confirm/replace/withdraw command path must use the same lock convention; in-memory repositories use a no-op/test lock. This is smaller than a new canonical member table and closes automatic/manual overlap races without using read models as a lock.[VERIFIED: current transaction boundary supports a repository call before mutation]

### E. Relation-only projection

**Input:** eligible canonical facts `C`, active relations `R`, orthogonal exception/ignored metadata.
**Output:**

- one paired group per active relation, with all available canonical members;
- one unpaired singleton group per fact in `C-R`;
- ignored facts remain in the existing explicit ignored scope and are not misrepresented as a relation state.

Use stable DTO values `zone/status = paired|unpaired`, `group_type = relation|unpaired`; downstream relation projection remains `linked|unlinked`. Existing special relation modes may decorate labels/collapsed summaries but may not decide paired membership.[VERIFIED: locked decisions; downstream projection already has linked/unlinked fallback]

Delete completeness demotion, candidate/source-link aggregation, open candidate merge, decision projection stub and group/case-prefix visibility filters. A unique OA attachment source link is handled earlier by formal matching; if it is not unique/safe, OA and invoice remain separate unpaired facts.[VERIFIED: locked D-03, D-08, D-11, D-14]

## Deterministic Safety Rules

### Rule order

1. Remove rows already owned by an active relation from create consideration; load their relation as an extension anchor.
2. Resolve typed explicit ownership/original-reference edges over all retained history.
3. Formalize an explicit edge only when the reference is unique in its declared namespace and no active overlap/withdrawal block exists.
4. For residual positive flows, load the 365-day window, partition by normalized currency and direction, and cluster by strong evidence.
5. Generate exact-closure hyperedges within each evidence component.
6. Solve for unique non-overlapping membership. Formalize only edges present in the unique valid solution; ambiguous facts remain unpaired.
7. Recheck locks, active overlap, row-set withdrawal and current source fingerprints inside the write transaction.

[VERIFIED: locked D-06 through D-10; current engine provides reusable exact-sum and graph-connectivity code]

### Evidence policy

| Evidence | Window | May prove relation? | Conditions |
|---|---|---|---|
| typed OA attachment/source link to canonical OA identity | all retained | yes, including partial | unique namespace value; exact structured field; not free text |
| typed original invoice/transaction reference for red/refund/reversal | all retained | yes | unique original target and compatible reversal direction |
| exact tax identifier | 365 days | strong edge | valid normalized identifier and direction-specific party role |
| exact normalized legal counterparty name | 365 days | supporting edge | must have a second independent structured signal; common/weak names excluded |
| exact contract/order/project code, invoice number in allowlisted structured field | 365 days | strong supporting edge | exact token, typed field, not substring/fuzzy |
| project name/reason/summary text | 365 days | supporting only | exact normalized evidence plus independent party identity |
| scheduled/payment/invoice date | 365 days | compatibility/tie rejection only | never sufficient and never used to pick one ambiguous same-amount result |
| amount equality | 365 days | closure only | never evidence by itself |
| fuzzy/substring similarity | any | no | telemetry/debug only, no relation state |

[VERIFIED: current structured columns/token helpers and locked safety decisions]

The current matcher treats applicant/project/reason tokens generically and can score a same-amount invoice by date. Those branches must not be ported as formalization proof unless they satisfy the stronger table above. Existing exact tax/name/reference extraction helpers can be ported; date scoring and amount-only fallback must be deleted.[VERIFIED: local `workbench_free_matching_engine.py`]

### N:M:K exact closure

For every inferred plan, each participating pane total must equal the same signed minor-unit total after currency/direction partitioning. Two-pane relations compare the two participating totals; three-pane relations compare OA, bank and invoice totals. Every fact must have at least one strong edge and the induced evidence graph must be connected.[VERIFIED: locked D-07/D-08; current engine already implements connected three-pane evidence]

There is no `max_size=6` business rule. Preserve boundedness with a maximum search-state count, deadline/memory budget and deduplicated amount states. Explicit-reference components do not enumerate subsets and can contain arbitrary members. If a residual component exhausts its budget, emit only an operational `resource_limited` skip counter and create no relation or persisted state.[VERIFIED: locked D-07; current six-row constants are implementation-only]

### Ambiguity

Do not “pick the highest score.” Enumerate bounded valid exact-closure hyperedges and compare maximal non-overlapping assignments. A row set is safe only when its membership is invariant across all valid maximal assignments. If two invoice subsets, two party partitions or an extension/create alternative compete, none of the affected rows are formalized.[VERIFIED: locked D-08; current two-result conflict behavior is reusable but status persistence is not]

### Withdrawals and persistence

Reuse the existing exact row-set comparison from `WorkbenchMatchingRelationReadPort.has_withdrawn_relation_for_row_ids`, but move it out of the deleted reconciliation engine into the relation read repository/command boundary and fingerprint canonical object identities plus row types in sorted order. Only an explicit user `withdraw_link`/cancel history blocks recreation of that exact set; automated replace history must not over-block unrelated future sets.[VERIFIED: local `workbench_reconciliation_engine.py:60-86`; locked D-10]

## All-Scope Composition Design

Replace latest-shard selection with one reusable repository SQL composition owned beside Workbench read-model queries:

1. `active_generation_set`: capture every `(scope_key,generation_id)` whose generation is active, plus a deterministic version hash.
2. `physical_groups`: all groups in that exact set.
3. `logical_groups`: paired key is canonical active relation/case identity; unpaired key is `(pane,object_identity_key)` with stable `(pane,row_id)` fallback. Do not merge by source-link/candidate prefix.
4. `logical_members`: join every physical group instance to `workbench_group_rows`, dedupe by `(logical_group,pane,object_identity_key)`, exclude summary roles from canonical fact counts.
5. Aggregate header fields and sort bounds from the complete member set; validate zone/group metadata agreement instead of choosing newest payload.
6. Use the same CTE/helper in count, list, detail and the Workbench page Audit proof.

[VERIFIED: existing group/member schemas and current root cause]

All repository calls involved in one response must execute in one read-only repeatable-read transaction. The response continues to publish the active-generation-set version. Detail should accept the list version as an optional expected version and return the existing stale/version error contract if generations changed, so the UI cannot silently mix a list from one set with detail from another.[VERIFIED: existing active-generation version and stale-precondition patterns]

Required proofs in `collect_workbench_page_integrity_issues`:

- `P = R`: visible paired typed member identities equal active canonical relation member identities.
- `U = C-R`: visible unpaired typed member identities equal eligible canonical facts minus active members.
- no identity appears in both sets or more than once.
- composed-all member identities equal the union of all active month-shard member identities.
- every paired group points to one active relation; no group ID prefix decides status.
- list/detail materialization for a sampled/all bounded group set returns the same identity set and generation version.

[VERIFIED: existing Audit is already a single repeatable-read snapshot and is the correct proof owner]

## Whole-Repository Legacy Inventory

### Delete after porting

| Legacy area | Files / objects | Required action |
|---|---|---|
| candidate store/service | `workbench_candidate_match_service.py`, state-store protocol/methods, Postgres repository methods, app wiring | delete service, snapshot restore, scope freshness, consume/suppress calls and runtime source version |
| candidate DB | `read_model.workbench_candidate_matches` and its scope/GIN indexes/grants | inventory then forward drop; do not edit migration 0006 |
| legacy candidate rules | `workbench_matching_rules.py`, orchestrator legacy branch | port only still-valid evidence extraction/exact checks, then delete |
| decision model/store | `workbench_reconciliation_models.py`, `workbench_reconciliation_decision_store.py`, cleanup service | delete statuses/models/store/cleanup |
| decision orchestration | `workbench_reconciliation_engine.py`, `workbench_special_reconciliation_adapter.py`, orchestrator decision branch | port direct formalization/extension/withdraw guard and special deterministic rules, then delete redundant layer |
| decision DB | `read_model.workbench_reconciliation_decisions` and all indexes/grants | inventory then forward drop; preserve matching dirty queue and matching runs |
| projection/grouping semantics | candidate grouping heuristics, SQL projection decision stub, automatic group filters, demotion/promotion/source-linked/auto-close branches | replace with relation-only grouper |
| UoW contamination | `WorkbenchWriteUnitOfWorkContext.candidate_matches`; exception consume/suppress hooks | remove candidate repository from UoW context and callers |
| tools/scripts | `repair_workbench_reconciliation_decisions.py`, candidate portions of `workbench_compute_evidence.py`, `check-local-runtime.sh`, `reconcile-runtime-read-models.py`, rehydrate hooks | delete/replace old inventory and repair semantics |
| API/frontend | workbench group-type mappings, decision/candidate DTOs, relation-status candidate in bank detail/input usage, candidate-semantics browser fixtures | expose relation/unpaired and linked/unlinked only |
| tests/docs | dedicated candidate/decision store/cleanup/model tests and legacy behavior assertions | delete obsolete tests; rewrite valuable scenarios against formal relation/unpaired behavior; update current docs |

[VERIFIED: whole-repo literal scan and CodeGraph impact: candidate service affects app wiring, worker, orchestrator, exception flows and tests; decision store affects reconciliation engine, app/API and downstream tests]

### Port before deletion

- Exact amount minor-unit arithmetic, subset DP mechanics, connected evidence graph and ambiguity detection from `workbench_free_matching_engine.py`.[VERIFIED: local code]
- OA attachment source identity helpers from `oa_attachment_invoice_linking.py` and source-link resolver.[VERIFIED: local code]
- Tax/name/reference token normalization, but only under the stricter evidence policy above.[VERIFIED: local code]
- Special business detectors needed by ETC, batch accounting, turnover and no-OA flows; their decision adapter/status wrapper is deleted.[VERIFIED: scope fence and current special services]
- Existing direct formal relation create/extend, amount check, history metadata, idempotency and exact withdrawn-row-set guard.[VERIFIED: local command/reconciliation code]

### Explicitly preserve

- `job.workbench_matching_dirty_scopes`, `app.matching_runs`, the `workbench-matching` required worker registration, CLI flags and systemd/env unit. Only semantics/source-version names change.[VERIFIED: runtime registry, worker and migrations]
- `app.workbench_pair_relations`, relation histories, command/UoW, outbox, read-model refresh gateway and active generations.[VERIFIED: canonical-fact/read-model contracts]
- ETC, batch accounting, turnover closure, no-OA/bank-flow relation modes and their presentation metadata.[VERIFIED: scope fence]
- Exception `candidate_evidence`, pending-invoice search candidates, OA pending bank candidates, input-invoice reverse candidates, bank auto-category candidates and ordinary local variable names `candidate`; these are option/evidence concepts, not Workbench relation states.[VERIFIED: semantic scan and D-14]
- Ignored/exception UI workflows as orthogonal fact eligibility/resolution behavior; remove only their candidate-store consume/suppress dependency.[VERIFIED: existing module behavior and scope fence]

### Static closure guard

Add a focused repository-boundary test that fails if production runtime code imports the deleted candidate/decision modules or contains the old DB table names/status constants. Allow historical migration files and archived implementation notes through an explicit path allowlist; do not use a blind whole-repo ban that breaks unrelated selection candidates.[VERIFIED: repository already uses runtime boundary guard tests]

## Runtime State Inventory

| Category | Items Found | Action Required |
|---|---|---|
| Stored data | two legacy read-model tables; active canonical relations/history; active Workbench generations; dirty scopes/matching runs; Redis group-page cache | snapshot legacy inventories, preserve/hash canonical state, rebuild affected read models, evict/bump cache schema, then forward-drop only legacy tables |
| Live service config | required `workbench-matching` worker consumes DB dirty scopes; deploy docs currently say it generates decisions | keep worker/unit/flags, update handler and documentation; quiesce it during schema cutover |
| OS-registered state | systemd worker instance name `workbench-matching` | no rename/re-registration; verify active worker after deploy |
| Secrets/env vars | no candidate/decision-specific secret or env key found; matching batch/lease/retry flags remain | no secret migration; preserve existing local admin-token handling |
| Build artifacts | old release directories/images may contain old Python code, but active release symlink determines runtime | normal release activation and runtime consistency check; no in-place artifact edits |

[VERIFIED: migrations, runtime registry, deploy env/docs, source scan]

The forward migration must drop `read_model.workbench_candidate_matches` and `read_model.workbench_reconciliation_decisions`. Their indexes and table grants disappear with the tables. It must not drop the dirty-scope table, matching-runs table or the columns/indexes added to those operational objects by migration 0028.[VERIFIED: migrations 0006, 0028, 0029, 0093]

## Manifest-Driven Migration and Rollback

### Two-release cutover

1. **Release A, inert legacy storage:** new runtime no longer reads/writes either legacy table; matching worker is quiesced during activation. A read-only planner records pre-state and re-evaluates legacy rows using current canonical facts and the new pure matcher.
2. Apply only manifest entries classified `promote_safe` through command/UoW. Entries classify as `preserve_active`, `promote_safe`, `ambiguous`, `ineligible`, `missing_fact`, `withdrawal_blocked` or `resource_limited`; only one class writes.
3. Drain queue, rebuild only affected scopes, run visibility/System Audit and observe one stabilization window with zero old-table access.
4. **Release B, forward removal:** add the next migration (currently 0104) that drops both legacy tables; remove the temporary legacy inventory reader and all old runtime code/tests/docs.

[VERIFIED: current latest migration is 0103; deploy applies forward migrations; D-14/D-15]

This staged sequence is not a dual business path: Release A has one new runtime path and leaves old tables inert only long enough to support audited inventory/rollback. No runtime fallback may read them.[VERIFIED: D-14]

### Manifest fields

- immutable manifest ID/schema/rule version, tenant, created-at, operator and approval;
- SHA-256 hashes/counts for eligible canonical OA/bank/invoice facts, active relations, relation histories, projected paired/unpaired identity sets, queue/freshness state and both legacy inventories;
- each evaluated row set, evidence, classification and reason;
- command idempotency key, created/extended relation ID, affected scopes and outbox IDs;
- pre/post hashes and Audit snapshot ID;
- rollback status.

Do not place raw sensitive payloads or credentials in the manifest; use canonical IDs, normalized evidence summaries and hashes.[VERIFIED: security/logging constraints]

### Idempotency and rollback

Use `manifest_id + sorted canonical row-set fingerprint + rule_version` as the command idempotency basis. Re-running apply must replay the same committed result. Existing active relations, including the 520 relation, classify `preserve_active` and are never replaced.[VERIFIED: existing UoW durable idempotency and D-05/D-16]

Rollback reads only the manifest-created relation-ID allowlist, previews current versions, and invokes the official audited withdraw command. It may not delete SQL rows, restore candidates, withdraw pre-existing relations, or rewrite canonical facts. After legacy tables are dropped, application rollback to old code is unsupported; use roll-forward for code and the manifest withdraw for data.[VERIFIED: D-15 and production operation constraints]

## Common Pitfalls

### Treating “unpaired” as a persisted candidate
**Failure:** creates a replacement state table and another visibility policy.
**Prevention:** unpaired is computed `C-R` at projection time; unsafe matcher output is nothing.
**Warning:** any new candidate ID/status/store/upsert method.

### Preserving pane-completeness in visibility
**Failure:** active OA+invoice such as the 520 relation remains open/unpaired.
**Prevention:** paired membership is exactly active relation membership; amount/pane completeness is creation safety only.
**Warning:** `_paired_group_has_enough_row_types`, relation-mode allowlists or bank requirement metadata in zone selection.

### Calling the matcher per month or per row
**Failure:** cross-month links are missed and DB I/O becomes N+1.
**Prevention:** seed → all-history explicit references + one 365-day bulk window.
**Warning:** repository calls inside match loops.

### Replacing the six-row cap with a larger business cap
**Failure:** legitimate large N:M:K relations remain impossible.
**Prevention:** bound search states/time/memory, not valid cardinality; fail closed with no stored state.
**Warning:** `MAX_*_COMBINATION_SIZE`.

### Using amount/date/name score to choose one ambiguous match
**Failure:** irreversible false formal relation.
**Prevention:** exact closure + strong graph + invariant unique partition.
**Warning:** best-score/date-distance winner logic.

### Dropping tables before the new runtime is active
**Failure:** old worker crashes or loses migration inventory.
**Prevention:** quiesce worker, Release A zero-access proof, then Release B drop.
**Warning:** migrations applied while old matching worker is still running.

### Rebuilding or mutating all canonical facts
**Failure:** repair exceeds scope and data safety cannot be proven.
**Prevention:** hash facts, write only formal relations through command, refresh only affected scopes.
**Warning:** direct UPDATE/DELETE on invoices/OA/bank/relation tables.

### Fixing all-scope only in list
**Failure:** count, pagination, detail and Audit disagree.
**Prevention:** one logical-group/member SQL owner and generation-set boundary.
**Warning:** a Python post-filter or detail-specific latest-shard query.

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Backend | Python unittest discovery; pytest 9.0.2 available for opt-in fixtures |
| Frontend | Vitest 2.1.9 |
| Browser | Playwright 1.60.0 |
| Quick backend | `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_matching_orchestrator tests.test_workbench_sql_runtime -v` (file names will change with legacy deletion) |
| Full | `bash scripts/verify.sh all` plus `bash scripts/verify.sh infra-smoke` |

[VERIFIED: local scripts and installed packages]

### Requirements to tests

| Req | Required automated proof | Primary files |
|---|---|---|
| RELVIS-01/06 | partition equality, duplicate/orphan checks, active two-pane always paired, case-prefix/origin invariant | new deterministic projection unit tests; `test_workbench_sql_runtime.py`; Audit tests |
| RELVIS-02/03/04 | pure matcher table tests: 1:1, N:M:K, two-pane, cross-month, explicit vs composite, ambiguity, resource limit, negative/refund | rewrite `test_workbench_free_matching_engine.py` as deterministic matcher tests |
| RELVIS-02/08 | worker → command/UoW → history/outbox; idempotency, conflict lock, rollback on failure | orchestrator, command, UoW and dirty-worker service tests |
| RELVIS-05 | no production import/table/status strings; migrations drop only two legacy tables | boundary/migration tests |
| RELVIS-07 | multi-shard source-linked regression: older shards contribute 13 synthetic input invoices totaling 1709.49; list/count/detail/Audit agree | `test_workbench_sql_runtime.py`, Audit tool tests |
| RELVIS-09 | manifest plan/apply/replay/rollback allowlist; canonical hashes unchanged | new migration tool unit + disposable PG integration |
| RELVIS-10 | 520 active OA+invoice paired without new relation; downstream linked; queue drain/fresh/Audit | backend integration + Workbench browser flow + controlled verification runner |

### Seven-category coverage

1. **Business core unit tests — applicable:** exact sums, evidence, unique partition, arbitrary cardinality, negative/refund, withdrawal block.
2. **Service-layer tests — applicable:** bulk repository contract, orchestrator, command/UoW, audit/history/outbox, idempotency and race.
3. **API contract tests — applicable:** paired/unpaired DTO, list/detail version, invalid zone/version, permissions/non-fresh behavior.
4. **Read model/cache/worker tests — applicable:** active-generation union, cache schema/invalidation, dirty worker retry/drain, no per-row rebuild.
5. **Frontend tests — applicable:** paired/unpaired rendering, singleton rows, loading/empty/error/stale, filters/sort/page/detail, no candidate chip.
6. **End-to-end integration — applicable:** import/change → dirty scope → formal relation → generation → downstream; withdraw prevents recreate; ambiguity stays singleton.
7. **Regression — applicable:** ETC/batch/turnover/no-OA modes, ignored/exception flows, downstream exports/permissions/search/pagination and existing active relations.

No category is non-applicable because the phase changes business rules, services, API/read model, worker, UI and cross-module flow.[VERIFIED: AGENTS test policy and impact scan]

### Sampling

- Per task: target unit/contract files plus `bash scripts/verify.sh lint`.
- Per wave: backend targeted set + `cd web && npm test -- --run` + `npm run build`.
- Phase gate: `bash scripts/verify.sh all`, `bash scripts/verify.sh infra-smoke`, disposable PostgreSQL migration/audit suite, static old-chain guard.
- Production apply gate: dry-run manifest, authorized deployment entrypoint, worker drain/readiness, Workbench page Audit and System Audit; never run automatically from implementation tests.

### Wave 0 gaps

- New pure matcher tests and formal plan fixture.
- New relation-only projection partition fixture.
- New all-scope 13-member multi-shard fixture.
- New manifest planner/apply/rollback tests.
- A disposable PostgreSQL URL is not currently configured; integration must fail/skip with an explicit external-input-required result rather than claim execution.

## Environment Availability

| Dependency | Required By | Available | Version/status | Fallback |
|---|---|---|---|---|
| Python | backend/tests/tools | yes | 3.13.9 | — |
| Node/npm | frontend/tests/build | yes | 26.3.0 / 11.16.0 | — |
| PostgreSQL CLI/server | migrations/integration | partially | psql 17.10; local socket accepts connections | set an explicitly test-owned database URL |
| `FIN_OPS_TEST_DATABASE_URL` | disposable PG suite | no | unset | blocking for real PG integration evidence |
| Docker daemon | optional disposable service | no verified daemon | client 28.5.1 only | local PostgreSQL test DB |
| Production admin/runtime authorization | controlled closure | not inspected | deliberately unavailable in research | user-authorized operational run |

[VERIFIED: local environment probes; secret values were not printed]

## Security Domain

### Applicable ASVS categories

| Category | Applies | Control |
|---|---|---|
| V2 Authentication | no contract change | keep existing API/worker authentication boundaries |
| V3 Session Management | no contract change | no new session/token storage |
| V4 Access Control | yes | migration apply/rollback and repair remain admin/operator approved; UI mutations keep current permissions |
| V5 Input Validation | yes | typed DTOs, normalized canonical IDs, bounded arrays/states, parameterized SQL, fail-fast command validation |
| V6 Cryptography | yes for evidence hashes | standard SHA-256 utility for manifest integrity; no custom crypto |

### Threat patterns

| Pattern | STRIDE | Mitigation |
|---|---|---|
| direct SQL or malicious reference value | Tampering | parameterized repository queries and allowlisted typed reference fields |
| duplicate concurrent formalization | Tampering | sorted transaction advisory row locks + post-lock active-overlap recheck |
| replayed migration/apply | Spoofing/Tampering | durable idempotency fingerprint and signed-off manifest hash |
| combinatorial matcher input | Denial of Service | evidence clustering, search-state/deadline/memory budgets, fail closed |
| operator rolls back pre-existing relation | Elevation/Tampering | manifest-created relation-ID allowlist and official withdraw preview/version |
| evidence leaks invoice/OA payload | Information disclosure | IDs/hashes/minimal evidence summary only; no raw payload or secrets |
| stale generation presented as fresh | Tampering | freshness gate, generation-set version and Audit equality proof |

[VERIFIED: repository security constraints and current command/queue patterns]

## Documentation Impact

Current canonical reference paths in CONTEXT contain two stale links: `docs/product-specs/workbench.md` and `docs/product-specs/reconciliation.md` do not exist; the actual product fact source is `docs/product-specs/reconciliation-and-workbench.md`. Implementation must correct these references where promoted, not create duplicate product specs.[VERIFIED: local files]

Update after implementation:

- product behavior: `docs/product-specs/reconciliation-and-workbench.md`;
- app runtime/ownership and API/read-model flows;
- reconciliation-workbench, workbench-relations, read-models, runtime-workers boundary/state/tests docs;
- read-model contracts and runtime worker governance;
- deploy worker description (direct formal relation, not decision generation);
- testing inventory/e2e coverage and operations runbook for manifest/rollback.

Historical implementation notes/migrations remain historical and must not be rewritten. Current-state docs must stop teaching candidate/decision states.[VERIFIED: AGENTS documentation rules]

## State of the Art in This Repository

| Old/current approach | Target | Impact |
|---|---|---|
| candidate table plus decision table | no persisted nonformal relation | removes false relationship state |
| T-2..T+2 matching | all-retained explicit refs + 365-day composite | closes cross-month gap |
| max six rows | no business cardinality cap; state-budget fail-closed | supports N:M:K |
| score/date winner | unique partition only | prevents false formalization |
| active two-pane may remain open | every active relation paired | fixes 520 semantics |
| source-linked/candidate groups | unpaired singleton unless formal relation | no hidden fake group |
| latest shard `distinct on` | all active shard member union | restores omitted facts |
| group-prefix visibility filters | canonical active relation membership | origin/prefix no longer business state |

[VERIFIED: local code and locked decisions]

## Assumptions Log

No `[ASSUMED]` claims are used. Design decisions come from locked CONTEXT; implementation facts come from local code, migrations, tests and repository documentation.

## Open Questions / Operational Inputs

No unresolved product or architecture choice remains. Two operational inputs are intentionally unavailable during research:

1. The exact 13 production invoice IDs are not stored in repository fixtures; only the locked count and total 1709.49 are available. The read-only pre-migration manifest must discover and freeze their canonical identities, while automated tests use a 13-row synthetic multi-shard fixture with the same total.[VERIFIED: repository search and D-16]
2. `FIN_OPS_TEST_DATABASE_URL` and production authorization are absent. Planning must create/use a test-owned disposable database first and leave real production apply as an explicit approval checkpoint.[VERIFIED: environment probe and scope fence]

## Planning Recommendation

Plan the phase in four dependency-ordered waves:

1. **Characterization and pure core:** freeze current data/read-model counterexamples; add canonical bulk reader contract, pure matcher, safety/ambiguity tests and row lock contract.
2. **Single write chain:** simplify orchestrator/worker to direct formal commands, remove candidate/decision dependencies from UoW/exception flows, prove history/outbox/idempotency.
3. **Relation-only projection/all-scope:** replace candidate grouping and latest-shard composition, align API/frontend/downstream linked/unlinked, extend Audit and cache/generation contracts.
4. **Migration and closure:** manifest dry-run/apply/rollback tooling, Release A zero-access proof, forward DB drop/legacy code deletion, full seven-category verification, docs and controlled data gates.

Do not combine DB dropping with the first runtime cutover task, and do not declare completion before the static old-chain guard, disposable PostgreSQL suite, 520/13 counterexamples, worker drain/freshness and System Audit all pass.[VERIFIED: migration risks and locked acceptance]

## Sources

### Primary (HIGH confidence)

- `AGENTS.md`, `ARCHITECTURE.md`, module boundary docs and runtime worker governance.
- `workbench_matching_orchestrator.py`, `workbench_reconciliation_engine.py`, `workbench_free_matching_engine.py`.
- `workbench_candidate_grouping.py`, `workbench_sql_projection.py`, `postgres_repositories/read_models.py`.
- `workbench_relation_command_service.py`, `workbench_uow.py`, relation repositories/migrations.
- PostgreSQL migrations 0002, 0003, 0006, 0028, 0029, 0093.
- `workbench_page_audit.py`, `workbench_projection_audit.py`, Operations/System Audit integration.
- Whole-repo CodeGraph context/impact and literal semantic scans.

### Historical evidence used only for the named counterexample

- `.planning/debug/resolved/input-invoice-520-oa-missing.md` — read-only evidence that the 520 facts and active relation exist; its old “two-pane stays open” product conclusion is superseded by D-01/D-16.

## Metadata

**Confidence breakdown**

- Standard stack: HIGH — installed versions and repository scripts inspected.
- Architecture: HIGH — canonical code paths, CodeGraph impacts, migrations and boundary docs inspected.
- Matching safety: HIGH — user-locked rules mapped to current reusable algorithms and known unsafe branches.
- Migration: HIGH for repository/runtime sequence; production execution remains approval-gated.
- Counterexample identity: HIGH for 520; MEDIUM for the exact 13 production IDs until manifest capture.

**Research date:** 2026-07-14
**Valid until:** 2026-08-13, or earlier if Workbench matching/projection migrations change.

## RESEARCH COMPLETE
