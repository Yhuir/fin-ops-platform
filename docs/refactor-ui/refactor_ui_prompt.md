# Refactor UI Prompt Registry

本文档保存每一次 Micro-JIT 切片 prompt、审查记录、执行记录和 cumulative MG prompt。执行者每次只能生成一条新的 prompt，审查通过后才能执行。

## Operating Prompt

```text
/goal 在 refactor-ui 分支上，将 fin-ops-platform 的非关联台前端 UI 从 MUI 迁移到 React 19 + HeroUI v3 + Tailwind CSS v4。保留现有大布局、全部用户可见功能入口、权限语义、业务行为和用户操作体感。不改后端、API contract、read model、worker 或业务状态机。App Shell 迁移到 HeroUI + Tailwind，关联台内部工作区冻结。旧右侧抽屉必须仍是右侧抽屉，旧弹窗必须仍是弹窗，旧菜单/Popover/表格行操作/工具栏入口必须保持同类交互形态。每次只处理一个模块或一个明确切片，执行后更新 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md 和相关模块文档。
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

文档更新要求必须区分两类：

- 必须更新：`refactor_ui_state.md`、`refactor_ui_prompt.md` 和已有相关模块文档。
- 按需新建：只有当 discovery、旧入口对照、风险、测试策略或组件迁移规则需要跨切片复用时，才新建 `docs/refactor-ui/modules/<module>.md` 或其他明确命名的专项 md。若现有文档足够承载，不得为了记录临时分析而新建 md。

每条 prompt 执行前必须审查：

- 是否只处理一个模块或明确切片。
- 是否保持 Micro-JIT 顺序。
- 是否禁止后端/API/read model/worker 改动。
- 是否冻结关联台内部工作区。
- 是否保留用户可见操作入口。
- 是否保持旧 overlay 和控件形态等价，例如旧右侧抽屉仍为右侧抽屉。
- 是否有可运行的验证命令。
- 是否要求更新 state/prompt/module docs，并说明是否需要新建专项 md。

## Phase-to-Prompt Rules

- `phase_0` 到 `phase_9` 是阶段容器，每个 phase 可以包含多个执行 prompt 和多个 MG。
- 不允许一次性生成一个 phase 的全部 prompt；每次只能生成一条 prompt。
- 下一条 prompt 必须基于上一条 prompt 或 MG 的完成情况、验证结果、当前 diff、untracked files、状态机和模块文档单独分析生成。
- 如果上一条 prompt 暴露出新风险、测试缺口、范围变化或文档缺口，下一条 prompt 必须先处理这些事实。
- 只有当前 phase 必要 prompt 和 MG 都达到 `verified`，才能把 state 推进到下一 phase。

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

### P001-baseline-doc-gap-fill

- Phase: `phase_0_baseline`
- Status: `verified`
- Type: `discovery/planning`
- Scope: 补齐 UI 重构文档缺口，建立 baseline inventory、platform stack migration、test migration strategy、module inventory，并把“功能体感等价”、“右侧抽屉保持右侧抽屉”和“专项 md 按需沉淀”写入事实源。

#### Prompt

```text
阅读 codebase、docs/refactor-ui/README.md、refactor_ui_state.md、refactor_ui_prompt.md、table_layout_system.md、DESIGN.md、PRODUCT.md，以及当前前端 MUI 使用情况。补齐 docs/refactor-ui/baseline_inventory.md、platform_stack_migration.md、test_migration_strategy.md、module_inventory.md。同步更新 README、refactor_ui_state.md、refactor_ui_prompt.md、table_layout_system.md、docs/index.md、DESIGN.md、PRODUCT.md。文档必须包含 MUI 文件清单、非关联台/关联台分类、测试清单、页面清单、风险等级、React 19 + HeroUI v3 + Tailwind v4 安装/导入/provider/rollback、MUI class/theme 测试迁移策略、模块队列，以及旧右侧抽屉必须仍为右侧抽屉的硬约束。不改前端实现、不改后端、不改依赖。
```

#### Review

- Single slice: yes。
- Backend untouched: yes。
- Workbench internals frozen: yes。
- Behavior equivalence required: yes。
- Right drawer stays right drawer: yes。
- Verification defined: 文档路径检查、关键规则检索、`git diff --check`、`git status --short --branch`。
- Docs update required: yes。

#### Execution Notes

- 新增 `baseline_inventory.md`、`platform_stack_migration.md`、`test_migration_strategy.md`、`module_inventory.md`。
- 新增 `refactor_ui_master_goal_prompt.md`，保存可直接交给 Codex 的端到端 `/goal` 主控指令。
- 更新 `README.md`、`table_layout_system.md`、`DESIGN.md`、`PRODUCT.md`、`docs/index.md`。
- 补充重构理念和文档沉淀规则：需要跨切片复用时才新建专项 md，一次性分析不单独落盘。
- 补充完整重构路径：从 `MG-P001-baseline-doc-gap-fill` 到 `phase_9_closeout`，并要求不得跳过平台栈、primitives 或表格系统直接迁页面。
- 补充 phase-to-prompt 规则：每个 phase 可包含多个 prompt，下一条 prompt 必须由上一条完成情况、验证结果和状态机现场生成。
- 本切片只改文档，不修改前端实现、后端、依赖或 lockfile。

#### Verification

- Status: verified。
- Commands:
  - `find docs/refactor-ui -maxdepth 1 -type f -name '*.md' | sort`
  - `rg -n "baseline_inventory|platform_stack_migration|test_migration_strategy|module_inventory|右侧抽屉|行为等价|Behavioral Equivalence" docs/refactor-ui docs/index.md DESIGN.md PRODUCT.md`
  - `rg -n "重构理念|文档沉淀规则|按需新建|Module docs on demand|modules/<module>|不为一次性临时分析新建 md" docs/refactor-ui docs/index.md DESIGN.md PRODUCT.md`
  - `rg -n "完整重构路径|MG-P001-baseline-doc-gap-fill|phase_1_docs_and_tokens|phase_9_closeout|不得跳过平台栈" docs/refactor-ui/README.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
  - `rg -n "Phase 与 Prompt 关系|Phase-to-Prompt Rules|每个 phase 可以包含多个|上一条 prompt|单独分析生成" docs/refactor-ui/README.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/module_inventory.md docs/refactor-ui/refactor_ui_state.md`
  - `rg -n "/goal|完整执行 fin-ops-platform 非关联台 UI 平台迁移计划|最终完成条件|每次最终回复或阶段记录必须包含" docs/refactor-ui/refactor_ui_master_goal_prompt.md`
  - `git diff --check`
  - `git status --short --branch`

## Prompt History

| Prompt ID | Phase | Slice | Status | Verification | Notes |
| --- | --- | --- | --- | --- | --- |
| `P000-docs-bootstrap` | `phase_0_baseline` | docs bootstrap | `verified` | passed | 文档切片已验证 |
| `P001-baseline-doc-gap-fill` | `phase_0_baseline` | docs gap fill | `verified` | passed | 基线、平台栈、测试策略、模块队列、文档沉淀规则、完整重构路径、phase-to-prompt 规则、主控 goal prompt 已补齐 |

## Next Prompt Draft Slot

下一条实现 prompt 必须在 `MG-P001-baseline-doc-gap-fill` 执行并 push 后生成。若用户只要求继续本地规划，可先生成 `phase_1_docs_and_tokens` 的 discovery prompt，但必须明确 MG 尚未 push。

```text
未生成。执行者必须先读取 refactor_ui_state.md，确认 P001 verified，并决定是否先执行 MG-P001-baseline-doc-gap-fill。
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

### MG-P001-baseline-doc-gap-fill

- Status: `reviewed-not-executed`
- Scope:
  - `PRODUCT.md`
  - `DESIGN.md`
  - `docs/index.md`
  - `docs/refactor-ui/README.md`
  - `docs/refactor-ui/baseline_inventory.md`
  - `docs/refactor-ui/platform_stack_migration.md`
  - `docs/refactor-ui/test_migration_strategy.md`
  - `docs/refactor-ui/module_inventory.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`
  - `docs/refactor-ui/refactor_ui_master_goal_prompt.md`
  - `docs/refactor-ui/table_layout_system.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、baseline_inventory.md、platform_stack_migration.md、test_migration_strategy.md、module_inventory.md、refactor_ui_master_goal_prompt.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试/验证结果和文档状态。确认 scope 只包含 PRODUCT.md、DESIGN.md、docs/index.md 和 docs/refactor-ui/*.md。禁止 git add . 和 git add -A。只允许精确 git add PRODUCT.md DESIGN.md docs/index.md docs/refactor-ui/README.md docs/refactor-ui/baseline_inventory.md docs/refactor-ui/platform_stack_migration.md docs/refactor-ui/test_migration_strategy.md docs/refactor-ui/module_inventory.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md docs/refactor-ui/refactor_ui_master_goal_prompt.md docs/refactor-ui/table_layout_system.md。提交信息使用 docs: complete ui refactor baseline。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
```

#### Review

- Branch check required: yes。
- Scope precise: yes。
- Untracked check required: yes。
- Diff check required: yes。
- Exact staging required: yes。
- Push required: yes。
- Docs update after MG required: yes。
- Status: reviewed, not executed in P001 documentation slice。

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
