# Phase 27: Research

**Date:** 2026-07-22
**Question:** 如何以最少新代码，把现有系统收敛为普通写零全局 fan-out、访问时精确 freshness/rebuild，并完成全页面生产性能闭环？

## Existing Capabilities To Reuse

- `READ_MODEL_MANIFEST` 已登记 15 个 read model、owner、scope、projection strategy、freshness proof、worker 和测试责任。
- `ReadModelQueryGateway` 已协调 expected source versions、SQL view、fresh cache 和 stale/missing enqueue。
- `ReadModelRefreshGateway`、scope policy registry 和 PostgreSQL durable queue 已提供 normalize/validate/dedupe/refresh truth。
- 多数 worker 已支持 scoped build、source versions、current-effective dirty/outbox 和原子发布；invoice lifecycle 已有旧 event source-version 拒绝逻辑。
- Workbench 已有 active-generation 原子发布；不得替换。
- 银行详情路由已支持 old rows + refreshing 或 missing→202；前端已有 BroadcastChannel/focus/visibility 示例。
- `write-entry-inventory.md` 已双向校验页面注册和主要写控件，并登记 mutating feature APIs、动态 opener 和 Browser 权限证据。
- Phase 20 controlled operation runner、Page/System Audit、生产 token wrapper 和正式 deploy 脚本可复用为部署后验证基础。

## Current Root Causes

1. `DerivedDataLifecycleService` 默认 `include_all=True`，精确月份容易扩展为 `[month, all]`。
2. 银行自动标签普通保存会刷新 turnover `all`，再执行 `bank_auto_tag_rules_changed` lifecycle `all`。
3. 银行分类、no-OA/tag selection 等路径存在 `affected_months or ["all"]` 或固定 `all` fallback。
4. pending invoice executor 可忽略 domain plan scope 并退化为宽父 scope。
5. Workbench、bank batch、imports、invoice lifecycle 等 mutation 路径仍有直接 lifecycle/fan-out；连续写形成移动目标和任务放大。
6. 部分前端保存等待全局 operation barrier，导致写已经提交但 UI 被所有下游收敛时间阻塞。
7. Phase 0 页面清单已过时：当前正式页面是 `bank-flow-rule-batches`，不再是 no-OA 页面；计划必须以当前 registry 为准。

## Minimal Target Architecture

```text
command -> canonical UoW(facts + exact source version + audit) -> response

page/drawer query -> query owner -> freshness gate
  fresh -> payload
  stale/missing -> exact dependency intents -> existing refresh gateway/queue
  worker -> source-version CAS -> atomic publish -> refetch
```

不新增 runtime dependency registry。页面依赖继续由 manifest、query owner 和现有 page/status registry 表达；实施覆盖矩阵是 docs/test artifact，不参与生产 I/O。

## Operation Classification

| Type | Example | Refresh behavior |
|---|---|---|
| canonical fact mutation | relation confirm/withdraw, status, receipt | write exact fact/version; accessed consumers rebuild |
| projection semantic rule | bank auto-tag, pending/payment rules | save CAS rule version; accessed scopes rebuild |
| read-time/display rule | cost tag eligibility, receipt numbering, column layout | save/refetch only; zero projection job |
| explicit batch/repair | reapply all, reset, deploy rehydrate | bounded shards, progress, audit, recovery |

## Page/Resource Coverage

- 17 current pages from `pageRegistry.tsx`.
- 15 read models from `read_model_manifest.py`.
- Non-page resources: search, bank-account balance, workbench relation, invoice lifecycle and legacy no-OA.
- Named mutating Drawers: bank auto-tag, cost tag rules, payment rules, OA reverse, output status/reminder, red relation, receipt preview/history/settings, pending invoice picker/rules, turnover extra; plus page-defined bank-flow/turnover/OA rule panels.
- Read-only Drawers remain query-only and must not receive mutation/rebuild plumbing.

## Performance Strategy

1. Remove task amplification before micro-optimizing queries.
2. Coalesce by model/scope/target version.
3. Prioritize current visible exact scope.
4. Use existing SQL/index/projection paths; fix N+1 and unbounded loads per measured slow scope.
5. Keep writes free of downstream waits.
6. Measure separately: command latency, freshness gate, queue wait, handler duration, access-to-fresh and full-history batch throughput.

## Production Verification Strategy

- Pre-deploy: full repository verification, deterministic/disposable PostgreSQL tests where configured, performance harness against reference data, zero-unmapped and zero-legacy guards.
- Commit/push: exact commit on `main`, remote CI/result verification.
- Deploy: `./scripts/deploy-oa.sh`, release readiness and worker registry checks.
- Post-deploy read-only baseline: 17 pages, 15 read models, App/System Audit, queue and source-version status.
- Controlled writes: every registered operation/drawer scenario via existing controlled runner or owner API with idempotency, before/after fingerprints and rollback/withdraw where available.
- Performance record: page/operation count, p50/p95/p99/max, fresh convergence, jobs created, unrelated dirty deltas.
- Failure: stop, collect evidence, rollback active release when correctness/data-safety gate fails; otherwise fix on main and repeat exact release cycle.

## Risks

- Eliminating write-time dirty/outbox changes the current formal read-model contract; query expected-version providers must independently discover staleness before each model is migrated.
- Some projections depend on other read models; read-time enqueue must respect the existing dependency DAG and avoid cycles.
- Full-history and all-scope pages cannot promise the ordinary 3-second SLO without existing fresh shards; UI/status must distinguish partial/current-scope freshness from full-history completion.
- Phase 26 is unfinished and overlaps turnover/workbench. Phase 27 must not silently supersede its repair/migration contract.
- Production write verification needs configured admin token and reachable production; secret material must never be printed.

## Recommendation

Proceed in vertical slices, starting with a zero-runtime coverage guard, then bank-details + cost-statistics to prove all four operation classes. Delete old fan-out inside each slice. Do not perform a single repository-wide switch before per-slice expected-version and query-gate proofs exist.
