---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Release A clean branch passed full local gates after CI isolation and import publish-order repair; updated remote CI, production cutover and Release B remain gated.
last_updated: "2026-07-15T01:11:49+08:00"
last_activity: 2026-07-15 - Release A passed 4182 backend, 835 frontend, production build and 177 Chromium tests; durable import facts now commit before downstream publication
progress:
  total_phases: 21
  completed_phases: 2
  total_plans: 26
  completed_plans: 24
  percent: 92
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-16)

**Core value:** Preserve production finance workflow correctness while improving individual pages through isolated, reviewable GSD phases.
**Current focus:** Phase 21 Release A is isolated and fully verified locally after deterministic test-runner isolation and import I/O ordering repair; updated remote review/CI, clean deployment, rehydrate and production data-safety evidence remain gated. Migration 0104 stays in Release B only.

## Current Position

Phase: 21 of 21 (关联台确定性自动正式关系与全量可见性生产闭环)
Plan: 21-01 through 21-03 complete; 21-04 production cutover pending
Status: local implementation and automated verification complete; current production still shows the 520 relation as unpaired
Last activity: 2026-07-15 - Release A passed 4182 backend, 835 frontend, production build and 177 Chromium tests; durable import facts now commit before downstream publication

Progress: [█████████░] 92%

## Performance Metrics

**Velocity:**

- Total plans completed: 21
- Baseline planning docs completed: 1
- Average duration: N/A
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

## Accumulated Context

### Decisions

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

### Roadmap Evolution

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

- Phase 21 Release A full local gate is zero-failure: backend 4182 passed / 33 explicitly environment-gated skipped；frontend 835/835；Chromium 177/177；production build passed. 首次远端分支 CI 揭示一个既有测试模块依赖未声明的 `pytest`，且 4 个顶层测试未被 `unittest discover` 执行；现已改为标准 `unittest.TestCase`。第二次远端 CI 暴露 Vitest 文件并行下的全局 I/O/监听器竞争与 cross-realm Blob 断言；前端测试现固定单 worker，Blob 以 size/MIME 合同断言。第三次远端 CI 证明多个前端测试把页面/抽屉壳出现误当成异步数据 I/O 完成；相关测试现以用户可见数据行、详情字段或当前 DOM 节点作为 readiness anchor。第四次远端 CI 进一步暴露 OA 反提历史时间依赖执行机本地时区；该业务时间现显式按 `Asia/Shanghai` 格式化，并由语义表格 readiness + 精确时间断言保护。与 CI 一致的 Node 20 全量运行最终 71 files / 835 tests 全绿，且不再出现 `MaxListenersExceededWarning`。统一门禁还捕获 import confirm 在持久化前发布 matching 的竞态；已改为 durable delta 成功后才发布所有下游信号，并将 4 项 import-processing 测试纳入 `unittest discover`。
- 第五次远程 CI 为 176/177；唯一失败是待找发票文本选择 E2E 用元素 bounding-box 中线做像素拖拽，在 CI 字体/换行布局下落到空白区。测试现对同一可见文本节点执行 Playwright 浏览器文本选择，仍精确验证 `window.getSelection()`，不改业务 UI、不加 retry、不放宽结果。
- 第六次远程 CI 的唯一失败是 ETC 统一批次列表测试等待静态 list 容器后同步读取异步批次行；现以 `etc-batch-unsubmitted-01` 业务行作为 readiness anchor，不改 ETC 业务链路与 I/O。
- 第七次远程 CI 已通过后端、835 前端与 177 浏览器流，最后 docs gate 因 runner 未安装 `rg` 而把命令缺失误报为文档缺失。验证入口现集中选择 `rg` 或 `grep`/`git grep`，并移除未使用的固定 `/tmp` 文件写入。
- 第八次远程 CI 的后端已通过，前端仅有 3 个异步首帧时序失败：成本统计测试把页面标题误当成表格或 refreshing 状态已完成，税金抵扣测试把静态统计卡误当成发票选择行已完成。测试现直接等待对应表格、refreshing 文案和业务复选框，不改产品链路、不加 retry、不放宽业务结果。
- Release A 首次生产激活后，OA sync fan-out 暴露 PostgreSQL OA projection 历史 payload 仍含 `section=open`，新 Workbench core 按两态合同 fail fast。生产已立即回滚到 `etc-import-e5d6e6a4e-20260714-visibility`；hotfix 只在 repository 反序列化 I/O 边界把 legacy `open`/缺失值归一化为 `unpaired`，核心继续拒绝旧状态和未知状态。
- legacy section hotfix 分支精确 SHA CI 成功后，main 精确 merge SHA CI 暴露两个旧测试边界竞态：OA 待付款测试只等待静态页面容器便同步读取异步业务行；Workbench mock server 对同列多值使用 OR，而正式 repository 与本地 display model 使用 AND。测试现等待 OA 业务按钮，并让 mock 复刻正式 AND 合同；不改生产业务链路。
- `FIN_OPS_TEST_DATABASE_URL` is not configured, so real disposable PostgreSQL migration/catalog/hash integration remains unexecuted.
- Release A 已通过 PR #2 合并到 main（merge SHA `85ec4c26195bd7d2320b90c6c92ff3529d920d52`），分支与 main 精确 SHA 远程 CI 均成功；首次生产激活因上述 legacy OA projection payload 问题立即回滚，未把故障版本留作 active release。
- Hotfix 发布前基线仍显示云南立孚 520 关系为 unpaired；破坏性 migration 0104 已明确从 Release A 延后，只有 repaired release 激活后才允许运行已登记的 rehydrate、等待 worker drain 并执行生产 System Audit。
- 17/17 pages expose ready v17 proofs and local System Audit is complete; authorized production read-only execution has not occurred.
- External bank/OA/invoice/ETC control evidence remains unregistered/unknown, so end-to-end external source completeness is still unproven.

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

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-21
Stopped at: Completed quick task 260621-n7i and verified bank details date picker simplification.
Resume file: .planning/quick/260621-n7i-bank-details-date-picker/260621-n7i-SUMMARY.md
