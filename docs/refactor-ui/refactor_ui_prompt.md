# Refactor UI Prompt Registry

本文档保存每一次 Micro-JIT 切片 prompt、审查记录、执行记录和 cumulative MG prompt。执行者每次只能生成一条新的 prompt，审查通过后才能执行。

## Operating Prompt

```text
/goal 在 refactor-ui 分支上，将 fin-ops-platform 的非关联台前端 UI 从 MUI 迁移到 React 19 + HeroUI v3 + Tailwind CSS v4。保留现有大布局、全部用户可见功能入口、权限语义和业务行为。不改后端、API contract、read model、worker 或业务状态机。App Shell 迁移到 HeroUI + Tailwind，关联台内部工作区冻结。每次只处理一个模块或一个明确切片，执行后更新 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md 和相关模块文档。
```

## Global Prompt Rules

每条 prompt 必须包含：

- Prompt ID。
- 所属 phase。
- 单一模块或单一切片范围。
- 必读文档。
- 必读代码和测试。
- 明确非目标。
- 具体实施任务。
- 验证命令。
- 文档更新要求。
- 完成后状态更新要求。

每条 prompt 执行前必须审查：

- 是否只处理一个模块或明确切片。
- 是否保持 Micro-JIT 顺序。
- 是否禁止后端/API/read model/worker 改动。
- 是否冻结关联台内部工作区。
- 是否保留用户可见操作入口。
- 是否有可运行的验证命令。
- 是否要求更新 state/prompt/module docs。

## Micro-JIT Sequence

同一模块内 prompt 必须按顺序推进：

1. `discovery/planning`: 读取文档、当前模块专项文档、相关代码和测试，列出用户可见功能入口、风险和迁移切片。
2. `characterization tests`: 添加或更新特征测试，锁定旧行为和入口。
3. `extraction/refactor`: 抽取或迁移当前切片实现。
4. `verification`: 运行本切片验证并更新文档。
5. `cumulative MG`: 到达可合并边界后执行 MG。

不得跳过 characterization tests，除非该切片纯文档或纯配置，且必须在 prompt 中说明原因。

## Current Prompt

### P000-docs-bootstrap

- Phase: `phase_0_baseline`
- Status: `verified`
- Type: `discovery/planning`
- Scope: 建立 `docs/refactor-ui/` 文档入口、状态机、prompt 注册表和表格排版系统文档。

#### Prompt

```text
读取 AGENTS.md、README.md、docs/index.md、DESIGN.md 和当前 UI 重构对话结论。在 refactor-ui 分支上创建 docs/refactor-ui/README.md、refactor_ui_state.md、refactor_ui_prompt.md、table_layout_system.md，并更新 docs/index.md 文档地图。文档必须写明 React 19 + HeroUI v3 + Tailwind CSS v4、非关联台迁出 MUI、关联台内部冻结、MUI 短期仅供关联台内部使用、HeroUI Table 足够且不引入 TanStack、Micro-JIT 切片 prompt 工作流、cumulative MG 流程、精确 git add 规则、每次执行后更新 state/prompt/module docs 的要求。
```

#### Review

- Single slice: yes。
- Backend untouched: yes。
- Workbench internals frozen: yes。
- Verification defined: 文档路径检查、`git status --short --branch`。
- Docs update required: yes。

#### Execution Notes

- `DESIGN.md` 已重写为 Ledger Calm 设计系统。
- `docs/refactor-ui/` 文档正在创建。
- HeroUI MCP 已写入 `~/.codex/config.toml`，当前会话未 active，需要重启 Codex 后 `/mcp` 验证。

#### Verification

- Status: verified。
- Commands:
  - `find docs/refactor-ui -maxdepth 1 -type f -name '*.md' | sort`
  - `rg -n "refactor-ui|HeroUI|Micro-JIT|cumulative MG" docs/refactor-ui docs/index.md DESIGN.md`
  - `git status --short --branch`

## Prompt History

| Prompt ID | Phase | Slice | Status | Verification | Notes |
| --- | --- | --- | --- | --- | --- |
| `P000-docs-bootstrap` | `phase_0_baseline` | docs bootstrap | `verified` | passed | 文档切片已验证 |

## Next Prompt Draft Slot

下一条 prompt 必须在 `MG-P000-docs-bootstrap` verified 并 push 后生成。

```text
未生成。执行者必须先读取 refactor_ui_state.md，确认当前 prompt verified，再生成下一条 prompt。
```

## Cumulative MG Prompts

当前到达 docs bootstrap MG 边界。

### MG-P000-docs-bootstrap

- Status: `verified`
- Scope:
  - `DESIGN.md`
  - `docs/index.md`
  - `docs/refactor-ui/README.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`
  - `docs/refactor-ui/table_layout_system.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试和文档状态。确认 scope 只包含 DESIGN.md、docs/index.md 和 docs/refactor-ui/*.md。禁止 git add . 和 git add -A。只允许精确 git add DESIGN.md docs/index.md docs/refactor-ui/README.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md docs/refactor-ui/table_layout_system.md。提交信息使用 docs: add ui refactor workflow。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
```

#### Review

- Branch check required: yes。
- Scope precise: yes。
- Untracked check required: yes。
- Diff check required: yes。
- Exact staging required: yes。
- Push required: yes。
- Docs update after MG required: yes。

#### Execution

- Commit: `52f4520f`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified

### MG Prompt Template

```text
Prompt ID: MG-<phase-or-module>
Scope: <只包含已完成并验证的切片>

读取 refactor_ui_state.md、refactor_ui_prompt.md、相关模块文档和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含本 MG 允许的文件。禁止 git add . 和 git add -A。只允许精确 git add <file...>。如需要提交，commit message 必须描述本 MG 范围。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
```

## Final Response Template

每次 prompt 或 MG 执行后的回复必须包含：

- 完成了什么。
- 修改了哪些文档或模块。
- 验证命令和结果。
- 是否 push。
- 下一步是什么。
