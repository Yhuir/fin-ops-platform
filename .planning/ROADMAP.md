# Roadmap: fin-ops-platform Page Analysis

## Overview

This roadmap preserves a single global codebase map while creating isolated GSD phases for each target page. Phase 0 establishes the cross-page dependency baseline that every page phase must read before implementation planning. Each page phase should capture discussion context, research findings, implementation risks, test strategy, and executable plans inside its own phase directory.

This roadmap is the root page-analysis roadmap. Cross-module modular IO refactor execution lives under `.planning/refactors/modular-io-boundaries/`; that refactor must still read this file as an input, but its autonomous boundary queue and phase roadmap are tracked separately in `autonomous/MODULE-QUEUE.md` and `04-IMPLEMENTATION-ROADMAP.md`.

## Phases

**Phase Numbering:**

- Integer phases (0-17): Cross-page baseline first, then page-specific analysis and planning work for every registered app page.
- Phase 18: Cross-module repair/evolution work that closes the canonical invoice + ETC batch-link boundary after the page-analysis phases exposed the issue.
- Phase 19-21: Cross-page Audit, reversible relation runtime proof, and deterministic Workbench relation visibility production closure.
- Phase 27-29: Access-time read-model convergence, Cost recovery performance, and Workbench recovery performance closure.
- Phase 26: Turnover closure ownership/completion separation, frozen policy correction, historical repair and Workbench v6 production closure. Its dependencies are logical Phase 1 and Phase 21 contracts, not the immediately preceding numeric phase.
- Decimal phases (2.1, 2.2): Urgent insertions between existing phases.

## Phase Details

### Phase 0: 建立跨页依赖基线：页面数据流、read model/worker、legacy 清理和实施顺序

**Goal:** Capture the cross-page dependency baseline required before any page implementation starts, including page inventory, upstream/downstream data flow, read model/worker ownership, legacy entry points, risk gates, test matrix, docs impact, and recommended implementation order.
**Requirements**: BASE-00, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Global `.planning/codebase/` map and long-term docs under `docs/app-architecture/` and `docs/modules/`.
**Canonical refs:** `docs/app-architecture/pages.md`, `docs/app-architecture/runtime-and-ownership.md`, `docs/modules/README.md`, `docs/modules/read-models/README.md`, `docs/modules/runtime-workers/README.md`, `docs/modules/domain-events-lifecycle/README.md`, `docs/modules/permissions-and-audit/README.md`, `docs/dev/testing-closure-dependency-map.md`, `web/src/app/pageRegistry.tsx`, `web/src/features/domainEvents.ts`, `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`, `backend/src/fin_ops_platform/services/app_status_domain_registry.py`, `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`, `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify all registered pages, their routes, frontend entries, API clients, backend route/service boundaries, read model/worker dependencies, upstream data sources, downstream consumers, and App Status domain bindings.
  2. Cross-page data flow and lifecycle event fan-out are documented enough that a page phase can decide which other pages, read models, workers, caches, exports, and tests are affected.
  3. Legacy entry points and cleanup gates are documented so page phases can migrate callers to canonical boundaries before deleting old paths.
  4. Test matrix and docs impact rules are mapped to the repository's seven test categories and long-term module docs.
  5. Implementation order guidance distinguishes baseline analysis, page-level deep planning, strong dependency groups, and safe parallel work boundaries.

**Plans:** 9 plans

Plans:

- [x] 00-PLAN — Establish baseline artifacts and gates for downstream page phases.

### Phase 1: 完善外部往来款管理页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the external turnover ledger page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-01, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/turnover-ledger/README.md`, `docs/modules/turnover-ledger/state-machine.md`, `docs/modules/turnover-ledger/tests.md`, `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/features/turnoverLedger/api.ts`, `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify turnover-ledger module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 1 to break down)

### Phase 2: 完善银行明细页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the bank details page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-02, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/bank-details/README.md`, `docs/modules/bank-details/state-machine.md`, `docs/modules/bank-details/tests.md`, `web/src/pages/BankDetailsPage.tsx`, `web/src/features/bankDetails/api.ts`, `backend/src/fin_ops_platform/services/bank_details_export_service.py`, `backend/src/fin_ops_platform/services/bank_details_relation_tag_projection_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify bank-details module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 2 to break down)

### Phase 3: 完善税金抵扣页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the tax offset page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-03, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/tax-offset/README.md`, `docs/modules/tax-offset/state-machine.md`, `docs/modules/tax-offset/tests.md`, `web/src/pages/TaxOffsetPage.tsx`, `web/src/components/tax/*`, `web/src/features/tax/api.ts`, `backend/src/fin_ops_platform/app/routes_tax.py`, `backend/src/fin_ops_platform/services/tax_offset_service.py`, `backend/src/fin_ops_platform/services/tax_offset_runtime_service.py`, `backend/src/fin_ops_platform/services/tax_offset_read_model_service.py`, `backend/src/fin_ops_platform/services/tax_offset_read_model_refresh.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify tax-offset module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 3 to break down)

### Phase 4: 完善关联台页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the reconciliation workbench page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-06, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/reconciliation-workbench/README.md`, `docs/modules/reconciliation-workbench/state-machine.md`, `docs/modules/reconciliation-workbench/tests.md`, `web/src/pages/ReconciliationWorkbenchPage.tsx`, `web/src/components/workbench/*`, `web/src/features/workbench/api.ts`, `backend/src/fin_ops_platform/app/routes_workbench.py`, `backend/src/fin_ops_platform/services/live_workbench_service.py`, `backend/src/fin_ops_platform/services/workbench_action_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify reconciliation-workbench module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 4 to break down)

### Phase 5: 完善成本统计页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the cost statistics page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-07, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/cost-statistics/README.md`, `docs/modules/cost-statistics/state-machine.md`, `docs/modules/cost-statistics/tests.md`, `web/src/pages/CostStatisticsPage.tsx`, `web/src/components/cost-statistics/*`, `web/src/features/cost-statistics/api.ts`, `backend/src/fin_ops_platform/app/routes_cost_statistics.py`, `backend/src/fin_ops_platform/services/cost_statistics_query_service.py`, `backend/src/fin_ops_platform/services/cost_statistics_read_model_refresh.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify cost-statistics module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 5 to break down)

### Phase 6: 完善待找发票页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the pending invoices page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-08, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/pending-invoices/README.md`, `docs/modules/pending-invoices/state-machine.md`, `docs/modules/pending-invoices/tests.md`, `web/src/pages/PendingInvoicesPage.tsx`, `web/src/components/pendingInvoices/*`, `web/src/features/pendingInvoices/api.ts`, `backend/src/fin_ops_platform/app/routes_pending_invoices.py`, `backend/src/fin_ops_platform/services/pending_invoice_service.py`, `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify pending-invoices module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 6 to break down)

### Phase 7: 完善进项发票使用情况页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the input invoice usage page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-09, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/input-invoice-usage/README.md`, `docs/modules/input-invoice-usage/state-machine.md`, `docs/modules/input-invoice-usage/tests.md`, `web/src/pages/InputInvoiceUsagePage.tsx`, `web/src/components/inputInvoiceUsage/*`, `web/src/features/inputInvoiceUsage/api.ts`, `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`, `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify input-invoice-usage module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 7 to break down)

### Phase 8: 完善OA待付款核对页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the OA pending payments page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-10, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/oa-pending-payments/README.md`, `docs/modules/oa-pending-payments/state-machine.md`, `docs/modules/oa-pending-payments/tests.md`, `web/src/pages/OaPendingPaymentsPage.tsx`, `web/src/components/oaPendingPayments/*`, `web/src/features/oaPendingPayments/api.ts`, `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`, `backend/src/fin_ops_platform/services/oa_pending_payment_service.py`, `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify oa-pending-payments module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 8 to break down)

### Phase 9: 完善销项发票收款情况页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the output invoice collections page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-11, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/output-invoice-collections/README.md`, `docs/modules/output-invoice-collections/state-machine.md`, `docs/modules/output-invoice-collections/tests.md`, `web/src/pages/OutputInvoiceCollectionsPage.tsx`, `web/src/components/outputInvoiceCollections/*`, `web/src/features/outputInvoiceCollections/api.ts`, `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`, `backend/src/fin_ops_platform/services/output_invoice_collection_service.py`, `backend/src/fin_ops_platform/services/output_invoice_collection_lifecycle_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify output-invoice-collections module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 9 to break down)

### Phase 10: 完善免OA流水批量处理页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the no-OA bank batches page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-12, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/no-oa-bank-batches/README.md`, `docs/modules/no-oa-bank-batches/state-machine.md`, `docs/modules/no-oa-bank-batches/tests.md`, `web/src/pages/NoOaBankBatchPage.tsx`, `web/src/features/noOaBankBatches/api.ts`, `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`, `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`, `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify no-oa-bank-batches module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 10 to break down)

### Phase 11: 完善批量账务页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the batch accounting page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-13, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/batch-accounting/README.md`, `docs/modules/batch-accounting/state-machine.md`, `docs/modules/batch-accounting/tests.md`, `web/src/pages/BatchAccountingPage.tsx`, `web/src/features/batchAccounting/api.ts`, `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify batch-accounting module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 11 to break down)

### Phase 12: 完善ETC票据管理页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the ETC ticket management page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-14, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/etc-tickets/README.md`, `docs/modules/etc-tickets/state-machine.md`, `docs/modules/etc-tickets/tests.md`, `web/src/pages/EtcTicketManagementPage.tsx`, `web/src/features/etc/api.ts`, `backend/src/fin_ops_platform/app/routes_etc.py`, `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`, `backend/src/fin_ops_platform/services/etc_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify etc-tickets module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 1 plan

Plans:

- [x] 12-01-PLAN — Deliver the direct-canonical ETC page performance path, three-bucket OA lifecycle, recoverable scoped-CAS command flow, fail-closed Audit, legacy cleanup, and release verification.

### Phase 13: 关闭 Settings ACL T0-01 权限提权并完成生产发布验证

**Goal:** 修复 Settings ACL T0-01 提权链，使固定 `YNSYLP005` 加 canonical Settings ACL 成为 APP 唯一授权事实源，并把 OA fin-ops menu 收敛为三专用角色的严格投影，完成旧授权链删除、安全发布及生产证据闭环。
**Requirements**: PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/settings/README.md`, `docs/modules/settings/state-machine.md`, `docs/modules/settings/tests.md`, `web/src/pages/SettingsPage.tsx`, `web/src/components/settings/*`, `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/app_settings_service.py`, `backend/src/fin_ops_platform/services/settings_data_reset_service.py`
**Success Criteria** (what must be TRUE):

  1. `YNSYLP005` 是唯一 protected administrator；普通 settings API 不再读取、返回或写入 ACL，full/read/denied 均不能通过 APP API 自提为 admin。
  2. admin-only ACL GET/PUT 使用独立 version/CAS，只合并 ACL family，并将 canonical settings 与 secret-safe durable audit 同事务提交；generic writer 保留并发最新 ACL。
  3. ACL/generic writer共享固定session advisory lock；ACL专用guard内完成stale/no-op、bounded OA target、同步DB commit与锁内失败补偿，确定性并发测试证明settings/audit/OA一致。
  4. SettingsPage 是唯一 ACL UI；Workbench modal、column-layout、pending fallback、runtime env/dynamic admin、mocks/tests中的旧 ACL 路径完整删除。
  5. 两级批准把candidate/control-plane bootstrap与activation分离；首次helper bootstrap使用hash-pinned manual-root同文件系统原子替换并禁止legacy self-update/runtime-worker helper变更；remote fingerprints、API quiesce、migration/CHECK、`--activate-existing`及safe rollback gate阻止旧漏洞重开。
  6. 七类local/candidate回归、production只读DB/OA与双session身份盘点、用户批准后的正式发布和post-deploy full/read/denied逐档API/OA/latency/恢复证据全部通过；不新增表、worker、cache或其它页面/read-model业务事实。
  7. 除固定 `YNSYLP005` 外，APP tier只由一次canonical ACL snapshot决定；OA permission（含`finops:app:view`）、role、三项retired admission env和provider failure均不能授权，缺席即denied且ACL撤权在下一次session/direct API立即生效。
  8. OA只认证username并使用目标OA实测的共享comparison key；Settings是ACL唯一人工I/O，full/read名单完整展示，absence明确denied。
  9. 固定`FIN_OPS_OA_REQUIRED_PERMISSION=finops:app:view`仅定位OA menu；该menu只绑定finops_read_export/full_access/admin三专用role。disabled/missing/menu/role/binding/drift/timeout均失败，non-dedicated cleanup/rollback只作用于approved exact bindings，不触碰业务role/member或其它menu。

**Plans:** 14/15 plans executed

Plans:

- [x] 13-01-PLAN.md — Wave 0：migration、repository CAS/audit 与 local-store 原子合同。
- [x] 13-02-PLAN.md — Wave 1：后端可信 API/auth/request-id/OA 边界及全部 backend legacy caller 删除。
- [x] 13-03-PLAN.md — Wave 2：dedicated ACL frontend、第二入口/旧 payload删除与 Browser 直接提权回归。
- [x] 13-06-PLAN.md — Wave 3：只读实测目标OA username collation/identity并锁定共享comparison contract。
- [x] 13-07-PLAN.md — Wave 4：删除APP permission/role/三env admission，收敛为005加单次canonical ACL snapshot。
- [x] 13-08-PLAN.md — Wave 5：OA runtime三专用角色严格menu投影与现有补偿/fail-closed合同。
- [x] 13-10-PLAN.md — Wave 6：fixed menu selector、deployment exact cleanup/rollback与secret-safe evidence gate。
- [x] 13-09-PLAN.md — Wave 7：backend七类跨模块回归与唯一whole-repo inventory/I-O guard。
- [x] 13-11-PLAN.md — Wave 7：frontend fixtures、direct URL/API、17-route与Browser四tier回归。
- [x] 13-04-PLAN.md — Wave 8：全局安全、产品、API与app-architecture长期事实同步。
- [x] 13-12-PLAN.md — Wave 9：Settings与permissions/audit模块边界、状态机及测试文档同步。
- [x] 13-13-PLAN.md — Wave 10：OA、app-shell与deploy架构/模块合同同步。
- [x] 13-14-PLAN.md — Wave 11：candidate preflight/deploy-control、canonical activation gate与全回归准备。
- [x] 13-15-PLAN.md — Wave 12：以exact `main-2298ba8c-settings-acl-20260802`重新闭合candidate upload、already-exact-noop bootstrap、双身份remote preflight与无漂移activation批准；旧db914/f12链不可复用。
- [ ] 13-05-PLAN.md — Wave 13：基于2298ba8c exact artifacts执行完整JIT preflight→activation→postdeploy/restore→T0–T4及005/006最终验收生产序列。

### Phase 14: 完善系统状态页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the app health operations page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-16, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/app-health-operations/README.md`, `docs/modules/app-health-operations/state-machine.md`, `docs/modules/app-health-operations/tests.md`, `web/src/pages/AppHealthOperationsPage.tsx`, `web/src/features/appHealth/*`, `web/src/features/appStatus/*`, `backend/src/fin_ops_platform/services/app_health_service.py`, `backend/src/fin_ops_platform/services/app_status_overview_service.py`, `backend/src/fin_ops_platform/services/runtime_monitoring.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify app-health-operations module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 14 to break down)

### Phase 15: 完善银行流水导入页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the bank transaction import page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-17, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/imports-bank-transactions/README.md`, `docs/modules/imports-bank-transactions/state-machine.md`, `docs/modules/imports-bank-transactions/tests.md`, `web/src/pages/imports/ImportBankTransactionsPage.tsx`, `web/src/components/imports/ImportWorkflowPage.tsx`, `web/src/features/imports/api.ts`, `backend/src/fin_ops_platform/services/import_file_service.py`, `backend/src/fin_ops_platform/services/import_processing_service.py`, `backend/src/fin_ops_platform/services/import_job_queue.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify imports-bank-transactions module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 15 to break down)

### Phase 16: 完善发票导入页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the invoice import page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-18, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/imports-invoices/README.md`, `docs/modules/imports-invoices/state-machine.md`, `docs/modules/imports-invoices/tests.md`, `web/src/pages/imports/ImportInvoicesPage.tsx`, `web/src/components/imports/ImportWorkflowPage.tsx`, `web/src/features/imports/api.ts`, `backend/src/fin_ops_platform/services/import_file_service.py`, `backend/src/fin_ops_platform/services/import_processing_service.py`, `backend/src/fin_ops_platform/services/import_job_queue.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify imports-invoices module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 16 to break down)

### Phase 17: 完善ETC发票导入页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the ETC invoice import page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-19, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/imports-etc-invoices/README.md`, `docs/modules/imports-etc-invoices/state-machine.md`, `docs/modules/imports-etc-invoices/tests.md`, `web/src/pages/imports/ImportEtcInvoicesPage.tsx`, `web/src/components/imports/ImportWorkflowPage.tsx`, `web/src/features/etc/api.ts`, `backend/src/fin_ops_platform/services/etc_service.py`, `backend/src/fin_ops_platform/services/import_processing_service.py`, `backend/src/fin_ops_platform/services/import_job_queue.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify imports-etc-invoices module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 17 to break down)

### Phase 18: 发票池与 ETC 批次关系闭环：生产修复、事实源边界和历史迁移

**Goal:** Close the duplicate-invoice defect caused by formal invoice imports overlapping submitted ETC batch history, then evolve the architecture so `app.invoices` is the single canonical invoice pool and ETC batch membership is represented by an explicit link fact instead of by duplicate workbench rows.
**Requirements**: INV-ETC-01, INV-ETC-02, INV-ETC-03, INV-ETC-04, INV-ETC-05, INV-ETC-06
**Depends on:** Phase 0 cross-page dependency baseline, Phase 4 reconciliation workbench, Phase 12 ETC ticket management, Phase 16 invoice import, Phase 17 ETC invoice import, and current module docs.
**Canonical refs:** `docs/modules/reconciliation-workbench/README.md`, `docs/modules/reconciliation-workbench/tests.md`, `docs/modules/imports-invoices/README.md`, `docs/modules/imports-invoices/tests.md`, `docs/modules/imports-etc-invoices/README.md`, `docs/modules/imports-etc-invoices/tests.md`, `docs/modules/etc-tickets/README.md`, `docs/modules/etc-tickets/tests.md`, `docs/modules/data-safety-reset/README.md`, `docs/modules/read-models/README.md`, `docs/modules/runtime-workers/README.md`, `backend/src/fin_ops_platform/postgres/migrations/0002_core_imports_invoices_bank.sql`, `backend/src/fin_ops_platform/postgres/migrations/0005_tax_etc_turnover_settings_jobs.sql`, `backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py`, `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
**Success Criteria** (what must be TRUE):

  1. Phase A production stabilization prevents submitted ETC batch invoices from appearing as separate open invoice rows in the reconciliation workbench when the same real invoice exists in `app.invoices`.
  2. Phase A includes a dry-run-first database repair plan that classifies current overlap rows, preserves auditability, refreshes affected read models, and does not delete production data without an explicit apply gate.
  3. Phase B introduces `app.etc_batch_invoice_links` as the canonical ETC batch membership fact while preserving `app.invoices` as one real invoice per active row.
  4. Phase B keeps `app.etc_invoices` only as ETC source/import metadata during migration, not as a competing workbench invoice fact source.
  5. Phase C backfills historical links, removes or deprecates duplicate old paths, updates reset semantics, and documents the final long-term boundary.
  6. Excel full-mirror reconciliation is rerun before data apply: `发票基础信息` invoice identities, `信息汇总表` line rows, DB pool count, missing/extra identities, and field mismatches are all explicitly reported.
  7. Tests cover business core, service/repository, API/read-model/workbench display, import/regression, and at least one cross-module integration flow before completion.

**Plans:** 3 plans

Plans:

- [x] 18-PLAN — Execute Phase A-C as a gated master workflow driven by `18-GOAL-PROMPT.md`; implementation is closed, production apply remains gated by explicit user approval.

---

## Progress

**Execution Order:**
Phase 0 is the shared baseline and must be completed before page implementation planning. After Phase 0, page-analysis phases can run independently in separate worktree threads when they only write their assigned phase directory. Merge planning artifacts carefully if multiple threads update shared root planning files.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. 跨页依赖基线 | 1/1 | Complete | 2026-06-16 |
| 1. 外部往来款管理 | 0/0 | Not started | - |
| 2. 银行明细 | 0/0 | Not started | - |
| 3. 税金抵扣 | 0/0 | Not started | - |
| 4. 关联台 | 0/0 | Not started | - |
| 5. 成本统计 | 0/0 | Not started | - |
| 6. 待找发票 | 0/0 | Not started | - |
| 7. 进项发票使用情况 | 0/0 | Not started | - |
| 8. OA待付款核对 | 0/0 | Not started | - |
| 9. 销项发票收款情况 | 0/0 | Not started | - |
| 10. 免OA流水批量处理 | 0/0 | Not started | - |
| 11. 批量账务 | 0/0 | Not started | - |
| 12. ETC票据管理 | 1/1 | Complete — READY_FOR_UNIFIED_DEPLOYMENT; production gates pending | 2026-07-18 |
| 13. 设置 | 14/15 | In Progress|  |
| 14. 系统状态 | 0/0 | Not started | - |
| 15. 银行流水导入 | 0/0 | Not started | - |
| 16. 发票导入 | 0/0 | Not started | - |
| 17. ETC发票导入 | 0/0 | Not started | - |
| 18. 发票池与 ETC 批次关系闭环 | 1/1 | Implementation complete, apply gated | 2026-06-23 |
| 26. 外部往来闭环冻结要求分区 | 0/2 | Planned | - |
| 30. 关联台并发恢复与性能闭环 | 5/5 | Complete | 2026-07-26 |
| 31. 外部往来款与关联台闭环一致性 | 1/1 | Complete | 2026-07-26 |
| 32. 全页面精确事实证明闭环 | 0/1 | In progress | - |

### Phase 19: 全页面 Audit 证明、跨页关系一致性、readiness 语义与旧链路移除的生产闭环

**Goal:** Establish a production-grade, version-bound and system-snapshot Audit proof for every registered page; prove canonical/shared/consumer relation equality; unify manifest-driven current-effective readiness; remove parallel legacy Audit runtime paths; and close production verification without overstating unavailable external evidence.
**Requirements**: AUDIT-01, AUDIT-02, AUDIT-03, AUDIT-04, AUDIT-05, AUDIT-06, AUDIT-07, AUDIT-08, AUDIT-09, AUDIT-10, AUDIT-11, AUDIT-12
**Depends on:** Phase 0 cross-page baseline and the current long-term module/read-model/worker contracts. Phase 18 is relevant only where ETC invoice facts overlap page proof.
**Canonical refs:** `.planning/phases/19-audit-readiness/19-CONTEXT.md`, `.planning/phases/19-audit-readiness/19-INVENTORY.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/permissions-and-audit/boundary-io.md`, `docs/modules/app-health-operations/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. Every registered page is covered by a fail-closed contract and the registry/page coverage guard passes.
  2. One read-only system snapshot proves independent expected-set equality, critical field recalculation, and canonical/shared/every-consumer relation equality with version-bound results.
  3. Audit, App Status, barriers and SLO share one manifest-driven current-effective policy; `fan_out_command/all` history cannot falsely block while real current failures still block.
  4. Specialized legacy Audit routes/modules/clients are removed after caller evidence, with no runtime fallback or duplicate fact source.
  5. Applicable seven-category tests, exact omission regression, architecture guards, docs verification and authorized production read-only closure all pass.

**Plans:** 19 plans

Plans:

- [x] 19-01-PLAN — Make manifest scope roles authoritative for command-only parent readiness and App Status current-effective aggregation.
- [x] 19-02-PLAN — Establish the 17-page Audit registry and unified page-key runtime; migrate the current 9 controls and make invoice queue proof real.
- [x] 19-03-PLAN — Prove invoice consumer relation edges bidirectionally and remove specialized HTTP Audit runtime paths.
- [x] 19-04-PLAN — Prove OA pending-payment and pending-invoice consumer relation edges bidirectionally.
- [x] 19-05-PLAN — Prove bank-detail linked relation tags, case identity, status, and active-row uniqueness.
- [x] 19-06-PLAN — Prove bank-flow rule batch canonical/page/relation status and member-set equality.
- [x] 19-07-PLAN — Prove batch-accounting direct shared-relation consumer case/mode/source equality.
- [x] 19-08-PLAN — Preserve turnover structured relation summaries and prove per-ledger-row consumer edges.
- [x] 19-09-PLAN — Unify Workbench active-generation display proof, enable the page Audit, and reduce the legacy tool to a thin CLI.
- [x] 19-10-PLAN — Prove the complete Workbench canonical object inventory, critical fields, summaries, and all-scope union.
- [x] 19-11-PLAN — Close cost-statistics upstream lineage, canonical bank set, critical fields, and source-version binding.
- [x] 19-12-PLAN — Prove tax-offset canonical invoice/certified sets, matching, fields, summaries, versions, and queue closure.
- [x] 19-13-PLAN — Prove ETC ticket direct canonical sets, internal relations, files, and import queue closure.
- [x] 19-14-PLAN — Prove Settings direct canonical configuration, credential summaries, projects, and reset queue without secret exposure.
- [x] 19-15-PLAN — Prove bank-transaction import sessions, files, batches, rows, canonical transactions, jobs, and remove the parallel legacy HTTP path.
- [x] 19-16-PLAN — Prove invoice-import files, batches, rows, canonical invoice/source-link edges, isolate page jobs, and remove inline/revert/file-batch legacy paths.
- [x] 19-17-PLAN — Make ETC invoice import sessions durable across processes, prove task/archive/preview/batch/invoice/job equality, and remove in-memory/inline/direct-import legacy paths.
- [x] 19-18-PLAN — Make App Health the fail-closed system Audit owner, run every page proof in one database snapshot, bind version/evidence sets, separate runtime/external observations, and remove the page-private invoice Audit panel.
- [x] 19-19-PLAN — Converge the 13 backend baseline failures to zero by updating stale proof fixtures/contracts and fixing stable legacy exception idempotency without weakening production gates.
- [x] 19-20-PLAN — Register immutable external complete-snapshot manifests and prove bank/OA/invoice/ETC exact sets against canonical App facts without polluting the read-only System Audit.
- [ ] 19-21-PLAN — Deploy the reviewed exact release and capture a read-only 17-page internal System Audit closure report; keep optional external source reconciliation separate and unknown when no independent evidence exists.

### Phase 20: 三组可逆关系写操作的 Fan-out、Worker、Freshness 与 System Audit 生产级闭环

**Goal:** Extend the existing controlled write-operation runner into one production-grade per-mutation closure path, then prove reversible bank+invoice, bank+turnover, and bank+OA+invoice relation shapes across canonical writes, durable fan-out, workers, freshness, affected consumers, and a new read-only System Audit after both confirm and withdraw.
**Requirements**: RELCL-01, RELCL-02, RELCL-03, RELCL-04, RELCL-05, RELCL-06, RELCL-07
**Depends on:** Phase 19
**Canonical refs:** `.planning/phases/20-fan-out-worker-freshness-system-audit/20-CONTEXT.md`, `.planning/phases/20-fan-out-worker-freshness-system-audit/20-RESEARCH.md`, `docs/architecture/module-boundaries/canonical-facts.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/modules/app-health-operations/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. One checkpoint runner proves each mutation independently; no scenario-level shortcut combines confirm and withdraw evidence.
  2. Three reversible relation shapes pass required fan-out, worker drain, freshness, affected consumer and new System Audit gates after both directions.
  3. Canonical relation, queue, freshness and Audit ownership remain modular and no test/runtime path writes derived facts directly.
  4. Retired parallel/legacy execution paths are removed after caller scan; retained adapters have explicit owner and deletion conditions.
  5. Deterministic/full regression and opt-in disposable PostgreSQL gates are complete without 17×operation duplication or external-source overclaim.

**Plans:** 1 plan

Plans:

- [x] 20-01-PLAN — Build the single checkpoint closure runner, register three reversible relation shapes, remove retired paths, and verify deterministic plus disposable-PostgreSQL evidence.

### Phase 21: 关联台确定性自动正式关系与全量可见性生产闭环

**Goal:** Replace persisted automatic candidates/decisions with one deterministic fail-closed formal-relation path, make the Workbench projection an exact partition of canonical facts into active paired groups or standalone unpaired rows, repair all-scope union omissions, remove the complete legacy runtime chain, and prove data-safe recovery through production-grade tests and controlled evidence.
**Requirements**: RELVIS-01, RELVIS-02, RELVIS-03, RELVIS-04, RELVIS-05, RELVIS-06, RELVIS-07, RELVIS-08, RELVIS-09, RELVIS-10
**Depends on:** Phase 20
**Canonical refs:** `.planning/phases/21-workbench-deterministic-relations/21-CONTEXT.md`, `docs/product-specs/workbench.md`, `docs/product-specs/reconciliation.md`, `docs/architecture/module-boundaries/canonical-facts.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. For eligible canonical facts `C`, active relation members `R`, visible paired facts `P`, and visible unpaired facts `U`: `P = R`, `U = C - R`, `P ∩ U = ∅`, and `P ∪ U = C`, with every fact represented once.
  2. Deterministic safe automatic results directly create formal active relations through the existing command/UoW boundary; no candidate/decision persistence, display state, compatibility filter or dual orchestrator path remains.
  3. Cross-month arbitrary N:M:K matching is exact, evidence-connected, bounded and ambiguity-safe; existing relations remain stable and explicit withdrawal/cancel remains the only lifecycle exit.
  4. `month=all` unions active month-shard members by canonical identity without omission or duplication, including the known 13-invoice counterexample; the Yunnan Lifu 520 OA+invoice relation is displayed as paired.
  5. Forward schema migration, read-model rebuild, worker drain, seven-category tests, data hashes and System Audit prove no canonical fact damage and no runtime access to retired candidate/decision objects.

**Plans:** 4 plans
Plans:

- [x] 21-01 — Freeze deterministic matching contracts, 520/13 fixtures and fail-closed safety rules.
- [x] 21-02 — Replace candidate/decision persistence with direct formal relation command/UoW orchestration.
- [x] 21-03 — Enforce the paired/unpaired exact visibility partition across read models, API, UI and downstream consumers.
- [ ] 21-04 — Deploy the clean cutover, run migration 0104, rehydrate registered scopes and capture production data-safety/Audit evidence.

### Phase 21.1: ETC 批次正式关系归属与折叠数量闭环

**Goal:** Make an ETC OA's exact batch marker enrich the one active formal Workbench relation, display the canonical invoice count consistently, remove obsolete operator-only link/migration paths, and prove fast isolated production convergence.
**Requirements:** RELVIS-ETC-01, RELVIS-ETC-02, RELVIS-ETC-03, RELVIS-ETC-04, RELVIS-ETC-05, RELVIS-ETC-06
**Depends on:** Phase 21 deterministic relation runtime and Phase 12 ETC business-batch state machine.
**Canonical refs:** `.planning/phases/21.1-workbench-etc-relation-enrichment/21.1-CONTEXT.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/modules/etc-tickets/boundary-io.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. Collapsed ETC summary and expansion copy both use the canonical detail count; a 34-invoice batch never renders as 35.
  2. An exact OA `etc_batch_id` and exactly one submitted ETC business batch enrich exactly one formal relation through the existing UoW/command boundary; ambiguous or conflicting ownership fails closed.
  3. Paired and unpaired projection use one canonical relation-batch resolver, so one batch has one display owner.
  4. Page Audit proves expected ETC relation enrichment and unique ownership, including post-write freshness/queue closure.
  5. Retired operator-only existing-link and historical-migration services/tools/tests/docs are removed after whole-repository caller evidence.
  6. API p95 is at most 1 second and operation-to-fresh p99 is at most 3 seconds without a new worker, table, cache, fallback, or cross-page write path.

**Plans:** 1 plan

Plans:

- [ ] 21.1-01 — Implement exact enrichment, canonical count/ownership, scoped fast convergence, Audit proof, old-path removal, and production verification.

### Phase 26: 修复外部往来闭环按冻结 OA/发票要求进入关联台分区

**Goal:** Separate canonical active relation ownership from Workbench completion for turnover manual closures; freeze the actual Bank Transaction Paired Policy at confirmation, fail closed when merged bank membership is not fully selected, remove hard-coded and legacy resync paths, repair historical invalid snapshots with fingerprint-bound exact metadata rollback that preserves relation ownership/lifecycle, upgrade Workbench to v6 and close exact-release production rehydration without adding runtime architecture.
**Requirements**: TURN-CLOSURE-01, TURN-CLOSURE-02, TURN-CLOSURE-03, TURN-CLOSURE-04, TURN-CLOSURE-05, TURN-CLOSURE-06
**Depends on:** Phase 1 turnover-ledger canonical closure/write contracts and Phase 21 formal-relation paired/unpaired visibility contracts. There is no dependency on Phase 25 merely because of numbering.
**Canonical refs:** `.planning/phases/26-oa/26-CONTEXT.md`, `.planning/phases/26-oa/26-RESEARCH.md`, `docs/product-specs/bank-turnover-and-no-oa.md`, `docs/modules/turnover-ledger/boundary-io.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/modules/bank-flow-rule-batches/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. Bank-only `turnover_manual_closure` with frozen OA requirement remains one active same-case unpaired relation with missing OA; adding OA moves the same case to paired, while a frozen double-false policy permits direct paired display.
  2. New turnover relations freeze actual selected bank tag codes, canonical rule version/source and OR-composed OA/invoice requirements through the existing helper; unknown/missing inputs fail closed.
  3. Merged closure bank members are a subset of selected bank IDs, selected-row cache covers every policy input with zero additional bank list I/O, and invalid supersets conflict before relation mutation.
  4. The turnover completion bypass, hard-coded metadata and legacy no-OA active-relation resync chain are deleted with no fallback or old runtime references; API/DTO/frontend production code and unrelated relation modes remain unchanged.
  5. Existing repair ops safely repair active legacy-invalid turnover snapshots with metadata-preimage+after-image fingerprint, original-plan reconstruction for audited/idempotent partial execution, and history-based in-place exact metadata rollback; relation members/status/mode/lifecycle/created fields remain unchanged, while Workbench v6 plus existing atomic rehydrate prevents v5 generation/cache from appearing fresh.
  6. Seven-category tests, provider call counts, exact current/previous release evidence, formal readiness/identity/Page/System Audit, controlled dry-run SLO and same-scenario reversible E2E pass; post-execute failure rolls metadata back before previous-release activation/rehydration. The test-owned reversible fixture uses audited fixture recovery and release rollback without creating an additional database backup.

**Plans:** 5 plans

Plans:

- [x] 26-01-PLAN — TDD online root-cause fix, selected-member invariant, real policy snapshot, legacy sync deletion, minimal docs and isolated regression coverage.
- [x] 26-02-PLAN — Historical repair target expansion, Workbench v6 and automatic verification; production dry-run found zero metadata-repair targets but exposed a separate lifecycle dependency loop before final closure.
- [x] 26-03-PLAN — Minimal invoice-lifecycle dependency-scope repair, regression/docs, exact-release deployment, queue drain, affected-page Audit and performance closure.
- [x] 26-04-PLAN — Strict-versus-legacy invoice provenance and ETC imported/closed Audit classification closure.
- [x] 26-05-PLAN — Invoice-page relation relevance Audit closure and restored test-owned Turnover fixture proof.

### Phase 27: 按页面访问收敛 Read Model、消除写后全局 Fan-out 并完成全页面生产验证

**Goal:** Migrate ordinary writes from synchronous cross-page read-model fan-out to canonical commit plus exact access-time freshness convergence, without new runtime infrastructure, while preserving strict correctness, Workbench active generations, explicit batch workflows and full production verification. Latency is measured, but the 3-second stale-to-fresh target is deferred from this phase's completion gate.
**Requirements**: RMF-01, RMF-02, RMF-03, RMF-04, RMF-05, RMF-06, RMF-07, RMF-08, RMF-09
**Depends on:** Phase 26 correctness/frozen-requirement contracts and its controlled production fixture baseline; Phase 27 closes the fan-out performance failures exposed by that baseline.
**Canonical refs:** `.planning/phases/27-read-model-fan-out/27-CONTEXT.md`, `.planning/phases/27-read-model-fan-out/27-RESEARCH.md`, `.planning/phases/27-read-model-fan-out/27-COVERAGE-MATRIX.md`, `docs/app-architecture/pages.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. All 17 registered pages, 110 exported POST/PUT/PATCH/DELETE clients, business Drawers/dynamic openers, 15 manifest read models and direct lifecycle/enqueue/barrier sites stay at zero unmapped coverage.
  2. Ordinary fact/rule writes commit canonical facts, audit/idempotency and stable versions without downstream page refresh fan-out; read-like commands never invalidate and explicit batches remain observable durable jobs.
  3. Page route entry/re-entry, query change, browser manual reload, explicit retry and current-page reconcile perform a cheap freshness/version check and enqueue at most one exact-scope job on mismatch; focus/visibility/BFCache/other-page writes produce no business I/O and stale dependencies fail closed.
  4. Existing gateway/queue/worker/CAS boundaries are reused, Workbench keeps active-generation atomic publish, and superseded lifecycle/barrier/fallback paths are deleted rather than retained in parallel.
  5. Seven-category local gates and exact deployed production probes cover every page, operation and writable Drawer, including correctness, isolation, amplification, retry/reload recovery and measured latency. Completion requires eventual fresh canonical payloads within the existing bounded validation timeout, not a hard 3-second result; slower samples are recorded as `performance_follow_up`.

**Plans:** 7 plans

Plans:

- [x] 27-01-PLAN — Freeze the mechanically checked page, operation, Drawer, read-model and legacy-call coverage contract.
- [x] 27-02-PLAN — Prove the architecture vertically on bank-details and cost-statistics fact/rule/batch behavior.
- [x] 27-03-PLAN — Migrate Workbench, bank-flow, batch-accounting and Turnover relation-heavy writes.
- [x] 27-04-PLAN — Migrate pending/input/OA/output invoice-family rules, facts, Drawers and strict consumers.
- [x] 27-05-PLAN — Complete imports, tax, ETC, settings, App Health and minimal page activation behavior.
- [x] 27-06-PLAN — Delete superseded fan-out paths and close all local correctness/performance gates.
- [x] 27-07-PLAN — Candidate A `bef73c4b6` 完成全矩阵后，Candidate B `3b44f08ef` 集中修复验证 evidence gate；最终 production release、fixture recovery、52/52 probes、System Audit 与 runtime convergence 全部闭合。

### Phase 28: 优化成本统计写后完整 Fresh 的访问恢复热路径

**Goal:** Remove repeated full-history Cost statistics proof I/O while a durable exact recovery is already active, so Bank Detail rows remain independently available and global statistics converge with materially lower database contention, without changing writes, fan-out, scope, workers or correctness semantics.
**Requirements:** Performance follow-up from Phase 27; no new product requirement IDs.
**Depends on:** Phase 27 production correctness and isolation closure.
**Canonical refs:** `.planning/phases/28-cost-statistics-recovery-performance/28-01-PLAN.md`, `docs/modules/cost-statistics/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`
**Success Criteria** (what must be TRUE):

  1. Cost `time|bank_tag` retries use a lightweight durable active-recovery gate while Workbench/Cost recovery is pending or processing; the full statistics proof only runs when no known recovery is active.
  2. Bank Detail rows remain independently fresh, statistics remain fail closed, and exact scope/zero write fan-out contracts do not change.
  3. Targeted local gates and one production candidate prove correctness, isolation, queue/worker drain and a material improvement over the 7.432-second baseline.

**Plans:** 1 plan

Plans:

- [x] 28-01-PLAN — Add the Cost active-recovery fast gate, run targeted regression, and close production performance/correctness proof (`d8e4c5946`, corrective root fix `b6e814b05`).

### Phase 29: 优化关联台写后和页面访问的完整 Fresh 热路径

**Goal:** Remove repeated full Workbench payload polling during active recovery and reuse the existing lightweight freshness port for public status checks, without changing canonical writes, exact scopes, active-generation publication or cross-page isolation.
**Requirements:** Performance follow-up from Phase 27; no new product requirement IDs.
**Depends on:** Phase 28 production closure and Phase 27 Workbench correctness/isolation contracts.
**Canonical refs:** `.planning/phases/29-workbench-access-performance/29-01-PLAN.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`
**Success Criteria** (what must be TRUE):

  1. Operation recovery performs at most one initial trigger load and one final fresh payload load; active waiting uses the existing lightweight refresh-status boundary.
  2. Canonical source proof remains fail closed, active generations remain atomic, and write-time zero fan-out/exact-scope contracts do not change.
  3. Targeted local gates and one production candidate prove correct confirm/withdraw recovery, reduced access I/O, runtime drain and no unrelated page I/O.

**Plans:** 1 plan

Plans:

- [x] 29-01-PLAN — Reuse lightweight Workbench status, remove repeated full payload polling, and close production performance/correctness proof (`6ec4bc48a`, SQL root fix `f06711b7a`).

### Phase 30: 关联台确认/撤回与并发恢复生产闭环

**Goal:** Close Workbench confirm/withdraw correctness, immediate interaction feedback, zero write-time fan-out, exact access-time consumer recovery and reversible production proof while recording the deferred hard 3-second performance gap honestly.
**Requirements:** AUDIT-04, RELCL-01, RELCL-02, RELCL-03, RELCL-05, RMF-02, RMF-03, RMF-08
**Depends on:** Phase 29 and Phase 27 access-time freshness contracts.
**Canonical refs:** `.planning/phases/30-workbench-concurrent-recovery-performance/30-05-SUMMARY.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. Confirm and withdraw use the one canonical relation command/UoW with immediate pending feedback and no write-time page refresh targets.
  2. The sanctioned reversible production fixture proves all registered relation consumers, isolation pages, queue drain and System Audit after both directions.
  3. Slower-than-3-second samples are measured and reported without weakening correctness or hiding them as performance pass.

**Plans:** 5 plans

Plans:

- [x] 30-01-PLAN — Bound the selected-row preview and formal mutation contract.
- [x] 30-02-PLAN — Optimize concurrent exact recovery without changing canonical ownership.
- [x] 30-03-PLAN — Add synchronous pending feedback and safe error mapping.
- [x] 30-04-PLAN — Establish the sanctioned reversible production fixture.
- [x] 30-05-PLAN — Close confirm/withdraw, nine consumers, zero fan-out and System Audit in production.

### Phase 31: 外部往来款与关联台闭环一致性

**Goal:** Remove the unrelated whole-page freshness precondition from turnover closure confirmation, bind the mutation to exact selected bank/category facts, preserve one canonical relation source and add the requested row separator without new runtime architecture.
**Requirements:** TURNWB-01, TURNWB-02, TURNWB-03, TURNWB-04
**Depends on:** Phase 30 canonical relation and reversible production fixture contracts.
**Canonical refs:** `.planning/phases/31-turnover-workbench-closure-consistency/31-01-PLAN.md`, `docs/modules/turnover-ledger/boundary-io.md`, `docs/modules/bank-details/boundary-io.md`, `docs/modules/workbench-relations/boundary-io.md`
**Success Criteria** (what must be TRUE):

  1. Turnover closure confirm validates exact selected canonical bank/category facts and is not blocked by unrelated Bank Detail page state.
  2. Turnover and Workbench continue to read/write one canonical formal relation with zero write-time page fan-out.
  3. Pending feedback, schema invalidation and the requested fine row separator are present without a second projection path.

**Plans:** 1 plan

Plans:

- [x] 31-01-PLAN — Persist and propagate exact bank-row selection proof, invalidate old projections and preserve the proof through the tag facade.

### Phase 32: 修复全页面精确事实证明与历史 Read Model 收敛

**Goal:** Eliminate false-fresh shared relation and Cost scopes by making typed canonical relation membership and current dependency schemas part of exact scope proof, remove the weak legacy paths, rebuild only affected derived scopes through the formal gateway, and close one candidate production deployment with all-page correctness, isolation and measured performance.
**Requirements:** AUDIT-04, AUDIT-11, AUDIT-12, RMF-09
**Depends on:** Phase 30 relation write closure and Phase 31 turnover exact-selection implementation.
**Canonical refs:** `.planning/phases/32-read-model-exact-source-proof-closure/32-01-PLAN.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/modules/cost-statistics/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. Shared relation projection freshness requires exact typed canonical active-edge membership; UUID/legacy aliases, withdrawals, member replacement and cross-month relations cannot leave stale groups marked fresh.
  2. Cost freshness rejects old Workbench business proof and Bank Detail schema while preserving the existing semantic exclusion of the Workbench execution cursor and exact child-scope recovery.
  3. Ordinary writes remain zero fan-out, page access enqueues at most one exact current-effective scope, unvisited pages produce no unrelated I/O, and stale payload is never labeled fresh.
  4. Existing correct page implementations are reused; only a page whose own fail-closed gate still fails after the shared repair may change.
  5. Targeted local gates, one pushed `main` candidate, formal derived-scope recovery, reversible production fixture, measured page performance, queue/worker drain and 16/16 internal System Audit pass.

**Plans:** 1 plan

Plans:

- [ ] 32-01-PLAN — Add RED counterexamples, repair exact relation/Cost proof, delete weak paths, run targeted gates, deploy once and close production evidence.

### Phase 33: 外部往来款直接读取统一事实源

**Goal:** Replace the Turnover ledger read-model/freshness/worker path with one repeatable-read
canonical query on page access, while preserving canonical writes, API behavior and other-page isolation.
**Requirements:** TURNWB-01, TURNWB-02, TURNWB-03, TURNWB-04
**Depends on:** Phase 32 local exact-source proof and Phase 31 canonical closure selection.
**Canonical refs:** `.planning/phases/33-turnover-direct-canonical-read/33-01-PLAN.md`,
`docs/modules/turnover-ledger/boundary-io.md`, `docs/modules/workbench-relations/boundary-io.md`,
`docs/modules/bank-details/boundary-io.md`
**Success Criteria** (what must be TRUE):

  1. Every Turnover page GET reads current canonical bank/category/settings/relation/extra facts in one read-only snapshot.
  2. Turnover GET creates no read-model job or unrelated page I/O, and writes continue through the existing canonical UoW.
  3. The retired Turnover projection, worker, freshness and polling paths have no production callers.
  4. Targeted local gates and one production candidate prove Turnover/Workbench equality, rollback-safe fixture recovery and measured latency.

**Plans:** 1 plan

Plans:

- [ ] 33-01-PLAN — Direct canonical read cutover, legacy removal, targeted verification and production closure.

### Phase 34: 关联台一秒交互热路径与共享投影恢复

**Goal:** Remove duplicate concurrent Workbench initial reads, restore the broken shared
`workbench_relation` projection writer, and verify the existing confirm/withdraw consistency
contracts against explicit production latency targets without adding another cache or read path.
**Requirements:** Performance follow-up from Phase 30; no new product requirement IDs.
**Depends on:** Phase 30 Workbench mutation and active-generation contracts.
**Canonical refs:** `.planning/phases/34-workbench-performance-slo/34-01-PLAN.md`,
`docs/modules/reconciliation-workbench/boundary-io.md`,
`docs/modules/workbench-relations/boundary-io.md`,
`docs/modules/read-models/boundary-io.md`,
`docs/modules/runtime-workers/boundary-io.md`
**Success Criteria** (what must be TRUE):

  1. Concurrent identical background combined-initial reads share one in-flight HTTP request; completed requests are never cached and cancellable search/filter reads remain independent.
  2. Full, partial and empty `workbench_relation` projection writes all update scope metadata without worker dead letters.
  3. Confirm keeps immediate committed projection feedback, withdraw waits for real fresh active-generation convergence, and neither write restores page fan-out.
  4. Targeted local gates, one `main` deployment, queue recovery, authenticated production reads and a reversible write probe record real latency without weakening correctness.

**Plans:** 1 plan

Plans:

- [x] 34-01-PLAN — Fix the shared repository binding, coalesce exact in-flight reads, run targeted gates, deploy once and close production evidence.

### Phase 35: 流水规则批量处理实时统一事实源候选

**Goal:** Derive unsubmitted bank-flow rule candidates directly from current canonical bank,
classification, rule, settings and active-relation facts on page access; preserve submitted/history
facts and canonical relation writes; remove the asynchronous canonical-draft runtime chain.
**Requirements:** Correctness and legacy-removal follow-up from the direct-canonical bank-flow page.
**Depends on:** Phase 34 release baseline and the current canonical relation command contracts.
**Canonical refs:** `.planning/phases/35-bank-flow-rule-batch-live-candidates/35-01-PLAN.md`,
`docs/modules/bank-flow-rule-batches/boundary-io.md`,
`docs/modules/bank-details/boundary-io.md`,
`docs/modules/workbench-relations/boundary-io.md`,
`docs/modules/runtime-workers/boundary-io.md`
**Success Criteria** (what must be TRUE):

  1. Unsubmitted candidates are live-derived in one canonical snapshot and never depend on a prewritten draft, worker, replay or cache.
  2. The known 188500 internal-transfer pair appears once in May with the correct two members and single-side amount.
  3. Submit/withdraw preserves the existing formal relation UoW, idempotency and history while rereading the live candidate at command time.
  4. Audit detects missing expected candidates, UI facets reflect actual candidates, and the canonical-draft owner/producer/event/deploy chain is deleted.
  5. Targeted local gates, one pushed `main` release and authenticated production probes prove correctness, isolation and sub-second warm reads without Redis or a new read model.

**Plans:** 1/1 plans complete

Plans:

- [x] 35-01-PLAN — Live candidate derivation, command revalidation, Audit/UI closure, canonical-draft deletion and production verification.

### Phase 36: 全站右侧抽屉滑入动效与详情链路生产闭环

**Goal:** Make every right-side drawer enter from the right and exit back to the right through one native HeroUI/CSS motion contract, remove custom drawer shells that bypass it, and release the already-landed Workbench exact-generation detail fix with measured production correctness and performance.
**Requirements:** User-approved drawer motion and Workbench detail production closure; no new product requirement IDs.
**Depends on:** Phase 35 verified release baseline and commit `825d34011` Workbench stable-generation detail contract.
**Canonical refs:** `.planning/phases/36-right-drawer-motion-production-closure/36-01-PLAN.md`, `docs/refactor-ui/interaction_smoothness.md`, `docs/modules/finance-table-system/boundary-io.md`, `docs/modules/reconciliation-workbench/boundary-io.md`
**Success Criteria** (what must be TRUE):

  1. Modal right drawers reuse HeroUI Drawer placement and animate the container from 100% right to 0 on enter and back to 100% on exit, with a 240ms/180ms transform-only contract and reduced-motion support.
  2. The OA bank-link and bank-flow tag-management custom shells are replaced by `AppDrawer` without changing their business I/O, permissions, forms, loading, error or mutation behavior.
  3. The tax certified-results complementary rail remains non-modal but collapses/expands with transform and opacity, correct inert/focus behavior, and no width/grid layout animation.
  4. Conflicting legacy keyframes, transition overrides, duplicate Escape ownership and obsolete custom shells are deleted; no animation dependency, fallback path or parallel abstraction is added.
  5. Targeted frontend/backend gates, one pushed `main` deployment, authenticated Workbench detail probes and browser motion measurements prove correctness, page isolation and production performance.

**Plans:** 1/1 plans complete

Plans:

- [x] 36-01-PLAN — Shared native drawer motion, custom-shell migration, regression gates, deployment and production verification.

### Phase 37: App Shell 侧栏层级、OA 身份区与静态品牌状态入口

**Goal:** Improve sidebar hierarchy and spacing, add a fixed clickable current-OA-user area, and replace the rotating status graphic with a static local brand mark while preserving the global status popover and all existing route/business I/O contracts.
**Requirements:** User-approved sidebar redesign; no new product requirement IDs.
**Depends on:** Phase 36 verified shell and drawer baseline.
**Canonical refs:** `.planning/phases/37-app-shell-sidebar-identity/37-01-PLAN.md`, `docs/modules/app-shell-navigation/boundary-io.md`, `web/src/components/shell/AppSidebar.tsx`, `web/src/contexts/SessionContext.tsx`
**Success Criteria** (what must be TRUE):

  1. Desktop, collapsed and mobile sidebars use a fixed brand zone, independently scrollable navigation and fixed OA account footer without changing the `232px / 72px` shell width contract.
  2. Current account identity comes only from existing SessionContext and opens a lightweight details popover with zero additional API or image I/O.
  3. The static local brand mark remains the global runtime-status entry; the rotating SVG, keyframes and obsolete styles are deleted without a fallback or second status path.
  4. Page names, route order, permissions and business pages are unchanged; no dependency is added.
  5. Targeted/full frontend gates, browser interaction/performance proof, one pushed main deployment and production route/health smoke pass.

**Plans:** 1/1 plans complete

Plans:

- [x] 37-01-PLAN — Sidebar identity, spacing, legacy cleanup, regression gates, main deployment and production verification.

### Phase 38: ETC 票据页面扁平化与流程可见性生产闭环

**Goal:** Flatten the ETC ticket page into one batch rail and one continuous workflow surface, remove the obsolete page-level plate/keyword query path, and present a fact-driven four-stage reconciliation/import/OA lifecycle without changing backend contracts or downstream behavior.
**Requirements:** User-approved ETC page redesign; no new product requirement IDs.
**Depends on:** Phase 37
**Canonical refs:** `.planning/phases/38-etc/38-01-PLAN.md`, `docs/modules/etc-tickets/boundary-io.md`, `docs/modules/imports-etc-invoices/boundary-io.md`, `web/src/pages/EtcTicketManagementPage.tsx`, `web/src/features/etc/api.ts`
**Success Criteria** (what must be TRUE):

  1. The page keeps one left batch rail and one continuous right workflow, removes the plate/keyword UI/request/CSS/test/docs path, and deletes conflicting nested-card legacy rules.
  2. A read-only four-stage summary derives only from current business batch, reconciliation task, import and OA facts, including failure, retry, rollback and manual-confirmation states.
  3. Existing permissions, actions, stale-request protection, independent ETC import route, import worker and Workbench ETC summary remain behaviorally unchanged.
  4. No dependency, backend state, API, cache, read model or worker is added; targeted/full local gates and cross-page regressions pass.
  5. One pushed `main` release and authenticated production probes prove the UI, request-count, performance, worker/queue and health contracts.

**Plans:** 1/1 plans complete

Plans:

- [x] 38-01-PLAN — ETC lifecycle summary, flat workspace, legacy cleanup, regression gates, deployment and production verification.

### Phase 39: Runtime Worker 拓扑收敛与旧派生链删除

**Goal:** Remove unconsumed Search and No-OA derived runtimes plus pure capacity replicas, preserve canonical relation/business owners, and converge the required production topology from 11 to 6 workers without adding a replacement framework.
**Requirements:** User-approved worker architecture reduction; no new product requirement IDs.
**Depends on:** Phase 38 verified release baseline and the current canonical-query-first contracts.
**Canonical refs:** `.planning/phases/39-runtime-worker-topology-convergence/39-01-PLAN.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/no-oa-bank-batches/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. Required worker inventory is exactly six instances and release activation disables every removed instance.
  2. Search API/read model/runtime and the three capacity replicas are deleted with no UI, queue, health, env, test or docs residue.
  3. No-OA canonical relation and Workbench internal-transfer commands remain; its legacy list API reads canonical facts directly and its read model/worker are deleted.
  4. Workbench generation, relation distribution, OA sync, import and settings maintenance correctness/rollback contracts remain unchanged.
  5. Full local gates, one pushed main deployment and T+300 production evidence prove queue drain, freshness, API performance, page isolation and rollback readiness.

**Plans:** 1/1 plans complete

Plans:

- [x] 39-01-PLAN — Runtime topology convergence, legacy derived-chain deletion, regression gates, deployment and production verification.

### Phase 40: 性能合同与核心热路径闭环

**Goal:** Establish target-scale/concurrent/browser performance evidence, repair proven frontend/SQL/application/import hot paths, and make Workbench access-time freshness fully self-converging after any canonical writer while writers remain zero-notification; remove stale legacy paths and close one production release without adding workers, page read models, cache, event transport or a query framework.
**Requirements:** User-approved T0-6 performance audit; no new product requirement IDs.
**Depends on:** Phase 39 verified six-worker/two-read-model production baseline.
**Canonical refs:** `.planning/phases/40-performance-contract-hot-path-closure/40-CONTEXT.md`, `.planning/phases/40-performance-contract-hot-path-closure/40-RESEARCH.md`, `.planning/phases/40-performance-contract-hot-path-closure/40-01-PLAN.md` through `40-08-PLAN.md`, `docs/operations/monitoring.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, affected module `boundary-io.md` files.
**Success Criteria** (what must be TRUE):

  1. Target-scale, concurrent and browser evidence separates database, application, payload and rendering costs without writing production business data.
  2. FinanceTable pagination and proven pending/invoice/Workbench hot paths are bounded while exact financial and generation contracts remain unchanged.
  3. Only measured application/import hotspots change, using existing repository and batch/COPY capabilities with no new runtime architecture.
  4. Every Workbench-affecting canonical writer advances exact source proof but never sends a Workbench notification; existing refresh-status detects stale, enqueues only exact scopes through the current gateway, and the current worker atomically activates one fresh generation.
  5. A visible Workbench checks immediately on entry/focus and then one second after each completed status request, pauses while hidden, remains strict single-flight and reloads the full payload once per changed fresh generation.
  6. Target concurrency is derived from a named production evidence window or approved capacity contract; both derived load tiers meet p95/error/resource gates, and same-clock t0..t4 samples prove commit-to-visible p99 `<=3000ms` with every segment summing to the total.
  7. Retired Search/read-model and Workbench-local target paths are deleted with no fallback, double-read or retained-job regression; full local gates, one pushed `main`, one exact deployment, T+300 and rollback evidence prove correctness, isolation and performance.

**Plans:** 6/8 plans executed
Plans:

- [x] 40-01-PLAN — Wave 1: bounded performance probes/contract and constant-size FinanceTable pagination.
- [x] 40-02-PLAN — Wave 1: three proven SQL hot paths with exact-result PostgreSQL regression.
- [x] 40-03-PLAN — Wave 1: proven import batch-row multi-value path only; speculative page/DTO hot paths excluded.
- [x] 40-04-PLAN — Wave 2 after 40-01/02/03: Search/no-OA fact/guard cleanup, full local gates and exact candidate handoff; no push/deploy.
- [x] 40-05-PLAN — Wave 1: backend refresh-status exact self-heal and unchanged API/writer contracts.
- [x] 40-06-PLAN — Wave 1: visible completion-driven one-second Workbench poller and interaction contracts.
- [ ] 40-07-PLAN — Wave 2 after 40-05/06: real writer→proof matrix, zero-fanout worker closure, local target cleanup and deterministic Browser E2E.
- [ ] 40-08-PLAN — Wave 3 after 40-04/07: affected docs, derived target capacity, Playwright same-clock browser p99, full gates and the only push/deploy/production/rollback closure.

---
