# Workbench Migration State

本文档是关联台内部工作区 MUI 迁移的专项状态机事实源。每次执行 prompt 或 cumulative MG 后必须更新。

## Current Phase

- Phase: `wb_phase_2_zone_header_controls`
- Status: `completed`
- Branch: `refactor-ui`
- Last Updated: `2026-06-07`
- Current Prompt ID: `P-WB003-zone-header-controls`
- Current MG ID: `MG-WB003-zone-header-controls`

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
| `wb_phase_0_baseline` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | 专项 state/prompt/module 文档已创建，MUI/CSS/test/dependency 基线已记录；MG-WB001 已 push |
| `wb_phase_1_characterization` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | WorkbenchZone/PaneSearch/RecordCard 行为 characterization tests 已补，MG-WB002 已 push |
| `wb_phase_2_zone_header_controls` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | `WorkbenchZone.tsx` 已迁出 MUI；MG-WB003 已 push |
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
| `MG-WB001-baseline` | `wb_phase_0_baseline` | `cumulative MG` | `verified` | 精确 stage、commit、push 完成 |
| `P-WB002-characterization-tests` | `wb_phase_1_characterization` | `characterization tests` | `verified` | Zone toolbar/toggle/search、RecordCard warning/action bubbling、source target contract 已覆盖 |
| `MG-WB002-characterization` | `wb_phase_1_characterization` | `cumulative MG` | `verified` | 精确 stage、commit、push 完成 |
| `P-WB003-zone-header-controls` | `wb_phase_2_zone_header_controls` | `extraction/refactor` | `verified` | `WorkbenchZone.tsx` MUI imports/JSX 已清理 |
| `MG-WB003-zone-header-controls` | `wb_phase_2_zone_header_controls` | `cumulative MG` | `verified` | 精确 stage、commit、push 完成 |
| `P-WB004-pane-search` | `wb_phase_3_pane_search` | `extraction/refactor` | `drafted` | MG-WB003 push 后执行 |

## Verification Log

| Date | Prompt / MG | Command | Result | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-07 | `P-WB001-baseline-discovery` | `git status --short --branch` | passed | 当前分支 `refactor-ui...origin/refactor-ui`；存在本次文档变更 |
| 2026-06-07 | `P-WB001-baseline-discovery` | workbench MUI baseline scan | passed | 运行时 MUI 集中在 `WorkbenchZone.tsx`、`WorkbenchPaneSearch.tsx`、`WorkbenchRecordCard.tsx` 和 workbench CSS/test helper |
| 2026-06-07 | `P-WB001-baseline-discovery` | non-workbench runtime MUI scan | passed | `rg` 无输出，非关联台 runtime 当前无 `@mui/*` import |
| 2026-06-07 | `P-WB001-baseline-discovery` | `rg --files web/src/components/workbench web/src/test` | passed | 工作台组件/测试清单已记录到模块文档 |
| 2026-06-07 | `MG-WB001-baseline` | `git add docs/refactor-ui/README.md docs/refactor-ui/workbench_migration_master_goal_prompt.md docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md && git commit && git push origin refactor-ui` | passed | Commit `1b2ef143` pushed to `origin/refactor-ui` |
| 2026-06-07 | `P-WB002-characterization-tests` | `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx` | passed | 2 files / 36 tests passed |
| 2026-06-07 | `P-WB002-characterization-tests` | `cd web && npx vitest run WorkbenchSelection.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx` | passed | 8 files / 118 tests passed |
| 2026-06-07 | `P-WB002-characterization-tests` | non-workbench runtime MUI scan | passed | 无 `@mui/*` import 命中 |
| 2026-06-07 | `P-WB002-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-WB002-characterization` | `git add web/src/test/WorkbenchZone.test.tsx web/src/test/WorkbenchColumns.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md && git commit && git push origin refactor-ui` | passed | Commit `2820549c` pushed to `origin/refactor-ui` |
| 2026-06-07 | `P-WB003-zone-header-controls` | scoped `WorkbenchZone.tsx` no-MUI grep | passed | No `@mui/*`, `Mui[A-Z]` or MUI JSX symbols remain in `WorkbenchZone.tsx` |
| 2026-06-07 | `P-WB003-zone-header-controls` | `cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx` | passed | 2 files / 36 tests passed |
| 2026-06-07 | `P-WB003-zone-header-controls` | `cd web && npx vitest run WorkbenchSelection.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx` | passed | 8 files / 118 tests passed |
| 2026-06-07 | `P-WB003-zone-header-controls` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P-WB003-zone-header-controls` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-WB003-zone-header-controls` | `git add web/src/components/workbench/WorkbenchZone.tsx web/src/test/WorkbenchZone.test.tsx docs/refactor-ui/workbench_migration_state.md docs/refactor-ui/workbench_migration_prompt.md docs/refactor-ui/modules/workbench_mui_migration.md && git commit && git push origin refactor-ui` | passed | Commit `048aeaf4` pushed to `origin/refactor-ui` |

## Push Log

| Date | MG | Commit | Remote | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-07 | `MG-WB001-baseline` | `1b2ef143` | `origin/refactor-ui` | baseline docs pushed |
| 2026-06-07 | `MG-WB002-characterization` | `2820549c` | `origin/refactor-ui` | characterization tests pushed |
| 2026-06-07 | `MG-WB003-zone-header-controls` | `048aeaf4` | `origin/refactor-ui` | workbench zone controls migrated |

## Next Action

从远端最新 `refactor-ui` 继续执行 `P-WB004-pane-search`。该 prompt 只迁移 `WorkbenchPaneSearch.tsx`，不处理 RecordCard、CSS cleanup、test provider 或依赖。
