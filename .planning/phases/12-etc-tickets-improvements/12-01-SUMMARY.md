---
phase: 12-etc-tickets-improvements
plan: "01"
subsystem: etc-tickets
tags: [react, postgres, direct-canonical, page-audit, playwright]

requires:
  - phase: existing-etc-business-batches
    provides: ETC business batch、reconciliation task、OA client 和 canonical relation/lifecycle 边界
provides:
  - ETC 页面未提交、暂存、已提交三个互斥 bucket 和 business-batch 单一选择事实源
  - PostgreSQL direct-canonical summary/detail 窄查询与固定 I/O 预算
  - OA 草稿 prepare/锁外 execute/CAS finalize、结果未知恢复和可靠暂存确认
  - ETC Page Audit fail-closed、旧页面热链删除和跨页面隔离验证
affects: [unified-deployment, etc-import-center, workbench, cost-statistics, oa-pending-payments, tax-offset]

tech-stack:
  added: []
  patterns: [direct-canonical narrow read, server-owned action contract, durable external-command state, fail-closed page audit]

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/services/etc_business_batch_application_service.py
    - backend/src/fin_ops_platform/services/etc_service.py
    - backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py
    - backend/src/fin_ops_platform/services/postgres_repositories/etc_tickets_page_audit.py
    - web/src/pages/EtcTicketManagementPage.tsx
    - web/src/features/etc/api.ts
    - tests/test_etc_backend.py
    - web/e2e/etc-tickets-flow.spec.ts

key-decisions:
  - "不新增 ETC read model、cache、worker、schema 或通用 workflow 框架；直接在现有 state store/repository 边界做窄读。"
  - "oa_confirmation_pending 是唯一暂存事实；未提交/需修改只释放 OA 占用，不删除批次、发票、文件或核对结果。"
  - "外部 OA 不支持已验证的 idempotency/marker lookup 时，不伪造 exactly-once；unknown outcome 必须人工证据恢复。"
  - "正式 reconciliation/import/source-file API 保留；仅删除新页面的 full task、双选择、重复 detail、旧 task UI/CSS/mocks。"

patterns-established:
  - "ETC summary list 只返回轻量 DTO；detail 只按一个 business batch、其 invoice IDs 和绑定 task 精确读取。"
  - "ETC OA action eligibility 由服务端纯函数统一供 list/detail/command 使用，前端只展示 enabled/code/message。"
  - "外部 OA I/O 采用 prepare commit -> 无业务锁 HTTP -> finalize CAS；ambiguous 结果禁止盲目重试。"

requirements-completed: [PAGE-14, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

duration: 1h39m
completed: 2026-07-18
---

# Phase 12 Plan 01：ETC 票据改进 Summary

**ETC 页面已收敛为三 bucket 的 direct-canonical 窄读链，并完成可恢复 OA 暂存、fail-closed Audit、旧链删除和部署前性能预算闭环。**

## Performance

- **Duration:** 1h39m
- **Started:** 2026-07-18T13:48:20+08:00
- **Completed:** 2026-07-18T15:26:32+08:00
- **Tasks:** 7
- **Files modified:** 31

## Accomplishments

- 首屏不再读取约 556 KB 的 full reconciliation task 列表，不再重复读取同一 detail；summary/detail 走现有 PostgreSQL 窄查询，不新增 projection、cache 或 worker。
- 页面以 business batch 为唯一可见事实源，支持 `unsubmitted | staged | submitted` 三个互斥 bucket；OA 草稿成功后即使当前 selection 迁移，确认窗口仍保留完整 batch/version，可可靠进入已提交或退回未提交。
- OA 草稿创建使用 durable prepare、锁外 HTTP、CAS finalize、稳定本地 idempotency attempt 和人工 evidence recovery；外部结果未知时不会自动重复创建。
- ETC Page Audit 新增超时 creating、attempt/idempotency 缺失、pending draft/submission 缺失、三 bucket/关系/占用不闭合检查。
- 删除 ETC 页面 full task consumer、双 selection owner、duplicate detail effect、task-row/task-delete 私有 UI/CSS 和旧 mocks；正式导入、核对、source-file API 因仍有 owner/consumer 而保留。

## Task Commits

1. **Task 1：锁定外部 OA 能力、consumer 和性能基线门** — `c35021c76`
2. **Task 2：固定三 bucket、唯一选择和调用预算合同** — `17ce54a4c`
3. **Task 3：direct-canonical business batch 窄读** — `1fe13bd87`
4. **Task 4：business batch 页面单一 owner 与三 bucket** — `7ebd2563e`
5. **Task 5：OA 草稿可恢复 command** — `1d82e2da8`
6. **Task 6：Page Audit 和旧页面链收口** — `9e78d4311`
7. **Task 7：七类回归、性能预算和部署前闭环** — `2acc1d97b`、`dc20a0773`、`10257a286`、`31c7280cd`

## Files Created/Modified

- `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py` — summary/detail/action/OA command 应用服务边界。
- `backend/src/fin_ops_platform/services/etc_service.py` — business batch 状态机、OA prepare/finalize/recovery 和窄读入口。
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py` — 两条 list SQL 与三条 detail SQL 的 direct-canonical 查询。
- `backend/src/fin_ops_platform/services/postgres_repositories/etc_tickets_page_audit.py` — 三 bucket、creating/pending 和关系占用 fail-closed Audit。
- `web/src/pages/EtcTicketManagementPage.tsx` — 三 bucket、单 selection、一次 detail、渐进详情、暂存确认和明确禁用原因。
- `web/src/features/etc/api.ts`、`web/src/features/etc/types.ts` — 新 bucket/count/action DTO 和带 idempotency/version 的 command 合同。
- `tests/test_etc_backend.py` — 状态机/API/Audit/固定 65 张发票 I/O 预算。
- `tests/test_platform_runtime_boundary_guards.py` — 禁止旧 full task、双 selection、旧 route/mocks 和锁内 OA I/O 回归。
- `web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/EtcApi.test.ts` — 页面交互、请求次数、失败恢复和 API contract。
- `web/e2e/etc-tickets-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts` — 三 bucket、暂存确认、删除/上传/OA 失败恢复和 PDF 下载真实 Chromium 流。
- `docs/modules/etc-tickets/*`、`docs/dev/api-contracts.md`、`docs/operations/etc-business-batches.md` — 状态机、边界、测试、API 和运维事实同步。

## Decisions Made

- 生产性能优先通过减少瀑布、payload 和 I/O 次数获得，不引入第二事实源或异步 projection。
- summary 不包含 `invoiceIds/importAttempts/auditEvents/invoiceItems`；详情才返回当前批次所需数组。
- `createOaDraftAction.enabled/code/message` 是服务端唯一资格合同；按钮禁用必须有用户可见原因。
- not-submitted 是可恢复业务状态而不是删除；永久删除仍使用独立 delete/reset 二次确认链。
- 正式 `/api/etc/reconciliation-tasks*` 合同继续服务 Import Center、核对、上传和导入流程，因此不作为旧代码删除。

## Verification and Seven Test Categories

1. **Business core unit tests — 适用。** `tests.test_etc_backend` 覆盖三 bucket、状态转换、资格、幂等、version conflict、unknown outcome 和恢复。
2. **Service-layer tests — 适用。** 覆盖窄 repository/state store、持久化、锁外 OA I/O、partial failure、CAS、删除/reset 和 relation command 边界。
3. **API contract tests — 适用。** 覆盖权限、三 bucket/count/action shape、错误、idempotency key、manual status、detail 和旧 route 防回归。
4. **Read model/cache/background job tests — 适用。** ETC 页面没有新增 read model/cache/worker；现有 direct-canonical Audit、durable import 和 Workbench relation/lifecycle 回归均通过。
5. **Frontend component and interaction tests — 适用。** 覆盖 loading/empty/error、三 bucket、单 selection、一次 detail、禁用原因、暂存、失败重试和删除/上传。
6. **End-to-end integration tests — 适用。** Chromium 覆盖 OA draft -> staged -> submitted、网络失败重试、PDF 下载，以及 ETC Import Center 导入链。
7. **Existing feature regression tests — 适用。** Import Center、关联台、成本统计、OA 待付款和税务定向前端回归通过；architecture guard 保证没有跨页面 I/O/read model 污染。

执行结果：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend tests.test_audit_etc_tickets_read_model_tool tests.test_platform_runtime_boundary_guards -v`：353 项通过，4 项因本机缺少真实票根样例条件性 skip；新增 65 张性能预算测试另行通过，因此本阶段相关后端合计 354 项通过。
- 固定 65 张发票 fixture：首屏 JSON `<=250 KB`、summary 无 `invoiceIds`、detail 65 行、list/detail 对象存储 read/exists 调用均为 0、PostgreSQL list 固定 2 SQL、detail 固定 3 SQL。
- 前端 ETC/API/Import Center/关联台/成本统计/OA 待付款/税务定向 Vitest：9 files、228 tests 通过。
- `npx playwright test e2e/etc-tickets-flow.spec.ts e2e/imports-etc-invoices-flow.spec.ts`：14/14 通过。
- `npm run build`：通过；仅保留既有依赖 CSS syntax/chunk-size warning。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：通过。

## Deviations from Plan

### Auto-fixed Issues

**1. 创建批次 summary 缺少 detail-only 数组导致页面崩溃**

- **Found during:** Task 7 前端组件发布门
- **Issue:** `POST /business-batches` 合法返回轻量 summary，页面却直接读取 `invoiceItems.length`。
- **Fix:** 对尚未加载的 detail-only 数组使用明确空值保护，并清理仍绑定旧 task UI 的测试。
- **Verification:** ETC 页面组件 67/67 通过。
- **Committed in:** `2acc1d97b`

**2. 性能预算尚未机械证明**

- **Found during:** Task 7 性能验收复核
- **Issue:** 原测试只证明 full task=0 和单 detail=1，没有固定 64+ 数据规模、payload bytes、对象存储和 SQL 数上界。
- **Fix:** 在现有后端测试内加入 65 张发票 fixture，并把旧 API 测试的 OA draft 调用补齐 required idempotency key。
- **Verification:** 新预算测试、EtcApi 20/20、lint 通过。
- **Committed in:** `dc20a0773`

**3. OA 草稿成功后人工确认 target 被 selection 迁移清空**

- **Found during:** Task 7 ETC Playwright
- **Issue:** OA 草稿成功会把 batch 从未提交集合移到暂存集合；旧 `draftResult` 只保存展示字段，导致确认弹窗点击“已提交/未提交”时无法解析 batch/version，并静默不发请求。
- **Fix:** 在确认窗口保存完整服务端 `EtcBusinessBatchDetail`，用它作为唯一人工确认 target；E2E mock 同步三 bucket、轻量 summary 和 action DTO。
- **Verification:** ETC 页面组件 67/67、ETC/ETC 导入 Playwright 14/14、production build 通过。
- **Committed in:** `10257a286`

---

**Total deviations:** 3 个计划内 auto-fix（1 个阻塞 UI、1 个缺失验证门、1 个状态迁移正确性问题）。

**Impact on plan:** 均直接服务既定三 bucket、性能预算和暂存闭环，没有新增架构层、依赖、schema、read model、worker 或跨页面行为。

## Post-execution Review Closure

- Standard code review 初审 24 个 source/test 文件，发现 5 Critical、5 Warning、1 Info；两轮修复后第三轮复审为 `clean`，最终 0 finding。
- 前端对象归属与性能闭环：显式暂存行优先 transient target、自动/手动 selection 都会同步失效旧 task、所有 mutation owner-bound、business detail 与精确 task 并行、人工状态变更只触发一次列表请求。
- OA durable 闭环：target-scoped PostgreSQL `FOR UPDATE + version` CAS 取代锁外等待后的全量 snapshot 保存；task metadata 半写可由同 idempotency key/recovery evidence 幂等补齐；local store persist 失败会回滚内存 task/version/metadata/audit，再次跨实例读取仍一致。
- Audit 闭环：creating 超时使用 durable attempt 事件/业务 payload 时间；not-submitted retained membership 与 current owner 分离；新批次合法接管并 submitted 后整页 Audit 仍通过。
- Review fix commits：`936d9a0af`、`1b8cc9c83`、`c599d86a7`、`b071b1d7f`、`40a5ed5c5`、`d89d9d651`、`49e8c40f6`。
- Review 修复后最终组合门：backend 451 passed / 5 skipped / 34 subtests；frontend 12 files / 286 passed；Chromium ETC + ETC import 14/14；production build、lint、docs、ruff、diff-check 通过；schema drift=false。
- 独立 verifier：6/6 requirements、7/7 must-have truths，判定 `READY_FOR_UNIFIED_DEPLOYMENT`。真实生产 p95/p99、真实 OA/对象存储/PostgreSQL contention、部署后 Audit 和混合负载仍是统一部署后的外部门禁。

## Issues Encountered

- 4 个后端测试依赖仓库外真实票根样例，按既有条件性规则 skip；不影响本次业务合同，但真实样例解析仍需 staging/生产 smoke。
- Vite build 报告既有第三方 CSS selector 和 chunk-size warning；build 成功，本轮未修改依赖或通用 bundling。
- OA provider 的原生 idempotency/marker lookup 仍未被证明，因此生产历史 `oa_draft_creating` 批次不能自动猜测恢复结果。

## User Setup Required

None — 本阶段未增加依赖、环境变量、schema 或外部服务配置。

## Next Phase Readiness

- 代码和本地发布门达到 `READY_FOR_UNIFIED_DEPLOYMENT`；未部署、未 push、未修改生产数据。
- 统一部署后必须运行真实 list/detail/Audit canary，并验证 list p95<=300ms/p99<=500ms、detail p95<=500ms/p99<=800ms、action-ready p95<=500ms/p99<=800ms、核心 detail ready p95<=800ms/p99<=1.2s、写后可见 p95<=500ms/p99<=800ms。
- 随后用可回滚测试批次验证 staged -> submitted 和 staged -> unsubmitted 两个出口，再执行 ETC + 关联台/成本统计/OA 待付款/税务/Import Center 混合负载隔离验证。
- 当前历史 `oa_draft_creating` 批次必须先依据真实 OA 证据确认草稿存在与否，再走管理员恢复；不得自动重试创建。

---

*Phase: 12-etc-tickets-improvements*
*Completed: 2026-07-18*
