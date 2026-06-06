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

### P002-phase-1-docs-and-tokens-discovery

- Phase: `phase_1_docs_and_tokens`
- Status: `verified`
- Type: `discovery/planning`
- Scope: 读取当前前端 CSS/package/Vite/test 入口和 HeroUI/Tailwind 官方事实源，建立 phase 1 token 落地边界和下一条 characterization test prompt。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、refactor_ui_prompt.md、README.md、platform_stack_migration.md、table_layout_system.md、DESIGN.md、PRODUCT.md、web/package.json、web/package-lock.json、web/vite.config.ts、web/src/main.tsx、web/src/app/styles.css、web/src/test/TableAlignmentStyles.test.ts。使用 HeroUI MCP quick-start/theming 和 Tailwind CSS 官方 Vite/theme 文档核对 React 19、Tailwind v4、HeroUI v3、CSS import、@theme inline 事实。只做 discovery/planning，不改依赖、不改前端实现、不改后端。若发现 token 落地信息需要跨切片复用，创建 docs/refactor-ui/modules/phase_1_docs_and_tokens.md。文档必须记录当前 CSS hard-code/token 问题、目标 token groups、HeroUI/Tailwind bridge、下一条 characterization tests prompt 建议和验证命令。
```

#### Review

- Single slice: yes。
- Backend untouched: yes。
- Runtime implementation untouched: yes。
- Workbench internals frozen: yes。
- Docs on demand: yes，phase 1 token 规则需要跨后续切片复用。
- Verification defined: 文档路径检查、关键规则检索、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 新增 `docs/refactor-ui/modules/phase_1_docs_and_tokens.md`。
- 记录 HeroUI MCP quick start/theming 和 Tailwind CSS v4 Vite/theme 官方事实。
- 记录当前 `web/package.json`、`web/package-lock.json`、`web/vite.config.ts`、`web/src/main.tsx`、`web/src/app/styles.css` 和 `TableAlignmentStyles.test.ts` 的 token 相关状态。
- 本切片只改文档，不修改前端实现、后端、依赖或 lockfile。

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_1_docs_and_tokens.md`
  - `rg -n "P002-phase-1-docs-and-tokens-discovery|Target Token Boundary|Required Characterization Tests|P003-phase-1-token-characterization-tests" docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/modules/phase_1_docs_and_tokens.md`
  - `git diff --check`
  - `git status --short --branch`

### P003-phase-1-token-characterization-tests

- Phase: `phase_1_docs_and_tokens`
- Status: `verified`
- Type: `characterization tests`
- Scope: 添加 token characterization tests，锁定 Ledger Calm CSS token names、HeroUI/Tailwind import order 目标和表格 token names；不修改 CSS 实现、依赖、Vite 或页面代码。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_1_docs_and_tokens.md、DESIGN.md、table_layout_system.md、platform_stack_migration.md、web/src/app/styles.css 和 web/src/test/TableAlignmentStyles.test.ts。新增 web/src/test/DesignTokens.test.ts 和 web/src/test/TableLayoutTokens.test.ts，测试读取 web/src/app/styles.css，断言 Ledger Calm CSS tokens、HeroUI/Tailwind import order、@theme inline bridge 和表格 token names 存在。只添加 characterization tests，不改 CSS 实现、不改依赖、不改 Vite、不改页面。运行新增测试，预期失败以证明测试能捕获当前缺口。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend untouched: yes。
- Runtime CSS untouched: yes。
- Dependencies untouched: yes。
- Workbench internals frozen: yes。
- Expected failure acceptable: yes，characterization tests 先暴露 token 缺口。
- Verification defined: targeted Vitest expected fail、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 新增 `web/src/test/DesignTokens.test.ts`。
- 新增 `web/src/test/TableLayoutTokens.test.ts`。
- 新增测试只读取 `web/src/app/styles.css`，不渲染页面、不触发后端。
- 新增测试当前预期失败，下一条 `P004-phase-1-token-implementation` 必须只实现 token/CSS bridge 让它们通过。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npm run test -- DesignTokens.test.ts TableLayoutTokens.test.ts`
  - `git diff --check`
  - `git status --short --branch`
  - Expected: targeted Vitest fails before P004 because CSS tokens/imports are not implemented yet.

### P004-phase-1-token-implementation

- Phase: `phase_1_docs_and_tokens`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只修改 `web/src/app/styles.css` 的 Ledger Calm token、HeroUI semantic variable bridge、Tailwind v4 `@theme inline` bridge 和表格 layout tokens，让 P003 新增测试通过。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_1_docs_and_tokens.md、DESIGN.md、table_layout_system.md、platform_stack_migration.md、web/src/app/styles.css、web/src/test/DesignTokens.test.ts 和 web/src/test/TableLayoutTokens.test.ts。只修改 web/src/app/styles.css，添加 @import "tailwindcss";、@import "@heroui/styles";、Ledger Calm CSS variables、HeroUI semantic variable overrides、Tailwind v4 @theme inline bridge 和 table layout tokens。不得修改依赖、Vite、页面实现、后端、API、read model 或 worker。运行 P003 新增测试，必须通过；记录 build 尚未运行，因为 Tailwind/HeroUI 依赖尚未在 phase_2 安装。
```

#### Review

- Single slice: yes。
- Backend untouched: yes。
- Dependencies untouched: yes。
- Vite untouched: yes。
- Page migration untouched: yes。
- Workbench internals frozen: yes。
- Verification defined: targeted token tests、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `web/src/app/styles.css` 顶部添加 Tailwind/HeroUI import order。
- `:root` 添加 `--fp-*` Ledger Calm tokens。
- `:root` 添加 HeroUI semantic variable bridge。
- `@theme inline` 添加 project token bridge。
- 添加 finance table layout tokens。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run DesignTokens.test.ts TableLayoutTokens.test.ts`
  - `git diff --check`
  - `git status --short --branch`

### P005-phase-2-platform-stack-migration

- Phase: `phase_2_platform_stack`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 升级 React 19，安装 HeroUI v3、Tailwind CSS v4 和 Vite plugin，修复 React 19/type resolution 兼容问题，并添加 HeroUI Button smoke test。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、platform_stack_migration.md、docs/refactor-ui/modules/phase_1_docs_and_tokens.md、web/package.json、web/package-lock.json、web/vite.config.ts、web/tsconfig.node.json、web/src/app/PageKeepAliveHost.tsx、web/src/pages/BankDetailsPage.tsx 和关键测试。安装 React 19、HeroUI v3、Tailwind CSS v4、@tailwindcss/vite；保守保留 Vite 5，因为 @tailwindcss/vite@4.3.0 支持 Vite 5.2+，@vitejs/plugin-react@6 需要 Vite 8。修改 Vite plugin、lockfile 和最小 React 19 类型兼容问题。添加 HeroUIPlatformSmoke.test.tsx。不得迁移业务页面，不移除 MuiProviders，不改后端/API/read model/worker。运行 build、平台 smoke、关键 shell/MUI/month tests，并记录 warnings。
```

#### Review

- Single slice: yes。
- Backend untouched: yes。
- API/read model/worker untouched: yes。
- Business pages not migrated: yes。
- Workbench internals frozen: yes。
- MUI removal deferred: yes。
- Verification defined: build、targeted Vitest、dependency tree、CSS import order、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- Installed React 19.2.7, ReactDOM 19.2.7, React types 19.x, HeroUI 3.1.0, Tailwind 4.3.0, and `@tailwindcss/vite` 4.3.0.
- Updated `react-is` direct dependency and override to 19.2.7 after npm rejected the conflicting React 18 override.
- Updated `vite.config.ts` and tracked `vite.config.js` output with Tailwind plugin.
- Updated `tsconfig.node.json` to `moduleResolution: "Bundler"` for `@tailwindcss/vite` `.d.mts` resolution.
- Updated `PageKeepAliveHost.tsx` inactive page `inert` prop to boolean.
- Updated `BankDetailsPage.tsx` DatePicker blur handlers to read the inner input from the text field wrapper.
- Added `HeroUIPlatformSmoke.test.tsx`.

#### Verification

- Status: verified。
- Commands:
  - `cd web && npm run build`
  - `cd web && npx vitest run HeroUIPlatformSmoke.test.tsx DesignTokens.test.ts TableLayoutTokens.test.ts App.test.tsx CommonMuiComponents.test.tsx MonthPicker.test.tsx`
  - `cd web && npm ls react react-dom react-is @types/react @types/react-dom @heroui/react @heroui/styles tailwindcss @tailwindcss/vite --depth=0`
  - `rg -U -n '@import "tailwindcss";\n@import "@heroui/styles";' web/src web`
  - `git diff --check`
  - `git status --short --branch`
  - Build passed with HeroUI/Tailwind generated CSS minifier warnings and existing bundle size warning.

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
| `P002-phase-1-docs-and-tokens-discovery` | `phase_1_docs_and_tokens` | token discovery | `verified` | passed | Token 边界和 P003 characterization test 建议已记录 |
| `P003-phase-1-token-characterization-tests` | `phase_1_docs_and_tokens` | token tests | `verified` | expected fail | Ledger Calm 和 table token characterization tests 已新增 |
| `P004-phase-1-token-implementation` | `phase_1_docs_and_tokens` | token implementation | `verified` | passed | CSS token bridge 已落地，P003 tests 通过 |
| `P005-phase-2-platform-stack-migration` | `phase_2_platform_stack` | platform stack | `verified` | passed | React 19、HeroUI、Tailwind v4 和 Vite plugin 已接入 |

## Next Prompt Draft Slot

下一条 prompt 应执行 `MG-P005-phase-2-platform-stack`。

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_2_platform_stack.md 和 git status。检查 scope 只包含 phase_2 platform stack 文件。运行 build、targeted Vitest、dependency tree、CSS import order、git diff --check、git status。精确 git add，不使用 git add . 或 git add -A。提交信息使用 feat: migrate ui platform stack。push 到 refactor-ui，并更新 state/prompt Push Log。
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

- Status: `verified`
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
- Status: verified。

#### Execution

- Commit: `8f3daae8`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified

### MG-P004-phase-1-docs-and-tokens

- Status: `verified`
- Scope:
  - `web/src/app/styles.css`
  - `web/src/test/DesignTokens.test.ts`
  - `web/src/test/TableLayoutTokens.test.ts`
  - `docs/refactor-ui/modules/phase_1_docs_and_tokens.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_1_docs_and_tokens.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 phase_1 docs/tokens 文件：web/src/app/styles.css、web/src/test/DesignTokens.test.ts、web/src/test/TableLayoutTokens.test.ts、docs/refactor-ui/modules/phase_1_docs_and_tokens.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run DesignTokens.test.ts TableLayoutTokens.test.ts；git diff --check；git status --short --branch。提交信息使用 feat: add ui design token bridge。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
```

#### Review

- Branch check required: yes。
- Scope precise: yes。
- Untracked check required: yes。
- Diff check required: yes。
- Exact staging required: yes。
- Push required: yes。
- Docs update after MG required: yes。
- Status: verified。

#### Execution

- Commit: `541cd8d6`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified

### MG-P005-phase-2-platform-stack

- Status: `verified`
- Scope:
  - `web/package.json`
  - `web/package-lock.json`
  - `web/vite.config.ts`
  - `web/vite.config.js`
  - `web/tsconfig.node.json`
  - `web/src/app/PageKeepAliveHost.tsx`
  - `web/src/pages/BankDetailsPage.tsx`
  - `web/src/test/HeroUIPlatformSmoke.test.tsx`
  - `docs/refactor-ui/modules/phase_2_platform_stack.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_2_platform_stack.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 phase_2 platform stack 文件：web/package.json、web/package-lock.json、web/vite.config.ts、web/vite.config.js、web/tsconfig.node.json、web/src/app/PageKeepAliveHost.tsx、web/src/pages/BankDetailsPage.tsx、web/src/test/HeroUIPlatformSmoke.test.tsx、docs/refactor-ui/modules/phase_2_platform_stack.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npm run build；cd web && npx vitest run HeroUIPlatformSmoke.test.tsx DesignTokens.test.ts TableLayoutTokens.test.ts App.test.tsx CommonMuiComponents.test.tsx MonthPicker.test.tsx；cd web && npm ls react react-dom react-is @types/react @types/react-dom @heroui/react @heroui/styles tailwindcss @tailwindcss/vite --depth=0；rg -U -n '@import "tailwindcss";\n@import "@heroui/styles";' web/src web；git diff --check；git status --short --branch。提交信息使用 feat: migrate ui platform stack。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
```

#### Review

- Branch check required: yes。
- Scope precise: yes。
- Untracked check required: yes。
- Diff check required: yes。
- Exact staging required: yes。
- Push required: yes。
- Docs update after MG required: yes。
- Status: verified。

#### Execution

- Commit: `1eecabb9`
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
