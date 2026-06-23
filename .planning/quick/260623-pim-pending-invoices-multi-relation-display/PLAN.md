---
phase: quick
plan: 260623-pim-pending-invoices-multi-relation-display
type: pre-implementation-analysis
scope: pending-invoices
status: analysis-complete
created_at: 2026-06-23
autonomous: false
---

# 待找发票多 OA / 多流水 / 多发票 `+N` 展示实现前分析

## Goal

确认待找发票是否已经接入统一 relation 事实源，并规划完整实现：

- 待找发票必须根据 `workbench_relation` / Workbench canonical relation 的配对关系展示 OA、银行流水和发票。
- 同一 relation 下存在多项 OA、多项流水或多项发票时，在各自栏显示 `+N`。
- 点击 `+N` 后只展开对应类型的全部 N 项：OA 只看 OA，流水只看流水，发票只看发票。
- 被包含在 `+N` 里的 OA、流水或发票不得在同一行再作为单独主项展示；多项时 `+N` 代表全部 N 项，不是“主项 + 额外 N 项”。
- 同一 relation 的成员不得再作为 standalone 行重复出现。

## Current Findings

### 已接入统一事实源

待找发票读链路已经接入统一 relation read model：

- `GET /api/pending-invoices/rows` 通过 `PendingInvoiceApiRoutes.rows(...)` 调用 `PendingInvoiceReadModelService.rows(...)`，正式路径读取 pending invoice read model。
- SQL projection `SearchPendingSqlProjectionBuilder._pending_invoice_rows(...)` 通过 `WorkbenchRelationReadFacade.get_by_row_ids(..., require_fresh=True, reason="pending_invoice_sql_projection")` 读取 `workbench_relation` distribution。
- projection 将 `workbench_relation_source_versions` 写入 pending invoice source versions，read model fresh gate 能识别 relation distribution stale/source mismatch。
- fallback/query service `PendingInvoiceQueryService._row_payload(...)` 和 `relation_detail(...)` 也会从 relation facade 读取 `linked_oa`、`linked_bank_transactions`、`linked_input_invoices` / `linked_output_invoices`。
- 模块文档明确规定 OA/流水/发票配对关系不属于待找发票页面私有状态，读关系必须走 `WorkbenchRelationReadFacade` / `workbench_relation` distribution，写关系必须委托 `WorkbenchRelationCommandService`。

结论：事实源方向是正确的；本轮不是新建事实源，而是补齐 relation distribution 到 rows DTO、去重和 UI 表达。

### 当前未满足用户要求

1. 前端 rows DTO 只有单个 `bankTransaction`，没有 `bankTransactions` zone。
   - 现有类型已有 `inputInvoices` zone 和 `oa` zone：`primary / relationCount / hasMultiple / summaries`。
   - 银行流水区仍是单条 `bankTransaction`，多流水只能在 `PendingInvoiceRelationDrawer.paymentRows` 中看到，列表栏无法显示 `+N`。

2. 发票和 OA 的 `+N` 语义是“主项 + 额外项”，不是“全部 N 项”。
   - `PendingInvoicesTable` 当前显示 primary invoice / primary OA，并在旁边显示 `+{relationCount - 1}`。
   - 用户要求多项时只显示 `+N`；包含在 `+N` 中的成员不能再单独展示。

3. 关系 drawer 是按 transaction id 拉全量关系，不区分点击的是 OA、流水还是发票。
   - 当前 `PendingInvoiceRelationDrawer` 同时展示发票、OA 和历史支付流水。
   - 用户要求点击各自栏的 `+N` 后只显示对应类型的多项明细。

4. 后端 rows 构建没有 relation member 去重。
   - `SearchPendingSqlProjectionBuilder._pending_invoice_rows(...)` 按银行流水逐行构建 payload。
   - `PendingInvoiceQueryService.list_rows(...)` fallback 也按交易逐行 append。
   - 如果同一个 active relation 包含多条银行流水，facade 会对每个成员 row 返回完整 relation context；当前逻辑会给多个银行成员各生成一行，导致成员既在 `+N` 中又作为 standalone 行出现。

5. API contract 对待找发票 rows 还没有明确 `bankTransactions/detailMode` 聚合字段。
   - `docs/dev/api-contracts.md` 对待找发票只要求 relation detail 能表达全部付款流水、发票、OA。
   - 进项发票使用情况和 OA 待付款核对已经有类似 rows 聚合契约，可作为待找发票补齐方向。

## Product / UX Decisions

- 多项显示规则：
  - count = 0：显示空值。
  - count = 1：沿用当前单项展示和详情按钮。
  - count > 1：该栏只显示 `+N` 控件和必要的聚合金额；不显示任一成员作为 primary。
- `+N` 的 N 是该类型全部 summaries 数量，不是 extra count。
- 发票金额列在多发票时显示发票合计；不拼接某张发票号、某个供应商或 `+{N-1}`。
- 银行金额列在多流水时显示流水合计；对方户名、摘要等单笔字段不展示某个成员，避免误导。
- OA 多项时申请人/项目列不展示某个 primary OA，只展示对应 `+N` 明细入口。
- candidate relation 仍可作为候选证据展示 `+N`，但不能驱动 `paid_invoiced` / 已支付等 linked-only 业务判断。

## Proposed API Shape

向后兼容添加，不删除现有字段：

```json
{
  "id": "txn-primary-or-relation-case",
  "bank_transaction": { "...": "legacy single fallback" },
  "bank_transactions": {
    "primary": { "...": "single bank summary or null" },
    "relation_count": 3,
    "linked_relation_count": 3,
    "has_multiple": true,
    "detail_mode": "list",
    "summaries": [
      {
        "id": "txn-1",
        "trade_time": "2026-06-18 08:16:11",
        "counterparty_name": "...",
        "amount": "184.47",
        "debit_amount": "184.47",
        "credit_amount": "0.00",
        "bank_name": "建行",
        "account_last4": "8106",
        "summary": "电子转账",
        "relation_case_id": "case-...",
        "relation_status": "linked",
        "relation_source": "workbench_relation"
      }
    ],
    "payment_summary": {
      "paid_total": "587000.00"
    }
  },
  "input_invoices": {
    "relation_count": 2,
    "detail_mode": "list",
    "summaries": []
  },
  "oa": {
    "relation_count": 2,
    "detail_mode": "list",
    "summaries": []
  }
}
```

Detail endpoint options:

- Minimal implementation: keep `/api/pending-invoices/rows/{transaction_id}/relation-detail`, add optional `kind=bank|invoice|oa|all`, and filter the existing relation detail payload server-side.
- Preferred consistency: add `/api/pending-invoices/rows/{row_id}/relation-details?kind=bank|invoice|oa`, matching OA pending and input invoice usage patterns. The old singular endpoint can remain as compatibility alias.

## Backend Implementation Plan

### Task 1 - Tests First: Relation Group Aggregation

Add backend coverage before implementation:

- Query service fallback test with one relation containing 2 OA + 3 bank transactions + 2 input invoices.
- SQL projection test with the same relation distribution payload.
- Assert exactly one pending invoice row is emitted for the relation in the relevant scope.
- Assert all grouped bank transaction IDs are absent as standalone rows.
- Assert:
  - `bank_transactions.relation_count == 3`
  - `input_invoices.relation_count == 2`
  - `oa.relation_count == 2`
  - `payment_summary.paid_total` uses linked bank total only
  - `invoice_acquisition_status` uses linked invoices only
- Add candidate relation regression: candidate summaries may show as evidence, but status must remain linked-only.

### Task 2 - Build Bank Transaction Zone

Add shared helpers in pending invoice service/projection:

- Convert `linked_bank_transactions` relation distribution items into bank summaries.
- Prefer authoritative bank transaction facts when available; fall back to distribution item fields only for display.
- Deduplicate by transaction id while preserving relation distribution order.
- Carry `relation_case_id`, `relation_status`, `relation_source`.
- Compute linked bank count and paid total from linked-only items.

Update:

- `PendingInvoiceQueryService._row_payload(...)`
- `SearchPendingSqlProjectionBuilder._pending_invoice_rows(...)`
- pending invoice API mapper/read model payload contracts

### Task 3 - Suppress Standalone Relation Members

During rows construction:

- Track relation group ids / case ids already emitted in the current build.
- For a relation group with multiple bank members, select one canonical display row and mark all bank member transaction ids as consumed.
- Skip consumed transaction ids when their turn appears in the bank transaction loop.
- Preserve non-relation rows as one row per bank transaction.

Canonical display row selection should be deterministic:

- Prefer the first linked bank transaction in relation distribution that is present in current scope.
- Fallback to current transaction id.
- Keep `bank_transaction` populated as legacy fallback for existing consumers, but frontend should use `bank_transactions` zone when present.

Open design risk:

- Cross-month relations can create duplicate aggregate rows if each month shard emits the same relation group. If production has cross-month relation cases, define an owner month based on relation `month_scope` or first linked bank trade month, and ensure non-owner shards skip the aggregate display row while still marking member rows consumed. Add a targeted test if this exists in fixtures/production evidence.

### Task 4 - Kind-Specific Relation Details

Update relation detail service/API:

- Accept `kind=bank|invoice|oa|all`.
- Return only the requested section for `bank`, `invoice`, or `oa`.
- Preserve old response shape for `all` / omitted kind.
- Ensure detail reads existing row payload or relation facade, not private pair snapshots.

### Task 5 - Frontend DTO + Rendering

Update frontend types and mapper:

- Add `PendingInvoiceBankTransactionSummary`.
- Add `PendingInvoiceBankTransactionZone`.
- Add `bankTransactions` to `PendingInvoiceRow`, while preserving existing `bankTransaction`.
- Map snake_case `bank_transactions`.

Update table rendering:

- Bank section:
  - count > 1: render only `+N` control for bank detail and aggregate amount; do not render a primary counterparty/time/summary as standalone.
  - count = 1: render current single bank UI.
- Invoice section:
  - count > 1: render only invoice `+N` and aggregate invoice amount/payment summary; do not render primary invoice number/seller as standalone.
  - count = 1: render current single invoice UI.
- OA section:
  - count > 1: render only OA `+N`; do not render primary applicant/project as standalone.
  - count = 1: render current single OA UI.

Update drawer:

- Track detail target kind from the clicked `+N`.
- Show only the requested list.
- Keep relation status chips, especially candidate chips.

### Task 6 - Export / Search / Filter

Decide whether export should mirror grouped display:

- Recommended: export one grouped row with relation counts and joined detail fields, matching list semantics.
- Search/filter should match child OA/bank/invoice summaries and return the whole group row.
- Existing `searchable_text` currently omits invoice/OA child detail beyond first summary; expand it to include all grouped summaries.

## Docs Impact

Update when implementing:

- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/state-machine.md`
- `docs/modules/pending-invoices/tests.md`
- `docs/modules/pending-invoices/e2e-spec.md`
- `docs/modules/pending-invoices/e2e-coverage.md`
- `docs/modules/pending-invoices/implementation-notes.md`
- `docs/dev/api-contracts.md`
- `docs/product-specs/invoice-lifecycle.md` if product wording changes from “relation detail can express all” to “rows must group all relation members”.

No new source of truth should be introduced; docs should say this is a `workbench_relation` display/read-model contract completion.

## Seven-Category Test Matrix

1. Business core unit tests: applies.
   - Relation grouping, linked-only status, candidate evidence, paid/invoice totals, duplicate suppression.

2. Service-layer tests: applies.
   - Query service fallback, read model projection, relation facade dependency, detail endpoint filtering.

3. API contract tests: applies.
   - Rows response shape with `bank_transactions`, `detail_mode`, `relation_count`; detail endpoint `kind`; stale/non-fresh behavior unchanged.

4. Read model/cache/background job tests: applies.
   - `pending_invoice` SQL projection, source versions, `workbench_relation` freshness gate, cross-month/member dedupe if relevant.

5. Frontend component and interaction tests: applies.
   - `+N` display per section, no primary duplicate when count > 1, kind-specific drawer contents, candidate status chips.

6. End-to-end business-flow integration tests: applies.
   - Workbench confirm multi OA/bank/invoice relation -> `workbench_relation` fresh -> pending invoice rows fresh -> grouped row and detail expansion.

7. Existing feature regression tests: applies.
   - Single bank/single invoice/single OA rendering, attach existing drawer, income status batch, filter/sort/status filters, export, candidate-not-closing-status, manual endpoint removal.

## Acceptance Criteria

- A relation with multiple OA, multiple bank transactions, and multiple invoices appears as one pending invoice row in the current view.
- OA column shows `+N` for all OA members; clicking it shows only OA rows.
- Bank transaction section shows `+N` for all bank members; clicking it shows only bank rows.
- Invoice section shows `+N` for all invoice members; clicking it shows only invoice rows.
- No OA/bank/invoice member included in a `+N` detail list is rendered elsewhere in the same row as a standalone primary item.
- No grouped bank transaction is emitted as a separate standalone pending invoice row in the same scope.
- Linked relation facts drive paid/invoiced status; candidate relation facts stay display-only evidence.
- Rows remain behind pending invoice and workbench relation read model freshness gates; stale/missing does not return fake fresh.
- Existing single-item pending invoice rows still render as before.

## Verification Commands

Focused backend:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_search_pending_sql_runtime tests.test_pending_invoice_api -v
```

Focused frontend:

```bash
cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx
```

Browser flow if UI/detail behavior changes:

```bash
cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/pending-invoices-filter-sort-flow.spec.ts --project=chromium
```

Docs:

```bash
bash scripts/verify.sh docs
```

Broader regression if relation distribution/projection helpers are shared:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api tests.test_input_invoice_usage_api tests.test_oa_pending_payment_api -v
cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/InputInvoiceUsagePage.test.tsx
```

## Out of Scope

- Changing Workbench relation write semantics.
- Changing attach existing invoice confirm semantics.
- Production data repair or read model rebuild.
- OA pending payment behavior already handled by a separate quick task.
- Reworking table layout beyond the cells needed for `+N` grouping.

## Remaining Risks

- Current worktree has unrelated dirty changes in OA pending payment, Workbench, docs and tests. Implementation should avoid mixing those diffs unless the user confirms they are part of the same delivery.
- Cross-month relation grouping needs an explicit owner-month policy if such relations exist in production.
- Export semantics need product confirmation if grouped rows should export as one aggregate row or expanded child rows. The list UI requirement points to one aggregate row, but existing export consumers may expect row-level detail.
