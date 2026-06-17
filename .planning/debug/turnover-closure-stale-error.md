---
status: resolved
trigger: "外部往来款管理中选中两项点击确认闭环后弹出“银行流水状态已变化，请刷新后重试。”；需要修复页面，并解释为什么 e2e 没测出来。"
created: "2026-06-17"
updated: "2026-06-17"
---

# Debug Session: turnover-closure-stale-error

## Symptoms

- Expected behavior:
  - 在外部往来款管理中选中同组两笔可闭环流水，点击 `确认闭环` 后应提交成功，或在真正 stale 时先刷新并让用户重新选择。
- Actual behavior:
  - 页面允许打开确认闭环弹窗，提交后弹出 `操作失败`。
- Error messages:
  - `银行流水状态已变化，请刷新后重试。`
- Timeline:
  - 2026-06-17 用户截图反馈；发生在 OA 关联与闭环 chip 拆分修复后继续完善页面时。
- Reproduction:
  - 外部往来款管理 -> 个人往来 -> 展开刘涵静 -> 选中两笔 240,000 流水 -> 点击 `确认闭环` -> 确认弹窗提交。

## Current Focus

- hypothesis: 前端 fresh reload 后仍提交了后端不能接受的 `turnover_bank_row:*` expected_versions；真实 payload 中 bank row category/version 字段与 mock/e2e 用例不一致，导致 e2e 只断言 POST 发生，未断言真实 stale 409 成功路径。
- test: 先补页面/ API 测试复现 expected_versions 版本键或值不匹配，再补 e2e/mock 断言 confirm payload 包含真实 bank row versions 且成功后不出现操作失败。
- expecting: 修复后页面对缺失/不可靠版本不提交错误 expected_versions，或提交后端实际可比对的版本；e2e 覆盖 stale error dialog 不出现。
- next_action: complete verification and report root cause.

## Evidence

- timestamp: "2026-06-17"
  observation: "截图中两笔选中后按钮可用，但提交后后端返回 `银行流水状态已变化，请刷新后重试。`，说明错误发生在确认请求的 stale precondition，而不是前端选择规则。"
- timestamp: "2026-06-17"
  observation: "web/src/pages/TurnoverLedgerPage.tsx 在确认前重新拉 fresh ledger，并用 `closureExpectedVersions(freshRows)` 构造 `turnover_bank_row:{bankRowId}` expected_versions。"
- timestamp: "2026-06-17"
  observation: "web/e2e/fixtures/apiMocks.ts 对 `/api/turnover-ledger/closures/confirm` 是 mock 成功响应，未模拟 expected_versions 与真实后端 stale precondition 的比对。"

## Eliminated

- hypothesis: "按钮 gating 仍然把 OA linked 当闭环阻断"
  reason: "截图中 `确认闭环` 已可点击并进入提交，失败来自提交后的 stale precondition。"

## Resolution

- root_cause: 页面确认闭环前会重新拉 grouped ledger，但没有检查 fresh reload 的 `readModelStatus`，因此 reload 结果仍为 stale 时也会继续提交。另一个问题是 grouped flow row 缺少 `category_version` 时，前端 mapper 把缺失版本映射成 `0`，导致确认请求提交 `turnover_bank_row:* = 0`，后端用真实 bank row 版本比对后返回 `银行流水状态已变化，请刷新后重试。`
- fix: 前端把 `categoryVersion` 改为 `number | null`，只有后端明确提供版本时才提交 `expected_versions`；确认前 fresh reload 如果仍非 fresh，清空选择并提示重新选择，不再 POST `/closures/confirm`。浏览器 e2e mock 现在会校验 closure confirm 请求里的 bank row ids 和 `turnover_bank_row:*` versions，版本不匹配时返回 409。
- why_e2e_missed: 原 e2e fixture 对 `/api/turnover-ledger/closures/confirm` 无条件返回成功，不读取请求体，也不校验 `expected_versions`。用例只断言 POST 次数和成功 UI，所以页面即使发送错误版本也会通过。
- verification:
  - `cd web && npm test -- --run src/test/TurnoverLedgerPage.test.tsx -t "omits closure expected versions|blocks manual closure submit"` passed.
  - `cd web && npm test -- --run src/test/TurnoverLedgerPage.test.tsx src/test/TurnoverLedgerApi.test.ts` passed: 32 tests.
  - `cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts` passed: 1 test.
  - `cd web && npm run build` passed, with existing CSS minifier warnings unrelated to this change.
  - `git diff --check` passed.
- files_changed:
  - `web/src/features/turnoverLedger/api.ts`
  - `web/src/features/turnoverLedger/types.ts`
  - `web/src/pages/TurnoverLedgerPage.tsx`
  - `web/src/test/TurnoverLedgerPage.test.tsx`
  - `web/e2e/fixtures/apiMocks.ts`
  - `web/e2e/turnover-ledger-flow.spec.ts`
