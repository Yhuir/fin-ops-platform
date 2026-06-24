# Read Model Module Closure Worker Wave 1 Prompts - 2026-06-25

**Boundary:** `planning:read-model-module-closure-worker-wave-1-prompts`
**Status:** `worker-threads-created-monitoring-pending`
**Module closure:** `not-module-closed`
**Base commit for prompts:** `d9fb9ea9b633a22aa1d301603cde5cb52688ca9f`
**Thread creation base commit:** `71ef441df355bd26f1534a9ffeddbccf32af087a`
**Project:** `/Users/yu/Desktop/fin-ops-platform`
**Production mutation:** none
**Thread creation status:** four local project worker threads created

## Goal

Turn row248's read-model closure evidence ownership map into four bounded worker prompts. The workers are evidence producers. They must map local docs/tests/API/browser gaps and propose closure evidence; they must not edit controller-only files, mutate production, or claim module/global closure.

This controller slice intentionally separated prompt generation from thread creation. T0 committed this prompt file in `71ef441d`, released `/tmp/fin-ops-dev-write.lock`, created the four worker threads, then reacquired the write lease to record thread ids. Workers can acquire the write lease after this controller update is committed and released.

## Inputs Reviewed

- `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `analysis/planning-post-scope-contract-runtime-classification-next-boundary-selection-2026-06-25.md`
- `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
- `analysis/commit-backed-state-reconciliation-2026-06-25.md`
- `docs/modules/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `autonomous/NEXT-PROMPT.md`
- `12-PARALLEL-ORCHESTRATION.md`

## Shared Worker Rules

Every worker prompt below inherits these rules:

- Work in `/Users/yu/Desktop/fin-ops-platform` on branch `dev`.
- User-facing final answer and handoff conclusions must be in Simplified Chinese.
- Treat row245 and row246 as production baseline evidence only; do not claim module/global closure from them.
- Workers must not edit:
  - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
  - `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`
  - `.planning/refactors/modular-io-boundaries/prompts/05-parallel-thread-prompts.md`
  - `.planning/refactors/modular-io-boundaries/prompts/06-t0-meta-orchestrator-goal.md`
  - `.planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md`
  - any global progress/completion percentage document.
- Workers must not perform production writes, DB writes, queue/readiness mutation, worker replay/consume, systemd mutation, deploy/restart, OA mutation or secret reads.
- Workers may request T0 production read-only evidence in their handoff, but must not execute root SSH production checks unless the prompt explicitly limits them to non-secret read-only commands. This wave does not require production SSH.
- Before editing or writing a handoff, acquire `mkdir /tmp/fin-ops-dev-write.lock`; if unavailable, continue read-only analysis and stop with `handoff_status=waiting_for_dev_write_lease` instead of editing.
- After acquiring the lease, run `git fetch origin --prune`, `git pull --ff-only origin dev`, and `git status --short --branch`; proceed only on clean `dev`.
- Verification for evidence-only handoffs: at minimum `bash scripts/verify.sh docs` and `git diff --check` if files are changed. Add targeted tests only if changing tests/docs/contracts.
- Each worker writes exactly one handoff at its assigned path, even if no code/docs change is made.
- Handoff must include: status, base commit, head commit if changed, files changed, controller-only files touched as `none`, evidence read, local evidence map, remaining gaps, proposed T0 follow-up, verification run, seven test category assessment, and explicit `closure-not-claimed`.

## Thread Tracking

| Worker | Thread id | Status | Handoff path |
|---|---|---|---|
| W1 Workbench/Relations/Turnover | `019efb08-6669-7eb1-b5a2-166639ce50af` | created-monitoring-pending | `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-workbench-relations-turnover.md` |
| W2 Invoice/OA Family | `019efb08-8ff0-74a1-b0c9-300f39c96f73` | created-monitoring-pending | `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-invoice-oa-family.md` |
| W3 Bank/Pending/No-OA/Search | `019efb08-b871-7e00-9c36-8b621210d64b` | created-monitoring-pending | `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-bank-pending-nooa-search.md` |
| W4 Cost/Tax | `019efb08-e2a8-7722-8acd-452cd9629269` | created-monitoring-pending | `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-cost-tax.md` |

## W1 Prompt

```text
你是 Codex worker W1，运行在 /Users/yu/Desktop/fin-ops-platform，分支 dev。

目标：为 read-model module closure wave 1 产出 Workbench / Workbench Relations / Turnover Ledger 的本地证据与缺口 handoff。你是 evidence producer，不是 T0 controller。不要声明模块或全局 closure。

必须先读：
- AGENTS.md
- docs/modules/README.md
- docs/modules/read-models/README.md
- docs/modules/read-models/tests.md
- docs/modules/reconciliation-workbench/README.md
- docs/modules/workbench-relations/README.md
- docs/modules/turnover-ledger/README.md
- .planning/refactors/modular-io-boundaries/analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md
- .planning/refactors/modular-io-boundaries/analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md
- .planning/refactors/modular-io-boundaries/analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md
- .planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md

拥有文件范围：
- docs/modules/reconciliation-workbench/**
- docs/modules/workbench-relations/**
- docs/modules/turnover-ledger/**
- tests/test_workbench*
- tests/test_turnover*
- web/e2e/workbench-*.spec.ts
- web/e2e/workbench-relations-*.spec.ts
- web/e2e/turnover-ledger-flow.spec.ts
- 你的 handoff: .planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-workbench-relations-turnover.md

禁止文件：
- 所有 T0 controller-only 文件。
- 不相关模块 docs/tests/code。
- 生产环境、DB、queue、readiness、worker、systemd 的任何写操作。

任务：
1. 从当前代码/测试/docs 中映射 `reconciliation-workbench`、`workbench-relations`、`turnover-ledger` 的 local implementation evidence。
2. 把 row245/246 中适用的 production baseline 证据附到对应模块，但标记为 baseline，不得作为 closure 证明。
3. 列出仍缺的 authenticated API response-shape、browser first-screen/high-row/operation-barrier、export/detail、relation fan-out 证据。
4. 判断每个缺口应由 local test、browser smoke、T0 production read-only 或后续实现 worker 处理。
5. 如发现 docs/tests stale，可在拥有范围内做最小更新；否则只写 handoff。
6. 写 handoff，结论必须中文，并显式写 `closure-not-claimed`。

写入前获取 direct-dev write lease：`mkdir /tmp/fin-ops-dev-write.lock`。如果锁不可用，只做 read-only 分析并在最终回答说明等待写锁，不要改文件。

验证：如果改文件，运行 `bash scripts/verify.sh docs`、`git diff --check`，并运行你认为必要的最小 targeted tests。最终中文报告列出运行/未运行的验证。
```

## W2 Prompt

```text
你是 Codex worker W2，运行在 /Users/yu/Desktop/fin-ops-platform，分支 dev。

目标：为 read-model module closure wave 1 产出 Input Invoice Usage / Output Invoice Collections / OA Pending Payments / Invoice Lifecycle 的本地证据与缺口 handoff。你是 evidence producer，不是 T0 controller。不要声明模块或全局 closure。

必须先读：
- AGENTS.md
- docs/modules/README.md
- docs/modules/read-models/README.md
- docs/modules/read-models/tests.md
- docs/modules/input-invoice-usage/README.md
- docs/modules/output-invoice-collections/README.md
- docs/modules/oa-pending-payments/README.md
- .planning/refactors/modular-io-boundaries/analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md
- .planning/refactors/modular-io-boundaries/analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md
- .planning/refactors/modular-io-boundaries/analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md
- .planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md

拥有文件范围：
- docs/modules/input-invoice-usage/**
- docs/modules/output-invoice-collections/**
- docs/modules/oa-pending-payments/**
- docs/modules/read-models/** 仅限 invoice_lifecycle / invoice usage / output collection / OA pending payment 相关小节
- tests/test_input_invoice_usage*
- tests/test_output_invoice_collection*
- tests/test_oa_pending_payment*
- tests/test_invoice_lifecycle*
- tests/test_invoice_usage_collection*
- web/e2e/input-invoice-*.spec.ts
- web/e2e/output-invoice-*.spec.ts
- web/e2e/oa-pending-payments-*.spec.ts
- 你的 handoff: .planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-invoice-oa-family.md

禁止文件：
- 所有 T0 controller-only 文件。
- Workbench implementation files，除非只读引用。
- 生产环境、DB、queue、readiness、worker、systemd 的任何写操作。

任务：
1. 映射 `input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`invoice_lifecycle` 的 local implementation evidence、repository port、fresh gate、source-version、operation barrier、worker/fan-out 和 browser/API 测试证据。
2. 把 row245/246 production baseline 附到每个 read model key，但明确不能 closure。
3. 列出 authenticated rows/filter/detail/export API、browser relation fan-out、nonfresh states、invoice lifecycle dependency source-version proof 的剩余缺口。
4. 判断每个缺口的后续 owner：local test、browser smoke、T0 production read-only 或后续实现 worker。
5. 如发现 docs/tests stale，可在拥有范围内做最小更新；否则只写 handoff。
6. 写 handoff，结论必须中文，并显式写 `closure-not-claimed`。

写入前获取 direct-dev write lease：`mkdir /tmp/fin-ops-dev-write.lock`。如果锁不可用，只做 read-only 分析并在最终回答说明等待写锁，不要改文件。

验证：如果改文件，运行 `bash scripts/verify.sh docs`、`git diff --check`，并运行你认为必要的最小 targeted tests。最终中文报告列出运行/未运行的验证。
```

## W3 Prompt

```text
你是 Codex worker W3，运行在 /Users/yu/Desktop/fin-ops-platform，分支 dev。

目标：为 read-model module closure wave 1 产出 Bank Details / Bank Account Balance / Pending Invoices / No-OA Bank Batches / Search 的本地证据与缺口 handoff。你是 evidence producer，不是 T0 controller。不要声明模块或全局 closure。

必须先读：
- AGENTS.md
- docs/modules/README.md
- docs/modules/read-models/README.md
- docs/modules/read-models/tests.md
- docs/modules/bank-details/README.md
- docs/modules/bank-account-balance/README.md
- docs/modules/pending-invoices/README.md
- docs/modules/no-oa-bank-batches/README.md
- docs/modules/search/README.md
- .planning/refactors/modular-io-boundaries/analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md
- .planning/refactors/modular-io-boundaries/analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md
- .planning/refactors/modular-io-boundaries/analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md
- .planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md

拥有文件范围：
- docs/modules/bank-details/**
- docs/modules/bank-account-balance/**
- docs/modules/pending-invoices/**
- docs/modules/no-oa-bank-batches/**
- docs/modules/search/**
- tests/test_bank*
- tests/test_pending_invoice*
- tests/test_no_oa_bank_batch*
- tests/test_search*
- web/e2e/bank-details-*.spec.ts
- web/e2e/pending-invoices-*.spec.ts
- web/e2e/no-oa-bank-batches-flow.spec.ts
- 你的 handoff: .planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-bank-pending-nooa-search.md

禁止文件：
- 所有 T0 controller-only 文件。
- invoice usage / output collection / OA pending payment module files。
- 生产环境、DB、queue、readiness、worker、systemd 的任何写操作。

任务：
1. 映射 `bank_detail`、`bank_account_balance`、`pending_invoice`、`no_oa_bank_batch`、`search` 的 local implementation evidence、repository/query owner、freshness/source-version、operation barrier、worker/fan-out 和 API/browser 测试证据。
2. 把 row245/246 production baseline 附到每个 read model key，但明确不能 closure。
3. 列出 bank details high-row/export/stale-refreshing、pending invoice filters/export/relation fan-out、no-OA post-FK convergence browser/API、search fail-closed/API/high-row query 的剩余缺口。
4. 判断每个缺口的后续 owner：local test、browser smoke、T0 production read-only 或后续实现 worker。
5. 如发现 docs/tests stale，可在拥有范围内做最小更新；否则只写 handoff。
6. 写 handoff，结论必须中文，并显式写 `closure-not-claimed`。

写入前获取 direct-dev write lease：`mkdir /tmp/fin-ops-dev-write.lock`。如果锁不可用，只做 read-only 分析并在最终回答说明等待写锁，不要改文件。

验证：如果改文件，运行 `bash scripts/verify.sh docs`、`git diff --check`，并运行你认为必要的最小 targeted tests。最终中文报告列出运行/未运行的验证。
```

## W4 Prompt

```text
你是 Codex worker W4，运行在 /Users/yu/Desktop/fin-ops-platform，分支 dev。

目标：为 read-model module closure wave 1 产出 Cost Statistics / Tax Offset 的本地证据与缺口 handoff。你是 evidence producer，不是 T0 controller。不要声明模块或全局 closure。

必须先读：
- AGENTS.md
- docs/modules/README.md
- docs/modules/read-models/README.md
- docs/modules/read-models/tests.md
- docs/modules/cost-statistics/README.md
- docs/modules/tax-offset/README.md
- .planning/refactors/modular-io-boundaries/analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md
- .planning/refactors/modular-io-boundaries/analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md
- .planning/refactors/modular-io-boundaries/analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md
- .planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md

拥有文件范围：
- docs/modules/cost-statistics/**
- docs/modules/tax-offset/**
- tests/test_cost_statistics*
- tests/test_tax_offset*
- web/e2e/cost-statistics-*.spec.ts
- web/e2e/tax-offset-flow.spec.ts
- web/e2e/workbench-relations-tax-offset-fanout.spec.ts
- 你的 handoff: .planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-cost-tax.md

禁止文件：
- 所有 T0 controller-only 文件。
- 不相关财务模块 docs/tests/code。
- 生产环境、DB、queue、readiness、worker、systemd 的任何写操作。

任务：
1. 映射 `cost_statistics`、`tax_offset` 的 local implementation evidence、repository port、fresh gate、source-version、cache warmup/runtime executor、operation barrier、worker/fan-out 和 browser/API 测试证据。
2. 把 row245/246 production baseline 附到每个 read model key，特别是 cost/tax legacy dirty-scope historical done 分类，但明确不能 closure。
3. 列出 cost parent aggregate/high-row/relation fan-out、tax cache warmup/page/API/browser/workbench relation fan-out 的剩余缺口。
4. 判断每个缺口的后续 owner：local test、browser smoke、T0 production read-only 或后续实现 worker。
5. 如发现 docs/tests stale，可在拥有范围内做最小更新；否则只写 handoff。
6. 写 handoff，结论必须中文，并显式写 `closure-not-claimed`。

写入前获取 direct-dev write lease：`mkdir /tmp/fin-ops-dev-write.lock`。如果锁不可用，只做 read-only 分析并在最终回答说明等待写锁，不要改文件。

验证：如果改文件，运行 `bash scripts/verify.sh docs`、`git diff --check`，并运行你认为必要的最小 targeted tests。最终中文报告列出运行/未运行的验证。
```

## Next Controller Step

1. Commit and push this thread-tracking controller update.
2. Release `/tmp/fin-ops-dev-write.lock`.
3. Monitor W1-W4 with `read_thread`.
4. For each worker, verify final answer and handoff file before accepting evidence.
5. Pull any worker commits from `origin/dev`, inspect diffs, run required verification, and update controller state in a separate T0 commit.
