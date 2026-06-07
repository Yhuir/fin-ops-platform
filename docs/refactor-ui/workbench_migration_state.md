# Workbench Migration State

本文档是关联台内部工作区 MUI 迁移的专项状态机事实源。每次执行 prompt 或 cumulative MG 后必须更新。

## Current Phase

- Phase: `wb_phase_0_baseline`
- Status: `implemented`
- Branch: `refactor-ui`
- Last Updated: `2026-06-07`
- Current Prompt ID: `P-WB001-baseline-discovery`
- Current MG ID: `MG-WB001-baseline`

## Global Invariants

| Invariant | Status | Evidence |
| --- | --- | --- |
| Backend untouched | yes | `P-WB001` 只新增/更新 refactor-ui 文档 |
| API contract untouched | yes | 未修改 API client、backend 或 request/response shape |
| Read model / worker untouched | yes | 未修改 read model、worker、queue 或 background job |
| App Shell untouched | yes | 本专项只处理关联台内部工作区残留 MUI |
| Tri-pane core preserved | yes | `ResizableTriPane.tsx`、`CandidateGroupGrid.tsx` 当前无 MUI，专项规则要求不重写 |
| User-visible workbench behavior preserved | planned | 后续 prompt 必须先补 characterization tests，再迁移控件 |
| Prompt generated just-in-time | yes | `P-WB001` 为当前唯一执行 prompt；下一条为 `P-WB002` |
| Exact staging only | required | MG 明确禁止 `git add .` 和 `git add -A` |

## Phase Table

| Phase | Status | Started | Completed | Verification | Notes |
| --- | --- | --- | --- | --- | --- |
| `wb_phase_0_baseline` | `implemented` | 2026-06-07 | pending | `passed` | 专项 state/prompt/module 文档已创建，MUI/CSS/test/dependency 基线已记录；等待 MG push |
| `wb_phase_1_characterization` | `pending` | pending | pending | pending | 下一步：补 WorkbenchZone/PaneSearch/RecordCard 行为和 source contract 测试 |
| `wb_phase_2_zone_header_controls` | `pending` | pending | pending | pending | 迁移 `WorkbenchZone.tsx` 的 MUI controls |
| `wb_phase_3_pane_search` | `pending` | pending | pending | pending | 迁移 `WorkbenchPaneSearch.tsx` |
| `wb_phase_4_record_card_actions` | `pending` | pending | pending | pending | 迁移 `WorkbenchRecordCard.tsx` |
| `wb_phase_5_css_containment_cleanup` | `pending` | pending | pending | pending | 清理 workbench `.Mui*` CSS |
| `wb_phase_6_test_provider_cleanup` | `pending` | pending | pending | pending | 移除 `legacyWorkbenchMuiProvider` |
| `wb_phase_7_dependency_cleanup` | `pending` | pending | pending | pending | 移除无用途 MUI/Emotion 依赖 |
| `wb_phase_8_full_verification` | `pending` | pending | pending | pending | 工作台专项测试、非关联台回归、build、smoke |
| `wb_phase_9_closeout` | `pending` | pending | pending | pending | 最终 no-MUI contract、风险和 push log 收口 |

## Prompt Queue

| Prompt / MG | Phase | Type | Status | Notes |
| --- | --- | --- | --- | --- |
| `P-WB001-baseline-discovery` | `wb_phase_0_baseline` | `discovery/planning` | `verified` | 文档和基线扫描完成 |
| `MG-WB001-baseline` | `wb_phase_0_baseline` | `cumulative MG` | `pending` | 等待精确 stage、commit、push |
| `P-WB002-characterization-tests` | `wb_phase_1_characterization` | `characterization tests` | `drafted` | MG-WB001 push 后执行 |

## Verification Log

| Date | Prompt / MG | Command | Result | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-07 | `P-WB001-baseline-discovery` | `git status --short --branch` | passed | 当前分支 `refactor-ui...origin/refactor-ui`；存在本次文档变更 |
| 2026-06-07 | `P-WB001-baseline-discovery` | workbench MUI baseline scan | passed | 运行时 MUI 集中在 `WorkbenchZone.tsx`、`WorkbenchPaneSearch.tsx`、`WorkbenchRecordCard.tsx` 和 workbench CSS/test helper |
| 2026-06-07 | `P-WB001-baseline-discovery` | non-workbench runtime MUI scan | passed | `rg` 无输出，非关联台 runtime 当前无 `@mui/*` import |
| 2026-06-07 | `P-WB001-baseline-discovery` | `rg --files web/src/components/workbench web/src/test` | passed | 工作台组件/测试清单已记录到模块文档 |

## Push Log

| Date | MG | Commit | Remote | Notes |
| --- | --- | --- | --- | --- |
| pending | `MG-WB001-baseline` | pending | pending | baseline docs 等待 push |

## Next Action

执行 `MG-WB001-baseline`：检查 scope、untracked files、diff、文档验证；只精确 stage 本次文档文件；commit 并 push 到 `refactor-ui`。push 后把本文件 `wb_phase_0_baseline` 和 `MG-WB001-baseline` 标记为 verified/completed，再从远端最新 `refactor-ui` 生成并执行 `P-WB002-characterization-tests`。
