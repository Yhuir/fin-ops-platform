---
status: resolved
trigger: "免 OA 流水批量处理未提交流水行前没有 checkbox，无法选中流水后点击提交批次"
created: 2026-06-21T16:33:09Z
updated: 2026-06-21T16:39:45Z
---

# Debug Session: no-oa-selection-checkbox

## Symptoms

- Expected behavior: 未提交普通 draft 候选流水行前应显示 checkbox，用户可选择同月、同银行账户、同 category_code 的流水后点击“提交批次”。
- Actual behavior: 截图中右侧“费用 / 手续费”未提交流水列表没有可见 checkbox，但顶部存在“提交批次”按钮。
- Error messages: 未提供；截图中无明显错误提示。
- Timeline: 未提供。
- Reproduction: 打开 `/no-oa-bank-batches`，选择 `2026年01月`，停留在“未提交”，主标签“费用”，子标签“手续费”，查看右侧流水列表。

## Current Focus

- hypothesis: 页面组件或样式丢失/隐藏了未提交普通候选的行级选择控件；后端 submit-selection contract 仍存在。
- test: 检查 `NoOaBankBatchPage` 对 draft row selection 的渲染、权限门禁、CSS 布局和现有测试断言。
- expecting: 能定位到 checkbox 没有随流水行渲染，或旧组件/CSS 使其不可见。
- next_action: inspect page component, API mapper, tests, and styling around transaction rows and selection state.
- reasoning_checkpoint: 用户要求高维度修复；若是旧渲染逻辑绕过当前 selection contract，应删除或隔离旧逻辑，避免污染 submit-selection 新链路。
- tdd_checkpoint: add or tighten frontend regression test before/with fix.

## Evidence

- timestamp: 2026-06-21T16:33:09Z
  observation: 模块文档定义 `draft` 普通候选可选择行提交，`submit-selection` 只提交当前选择流水，且前端测试矩阵已有 selected-row submit/selection guard 入口。
- timestamp: 2026-06-21T16:36:16Z
  observation: `NoOaBankBatchPage` 已有 `selectedTransactionIds` state、row checkbox JSX 和 `submitNoOaBankBatchSelection` 调用，但 `canSelectBatchRows(...)` 额外依赖批次级 `canSubmit`。旧 SQL/read model payload 缺少 `can_submit` 时前端 mapper 将 `canSubmit` 归一为 `false`，从而隐藏普通 draft 行 checkbox。
- timestamp: 2026-06-21T16:39:45Z
  observation: 补充验证 `submit_selected_rows` 同账户多条手续费后，Workbench `/api/workbench?month=all` paired 区返回 `relation_mode=no_oa_bank_batch`、`display_mode=collapsed_summary`、`default_collapsed=true`、`bank_rows=[no_oa_summary:<batch_id>]`，原始流水保存在 `collapsed_rows.bank`。

## Eliminated

- hypothesis: 后端缺少 `submit-selection` API 或前端未实现 row selection。
  evidence: API client、页面 handler 和现有 submit-selection tests 均存在。

## Resolution

- root_cause: 普通未提交流水行级选择入口被旧批次级 `can_submit` flag 控制；旧 read model payload 缺字段时隐藏 checkbox，污染了 `submit-selection` 新链路。
- fix: `canSelectBatchRows(...)` 改为只依据 `bucket=unsubmitted`、`status=draft`、非 `internal_transfer`；内部往来整批提交仍保留 `canSubmit` 批次级门禁。新增页面回归测试覆盖缺失 `can_submit` 的旧 payload。
- verification: `cd web && npm test -- --run src/test/NoOaBankBatchPage.test.tsx`; `cd web && npm run build`; `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_workbench_integration.NoOaBankBatchWorkbenchIntegrationTests.test_submit_selection_fee_rows_render_as_collapsed_paired_workbench_group tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests.test_no_oa_bank_batch_group_collapses_to_summary_and_preserves_bank_rows tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests.test_single_row_no_oa_bank_batch_stays_as_regular_bank_row -v`; `cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/CandidateGroupGrid.test.tsx`; `bash scripts/verify.sh docs`.
- files_changed: `web/src/pages/NoOaBankBatchPage.tsx`; `web/src/test/NoOaBankBatchPage.test.tsx`; `tests/test_no_oa_bank_batch_workbench_integration.py`; `docs/modules/no-oa-bank-batches/tests.md`; `docs/modules/no-oa-bank-batches/implementation-notes.md`; `docs/modules/reconciliation-workbench/tests.md`.
