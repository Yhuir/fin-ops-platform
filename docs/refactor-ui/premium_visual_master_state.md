# Premium Visual Master State

本文档记录 premium visual slice + interaction smoothness 长跑任务的状态。它是执行状态机，不替代 `PRODUCT.md`、`DESIGN.md`、`docs/refactor-ui/table_layout_system.md` 或各模块事实源。

Last updated: 2026-06-08

## Goal

在 `main` 分支上，以银行明细 premium sample 为视觉和交互样板，把除关联台内部工作区之外的所有页面提升到统一的 HeroUI/Tailwind premium 产品质感，并保留所有原始功能。

## Non-Negotiable Boundaries

- 不改后端、API contract、read model、worker、权限语义或业务状态机。
- 不改关联台内部工作区：`ReconciliationWorkbenchPage` 和 `web/src/components/workbench/*`。
- 不恢复 `PageKeepAliveHost`、`keepAliveMode`、`PageSessionSnapshot`、`usePageSessionSnapshot`、`usePageScrollSession` 或 data snapshot。
- 保留 route code splitting、sidebar preload、`usePageSessionState`。
- 不新增 `@mui/*` 或 `@emotion/*`。
- 不使用 `git add .` 或 `git add -A`。

## Design Baseline

- `PRODUCT.md`: 克制、清晰、可靠的财务运营产品。
- `DESIGN.md`: Ledger Calm 设计系统。
- `docs/refactor-ui/prompt_premium_bank_detail.md`: 银行明细 premium sample。
- `docs/refactor-ui/table_layout_system.md`: 表格内容排版系统。
- `docs/refactor-ui/interaction_smoothness.md`: 动效和交互体感规则。

## Phase Queue

| Order | Slice | Status | Notes |
| --- | --- | --- | --- |
| 0 | `PV-000-premium-foundation-discovery` | verified | 建立主控 prompt、状态机、prompt 日志和 interaction_smoothness 规则。 |
| 1 | `PV-001-shared-premium-foundation` | verified | motion tokens、基础交互样式、reduced motion、foundation tests。 |
| 2 | `PV-002-tax-offset-discovery` | verified | `/tax-offset` 旧入口清单、表格/弹窗/右侧工作区矩阵、测试缺口。 |
| 3 | `PV-003-tax-offset-premium-visual` | verified | 税金抵扣 premium visual slice。 |
| 4 | `PV-004-app-health-discovery` | verified | `/operations/app-health` discovery。 |
| 5 | `PV-005-app-health-premium-visual` | verified | 系统状态 premium visual slice。 |
| 6 | `PV-006-import-pages-discovery` | verified | `/imports/*` discovery。 |
| 7 | `PV-007-import-pages-premium-visual` | verified | 导入页族 premium visual slice。 |
| 8 | `PV-008-cost-statistics-discovery` | verified | `/cost-statistics` discovery。 |
| 9 | `PV-009-cost-statistics-premium-visual` | verified | 成本统计 premium visual slice。 |
| 10 | `PV-010-pending-invoices-discovery` | verified | `/pending-invoices` discovery。 |
| 11 | `PV-011-pending-invoices-premium-visual` | pending | 待找发票 premium visual slice。 |
| 12 | `PV-012-input-invoice-usage-discovery` | pending | `/input-invoice-usage` discovery。 |
| 13 | `PV-013-input-invoice-usage-premium-visual` | pending | 进项发票使用 premium visual slice。 |
| 14 | `PV-014-oa-pending-payments-discovery` | pending | `/oa-pending-payments` discovery。 |
| 15 | `PV-015-oa-pending-payments-premium-visual` | pending | OA 待付款核对 premium visual slice。 |
| 16 | `PV-016-output-invoice-collections-discovery` | pending | `/output-invoice-collections` discovery。 |
| 17 | `PV-017-output-invoice-collections-premium-visual` | pending | 销项发票收款 premium visual slice。 |
| 18 | `PV-018-no-oa-bank-batches-discovery` | pending | `/no-oa-bank-batches` discovery。 |
| 19 | `PV-019-no-oa-bank-batches-premium-visual` | pending | 免 OA 流水批量处理 premium visual slice。 |
| 20 | `PV-020-batch-accounting-discovery` | pending | `/batch-accounting` discovery。 |
| 21 | `PV-021-batch-accounting-premium-visual` | pending | 批量账务 premium visual slice。 |
| 22 | `PV-022-turnover-ledger-discovery` | pending | `/turnover-ledger` discovery。 |
| 23 | `PV-023-turnover-ledger-premium-visual` | pending | 外部往来款管理 premium visual slice。 |
| 24 | `PV-024-etc-tickets-discovery` | pending | `/etc-tickets` discovery。 |
| 25 | `PV-025-etc-tickets-premium-visual` | pending | ETC 票据管理 premium visual slice。 |
| 26 | `PV-026-settings-discovery` | pending | `/settings` discovery。 |
| 27 | `PV-027-settings-premium-visual` | pending | 设置 premium visual slice。 |
| 28 | `PV-028-app-wide-smoothness-audit` | pending | 全 app interaction smoothness audit。 |
| 29 | `MG-PV-final-premium-visual-closeout` | pending | 全量验证、smoke、commit/push closeout。 |

## Current Slice

`PV-011-pending-invoices-premium-visual`

### Scope

- `docs/refactor-ui/premium_visual_master_state.md`
- `docs/refactor-ui/premium_visual_prompt.md`
- `docs/refactor-ui/premium_visual_master_state.md`
- `docs/refactor-ui/premium_visual_prompt.md`
- `docs/refactor-ui/modules/phase_6_pending_invoices.md`
- `web/src/pages/PendingInvoicesPage.tsx`
- `web/src/components/pendingInvoices/*`
- `web/src/app/styles.css`
- `web/src/test/PendingInvoicesPage.test.tsx`

### Verification

Required for PV-011:

- `cd web && npx vitest run PendingInvoicesPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- `rg` no keepalive/snapshot/scroll-session forbidden terms in current facts.
- `rg` no non-workbench runtime MUI imports.
- Browser smoke for `/pending-invoices` where practical.

PV-011 is a runtime visual/interactions slice. It must preserve PendingInvoices behavior and only polish the current project primitive implementation.

## Execution Rules

Each implementation slice must:

1. Read current state, prompt log, module docs, related code, and tests.
2. Generate exactly one next prompt.
3. Execute that prompt.
4. Update this state, `premium_visual_prompt.md`, and any module doc touched.
5. Run targeted tests, type check, build, diff check, forbidden grep, and smoke where applicable.
6. Commit with exact staging and push to `origin/main`.
7. Re-read `git status --short --branch` before moving to the next slice.

## Push Log

| Date | Slice | Commit | Push | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-08 | `PV-000-premium-foundation-discovery` | `2f26c79a` | pushed to `origin/main` | Docs foundation verified and pushed. |
| 2026-06-08 | `PV-000-state-update` | `4e276a95` | pushed to `origin/main` | State advanced to PV-001 after push. |
| 2026-06-08 | `PV-001-shared-premium-foundation` | current commit | pushed to `origin/main` | Shared motion foundation verified and pushed with the current commit. |
| 2026-06-08 | `PV-002-tax-offset-discovery` | current commit | pushed to `origin/main` | Tax Offset discovery and PV-003 prompt generated with the current commit. |
| 2026-06-08 | `PV-003-tax-offset-premium-visual` | current commit | pushed to `origin/main` | Tax Offset premium visual polish verified and pushed with the current commit. |
| 2026-06-08 | `PV-004-app-health-discovery` | current commit | pushed to `origin/main` | AppHealth discovery and PV-005 prompt generated with the current commit. |
| 2026-06-08 | `PV-005-app-health-premium-visual` | current commit | pushed to `origin/main` | AppHealth premium visual polish verified and pushed with the current commit. |
| 2026-06-08 | `PV-006-import-pages-discovery` | current commit | pushed to `origin/main` | Import pages premium discovery and PV-007 prompt generated with the current commit. |
| 2026-06-08 | `PV-007-import-pages-premium-visual` | current commit | pushed to `origin/main` | Import pages premium visual polish verified and pushed with the current commit. |
| 2026-06-08 | `PV-008-cost-statistics-discovery` | `44dd84de` | pushed to `origin/main` | Cost Statistics premium discovery and PV-009 prompt generated. |
| 2026-06-08 | `PV-009-cost-statistics-premium-visual` | `8a77149f` | pushed to `origin/main` | Cost Statistics premium visual polish verified; PV-010 prompt generated in `docs/refactor-ui/premium_visual_prompt.md`. |
| 2026-06-08 | `PV-009-push-log-update` | `70e7ddd8` | pushed to `origin/main` | Recorded PV-009 push status after push. |
| 2026-06-08 | `PV-010-pending-invoices-discovery` | `ac6861d8` | pushed to `origin/main` | Pending invoices premium discovery and PV-011 prompt generated. |
