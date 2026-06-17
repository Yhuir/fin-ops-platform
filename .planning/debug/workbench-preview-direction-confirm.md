---
status: resolved
trigger: "2026-06-17 用户反馈：关联台选择 1 条 OA、3 条银行流水点击确认关联，预览页显示金额不一致；金额应按收支方向核对，且预览页看不到确认关联按钮。"
created: "2026-06-17"
updated: "2026-06-17"
---

# Debug Session: workbench-preview-direction-confirm

## Symptoms

- Expected behavior:
  - OA 支付 300,000 与同方向支出流水 300,000 应显示金额一致；反向收入流水仍展示在明细中，但不应把银行流水绝对合计 600,000 当作本次可比金额。
  - 确认关联预览里应能直接看到并点击“确认关联”按钮。
- Actual behavior:
  - 预览页显示 `OA 300000.00 · 流水 600000.00`，状态为“金额不一致”，差额 300,000.00。
  - 预览内容过长时 footer 在首屏外，用户看不到确认按钮。
- Error messages:
  - 无后端错误；这是 preview payload 和前端展示问题。
- Timeline:
  - 2026-06-17 用户通过截图反馈。
- Reproduction:
  - 关联台未配对区选择 1 条 OA 支付 300,000，3 条银行流水：支出 300,000、收入 100,000、收入 200,000，点击“确认关联”进入预览。

## Current Focus

- hypothesis: `WorkbenchAmountCheckService.check()` 对银行流水按绝对金额求和，并且 `RelationPreviewTriPane` 忽略后端 `amount_summary.status`，用展示合计二次计算 mismatch；长弹窗 footer 未 sticky。
- test: 新增后端 core 单测、confirm preview API contract 测试和前端交互测试。
- expecting: preview amount summary 使用同方向银行子合计，状态为 matched；前端不再二次标黄，且“确认关联”按钮在 modal 底部操作区持续可见。
- next_action: resolved.

## Evidence

- timestamp: "2026-06-17"
  observation: "`WorkbenchAmountCheckService.check()` 原先设置 `bank_total = _sum_amounts(normalized_rows['bank'])`，未区分 debit/credit 方向。"
- timestamp: "2026-06-17"
  observation: "`RelationPreviewTriPane.resolveVisualMismatchFields()` 原先在 `mismatch_fields=[]` 时仍用展示 totals 比较 OA 与流水，导致后端 status 已为 matched 也会被视觉层重新标成 mismatch。"
- timestamp: "2026-06-17"
  observation: "`RelationPreviewDialog` footer 位于两段三栏预览和备注之后，`.detail-modal` 内滚动时首屏可能只看到预览内容，看不到提交按钮。"

## Eliminated

- hypothesis: "确认按钮完全没有渲染"
  reason: "`RelationPreviewDialog` 对 `confirm_link` preview 已渲染主按钮，问题是长内容下 footer 不在可见区域；同时某些已 active row-set 的 preview 仍应合法切换为 withdraw preview。"
- hypothesis: "应该改成前端本地按收支重新计算"
  reason: "关联台文档要求业务规则在后端 policy/service 中维护，页面只消费后端 preview 和 read model 结果。"

## Resolution

- root_cause: "后端 amount check 缺少方向化银行流水子合计；前端预览组件忽略后端 amount status 并用展示 total 二次推断 mismatch；预览 footer 非 sticky 导致长预览下确认按钮不可见。"
- fix: "`WorkbenchAmountCheckService.check()` 根据 OA/发票锚定的 relation direction 选择同方向银行/发票金额参与比较，并返回 `oa_amount`、`bank_amount`、`amount_delta` 兼容字段；`RelationPreviewTriPane` 使用后端 `status/mismatchFields` 作为状态事实；`RelationPreviewDialog` 改为中间内容滚动、底部 action 区固定可见。"
- verification:
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_amount_check_service -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_and_submit_require_note_for_amount_mismatch tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_uses_directional_bank_total_for_mixed_bank_directions tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_rejects_unbalanced_amounts -v"
  - "cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx"
  - "cd web && npm run build"
- files_changed:
  - "backend/src/fin_ops_platform/services/workbench_amount_check_service.py"
  - "tests/test_workbench_amount_check_service.py"
  - "tests/test_workbench_v2_api.py"
  - "web/src/components/workbench/RelationPreviewTriPane.tsx"
  - "web/src/pages/ReconciliationWorkbenchPage.tsx"
  - "web/src/app/styles.css"
  - "web/src/test/WorkbenchSelection.test.tsx"
  - "docs/modules/reconciliation-workbench/tests.md"
  - "docs/modules/reconciliation-workbench/implementation-notes.md"
