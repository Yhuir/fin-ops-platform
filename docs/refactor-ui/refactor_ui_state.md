# Refactor UI State

本文档是 `refactor-ui` 分支 UI 重构的状态机事实源。每次执行 prompt 或 cumulative MG 后必须更新。

## Current Phase

- Phase: `phase_3_primitives`
- Status: `in_progress`
- Branch: `refactor-ui`
- Last Updated: `2026-06-07`
- Current Prompt ID: `P006-phase-3-state-permission-primitives`
- Current MG ID: `MG-P006-phase-3-state-permission-primitives`

## Global Invariants

| Invariant | Status | Evidence |
| --- | --- | --- |
| Backend untouched | yes | 当前只修改设计/重构文档 |
| API contract untouched | yes | 当前只修改设计/重构文档 |
| Read model / worker untouched | yes | 当前只修改设计/重构文档 |
| Reconciliation workbench internals frozen | yes | 当前未改 `ReconciliationWorkbenchPage` 或 `web/src/components/workbench/*` |
| Non-workbench MUI additions | none | 当前未写实现代码 |
| User-visible actions preserved | documented | `baseline_inventory.md`、`module_inventory.md` 已要求逐页检查 |
| Behavior equivalence | documented | 旧右侧抽屉仍为右侧抽屉，旧弹窗仍为弹窗 |
| HeroUI MCP active | yes | 当前会话已调用 HeroUI MCP quick start、theming、Table/Drawer/Modal docs |
| Module docs on demand | documented | 只有需要跨切片复用的 discovery、旧入口对照、风险或测试策略才新建专项 md |
| Phase prompts generated just-in-time | documented | 每个 phase 可包含多个 prompt；下一条 prompt 由上一条完成情况、验证结果和状态机现场生成 |

## Phase Table

| Phase | Status | Started | Completed | Verification | Notes |
| --- | --- | --- | --- | --- | --- |
| `phase_0_baseline` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | baseline/platform/test/module 文档、文档沉淀规则、完整重构路径和 phase-to-prompt 规则已补齐；MG-P001 已 push |
| `phase_1_docs_and_tokens` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | MG-P004 已 push |
| `phase_2_platform_stack` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | MG-P005 已 push |
| `phase_3_primitives` | `in_progress` | 2026-06-07 |  | `partial-passed` | P006 StatePanel/PermissionNotice verified，MG-P006 已 push |
| `phase_4_shell` | `pending` |  |  |  | App Shell 迁移 |
| `phase_5_table_system` | `pending` |  |  |  | HeroUI Table 和表格排版 |
| `phase_6_page_batches` | `pending` |  |  |  | 非关联台页面模块迁移 |
| `phase_7_mui_containment` | `pending` |  |  |  | 非关联台无 MUI，关联台隔离 |
| `phase_8_full_verification` | `pending` |  |  |  | 全量验证 |
| `phase_9_closeout` | `pending` |  |  |  | 文档收口和后续计划 |

## Status Values

- `pending`: 未开始。
- `in_progress`: 正在执行。
- `implemented`: prompt 已执行完，等待验证记录。
- `verifying`: 正在验证。
- `verified`: 验证通过，执行者可自行标记。
- `blocked`: 需要用户决策或连续失败。
- `completed`: 阶段完成。
- `deferred`: 明确延期，例如关联台内部工作区。

## Active Checkpoint

- Scope: phase 3 shared state and permission primitives。
- Files touched:
  - `web/src/components/common/StatePanel.tsx`
  - `web/src/components/common/PermissionNotice.tsx`
  - `web/src/test/CommonMuiComponents.test.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`
  - `docs/refactor-ui/modules/phase_3_primitives.md`
- Verification run: passed
- Failures: none
- Next action: 从 `refactor-ui` 生成下一条 `phase_3_primitives` prompt。

## Prompt Lifecycle

1. `drafted`: 根据状态机生成一条 prompt。
2. `reviewed`: 审查 prompt 的范围、边界、验证、文档更新要求。
3. `approved_for_execution`: prompt 可执行。
4. `implemented`: prompt 已执行。
5. `verified`: 验证通过，状态机和 prompt 文档已更新。
6. `blocked`: prompt 需要用户决策、依赖问题或验证失败。

## Merge Gate Lifecycle

1. `mg_drafted`: 达到可合并边界后生成 MG prompt。
2. `mg_reviewed`: 检查 scope、diff、untracked files、测试和文档状态。
3. `mg_executed`: 精确 staging、必要 commit、push。
4. `mg_verified`: push 完成，远端分支更新。
5. `mg_blocked`: MG 未通过，记录原因。

## Module Queue

按实际执行时的 discovery 结果更新，不预先并行推进。

| Module / Slice | Status | Current Prompt | Notes |
| --- | --- | --- | --- |
| docs bootstrap | `verified` | `P000-docs-bootstrap` | 建立工作流文档 |
| baseline docs gap fill | `verified` | `P001-baseline-doc-gap-fill` | 基线、平台栈、测试策略、模块队列补齐 |
| docs and tokens | `verified` | `P004-phase-1-token-implementation` | Token implementation 和 MG-P004 已完成 |
| platform stack | `verified` | `P005-phase-2-platform-stack-migration` | Build、targeted tests 和 MG-P005 已完成 |
| primitives | `in_progress` | `P006-phase-3-state-permission-primitives` | StatePanel/PermissionNotice verified，MG-P006 已 push |
| app shell | `pending` |  | 新 shell 包住关联台 |
| table system | `pending` |  | HeroUI Table |
| page batches | `pending` |  | 详见 `module_inventory.md` |

## Verification Log

| Date | Prompt / MG | Command | Result | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-07 | `P000-docs-bootstrap` | `find docs/refactor-ui -maxdepth 1 -type f -name '*.md' | sort` | passed | 四份文档存在 |
| 2026-06-07 | `P000-docs-bootstrap` | `rg -n "refactor-ui|HeroUI|Micro-JIT|cumulative MG" docs/refactor-ui docs/index.md DESIGN.md` | passed | 关键规则和入口存在 |
| 2026-06-07 | `P000-docs-bootstrap` | `git status --short --branch` | passed | 仅文档变更和 docs/refactor-ui 新文件 |
| 2026-06-07 | `MG-P000-docs-bootstrap` | `git push -u origin refactor-ui` | passed | `52f4520f` pushed |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `find docs/refactor-ui -maxdepth 1 -type f -name '*.md' | sort` | passed | 八份 refactor-ui 文档存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "baseline_inventory|platform_stack_migration|test_migration_strategy|module_inventory|右侧抽屉|行为等价|Behavioral Equivalence" docs/refactor-ui docs/index.md DESIGN.md PRODUCT.md` | passed | 新事实源和行为等价规则存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "重构理念|文档沉淀规则|按需新建|Module docs on demand|modules/<module>|不为一次性临时分析新建 md" docs/refactor-ui docs/index.md DESIGN.md PRODUCT.md` | passed | 重构理念和按需新建专项 md 规则存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "完整重构路径|MG-P001-baseline-doc-gap-fill|phase_1_docs_and_tokens|phase_9_closeout|不得跳过平台栈" docs/refactor-ui/README.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | 完整重构路径存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "Phase 与 Prompt 关系|Phase-to-Prompt Rules|每个 phase 可以包含多个|上一条 prompt|单独分析生成" docs/refactor-ui/README.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/module_inventory.md docs/refactor-ui/refactor_ui_state.md` | passed | phase-to-prompt 规则存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "/goal|完整执行 fin-ops-platform 非关联台 UI 平台迁移计划|最终完成条件|每次最终回复或阶段记录必须包含" docs/refactor-ui/refactor_ui_master_goal_prompt.md` | passed | 主控 goal prompt 存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `git status --short --branch` | passed | 仅文档变更 |
| 2026-06-07 | `MG-P001-baseline-doc-gap-fill` | `git push origin refactor-ui` | passed | `8f3daae8` pushed |
| 2026-06-07 | `P002-phase-1-docs-and-tokens-discovery` | `test -f docs/refactor-ui/modules/phase_1_docs_and_tokens.md` | passed | phase 1 token discovery doc exists |
| 2026-06-07 | `P002-phase-1-docs-and-tokens-discovery` | `rg -n "P002-phase-1-docs-and-tokens-discovery|Target Token Boundary|Required Characterization Tests|P003-phase-1-token-characterization-tests" docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/modules/phase_1_docs_and_tokens.md` | passed | token discovery and next prompt recommendation exist |
| 2026-06-07 | `P003-phase-1-token-characterization-tests` | `cd web && npm run test -- DesignTokens.test.ts TableLayoutTokens.test.ts` | expected-fail | Token/import CSS not implemented before P004 |
| 2026-06-07 | `P004-phase-1-token-implementation` | `cd web && npx vitest run DesignTokens.test.ts TableLayoutTokens.test.ts` | passed | CSS token bridge tests pass |
| 2026-06-07 | `MG-P004-phase-1-docs-and-tokens` | `git push origin refactor-ui` | passed | `541cd8d6` pushed |
| 2026-06-07 | `P005-phase-2-platform-stack-migration` | `cd web && npm run build` | passed | Build passed with generated CSS minifier warnings and bundle size warning |
| 2026-06-07 | `P005-phase-2-platform-stack-migration` | `cd web && npx vitest run HeroUIPlatformSmoke.test.tsx DesignTokens.test.ts TableLayoutTokens.test.ts App.test.tsx CommonMuiComponents.test.tsx MonthPicker.test.tsx` | passed | 26 tests passed |
| 2026-06-07 | `P005-phase-2-platform-stack-migration` | `cd web && npm ls react react-dom react-is @types/react @types/react-dom @heroui/react @heroui/styles tailwindcss @tailwindcss/vite --depth=0` | passed | Target versions installed |
| 2026-06-07 | `P005-phase-2-platform-stack-migration` | `rg -U -n '@import "tailwindcss";\n@import "@heroui/styles";' web/src web` | passed | CSS import order exists |
| 2026-06-07 | `MG-P005-phase-2-platform-stack` | `git push origin refactor-ui` | passed | `1eecabb9` pushed |
| 2026-06-07 | `P006-phase-3-state-permission-primitives` | `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 6 tests passed |
| 2026-06-07 | `P006-phase-3-state-permission-primitives` | `cd web && npm run build` | passed | Build passed with known generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P006-phase-3-state-permission-primitives` | `rg -n '@mui/' web/src/components/common/StatePanel.tsx web/src/components/common/PermissionNotice.tsx` | passed | No matches; command exits 1 when no MUI import exists |
| 2026-06-07 | `P006-phase-3-state-permission-primitives` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P006-phase-3-state-permission-primitives` | `git push origin refactor-ui` | passed | `ca962587` pushed |

## Push Log

| Date | MG | Branch | Commit | Result |
| --- | --- | --- | --- | --- |
| 2026-06-07 | `MG-P000-docs-bootstrap` | `refactor-ui` | `52f4520f` | pushed |
| 2026-06-07 | `MG-P001-baseline-doc-gap-fill` | `refactor-ui` | `8f3daae8` | pushed |
| 2026-06-07 | `MG-P004-phase-1-docs-and-tokens` | `refactor-ui` | `541cd8d6` | pushed |
| 2026-06-07 | `MG-P005-phase-2-platform-stack` | `refactor-ui` | `1eecabb9` | pushed |
| 2026-06-07 | `MG-P006-phase-3-state-permission-primitives` | `refactor-ui` | `ca962587` | pushed |
