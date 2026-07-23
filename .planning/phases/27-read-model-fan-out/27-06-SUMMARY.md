---
phase: 27-read-model-fan-out
plan: "06"
subsystem: legacy-deletion-release-verification
tags: [zero-fanout, legacy-deletion, browser-performance, drawer-coverage, production-candidate]

requires:
  - phase: 27-05
    provides: all-page access activation and canonical-only remaining writes
provides:
  - Zero production caller for superseded ordinary write fan-out, legacy callbacks and import worker bridge
  - Full seven-category release gate and bounded 17-page/36-operation reference evidence
  - Browser performance coverage for all registered pages and key writable Drawers
  - Production candidate with no new runtime dependency, migration, queue, worker or framework
affects: [27-07]

tech-stack:
  added: []
  patterns: [canonical-only ordinary write, access-time exact freshness, explicit-batch isolation, BFCache page activation]

key-files:
  created:
    - .planning/phases/27-read-model-fan-out/27-REFERENCE-PERFORMANCE.md
    - .planning/phases/27-read-model-fan-out/27-VERIFICATION.md
    - .planning/phases/27-read-model-fan-out/27-06-SUMMARY.md
    - docs/modules/no-oa-bank-batches/README.md
  modified:
    - backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py
    - backend/src/fin_ops_platform/services/runtime_worker_handlers.py
    - backend/src/fin_ops_platform/services/oa_projection_sync.py
    - web/src/app/PageRouteHost.tsx
    - web/e2e/cost-statistics-flow.spec.ts
    - web/e2e/output-invoice-collections-flow.spec.ts
    - web/e2e/turnover-ledger-flow.spec.ts
    - docs/dev/write-operation-impact-matrix.json
  deleted:
    - backend/src/fin_ops_platform/services/bank_transaction_category_refresh.py
    - backend/src/fin_ops_platform/services/pending_invoice_scope_planner.py

key-decisions:
  - "Ordinary fact/rule writes own canonical fact, version, audit and current visible-page reconcile only; they produce zero downstream page refresh jobs."
  - "import.fact.changed is not a current worker event; its name remains only in bounded historical orphan cleanup diagnostics."
  - "PageRouteHost handles mount/focus/visibility and BFCache pageshow activation only; business I/O remains in each page query owner."
  - "Dangerous production mutations are not executed merely to inflate coverage; Plan 27-07 uses one explicitly test-owned reversible relation fixture and read-only probes elsewhere."

patterns-established:
  - "Ordinary write -> canonical commit -> zero page fan-out -> current page normal GET; another page converges only when accessed."
  - "Access -> expected versus actual version -> exact scope enqueue only if non-fresh -> bounded retry/fail closed."
  - "Explicit import/reapply/reset/repair remains separately classified, observable and recoverable."

requirements-completed: []
requirements-advanced: [RMF-01, RMF-06, RMF-07, RMF-08]

duration: multi-session
completed: 2026-07-23
---

# Phase 27 Plan 06: Legacy Deletion and Release Verification Summary

**旧普通写 fan-out 路径已从 production runtime 删除，17 页、36 个操作组、22 个业务 Drawer 和 23 个动态写入口已建立零遗漏本地证据；release candidate 正等待生产部署与真实 SLO 验证。**

## Accomplishments

- 删除 `import.fact.changed` worker/handler/dispatcher env 与普通 mutation derived-lifecycle bridge；保留的历史字符串只服务 orphan cleanup。
- 删除 category refresh 与 pending invoice scope planner 两个退役模块，以及 server/service/repository 中同步 Workbench snapshot、旧 callback、target planner、direct queue helper 和 OA downstream fan-out。
- 将 ordinary write impact matrix 收敛为 expected outbox scopes 为空、forbidden legacy signature 非空、目标消费者访问时收敛；SLO audit 会在旧 fan-out 返回时失败。
- 为 route shell 增加 BFCache `pageshow.persisted` reactivation；隐藏页面保持零 business I/O，再次可见时复用页面正常 query。
- 全量同步 runtime、read model、module boundary、API、testing、operations 和 deploy 文档；新增此前缺失的 no-OA bank batch 模块事实入口。
- 对 543 条 Browser operation record 做 bounded aggregate，450 个唯一 operation ID 全部 pass，settled p95 1.370s、p99 1.769s、max 2.591s。
- Grill-me 复审发现三个缺少独立 Browser latency 的关键 Drawer save，并补齐：成本标签规则、收据编号设置、往来款补充信息。
- 复审纠正 `CollectionStatusRulesDrawer` 误分类；它是只读 Sheet6 规则展示，不存在保存 I/O。

## Verification Evidence

- `bash scripts/verify.sh all` — pass：backend 4,299 passed / 51 environment-gated skipped；frontend 75 files / 890 tests；production build pass；Chromium 183/183 pass；docs pass。
- Targeted backend — 289 passed，80 subtests。
- Browser strict diagnostics — 9/9 pass；新增成功流必须执行 visible-error guard。
- `bash scripts/verify.sh infra-smoke` — 63 pass / 19 external-infra skipped；本机未配置 disposable PostgreSQL/RabbitMQ。
- `bash scripts/verify.sh runtime-check` — 本地按设计 fail closed：未配置生产 runtime `FIN_OPS_APP_STORAGE_BACKEND`；生产复跑是 27-07 blocking gate。
- `bash scripts/verify.sh lint`、`git diff --check` — pass。
- 详细七类、旧路径扫描和环境风险见 `27-VERIFICATION.md`；页面/操作/Drawer reference metrics 见 `27-REFERENCE-PERFORMANCE.md`。

## Seven-Category Assessment

七类全部适用并通过本地门禁：business core、service、API、read model/cache/job、frontend interaction、cross-module E2E、existing regression。没有 N/A 类别，也没有用 skipped/relaxed assertion 隐藏 background cleanup、permission、stale/refreshing 或 rollback 问题。

## Grill-me / Ponytail Review

- 无依赖、migration、table、queue、worker、cache、transport 或 framework 新增。
- diff 以删除为主：当前 Plan 27-06 净删除超过 3,000 行，两个旧生产模块被物理删除。
- 唯一新增生产 UI 逻辑是既有 route shell 的小型 BFCache activation handler；不含业务 API、page→model registry 或全局缓存。
- 页面继续拥有各自 query/service 边界；worker 不依赖 Application，service 不读 HTTP，业务 service 不写 queue SQL。
- 没有双写、fallback、legacy compatibility branch 或为未来需求预建的抽象。

## Deviations from Plan

- 第一次最终 backend gate 失败，因为新 cost rule Browser success flow 缺少统一 visible-error guard。修复测试断言后 strict diagnostics 9/9 和完整门禁通过；没有降低 guard。
- Drawer inventory 原把只读 `CollectionStatusRulesDrawer` 标成 writable。以代码事实为准修正为 read-only，不新增虚假 save endpoint。
- 本地没有真实 PostgreSQL/RabbitMQ/systemd runtime，因此不能把 deterministic reference latency 说成生产 SLO；生产证据保留在 Plan 27-07。

## Next Phase Readiness

- fetch 并确认 `origin/main` 无远端分叉，完成 secret/scope/staged diff review 后提交当前 Plan 27-06。
- push 全部 main commits，部署 exact SHA；部署过程不创建 PostgreSQL backup，也不删除任何已有 backup。
- 生产运行 17 页 HTTP/browser、runtime/worker/readiness、System Audit、read-model scope contract和 queue amplification probes。
- 使用明确 test-owned `txn_imported_1278` + `txn_imported_1348` fixture 做三轮 turnover confirm→withdraw；每轮 unique idempotency key，最终 inactive，禁止使用 discovery business candidate。
- 只有生产普通 command、access-to-fresh、零 fan-out、零 unrelated dirty delta 和 final Audit 全部通过，才能完成 27-07、更新 matrix 为 migrated 并标记目标 complete。

No production deploy, database backup creation, backup deletion or business-data mutation occurred in Plan 27-06.

---
*Phase: 27-read-model-fan-out*
*Completed locally: 2026-07-23*
