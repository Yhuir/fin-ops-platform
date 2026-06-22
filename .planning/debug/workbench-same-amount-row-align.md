---
status: investigating
trigger: "关联台三栏配对区域同一大组内，同金额或金额闭合的 OA、流水、发票没有显示在同一行；截图中 29350 OA 未与 29350 流水同行，88050 OA 未与两条合计 88050 的流水同行。"
created: 2026-06-23
updated: 2026-06-23
---

# Debug Session: workbench-same-amount-row-align

## Symptoms

- Expected behavior: 关联台同一个配对大组内，能证明对应关系的 OA、银行流水、进销项发票应显示在同一横向分段；用户要求缺少 source link 时，金额相同或金额合计闭合的行也要同排。
- Actual behavior: 该大组内所有 OA 在左栏连续显示，银行流水在中栏连续显示，同金额/合计闭合的行没有对齐。
- Error messages: 无前端错误；表现为布局分段缺失。
- Timeline: 现有其他配对组已能按 `sourceOaId` 对齐，本组没有使用该实现。
- Reproduction: 打开关联台已配对大组，观察 29350 OA/流水、88050 OA/多条流水是否同行。

## Current Focus

- hypothesis: 现有 `buildWorkbenchGroupDisplaySegments` 只在银行/发票 row 带有效 `sourceOaId` 且可归一到组内 OA 时启用分段；截图大组的相关银行流水没有 `sourceOaId`，因此函数返回 `null` 或把未链接行放到 group-level，导致整组按原始列表渲染。
- test: 添加模型层回归，构造多 OA 大组且银行/发票无 `sourceOaId`，断言同金额和唯一合计金额闭合的行进入对应 OA segment。
- expecting: 测试已先失败，修复后模型层与组件层聚焦测试通过。
- next_action: summarize and close

## Evidence

- 2026-06-23: `docs/modules/reconciliation-workbench/README.md` 已记录现有 source-OA 分段契约：确定 source OA 的发票或流水必须同排；无 source OA 的行原先保持 group-level。
- 2026-06-23: CodeGraph 定位到 `web/src/features/workbench/groupDisplayModel.ts::buildWorkbenchGroupDisplaySegments`。该函数只读取 `row.sourceOaId`，没有金额 fallback；当 `hasLinkedBankRows` 与 `hasLinkedInvoiceRows` 都为 false 时直接返回 `null`。
- 2026-06-23: 现有测试覆盖 source OA / item id 归一，但没有覆盖缺 source link 时同金额或合计金额闭合的展示 fallback。

## Eliminated

- hypothesis: CandidateGroupGrid DOM 渲染本身丢失分段。
  reason: `CandidateGroupGrid` 已调用 `buildWorkbenchGroupDisplaySegments` 并按 segment 渲染；根因在 display model 没生成 segment。

## Resolution

- root_cause: `buildWorkbenchGroupDisplaySegments` 只按 `sourceOaId` / `derived_from_oa_id` 归一后的父 OA id 分段；缺 source link 时即使金额相同或金额合计闭合，也不会生成 segment。
- fix: source link 仍优先；对无 source link 的同组银行/发票 row 增加前端展示 fallback：唯一精确金额先分配，随后对剩余 row 做唯一 2 到 6 条金额合计闭合分配，无法唯一判断的 row 保持 group-level。
- verification: `cd web && npm test -- --run src/test/groupDisplayModel.test.ts`；`cd web && npm test -- --run src/test/groupDisplayModel.test.ts src/test/CandidateGroupGrid.test.tsx`；`cd web && npm run build`；`bash scripts/verify.sh docs`。
- files_changed: `web/src/features/workbench/groupDisplayModel.ts`、`web/src/test/groupDisplayModel.test.ts`、`web/src/test/CandidateGroupGrid.test.tsx`、`docs/modules/reconciliation-workbench/README.md`、`docs/modules/reconciliation-workbench/state-machine.md`、`docs/modules/reconciliation-workbench/tests.md`、`docs/modules/reconciliation-workbench/implementation-notes.md`。
