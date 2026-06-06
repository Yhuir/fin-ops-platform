# Refactor UI State

本文档是 `refactor-ui` 分支 UI 重构的状态机事实源。每次执行 prompt 或 cumulative MG 后必须更新。

## Current Phase

- Phase: `phase_0_baseline`
- Status: `completed`
- Branch: `refactor-ui`
- Last Updated: `2026-06-07`
- Current Prompt ID: `P000-docs-bootstrap`
- Current MG ID: `MG-P000-docs-bootstrap`

## Global Invariants

| Invariant | Status | Evidence |
| --- | --- | --- |
| Backend untouched | yes | 当前只修改设计/重构文档 |
| API contract untouched | yes | 当前只修改设计/重构文档 |
| Read model / worker untouched | yes | 当前只修改设计/重构文档 |
| Reconciliation workbench internals frozen | yes | 当前未改 `ReconciliationWorkbenchPage` 或 `web/src/components/workbench/*` |
| Non-workbench MUI additions | none | 当前未写实现代码 |
| User-visible actions preserved | pending | 页面迁移阶段逐页检查 |
| HeroUI MCP configured | configured-not-active | 已写入 `~/.codex/config.toml`，需重启 Codex 后 `/mcp` 验证 |

## Phase Table

| Phase | Status | Started | Completed | Verification | Notes |
| --- | --- | --- | --- | --- | --- |
| `phase_0_baseline` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | docs bootstrap MG 已 push |
| `phase_1_docs_and_tokens` | `pending` |  |  |  | PRODUCT/DESIGN 和 Tailwind token |
| `phase_2_platform_stack` | `pending` |  |  |  | React 19 + HeroUI v3 + Tailwind v4 |
| `phase_3_primitives` | `pending` |  |  |  | 本地 UI primitives |
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

- Scope: 建立 UI 重构文档工作流。
- Files touched:
  - `DESIGN.md`
  - `docs/refactor-ui/README.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`
  - `docs/refactor-ui/table_layout_system.md`
  - `docs/index.md`
- Verification run: pending
- Failures: none
- Next action: 从 `refactor-ui` 分支生成下一条 prompt，进入 `phase_1_docs_and_tokens` 或重新确认是否先处理 PRODUCT.md。

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
| platform stack | `pending` |  | React 19 + HeroUI + Tailwind |
| primitives | `pending` |  | UI primitives |
| app shell | `pending` |  | 新 shell 包住关联台 |
| table system | `pending` |  | HeroUI Table |
| page batches | `pending` |  | 后续逐模块生成 |

## Verification Log

| Date | Prompt / MG | Command | Result | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-07 | `P000-docs-bootstrap` | `find docs/refactor-ui -maxdepth 1 -type f -name '*.md' | sort` | passed | 四份文档存在 |
| 2026-06-07 | `P000-docs-bootstrap` | `rg -n "refactor-ui|HeroUI|Micro-JIT|cumulative MG" docs/refactor-ui docs/index.md DESIGN.md` | passed | 关键规则和入口存在 |
| 2026-06-07 | `P000-docs-bootstrap` | `git status --short --branch` | passed | 仅文档变更和 docs/refactor-ui 新文件 |
| 2026-06-07 | `MG-P000-docs-bootstrap` | `git push -u origin refactor-ui` | passed | `52f4520f` pushed |

## Push Log

| Date | MG | Branch | Commit | Result |
| --- | --- | --- | --- | --- |
| 2026-06-07 | `MG-P000-docs-bootstrap` | `refactor-ui` | `52f4520f` | pushed |
