---
status: resolved
trigger: "OA 樊祖芳支付申请，云南心诚环保科技有限公司，金额 7000，2026-04-16，未自动匹配 2026-04-23 交通银行 3847 支出流水 7000；要求检查配对逻辑实现完整。"
created: 2026-06-22
updated: 2026-06-22
---

# Debug Session: oa-bank-auto-match-7000

## Symptoms

- Expected behavior: OA 待付款记录金额 7000、对方名“云南心诚环保科技有限公司”、申请日期 2026-04-16，应能自动关联金额 7000、同对方名、2026-04-23 的未配对支出流水。
- Actual behavior: OA 待付款核对页面该 OA 行仍显示“待支付/未写回”，流水列为空；关联支出流水抽屉搜索 7000 能查到对应流水但未自动关联。
- Error messages: 页面截图未显示错误。
- Timeline: 2026-06-22 截图发现；是否曾经可用未知。
- Reproduction: 打开 OA 待付款核对，选择 2026 年 04 月进行中 OA，查看“云南心诚环保科技有限公司”7000 元记录及关联支出流水抽屉。

## Current Focus

- hypothesis: 规则层能识别截图中的 7000 精确匹配；实际未自动配对更可能发生在 relation confirm / flow_id 解析 / OA MySQL 写回阶段，但旧实现会静默跳过。
- test: 用截图字段构造 WorkbenchMatchingRules 和 OaPendingPaymentCommandService 最小闭环，并新增自动匹配跳过诊断回归。
- expecting: 规则层生成 `oa_bank_exact_amount`；命令服务在 flow_id 缺失时返回 `skippedAutoMatches` 诊断。
- next_action: 发布后用 2026-04 调用 auto-reconcile 接口，查看该生产样本是否出现在 `skippedAutoMatches`。
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- 2026-06-22: `WorkbenchMatchingRules.generate_candidates` 对 OA `云南心诚环保科技有限公司/7000/2026-04-16` 与银行流水 `云南心诚环保科技有限公司/7000/2026-04-23` 生成 `oa_bank_exact_amount`，证据为 `counterparty_match` + `date_within_7_days`。
- 2026-06-22: `OaPendingPaymentCommandService.auto_reconcile_bank_transactions({"month":"2026-04"})` 最小闭环会确认 relation、写回 flow_id，并入队 `workbench:2026-04/all` 与 `oa_pending_payment:2026-04/all`。
- 2026-06-22: 原实现对自动候选确认、flow_id 解析或写回阶段的 `OaPendingPaymentError` 直接 `continue`，接口只返回 0，现场无法知道跳过原因。

## Eliminated

- 规则不支持同对方名、同金额、7 天内支付：已排除。
- 前端完全不调用自动匹配：代码显示有写权限时页面会调用 `auto-reconcile-bank-transactions`。
- 月份来源不是申请日期：Mongo adapter `_derive_month` 首选 `applicationDate`。

## Resolution

- root_cause: 不能从本地数据直接确认生产该条的最终跳过原因；代码级根因是自动匹配失败缺少可观测性，导致 flow_id 缺失、relation 冲突或写回失败都表现为“没有自动配对”。
- fix: `auto_reconcile_bank_transactions` 响应新增 `skippedAutoMatches`；自动候选在确认/flow_id/写回阶段失败时返回 OA row、bank row、规则码、错误码、消息和 details。
- verification: `tests.test_oa_pending_payment_command_service`、`tests.test_oa_pending_payment_api`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`scripts/verify.sh docs`、`web npm run build`。
- files_changed: `backend/src/fin_ops_platform/services/oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_command_service.py`、`web/src/features/oaPendingPayments/types.ts`、`docs/modules/oa-pending-payments/implementation-notes.md`、`docs/modules/oa-pending-payments/tests.md`。
