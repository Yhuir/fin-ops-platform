---
status: complete
created: 2026-06-22
description: OA 待付款自动匹配支出流水并自动写回
---

# Quick Task 260622-oaw: OA 待付款自动匹配和自动写回

## Scope

OA 待付款页面需要取消人工“确认已支付并写回”入口。进行中 OA 应自动匹配右侧抽屉中“未配对”的支出流水，匹配规则复用关联台现有 OA-bank 精确金额/精确合计规则；匹配不到时保留“关联支出流水”右侧抽屉作为人工兜底。completed 和 in-progress 只要已经匹配有效支出流水，都应自动写回 OA MySQL `t_payment_simple.pay_status=1`，页面 chip 从“未写回”刷新为“已写回”。

## Tasks

1. Backend command and API
   - Add `auto_reconcile_bank_transactions` command and `POST /api/oa-pending-payments/auto-reconcile-bank-transactions`.
   - Reuse `WorkbenchMatchingRules` for OA-bank exact amount/exact sum candidates only.
   - Write back completed/in-progress OA with existing active outflow relation when amount matches.
   - Make `link-bank-transactions` automatically write back after relation confirmation when amount/outflow/flow_id checks pass.

2. Frontend behavior
   - Call auto-reconcile once per visible scope, with StrictMode-safe promise sharing.
   - Remove manual confirm-paid button and styles.
   - Keep the bank link drawer for manual fallback and show automatic writeback success.
   - Preserve operation barrier before refreshing rows.

3. Tests and docs
   - Add/update backend command/API tests.
   - Update Vitest and Playwright flows for auto reconcile and bank-link auto writeback.
   - Update module docs, API contract, E2E spec/coverage, and GSD state.

## Acceptance Criteria

- No manual “确认已支付并写回” button is shown on OA 待付款.
- In-progress OA can be automatically matched to unpaired outflow bank transactions using only existing exact OA-bank rules.
- Existing completed/in-progress active outflow relations automatically write back `t_payment_simple.pay_status=1` when amount matches.
- Manual bank link drawer remains available and writes back automatically after successful relation confirmation.
- Candidate/unconfirmed relation evidence cannot write back.
- Auto writeback waits for `oa_pending_payment` operation barrier before rows refresh.
