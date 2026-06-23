---
status: resolved
trigger: "免 OA 流水批量处理未提交流水行前没有 checkbox，无法选中流水后点击提交批次"
created: 2026-06-21T16:33:09Z
updated: 2026-06-23T15:08:00Z
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
- timestamp: 2026-06-23T14:16:00Z
  observation: 新截图中批次标题为 `多账户8106` 且状态徽标显示“待提交”，但无 checkbox。组件复现显示 `status=stale,status_bucket=unsubmitted,blocked_reason=源流水或分类已变化，需要复核后处理。` 时页面只显示“待提交”，且只对 conflict 展示阻断原因，因此用户看不到为什么不可选。
- timestamp: 2026-06-23T14:16:00Z
  observation: 后端 service test `test_submitted_batch_that_becomes_stale_clears_active_relation` 定义 `status=stale,status_bucket=unsubmitted` 为源流水或分类漂移后不可提交、不可撤回状态；当时中间判断为显示“需复核”，后续生产口径已收敛为公开状态只保留 `draft/submitted/withdrawn`，该类内部诊断状态不进入主列表。
- timestamp: 2026-06-23T14:16:00Z
  observation: Playwright 新增 `ordinaryDraftMatrix` 场景，真实 Chromium 逐个验证 `fee/salary/holiday_bonus/bonus/tax_payment/treasury_tax_collection/social_security` 普通 draft 批次均显示行级 checkbox 且可勾选/取消。
- timestamp: 2026-06-23T15:08:00Z
  observation: 产品目标收敛为公开生命周期只保留 `draft/submitted/withdrawn`。`conflict/stale/superseded` 改为内部兼容/诊断状态，不进入主列表、summary 或 pagination；持久化改存 `public_snapshot()`，生产历史数据可用 `repair_no_oa_bank_batch_lifecycle` dry-run/apply 清理。

## Eliminated

- hypothesis: 后端缺少 `submit-selection` API 或前端未实现 row selection。
  evidence: API client、页面 handler 和现有 submit-selection tests 均存在。

## Resolution

- root_cause: 两类旧状态都会造成“看起来未提交但没有 checkbox”：一是普通 draft 被旧批次级 `can_submit` 或旧 `status=unsubmitted` 污染；二是 `conflict/stale` 被当成未提交 summary/list 项暴露，但这些内部状态本来不可提交。
- fix: 普通 draft/legacy unsubmitted 通过后端公开投影、API mapper 和 feature policy 统一判定并显示提交入口；`conflict/stale/superseded` 从公开 API/list/detail/summary/pagination 和持久化 public snapshot 清理。新增生产 repair CLI，默认 dry-run，`--apply` 才通过 PostgresStateStore 清理 DB/read model。
- verification: `pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_lifecycle_repair.py tests/test_no_oa_bank_batch_read_model_refresh.py -q`; `cd web && npm test -- --run src/test/NoOaBankBatchApi.test.ts src/test/NoOaBankBatchPolicy.test.ts src/test/NoOaBankBatchPage.test.tsx`; `cd web && npx playwright test e2e/no-oa-bank-batches-flow.spec.ts --project=chromium`; `cd web && npm run build`; `bash scripts/verify.sh docs`.
- files_changed: `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`; `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`; `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`; `backend/src/fin_ops_platform/services/no_oa_bank_batch_lifecycle_repair.py`; `backend/src/fin_ops_platform/tools/repair_no_oa_bank_batch_lifecycle.py`; `tests/test_no_oa_bank_batch_service.py`; `tests/test_no_oa_bank_batch_application_service.py`; `tests/test_no_oa_bank_batch_lifecycle_repair.py`; `web/src/features/noOaBankBatches/api.ts`; `web/src/features/noOaBankBatches/policy.ts`; `web/src/pages/NoOaBankBatchPage.tsx`; `web/src/test/NoOaBankBatchApi.test.ts`; `web/src/test/NoOaBankBatchPolicy.test.ts`; `web/src/test/NoOaBankBatchPage.test.tsx`; `web/e2e/no-oa-bank-batches-flow.spec.ts`; `web/e2e/fixtures/apiMocks.ts`; `docs/modules/no-oa-bank-batches/*`.
