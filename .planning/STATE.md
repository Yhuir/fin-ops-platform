---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 33 direct-canonical Turnover implementation started; Phase 32 production proof joins the same candidate
last_updated: "2026-07-26T20:20:00+08:00"
last_activity: 2026-07-26 -- Phase 33 implementation started after full boundary review
progress:
  total_phases: 30
  completed_phases: 5
  total_plans: 79
  completed_plans: 57
  percent: 17
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-16)

**Core value:** Preserve production finance workflow correctness while improving individual pages through isolated, reviewable GSD phases.
**Current focus:** Phase 33 — turnover-direct-canonical-read

## Current Position

Phase: 33 (turnover-direct-canonical-read) — EXECUTING
Plan: 1 of 1
Status: Direct-canonical implementation in progress
Last activity: 2026-07-26 -- Phase 33 implementation started after full boundary review

Progress: [██░░░░░░░░] boundary review and executable plan complete

## Performance Metrics

**Velocity:**

- Total plans completed: 38
- Baseline planning docs completed: 1
- Average duration: N/A
- Total execution time: 1 hour 40 minutes

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 28 | 1/1 | 1h 40m | 1h 40m |
| Phase 30 P02 | 31min | 3 tasks | 17 files |
| Phase 30 P03 | 24min | 3 tasks | 14 files |
| Phase 30 P04 | 24min | 3 tasks | 12 files |

## Accumulated Context

### Decisions

- Phase 29 closure: Workbench operation recovery performs one trigger combined-initial load, lightweight public refresh-status waiting and one final fresh combined-initial load; repeated full payload polling is deleted.
- Phase 29 SQL root fix: the existing all-scope active-member CTE is `NOT MATERIALIZED`, so search/source/column/time predicates can reach existing tables and indexes. The same SQL owner, generation, exact totals, row counts and matching IDs remain authoritative; no cache, table, index, migration or second query path was added.
- Phase 29 production release: `main-f06711b7-20260725213147` is active. Rolling Workbench `/groups` p95 improved from `3476.949 ms` to `2882.325 ms` (about 17.1%); hot all-scope searched reads were `340–756 ms`, and the worker p95 was `1799.628 ms`.
- Phase 29 correctness proof: reversible confirm/withdraw writes were `270.306/164.554 ms`; all business/input-isolation assertions, final fresh consumers, zero forbidden fan-out, durable drain, 24-worker effectiveness and System Audit passed. The fixture was restored inactive and the temporary scenario file was deleted.
- Phase 29 performance boundary: six-consumer concurrency still produced a slowest Workbench sample of `4616.117 ms`; the deferred hard 3-second SLO is not claimed. Cost recovery `5986–6212 ms` and Turnover confirm `3815.665 ms` remain independent follow-ups, not Workbench correctness blockers.
- Phase 29 verification: final corrective slices passed 278 backend and 64 frontend tests, production build, ruff/docs/diff gates and a PostgreSQL 200k-member plan comparison. The unrelated 183-browser suite and full CI were intentionally not run.
- Phase 29 scope: reuse the existing lightweight Workbench groups freshness repository port for public status and replace repeated operation-time combined initial polling with one trigger load, lightweight status waiting and one final fresh load. No projection rewrite, cache, table, index, migration, queue, worker, coordinator or second freshness system is allowed.
- Phase 28 closure: Cost active-recovery polling first performs one lightweight durable-state gate; only the no-active-recovery path executes the complete fail-closed statistics proof. No new cache, table, index, queue, worker, coordinator, frontend poller or write-time fan-out was added.
- Phase 28 closure: Candidate A `d8e4c5946` reduced the exact `2026-02` Cost recovery sample from 7432.418 ms to 723.151 ms. Its full production chain exposed one shared queue defect: a completed `force_refresh=true` event could cover a later freshness target. The root was fixed once in `RuntimeQueueRepository` by `b6e814b05`; no page-specific fallback was introduced.
- Phase 28 production release: `main-b6e814b0-20260725192427` is active. The reversible test-owned cross-month fixture returned to inactive state; direct final Workbench and Cost probes were fresh, all 15 read models had zero stale/unavailable scopes, durable outbox was empty, 24 required workers were effective and idle, and System Audit passed all 16 audited business pages.
- Phase 28 performance evidence: final hot Cost all/active reads were 714/447 ms; the last 15-minute Cost worker window was p50 327 ms, p95 1537 ms and p99 3697 ms across 22 samples. The slowest recorded exact cross-month Cost child recovery was 4397 ms and still converged fresh. The deferred hard 3-second SLO was not reintroduced as a correctness gate.
- Phase 28 verification: 696 targeted queue/gateway/worker/Cost/API/write/Workbench/boundary tests passed. Twenty-two real-PostgreSQL infrastructure tests remained explicitly environment-skipped locally and were covered by the production reversible fixture. The unrelated 183-browser suite and full CI were intentionally not rerun.
- Phase 27 closure: Candidate A `bef73c4b6` was deployed and fully diagnosed before any correction. Candidate B `3b44f08ef` was the single consolidated corrective release; its runtime is active as `main-3b44f08e-20260725151318`.
- Phase 27 closure: Final HTTP matrix is 52/52; scope contract has zero violations; durable outbox and all 15 read-model stale/unavailable counts are zero; 24 required workers are healthy; System Audit is pass for 16/16 audited business pages.
- Phase 27 closure: The test-owned confirm/withdraw fixture was restored. Ordinary writes produced zero forbidden downstream refresh events. No database backup was created because the fixture was fingerprinted, test-owned and recoverable through its business inverse.
- Phase 27 closure: 3-second performance is not a correctness gate. Workbench and Cost recovery samples above 3 seconds are retained as explicit performance follow-up, not hidden.
- Phase 27 current release: Cost compares the Workbench business proof but ignores only the active-generation execution cursor `source_version`; query, worker, parent/child SQL and System Audit use the same semantic contract, while real business-proof drift remains fail closed.
- Phase 27 current release: Bank-flow tag-rule save returns exact informational affected months with empty write targets and no dead `refresh_enqueued` DTO; current-page normal GET owns access-time convergence.
- Phase 27 current release: Application reuses one Workbench projection builder and coalesces only overlapping same-scope canonical proof; completed proofs are not cached, failed proofs remain retryable, and PostgreSQL queue/dirty state stays authoritative.
- Phase 27 current release: Workbench proof covers ETC, all relation/control statuses, cross-month members and consumed bank settings. Schema v7, migration `0125` and the official production Workbench rehydrate are already active in release `main-719c9a34-20260725101310`.
- Phase 27 scope decision: the later uncommitted exact-candidate delta-proof experiment was pure 3-second performance work, not a correctness fix. It was deleted completely; current `719c9a34` keeps the simpler full fail-closed canonical proof.
- Phase 27 acceptance decision: 3-second access-to-fresh remains a measured product target but is not a Phase 27 completion gate. A sample above 3 seconds is `performance_follow_up`; stuck/non-convergent refresh, incorrect/incomplete payload, unrelated I/O or queue/worker failure still blocks.
- Phase 27 release: Reuse the Phase 27-06 full-repository/183-browser evidence for unchanged behavior and run current-diff targeted gates plus real disposable PostgreSQL; do not rerun the unrelated 183-browser suite or redundant full CI.
- Phase 26 reconciliation: Plans 26-01 through 26-05 and their production follow-up fixes are complete in current history; no Phase 26 implementation is repeated during Phase 27.
- Phase 27-03: Ordinary Workbench relation, bank-flow/no-OA, batch-accounting and Turnover writes persist canonical facts/history/idempotency/audit only; freshness and operation-barrier targets are empty.
- Phase 27-03: Current-page commands reconcile through normal GET; other open/hidden pages do no business I/O on focus/visibility/BFCache or cross-page writes and only load on route re-entry, query change, browser manual refresh or explicit retry.
- Phase 27-03: Workbench keeps active-generation atomic publish but no longer publishes Cost refreshes; Cost access first converges exact Workbench months and only then its own exact scope.
- Phase 27-03: Existing Cost relation-delta capability is unreachable from ordinary writes and cannot act as a fallback; Phase 27-06 owns its final deletion or explicit-operations classification.
- Phase 27-02: Redis remains payload-only; current canonical/schema/dirty proof must pass before a cached bank/cost/tax/OA payload is accepted.
- Phase 27-02: Ordinary bank category/rule writes and cost tag-rule saves own zero downstream refresh/barrier targets; bank auto-tag reapply is the explicit bounded month-shard exception.
- Phase 27-02: Bank category/confirmation canonical drift is proven by a set-based month signature persisted in bank-detail schema v11; no per-row jobs or new coordinator were introduced.
- Phase 27-01: Reuse `PageRuntimeContext`, `ReadModelQueryGateway`, `ReadModelRefreshGateway`, PostgreSQL durable queue and existing workers; do not add a page coordinator, dependency registry or second freshness system.
- Phase 27-01: Classify all POST/PUT/PATCH/DELETE exports as `fact-write`, `rule-write`, `read-like-command` or `explicit-batch`; an HTTP mutation method alone does not justify read-model invalidation.
- Phase 27-01: Ordinary target behavior is canonical commit plus current-page exact reconcile and access-time consumer proof; full-history convergence remains an explicit batch exception, while Workbench keeps active-generation atomic publish.
- Phase 26-01: `turnover_manual_closure` active relation expresses ownership only; paired/unpaired comes from the immutable OA/invoice requirement snapshot.
- Phase 26-01: Turnover confirm reuses one selected-row snapshot and one canonical rules payload through the existing helper; merged bank membership must remain inside selected ids.
- Phase 26-01: Rule saves never retroactively rewrite Turnover relation requirements; legacy-invalid snapshots remain fail closed for controlled Plan 26-02 repair.

- Setup: Keep `.planning/codebase/` as a global map and preserve per-page analysis in dedicated phase directories.
- Setup: Parallel page analysis threads must not modify `.planning/codebase/*.md`.
- Setup: Page-analysis phases can run independently in separate worktree threads only after reading Phase 0 and only when they avoid overlapping shared write targets.
- Setup: `.planning/codebase/` was regenerated as a full-repository map; future page analysis must write `CONTEXT.md`, `RESEARCH.md`, and plan artifacts under the assigned phase directory.
- Setup: All 17 app registry pages now have dedicated phase directories.
- Setup: Phase 0 cross-page dependency baseline is required before page implementation planning; page phases must reference its dataflow, dependency, worker/read model, legacy, test, docs-impact, and implementation-order gates.
- Setup: Page development does not require all 17 pages to have deep `PLAN.md` files up front, but it does require Phase 0 L1 dependency baseline plus page-level L2 analysis for the selected page or dependency group.
- Phase 19: `fan_out_command/all` is a command parent, not a queryable readiness scope; manifest is the only scope-role policy source.
- Phase 19: historical command-parent readiness is diagnostic only; current durable outbox/dirty failures still block.
- Phase 19: invoice page relation proof uses typed `relationCaseId + member` equality from canonical/shared facts through page consumer summaries; no count-only inference is accepted.
- Phase 19: App Health and invoice pages use the unified page-key Audit runtime; removed specialized HTTP paths are guarded from reintroduction.
- Phase 19: OA pending-payment and pending-invoice complete-summary consumers now prove shared linked relation edges bidirectionally; pages without a registered consumer contract cannot claim that proof.
- Phase 19: bank-details proves its exact coarse linked tag/case/status display contract and separately blocks active relation row overlap; it does not claim member DTOs the page does not store.
- Phase 19: bank-flow rule batches prove canonical batch, page payload, and active relation status/member equality; submitted-without-relation cannot pass.
- Phase 19: batch-accounting is a direct shared-relation consumer; canonical/group logical case sets and mode/source metadata are explicitly proven without a second projection.
- Phase 19: turnover ledger/flow payload now preserves structured case-member evidence and proves each anchor against linked shared relation edges; schema v5 forces old payload rebuild.
- Phase 19: Workbench page/API/CLI now share one relation-display proof owner; the legacy tool is a thin adapter with no SQL.
- Phase 19: relation-display equality alone cannot make the full Workbench page proof-ready; relation-free canonical objects and key fields must be proven before cost lineage can rely on it.
- Phase 19: Workbench now proves its full canonical object inventory, critical fields, summaries, control facts and dependency versions; cost may reuse this proof but must bind it in the same snapshot.
- Phase 19: Cost statistics now reuses Workbench/bank-detail integrity in the same snapshot, derives bank-flow completeness from canonical bank facts, and binds month versions plus parent shard maps exactly.
- Phase 19: Tax-offset independently proves five canonical item sets, certified matching, calculated fields, controls, versions and queue; it is a registered relation non-consumer.
- Phase 19: Workbench/red-invoice relation writes no longer enqueue or fabricate tax-offset changes; only actual tax projection sources may refresh tax shards.
- Phase 19: App Health is the 17-page system proof owner; one outer PostgreSQL snapshot drives all internal proofs, while runtime observation and external control evidence remain separate.
- Phase 19: App Health has no own read model or business relation; a normal dashboard refresh invalidates the prior System Audit display, and external unknown keeps end-to-end source truth unproven.
- Phase 19: Cost statistics consumes active Workbench relations, not candidate-only grouping; tests and repair evidence must create formal relations before expecting cost rows.
- Phase 19: ETC tickets is a direct canonical page with no own manifest read model; its Audit must prove internal batch/task/invoice/file relations without treating downstream impact targets as page consumers.
- Phase 19: process-owned background-job service survives in-process runtime reload; only first application startup/real process restart may create an owner and run interrupted-job recovery.
- Phase 20: reversible relation runtime contracts ship inside backend code; the impact matrix is a test-constrained documentation mirror, not production file I/O.
- Phase 20: every checkpoint binds its mutation to exact committed idempotency outbox IDs, affected business-root assertions, non-consumer baseline equality and a new read-only System Audit.
- Phase 20: nonexpected HTTP/HTML/network outcomes remain ambiguous until durable evidence resolves them; committed responses may drive formal recovery, while missing/reserved evidence never triggers blind cleanup.
- [Phase 30]: Reuse existing generation/scope/row and generation/scope/zone/group indexes; EXPLAIN showed no migration or index justified.
- [Phase 30]: Bound relation preview input to 20 selected rows and 100 context rows, failing closed on missing, duplicate, non-fresh, cross-generation, drift, or overflow state.
- [Phase 30]: Keep preview DTOs derived-only; formal relation UoW always rereads canonical facts, versions, and idempotency state.
- [Phase 30]: Keep group_type=selection preview-only; require zone/status=unpaired and leave ordinary Workbench mapping strict.
- [Phase 30]: Share one synchronous confirm/withdraw pending guard and drop success responses after selection or read-model version drift.
- [Phase 30]: Derive user-visible Workbench errors only from approved code/status mappings while retaining status/code/requestId.
- [Phase 30]: Production relation apply requires one fixed root-owned mode-0600 bank_oa_invoice scenario with explicit test-owned ownership, confirm, withdraw and recovery; legacy scenarios are not upgraded by inference.
- [Phase 30]: Candidate A 3bf46e797 remains active and healthy; Candidate B is not used for fixture provisioning.
- [Phase 30]: Missing sanctioned production scenario provisioning fails closed before mutation; no direct SQL, arbitrary scenario file or secret access is permitted.
- [Phase 30]: OA pending-payment freshness and projection share the structured active relation set; membership count/digest invalidates exact scopes and historical raw payload no longer owns activity.
- [Phase 30]: Final Candidate D `77c580f01` is active as `main-77c580f0-20260726052834`; confirm/withdraw, nine consumers, zero fan-out, inverse recovery, queue drain and System Audit 16/16 passed in production.
- [Phase 30]: The relaxed correctness gate passed, while 4.58–14.02 second affected-page convergence and 3.69 second withdraw-preview p95 remain an explicit non-blocking performance follow-up.

### Roadmap Evolution

- 2026-07-22: Phase 27 added for access-time read-model freshness convergence, elimination of ordinary write-time global fan-out, complete page/drawer coverage, legacy-path removal, and production performance verification.
- 2026-07-22: Phase 26 added for fixing external-turnover closure partitioning by frozen OA/invoice requirements, including legacy-path removal, historical repair, and Workbench rehydrate safety.
- 2026-06-16: Minimal planning scaffold created for page-scoped GSD phases.
- 2026-06-16: Phase 1 added for 外部往来款管理 page analysis and improvement planning.
- 2026-06-16: Phase 2 added for 银行明细 page analysis and improvement planning.
- 2026-06-16: Phase 3 added for 税金抵扣 page analysis and improvement planning.
- 2026-06-16: `.planning/codebase/` regenerated as a global repository map; page-focused analysis policy reaffirmed.
- 2026-06-16: Phases 4-17 added for the remaining registered pages.
- 2026-06-16: Phase 0 added and completed as the cross-page dependency baseline before page implementation work.
- 2026-07-11: Phase 19 added for the cross-page Audit proof, readiness semantics, and legacy-path production closure.
- 2026-07-12: Phase 20 added for three reversible relation write scenarios spanning fan-out, worker drain, freshness, System Audit, and legacy test-path removal.
- 2026-07-13: Phase 20 implementation completed with disposable PostgreSQL, full backend/frontend/build and 178-test Chromium verification; real-environment apply remains an explicit external gate.
- 2026-07-14: Phase 21 added for deterministic automatic formal relations, exact Workbench visibility partition, all-scope omission repair, legacy candidate/decision removal, and data-safe recovery proof.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 29 has no remaining correctness, isolation, recovery, runtime or data-safety blocker. The deliberately deferred hard 3-second concurrent SLO, Cost/Turnover tail latency, unavailable RabbitMQ management metrics and external control evidence `unknown` are explicit non-blocking follow-ups.
- Phase 28 has no remaining correctness, isolation, recovery, runtime or data-safety blocker. Non-blocking follow-ups are the deliberately deferred hard 3-second SLO, unavailable RabbitMQ management metrics and external bank/OA/invoice/ETC control evidence remaining unknown; PostgreSQL durable queue evidence is drained and authoritative.
- Phase 21 Release A full local gate is zero-failure: backend 4182 passed / 33 explicitly environment-gated skipped；frontend 835/835；Chromium 177/177；production build passed. 首次远端分支 CI 揭示一个既有测试模块依赖未声明的 `pytest`，且 4 个顶层测试未被 `unittest discover` 执行；现已改为标准 `unittest.TestCase`。第二次远端 CI 暴露 Vitest 文件并行下的全局 I/O/监听器竞争与 cross-realm Blob 断言；前端测试现固定单 worker，Blob 以 size/MIME 合同断言。第三次远端 CI 证明多个前端测试把页面/抽屉壳出现误当成异步数据 I/O 完成；相关测试现以用户可见数据行、详情字段或当前 DOM 节点作为 readiness anchor。第四次远端 CI 进一步暴露 OA 反提历史时间依赖执行机本地时区；该业务时间现显式按 `Asia/Shanghai` 格式化，并由语义表格 readiness + 精确时间断言保护。与 CI 一致的 Node 20 全量运行最终 71 files / 835 tests 全绿，且不再出现 `MaxListenersExceededWarning`。统一门禁还捕获 import confirm 在持久化前发布 matching 的竞态；已改为 durable delta 成功后才发布所有下游信号，并将 4 项 import-processing 测试纳入 `unittest discover`。
- 第五次远程 CI 为 176/177；唯一失败是待找发票文本选择 E2E 用元素 bounding-box 中线做像素拖拽，在 CI 字体/换行布局下落到空白区。测试现对同一可见文本节点执行 Playwright 浏览器文本选择，仍精确验证 `window.getSelection()`，不改业务 UI、不加 retry、不放宽结果。
- 第六次远程 CI 的唯一失败是 ETC 统一批次列表测试等待静态 list 容器后同步读取异步批次行；现以 `etc-batch-unsubmitted-01` 业务行作为 readiness anchor，不改 ETC 业务链路与 I/O。
- 第七次远程 CI 已通过后端、835 前端与 177 浏览器流，最后 docs gate 因 runner 未安装 `rg` 而把命令缺失误报为文档缺失。验证入口现集中选择 `rg` 或 `grep`/`git grep`，并移除未使用的固定 `/tmp` 文件写入。
- 第八次远程 CI 的后端已通过，前端仅有 3 个异步首帧时序失败：成本统计测试把页面标题误当成表格或 refreshing 状态已完成，税金抵扣测试把静态统计卡误当成发票选择行已完成。测试现直接等待对应表格、refreshing 文案和业务复选框，不改产品链路、不加 retry、不放宽业务结果。
- Release A 首次生产激活后，OA sync fan-out 暴露 PostgreSQL OA projection 历史 payload 仍含 `section=open`，新 Workbench core 按两态合同 fail fast。生产已立即回滚到 `etc-import-e5d6e6a4e-20260714-visibility`；hotfix 只在 repository 反序列化 I/O 边界把 legacy `open`/缺失值归一化为 `unpaired`，核心继续拒绝旧状态和未知状态。
- main `1f1ec5324bc7dde9987b51f79d4d2a6ebe502841` 再次生产激活并完成受控 Workbench rehydrate 后，page Audit 捕获 51 个 ETC summary/detail mismatch 与 2 个 override ownership mismatch；生产立即回滚并 rehydrate `etc-import-e5d6e6a4e-20260714-visibility`，恢复 219 active relations、19 scopes、876 relation rows、1296 group rows与零问题，且 migration 仍为 0001–0103。v2 hotfix 已通过 4190 backend / 835 frontend / 177 Chromium 本地全量门禁，远程精确 SHA 与重新 cutover 仍待执行。
- v2 已合并并通过 branch/main CI；生产 release `main-a127c58c7-workbench-audit-v2-20260715072607` 的 19-month rehydrate 让 51 个 ETC mismatch 归零，但仍有 3 个合法 `pending_input_invoice` mode 被删除、2 个 active null override 被 candidate exception 覆盖。v3 修复未配对 override precedence 并通过 PR #6/双 CI；生产 release `main-427f8efac-workbench-audit-v3-20260715083006` 消除了前三项，最后两项确认是 active formal relation member 与历史 override/exception 的优先级冲突。生产再次立即回滚、rehydrate 并恢复零问题；v4 统一 formal relation > override > exception，本地完整门禁为 backend 4193 passed / 33 explicit environment-gated skipped、frontend 835 passed、production build succeeded、Chromium 177 passed。
- legacy section hotfix 分支精确 SHA CI 成功后，main 精确 merge SHA CI 暴露两个旧测试边界竞态：OA 待付款测试只等待静态页面容器便同步读取异步业务行；Workbench mock server 对同列多值使用 OR，而正式 repository 与本地 display model 使用 AND。测试现等待 OA 业务按钮，并让 mock 复刻正式 AND 合同；不改生产业务链路。
- Current `719c9a34` passed the final targeted local gate after deleting the exact-candidate diff: Workbench/Cost 274 tests plus 24 subtests, disposable PostgreSQL Workbench proof 6 tests, Phase 27 backend contract slice 215 tests plus 55 subtests, frontend activation/page slice 116 tests, lint/docs/runtime-check, and verified temporary database cleanup.
- Release A 已通过 PR #2 合并到 main（merge SHA `85ec4c26195bd7d2320b90c6c92ff3529d920d52`），分支与 main 精确 SHA 远程 CI 均成功；首次生产激活因上述 legacy OA projection payload 问题立即回滚，未把故障版本留作 active release。
- Hotfix 发布前基线仍显示云南立孚 520 关系为 unpaired；破坏性 migration 0104 已明确从 Release A 延后，只有 repaired release 激活后才允许运行已登记的 rehydrate、等待 worker drain 并执行生产 System Audit。
- 17/17 pages expose ready v17 proofs and local System Audit is complete; authorized production read-only execution has not occurred.
- External bank/OA/invoice/ETC control evidence remains unregistered/unknown, so end-to-end external source completeness is still unproven.
- Phase 30 has no remaining correctness, isolation, recovery, queue, worker or data-safety blocker. The deliberately deferred hard 3-second SLO and historical external source evidence `unknown` remain explicit non-blocking follow-ups.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260617-dt6 | 修正免OA流水批量处理提交/撤回状态展示并确认关联台配对收敛 | 2026-06-17 | — | [260617-dt6-oa](./quick/260617-dt6-oa/) |
| 260618-jc8 | 进项发票使用情况以发票反提OA新增暂存状态闭环 | 2026-06-18 | 2b5f59c5 | [260618-jc8-oa](./quick/260618-jc8-oa/) |
| 260618-m4d | 发票信息汇总表模板识别 | 2026-06-18 | — | [260618-m4d-excel](./quick/260618-m4d-excel/) |
| 260621-ivm | OA 附件发票 Promotion 设置化与读路径收敛 | 2026-06-21 | — | [260621-ivm-oa-promotion-oa-app-invoices-excel](./quick/260621-ivm-oa-promotion-oa-app-invoices-excel/) |
| 260621-n7i | 银行明细页面时间选择器简化为按年/按月和全部 | 2026-06-21 | — | [260621-n7i-bank-details-date-picker](./quick/260621-n7i-bank-details-date-picker/) |
| 260621-ssv | 免 OA 流水栏行级银行明细标签 | 2026-06-21 | — | [260621-ssv-oa-ui](./quick/260621-ssv-oa-ui/) |
| 260622-bta | 银行流水模板别名识别 | 2026-06-22 | — | [260622-bta-bank-import-template-aliases](./quick/260622-bta-bank-import-template-aliases/) |
| 260622-oaw | OA 待付款自动匹配和自动写回 | 2026-06-22 | — | [260622-oaw-oa-pending-auto-writeback](./quick/260622-oaw-oa-pending-auto-writeback/) |
| 260622-oal | OA 待付款表格 OA 区域五列压缩 | 2026-06-22 | — | [260622-oal-oa-pending-layout](./quick/260622-oal-oa-pending-layout/) |
| 260629-guf | fix read model freshness version contract and deploy | 2026-06-29 | — | [260629-guf-fix-read-model-freshness-version-contrac](./quick/260629-guf-fix-read-model-freshness-version-contrac/) |
| 260629-kcu | pending invoices +N drawer and input invoice usage relation status display | 2026-06-29 | — | [260629-kcu-pending-invoices-n-drawer-and-input-invo](./quick/260629-kcu-pending-invoices-n-drawer-and-input-invo/) |
| 260629-lud | show totals in ETC invoice detail table headers | 2026-06-29 | — | [260629-lud-show-totals-in-etc-invoice-detail-table-](./quick/260629-lud-show-totals-in-etc-invoice-detail-table-/) |
| 260630-qkx | 待找发票选中工具栏与表格列对齐修复 | 2026-06-30 | — | [260630-qkx-checkbox](./quick/260630-qkx-checkbox/) |
| 260630-r4a | 重新设计销项发票收款情况右侧详情抽屉排版 | 2026-06-30 | — | [260630-r4a-output-invoice-detail-drawer](./quick/260630-r4a-output-invoice-detail-drawer/) |
| 260630-tyy | 生产级修复 bank_flow_rule_batch App Status storage contract | 2026-06-30 | — | [260630-tyy-bank-flow-rule-batch-app-status-registry](./quick/260630-tyy-bank-flow-rule-batch-app-status-registry/) |
| 260721-nrf | 流水规则批量处理 canonical relation、Audit fresh 与内部 ID 隐藏生产闭环 | 2026-07-21 | fc5babd5b | [260721-nrf-audit-fresh](./quick/260721-nrf-audit-fresh/) |
| 260728-g9q | OA 来源别名确定性归一到 canonical OA ID | 2026-07-28 | PENDING | [260728-g9q-oa-oa-id-validate](./quick/260728-g9q-oa-oa-id-validate/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-07-25T19:51:00.368Z
Stopped at: Completed 30-04-PLAN.md with safe production blocker
Resume file: None
