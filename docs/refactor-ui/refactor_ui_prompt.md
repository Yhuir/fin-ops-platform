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

### P006-phase-3-state-permission-primitives

- Phase: `phase_3_primitives`
- Status: `approved_for_execution`
- Type: `characterization tests -> extraction/refactor`
- Scope: 只迁移 `StatePanel` 与 `PermissionNotice` 两个公共提示 primitive，从 MUI Alert/Progress/Spinner/Lock icon 迁到 HeroUI Alert/Spinner/ProgressBar + Tailwind token classes。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md、DESIGN.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/common/StatePanel.tsx、web/src/components/common/PermissionNotice.tsx、web/src/test/CommonMuiComponents.test.tsx 和相关使用点。使用 HeroUI MCP Alert、Spinner、ProgressBar docs 核对 API。只处理 StatePanel 与 PermissionNotice，不迁移 AppDialog、ConfirmActionDialog、AppDrawer、FileDropzone、App Shell 或业务页面。先把 CommonMuiComponents.test.tsx 中 StatePanel 测试改为用户可观察语义断言，并增加 PermissionNotice 行为断言；再把 StatePanel/PermissionNotice 实现迁到 HeroUI + Tailwind token classes。保留 tone/title/children/compact 契约，保留 loading=status、error=alert、非 error=status、loading indicator 和非 compact progressbar 语义。不得改后端/API/read model/worker，不得改关联台内部工作区。运行 targeted tests、build、MUI import grep、diff check 和 git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Business pages untouched: yes。
- Overlay shape not involved: yes。
- User-visible contract preserved: yes，锁定 `tone/title/children/compact`、roles、loading indicator 和 progressbar。
- Characterization tests required: yes，改为行为/语义断言，避免 MUI class/theme 断言。
- Verification defined: targeted Vitest、build、MUI import grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `StatePanel` 已从 MUI Alert/CircularProgress/LinearProgress/Typography/Box/Stack 迁到 HeroUI Alert/Spinner/ProgressBar + token classes。
- `PermissionNotice` 已从 MUI Alert/Lock icon 迁到 HeroUI Alert + token classes。
- `CommonMuiComponents.test.tsx` 已增加 loading indicator、compact loading、permission notice 行为断言。
- `web/src/app/styles.css` 已添加 `finance-state-panel*` primitive token classes。
- 未迁移 AppDialog、ConfirmActionDialog、AppDrawer、FileDropzone、App Shell 或业务页面。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `rg -n '@mui/' web/src/components/common/StatePanel.tsx web/src/components/common/PermissionNotice.tsx`
  - `git diff --check`
  - `git status --short --branch`

### MG-P006-phase-3-state-permission-primitives

- Status: `verified`
- Scope:
  - `web/src/components/common/StatePanel.tsx`
  - `web/src/components/common/PermissionNotice.tsx`
  - `web/src/test/CommonMuiComponents.test.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/modules/phase_3_primitives.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P006 state/permission primitive 文件：web/src/components/common/StatePanel.tsx、web/src/components/common/PermissionNotice.tsx、web/src/test/CommonMuiComponents.test.tsx、web/src/app/styles.css、docs/refactor-ui/modules/phase_3_primitives.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；rg -n '@mui/' web/src/components/common/StatePanel.tsx web/src/components/common/PermissionNotice.tsx；git diff --check；git status --short --branch。提交信息使用 feat: migrate state notice primitives。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `ca962587`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified

### P007-phase-3-dialog-primitives

- Phase: `phase_3_primitives`
- Status: `approved_for_execution`
- Type: `characterization tests -> extraction/refactor`
- Scope: 只迁移 `AppDialog` 与 `ConfirmActionDialog` 两个共享弹窗 primitive，从 MUI Dialog/Button 迁到 HeroUI Modal/Button + Tailwind token classes。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md、DESIGN.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/common/AppDialog.tsx、web/src/components/common/ConfirmActionDialog.tsx、web/src/test/CommonMuiComponents.test.tsx 和 `rg -n "AppDialog|ConfirmActionDialog" web/src --glob '!components/workbench/**'` 的使用点。使用 HeroUI MCP Modal/Button docs 和本地 d.ts 核对 controlled modal、dismiss、keyboard dismiss 和 button API。只处理 AppDialog 与 ConfirmActionDialog，不迁移 AppDrawer、FileDropzone、PageScaffold、PageToolbar、App Shell 或业务页面。先增加/调整 CommonMuiComponents.test.tsx 中共享弹窗的用户可观察行为断言：dialog accessible name/description、actions 位置、默认 Esc 关闭、disableEscapeClose 阻止 Esc、confirm/cancel/loading/destructive 行为。再把 AppDialog/ConfirmActionDialog 实现迁到 HeroUI Modal/Button + token classes。保留 open/title/description/children/actions/maxWidth/disableEscapeClose/onClose 契约；旧弹窗仍是居中 modal，不新增可见关闭按钮。不得改后端/API/read model/worker，不得改关联台内部工作区。运行 targeted tests、build、MUI import grep、diff check 和 git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Business pages untouched: yes。
- Overlay shape preserved: yes，旧弹窗仍为居中 modal dialog。
- User-visible contract preserved: yes，保留 `open/title/description/children/actions/maxWidth/disableEscapeClose/onClose` 和确认弹窗按钮行为。
- Characterization tests required: yes，断言 dialog roles/name/description、Esc close、disableEscapeClose、confirm/cancel/loading。
- Verification defined: targeted Vitest、build、MUI import grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `AppDialog` 已从 MUI Dialog/DialogTitle/DialogContent/DialogActions 迁到 HeroUI controlled Modal + token classes。
- `ConfirmActionDialog` 已从 MUI Button 迁到 HeroUI Button。
- 未迁移 ETC 页面内传入 `AppDialog.actions` 的业务按钮；页面批次迁移时处理。
- 未迁移 AppDrawer、FileDropzone、PageScaffold、PageToolbar、App Shell 或业务页面。
- Build 首次失败于 `sizeFromMaxWidth` 参数类型包含 `undefined`；已收紧为 `NonNullable<AppDialogProps["maxWidth"]>` 后通过。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/' web/src/components/common/AppDialog.tsx web/src/components/common/ConfirmActionDialog.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
  - `git status --short --branch`

### MG-P007-phase-3-dialog-primitives

- Status: `verified`
- Scope:
  - `web/src/components/common/AppDialog.tsx`
  - `web/src/components/common/ConfirmActionDialog.tsx`
  - `web/src/test/CommonMuiComponents.test.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/modules/phase_3_primitives.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P007 dialog primitive 文件：web/src/components/common/AppDialog.tsx、web/src/components/common/ConfirmActionDialog.tsx、web/src/test/CommonMuiComponents.test.tsx、web/src/app/styles.css、docs/refactor-ui/modules/phase_3_primitives.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/' web/src/components/common/AppDialog.tsx web/src/components/common/ConfirmActionDialog.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate dialog primitives。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `32841902`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified

### P008-phase-3-app-drawer-primitive

- Phase: `phase_3_primitives`
- Status: `approved_for_execution`
- Type: `characterization tests -> extraction/refactor`
- Scope: 只迁移 `AppDrawer` 共享右侧抽屉 primitive，从 MUI Drawer/IconButton/Typography/Stack/Close icon 迁到 HeroUI Drawer/Button + Tailwind token classes。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md、DESIGN.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/common/AppDrawer.tsx、web/src/test/CommonMuiComponents.test.tsx 和 `rg -n "AppDrawer" web/src --glob '!components/workbench/**'` 的使用点。使用 HeroUI MCP Drawer/Button docs 核对 controlled drawer、placement、dismiss 和 close button API。只处理 AppDrawer，不迁移 FileDropzone、PageScaffold、PageToolbar、App Shell 或业务页面。先增加 CommonMuiComponents.test.tsx 中 AppDrawer 的用户可观察行为断言：dialog accessible name、right placement、body/footer 渲染、关闭按钮触发 onClose。再把 AppDrawer 实现迁到 HeroUI Drawer/Button + token classes。保留 open/title/children/footer/width/onClose 契约；旧右侧抽屉必须仍为右侧抽屉。不得改后端/API/read model/worker，不得改关联台内部工作区。运行 targeted tests、build、MUI import grep、diff check 和 git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Business pages untouched: yes。
- Overlay shape preserved: yes，旧右侧抽屉仍为右侧抽屉。
- User-visible contract preserved: yes，保留 `open/title/children/footer/width/onClose`、关闭按钮和 body/footer。
- Characterization tests required: yes，断言 dialog name、right placement、body/footer、close button。
- Verification defined: targeted Vitest、build、MUI import grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `AppDrawer` 已从 MUI Drawer/IconButton/Typography/Stack/Close icon 迁到 HeroUI Drawer/Button + token classes。
- `Drawer.Content` 固定 `placement="right"`，保持旧右侧抽屉形态。
- 关闭按钮 accessible name 仍为 `关闭抽屉`。
- Build 首次失败于 `Drawer.Content` 不接受 `style`；已将动态宽度 CSS variable 移到 `Drawer.Dialog` 后通过。
- 未迁移 FileDropzone、PageScaffold、PageToolbar、App Shell 或业务页面。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/' web/src/components/common/AppDrawer.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
  - `git status --short --branch`

### MG-P008-phase-3-app-drawer-primitive

- Status: `verified`
- Scope:
  - `web/src/components/common/AppDrawer.tsx`
  - `web/src/test/CommonMuiComponents.test.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/modules/phase_3_primitives.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P008 AppDrawer primitive 文件：web/src/components/common/AppDrawer.tsx、web/src/test/CommonMuiComponents.test.tsx、web/src/app/styles.css、docs/refactor-ui/modules/phase_3_primitives.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/' web/src/components/common/AppDrawer.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate drawer primitive。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `1416b69a`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified

### P009-phase-3-file-dropzone-primitive

- Phase: `phase_3_primitives`
- Status: `approved_for_execution`
- Type: `characterization tests -> extraction/refactor`
- Scope: 只迁移 `FileDropzone` 共享上传 primitive，从 MUI icon/Box/Button/FormHelperText/Stack/Typography 迁到 HeroUI Button + Tailwind token classes，并迁移相关测试里的旧 `.mui-file-dropzone` class 断言。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md、DESIGN.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/common/FileDropzone.tsx、web/src/test/CommonMuiComponents.test.tsx、web/src/test/TaxOffsetPage.test.tsx 和 `rg -n "FileDropzone|mui-file-dropzone" web/src --glob '!components/workbench/**'` 的使用点。只处理 FileDropzone 和相关测试，不迁移 PageScaffold、PageToolbar、App Shell 或业务页面。保留 label/helperText/errorText/accept/multiple/disabled/onFiles 契约，保留 root role=button、aria-label、drop、Enter/Space、hidden input、helper/error 文案。把 FileDropzone 实现迁到 HeroUI Button + token classes，移除 @mui/* import 和 `.mui-file-dropzone` 命名。更新 CommonMuiComponents.test.tsx 和 TaxOffsetPage.test.tsx 的用户可观察行为/新 token class 断言。不得改后端/API/read model/worker，不得改关联台内部工作区。运行 targeted tests、build、MUI/class grep、diff check 和 git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Business pages untouched: yes。
- User-visible contract preserved: yes，保留 upload/drop/key/input/helper/error 行为。
- Characterization tests required: yes，迁移旧 MUI class 断言。
- Verification defined: targeted Vitest、build、MUI/class grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `FileDropzone` 已从 MUI icon/Box/Button/FormHelperText/Stack/Typography 迁到 HeroUI Button + token classes。
- `.mui-file-dropzone` 已替换为 `.finance-file-dropzone`。
- `TaxOffsetPage.test.tsx` 已迁移旧 class 断言。
- 初次 targeted tests 通过但 HeroUI 报告 custom `Button render` 返回 `span` 的语义警告；已改为原生 HeroUI Button 后复测通过。
- 未迁移 PageScaffold、PageToolbar、App Shell 或业务页面。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run CommonMuiComponents.test.tsx TaxOffsetPage.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/|mui-file-dropzone' web/src/components/common/FileDropzone.tsx web/src/test/TaxOffsetPage.test.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`
  - `git diff --check`
  - `git status --short --branch`

### MG-P009-phase-3-file-dropzone-primitive

- Status: `verified`
- Scope:
  - `web/src/components/common/FileDropzone.tsx`
  - `web/src/test/TaxOffsetPage.test.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/modules/phase_3_primitives.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P009 FileDropzone primitive 文件：web/src/components/common/FileDropzone.tsx、web/src/test/TaxOffsetPage.test.tsx、web/src/app/styles.css、docs/refactor-ui/modules/phase_3_primitives.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run CommonMuiComponents.test.tsx TaxOffsetPage.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/|mui-file-dropzone' web/src/components/common/FileDropzone.tsx web/src/test/TaxOffsetPage.test.tsx web/src/app/styles.css; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate file dropzone primitive。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `baba332d`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### P010-phase-3-page-layout-primitives

- Phase: `phase_3_primitives`
- Status: `approved_for_execution`
- Type: `characterization tests -> extraction/refactor`
- Scope: 只迁移 `PageScaffold` 与 `PageToolbar` layout primitives，从 MUI Box/Stack/Typography 迁到 semantic HTML + existing CSS classes。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md、DESIGN.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/test/CommonMuiComponents.test.tsx 和 `rg -n "PageScaffold|PageToolbar" web/src --glob '!components/workbench/**'` 的使用点。只处理 PageScaffold 和 PageToolbar，不迁移 App Shell、业务页面或 tax/import 子组件。增加 CommonMuiComponents.test.tsx 中 page scaffold/toolbar 的用户可观察行为断言：h1、description、actions、children、left/right/children fallback。再把实现迁到 semantic HTML + existing CSS classes。保留 title/description/actions/children/className、left/right/children/className 契约。不得改后端/API/read model/worker，不得改关联台内部工作区。运行 targeted tests、build、MUI grep、diff check 和 git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Business pages untouched: yes。
- User-visible contract preserved: yes，保留 heading、description/actions/children 和 toolbar left/right。
- Verification defined: targeted Vitest、build、MUI grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `PageScaffold` 已从 MUI Box/Stack/Typography 迁到 semantic HTML + existing classes。
- `PageToolbar` 已从 MUI Stack 迁到 semantic HTML + toolbar classes。
- `web/src/components/common` 已无 `@mui/*` import。
- 未迁移 App Shell、业务页面或 tax/import 子组件。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run CommonMuiComponents.test.tsx App.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/' web/src/components/common/PageScaffold.tsx web/src/components/common/PageToolbar.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
  - `git status --short --branch`

### MG-P010-phase-3-page-layout-primitives

- Status: `verified`
- Scope:
  - `web/src/components/common/PageScaffold.tsx`
  - `web/src/components/common/PageToolbar.tsx`
  - `web/src/test/CommonMuiComponents.test.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/modules/phase_3_primitives.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_3_primitives.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P010 page layout primitive 文件：web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/test/CommonMuiComponents.test.tsx、web/src/app/styles.css、docs/refactor-ui/modules/phase_3_primitives.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run CommonMuiComponents.test.tsx App.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/' web/src/components/common/PageScaffold.tsx web/src/components/common/PageToolbar.tsx; then exit 1; else exit 0; fi；if rg -n '@mui/' web/src/components/common --glob '!**/workbench/**'; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate page layout primitives。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified，并将 phase_3_primitives 标记 completed。
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

- Commit: `d4135cf3`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### P011-phase-4-shell-discovery

- Phase: `phase_4_shell`
- Status: `approved_for_execution`
- Type: `discovery/planning`
- Scope: 只建立 App Shell 迁移边界、MUI 使用清单、icon 依赖决策和下一条 prompt；不改运行时代码。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、README.md、baseline_inventory.md、module_inventory.md、platform_stack_migration.md、test_migration_strategy.md、web/src/app/App.tsx、web/src/app/MuiProviders.tsx、web/src/app/pageRegistry.tsx、web/src/components/shell/AppSidebar.tsx、web/src/components/shell/AppTopBar.tsx、web/src/components/shell/AppStatusIndicator.tsx、web/src/test/App.test.tsx、web/src/test/AppStatusIndicator.test.tsx 和相关 shell CSS。只做 discovery/planning，不改运行时代码、不改依赖、不改后端。创建 docs/refactor-ui/modules/phase_4_shell.md，记录 shell 范围、冻结边界、现有用户可见契约、MUI usage、lucide-react icon 依赖决策、Micro-JIT 切片计划和验证目标。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Runtime implementation untouched: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Dependency change deferred: yes，`lucide-react` 只记录决策，下一条 prompt 执行。
- Verification defined: 文档存在、关键规则 grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 新增 `docs/refactor-ui/modules/phase_4_shell.md`。
- 记录 App Shell 范围、workbench 冻结边界、既有 shell contract、MUI usage、lucide-react icon 依赖决策和 phase 4 Micro-JIT 切片计划。
- 本切片未修改运行时代码、依赖、后端或 workbench 内部。

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_4_shell.md`
  - `rg -n "Phase 4 Boundary|Icon Decision|lucide-react|P012-phase-4-shell-icon-dependency|ReconciliationWorkbenchPage|--sidebar-width" docs/refactor-ui/modules/phase_4_shell.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
  - `git diff --check`
  - `git status --short --branch`

### MG-P011-phase-4-shell-discovery

- Status: `verified`
- Scope:
  - `docs/refactor-ui/modules/phase_4_shell.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_4_shell.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、验证结果和文档状态。确认 scope 只包含 P011 shell discovery 文档文件：docs/refactor-ui/modules/phase_4_shell.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：test -f docs/refactor-ui/modules/phase_4_shell.md；rg -n "Phase 4 Boundary|Icon Decision|lucide-react|P012-phase-4-shell-icon-dependency|ReconciliationWorkbenchPage|--sidebar-width" docs/refactor-ui/modules/phase_4_shell.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md；git diff --check；git status --short --branch。提交信息使用 docs: add shell migration discovery。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `0c0e6b01`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### P012-phase-4-shell-icon-dependency

- Phase: `phase_4_shell`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 安装 `lucide-react`，迁移 `pageRegistry` sidebar icons/type、`AppSidebar` icon render compatibility 和 `App.test.tsx` icon 断言。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_4_shell.md、web/package.json、web/package-lock.json、web/src/app/pageRegistry.tsx、web/src/components/shell/AppSidebar.tsx、web/src/test/App.test.tsx。执行 `cd web && npm install lucide-react`。只迁移 shell sidebar icon dependency：pageRegistry 从 MUI icons/SvgIconComponent 改为 lucide-react/LucideIcon；AppSidebar 只做 icon render compatibility；App.test.tsx 更新为 lucide icon 断言。不得迁移 AppSidebar layout、AppTopBar、AppStatusIndicator、App runtime provider、业务页面、后端或 workbench 内部。运行 shell tests、build、lucide npm ls、MUI icon grep、diff check 和 git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Dependency justified: yes，shell MUI icons 需要非 MUI icon set；phase_4_shell.md 已记录 lucide-react 决策。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- AppSidebar layout migration deferred: yes。
- Verification defined: targeted Vitest、build、npm ls、MUI icon grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- Installed `lucide-react@1.17.0`。
- `pageRegistry.tsx` sidebar icon imports/type migrated to `LucideIcon`。
- `AppSidebar.tsx` icon render changed to lucide `size={18}` / `strokeWidth={2}`。
- `App.test.tsx` icon assertions migrated to lucide components。
- `npm install` still reports 9 vulnerabilities; no audit fix run in this slice。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run App.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `cd web && npm ls lucide-react --depth=0`
  - `if rg -n '@mui/icons-material' web/src/app/pageRegistry.tsx web/src/test/App.test.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
  - `git status --short --branch`

### MG-P012-phase-4-shell-icon-dependency

- Status: `verified`
- Scope:
  - `web/package.json`
  - `web/package-lock.json`
  - `web/src/app/pageRegistry.tsx`
  - `web/src/components/shell/AppSidebar.tsx`
  - `web/src/test/App.test.tsx`
  - `docs/refactor-ui/modules/phase_4_shell.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_4_shell.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P012 shell icon dependency 文件：web/package.json、web/package-lock.json、web/src/app/pageRegistry.tsx、web/src/components/shell/AppSidebar.tsx、web/src/test/App.test.tsx、docs/refactor-ui/modules/phase_4_shell.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run App.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；cd web && npm ls lucide-react --depth=0；if rg -n '@mui/icons-material' web/src/app/pageRegistry.tsx web/src/test/App.test.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate shell icons to lucide。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `a96087fc`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### P013-phase-4-shell-provider-runtime

- Phase: `phase_4_shell`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 App Shell root runtime provider：`App.tsx` 移出完整 `MuiProviders`，替换 App runtime 中的 MUI `Box/useMediaQuery/useTheme/Alert`，保留日期选择器临时兼容边界。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_4_shell.md、web/src/app/App.tsx、web/src/app/MuiProviders.tsx、web/src/app/muiTheme.ts、web/src/app/styles.css、web/src/test/App.test.tsx、web/src/test/AppStatusIndicator.test.tsx、web/src/test/PageKeepAliveHost.test.tsx 和 HeroUI Alert docs。只迁移 App Shell provider/runtime：从 App.tsx 移除完整 MuiProviders，替换 useTheme/useMediaQuery/Box/Alert 为 React matchMedia hook、semantic markup、HeroUI Alert 和 token CSS classes。若业务页面仍需要 MUI X DatePicker localization context，只允许新增窄兼容 provider，必须记录为临时边界。不得迁移 AppSidebar layout、AppTopBar、AppStatusIndicator、业务页面、后端/API/read model/worker 或 workbench 内部。运行 shell tests、build、App.tsx direct MUI import grep、diff check 和 git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Business pages untouched: yes。
- Full MUI ThemeProvider/CssBaseline removed from `App.tsx`: yes。
- Temporary compatibility justified: yes，existing MUI X DatePicker/MonthPicker still needs localization context until later page/date-picker migration slices.
- Verification defined: targeted Vitest、build、App.tsx direct MUI import grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `App.tsx` removed `MuiProviders` and no longer imports `@mui/*` directly.
- Added `useShellMediaQuery` backed by `window.matchMedia`.
- Converted App Shell wrapper/progress layout from MUI `Box` to semantic HTML and CSS classes.
- Converted operation error display from MUI `Alert` to HeroUI `Alert` with explicit close button.
- Added `MuiDatePickerCompatProvider` with MUI X `LocalizationProvider`, `AdapterDayjs`, `adapterLocale="zh-cn"` and date picker `localeText` from `@mui/x-date-pickers/locales`.
- First targeted Vitest run failed because MUI X pickers lost localization context and Chinese accessible labels after removing `MuiProviders`; the narrow compatibility provider fixed the root cause without restoring MUI ThemeProvider/CssBaseline.

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/' web/src/app/App.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
  - `git status --short --branch`

### MG-P013-phase-4-shell-provider-runtime

- Status: `verified`
- Scope:
  - `web/src/app/App.tsx`
  - `web/src/app/MuiDatePickerCompatProvider.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/modules/phase_4_shell.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_4_shell.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P013 shell provider runtime 文件：web/src/app/App.tsx、web/src/app/MuiDatePickerCompatProvider.tsx、web/src/app/styles.css、docs/refactor-ui/modules/phase_4_shell.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/' web/src/app/App.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate shell runtime provider。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `b26db303`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### P014-phase-4-sidebar-topbar

- Phase: `phase_4_shell`
- Status: `verified`
- Type: `characterization tests -> extraction/refactor`
- Scope: 迁移 `AppSidebar` 和 `AppTopBar` 的 MUI layout/navigation chrome 到 HeroUI/Tailwind/native markup；保持左侧菜单、移动端临时侧边栏、折叠/展开、embedded mode、active link 和 header mounting 行为。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_4_shell.md、DESIGN.md、web/src/components/shell/AppSidebar.tsx、web/src/components/shell/AppTopBar.tsx、web/src/components/shell/sidebarItems.ts、web/src/app/pageRegistry.tsx、web/src/app/styles.css、web/src/test/App.test.tsx 和 PageKeepAliveHost/AppStatusIndicator 相关测试。使用 HeroUI MCP Button/Tooltip/Drawer/Link/Separator docs 核对 API。每次只处理 AppSidebar + AppTopBar，不迁移 AppStatusIndicator、业务页面、后端/API/read model/worker 或 workbench 内部。先补强 App.test.tsx 中 sidebar/topbar 用户可观察行为断言（桌面折叠/展开、mobile open/close、embedded brand/header、active link、菜单入口不丢失），避免 MUI class/theme 断言。然后把 AppSidebar/AppTopBar 从 MUI Drawer/List/ListItem/ListItemButton/ListItemIcon/ListItemText/Stack/Collapse/Tooltip/IconButton/Divider/Typography/AppBar/Toolbar 等迁移到 HeroUI/Tailwind/native markup。保留 expandedSidebarWidth=232、collapsedSidebarWidth=72、aria-label、href/path、active aria-current、mobile overlay 关闭行为、global header hidden/workbench page mode。运行 targeted shell tests、build、shell MUI import grep、diff check 和 git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- AppStatusIndicator deferred: yes。
- User-visible behavior preserved: yes，same sidebar/topbar controls, labels, routes and mobile drawer shape。
- Characterization tests required: yes，P014 touches shell navigation behavior。
- Verification defined: targeted Vitest、build、shell MUI import grep、`git diff --check`、`git status --short --branch`。
- Status: verified。

#### Execution Notes

- Added compact/mobile sidebar characterization coverage in `App.test.tsx` using a shell `matchMedia` stub.
- Migrated `AppSidebar` to HeroUI Drawer/Button/Tooltip/Separator plus semantic `aside/nav/section/ul/li/a` markup.
- Migrated `AppTopBar` to HeroUI Button/Tooltip plus semantic `header` markup and lucide `Menu`.
- Preserved `expandedSidebarWidth = 232`, `collapsedSidebarWidth = 72`, mobile open/close, embedded brand behavior, active link `aria-current`, labels and route targets.
- Updated `styles.css` so sidebar/topbar no longer depend on MUI selected/collapse/list text classes.
- `AppStatusIndicator.tsx` still contains MUI and remains deferred to `P015-phase-4-status-indicator`.

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run App.test.tsx`
  - `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/' web/src/components/shell/AppSidebar.tsx web/src/components/shell/AppTopBar.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
  - `git status --short --branch`

### MG-P014-phase-4-sidebar-topbar

- Status: `verified`
- Scope:
  - `web/src/components/shell/AppSidebar.tsx`
  - `web/src/components/shell/AppTopBar.tsx`
  - `web/src/app/styles.css`
  - `web/src/test/App.test.tsx`
  - `docs/refactor-ui/modules/phase_4_shell.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_4_shell.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P014 sidebar/topbar 文件：web/src/components/shell/AppSidebar.tsx、web/src/components/shell/AppTopBar.tsx、web/src/app/styles.css、web/src/test/App.test.tsx、docs/refactor-ui/modules/phase_4_shell.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/' web/src/components/shell/AppSidebar.tsx web/src/components/shell/AppTopBar.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate shell sidebar topbar。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `3b124246`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### P015-phase-4-status-indicator

- Phase: `phase_4_shell`
- Status: `verified`
- Type: `characterization tests -> extraction/refactor`
- Scope: 迁移 `AppStatusIndicator` 的状态点、popover、domain chips、progress 和任务链接展示，从 MUI Popper/Paper/ClickAway/Chip/LinearProgress/Stack/Typography/SvgIcon/Box 迁到 HeroUI/Tailwind/native markup。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_4_shell.md、DESIGN.md、web/src/components/shell/AppStatusIndicator.tsx、web/src/contexts/AppHealthStatusContext.tsx、web/src/app/pageRegistry.tsx、web/src/app/styles.css、web/src/test/AppStatusIndicator.test.tsx、web/src/test/App.test.tsx 和相关 API mock。使用 HeroUI MCP Popover、Chip、ProgressBar、Link、Tooltip docs 核对 API。每次只处理 AppStatusIndicator，不迁移业务页面、AppSidebar/AppTopBar、后端/API/read model/worker 或 workbench 内部。先把 AppStatusIndicator tests 补强为用户可观察行为断言：正常/异常/刷新中状态、popover 打开关闭、admin operations link、route change stability、task/domain link 可访问、progress 展示。然后迁移 AppStatusIndicator 实现到 HeroUI/Tailwind/native markup，保留 role=status、aria-label、data-status-reason、popover hover/focus/click 行为、admin 权限入口、domain/task 链接和现有状态文本。运行 targeted shell tests、build、shell MUI import grep、diff check 和 git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- AppSidebar/AppTopBar untouched: yes。
- User-visible behavior preserved: yes，same status indicator role/name, popover content, admin operations link and health domain links。
- Characterization tests required: yes，P015 touches global status behavior and permission-based operations link。
- Verification defined: targeted Vitest、build、shell MUI import grep、`git diff --check`、`git status --short --branch`。
- Status: verified。

#### Execution Notes

- Migrated `AppStatusIndicator` from MUI imports to HeroUI `Chip`/`ProgressBar`/`Separator` plus native SVG, semantic links and a project-owned portal popover.
- Preserved status role/name, hover/focus/click open, delayed unhover close, Escape close, outside click close, route-change stability, domain links, task links, task progress, scope diagnostics and admin-only `App Health` link.
- Replaced MUI Popper with portal positioning to avoid sidebar clipping while keeping right-side placement.
- `web/src/components/shell` now has no `@mui/*` imports.

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run AppStatusIndicator.test.tsx`
  - `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/' web/src/components/shell; then exit 1; else exit 0; fi`
  - `git diff --check`
  - `git status --short --branch`

### MG-P015-phase-4-status-indicator

- Status: `verified`
- Scope:
  - `web/src/components/shell/AppStatusIndicator.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/modules/phase_4_shell.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_4_shell.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P015 status indicator 文件：web/src/components/shell/AppStatusIndicator.tsx、web/src/app/styles.css、docs/refactor-ui/modules/phase_4_shell.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/' web/src/components/shell; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate shell status indicator。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `6f1ac42a`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

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

### P016-phase-5-table-system-discovery

- Phase: `phase_5_table_system`
- Status: `verified`
- Type: `discovery/planning`
- Scope: 只做表格系统 discovery/planning，建立当前表格迁移队列、HeroUI Table 能力边界、内容排版契约、DataGrid session 替代策略和下一条 P017 characterization prompt。

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、table_layout_system.md、module_inventory.md、baseline_inventory.md、test_migration_strategy.md、web/src/app/styles.css 和当前表格/测试使用点。只做 phase 5 table system discovery/planning，创建或更新 docs/refactor-ui/modules/phase_5_table_system.md，记录迁移队列、排版规则和下一条 P017 prompt。运行文档/key grep、git diff --check、git status，并更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Runtime implementation untouched: yes。
- Workbench internals frozen: yes。
- User-visible behavior preserved: yes，本切片只写迁移边界和排版规则。
- Characterization tests deferred: yes，P016 是 discovery；P017 必须先补表格系统 tests。
- Docs on demand: yes，Phase 5 会跨多个表格模块复用 discovery，因此新增 `docs/refactor-ui/modules/phase_5_table_system.md`。
- Verification defined: 文档路径检查、关键规则 grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 新增 `docs/refactor-ui/modules/phase_5_table_system.md`。
- 记录 DataGrid-heavy、MUI Table dense finance tables、operational tables 和 frozen/out-of-phase buckets。
- 记录 HeroUI Table compound API、sorting、selection、footer pagination 的使用边界。
- 记录 column role alignment、Amount/DirectionTag 固定槽位、dense text、grouped headers 和 `useFinanceTableSession` 替代策略。
- 指出 `TableAlignmentStyles.test.ts` 当前仍断言 MUI/DataGrid 全局居中，P017 必须改为按表格列角色测试。
- 本切片未修改前端实现、CSS、依赖、后端、API、read model、worker 或关联台内部工作区。

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_5_table_system.md`
  - `rg -n "P016-phase-5-table-system-discovery|DataGrid-heavy|MUI Table Dense Finance Tables|DirectionTag|AmountCell|useFinanceTableSession|P017-phase-5-table-characterization-tests" docs/refactor-ui/modules/phase_5_table_system.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
  - `git diff --check`
  - `git status --short --branch`

### P017-phase-5-table-characterization-tests

- Phase: `phase_5_table_system`
- Status: `verified`
- Type: `characterization tests`
- Scope: 只处理表格系统测试契约，不实现 FinanceTable primitives，不迁业务页面。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/test_migration_strategy.md、DESIGN.md、web/src/app/styles.css、web/src/test/TableAlignmentStyles.test.ts、web/src/components/cost-statistics/CostStatisticsTable.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx 和 web/src/hooks/useMuiDataGridPageSession.ts。使用 HeroUI MCP Table/Chip/Tooltip/Pagination docs 核对 Table compound API、sorting、selection 和 footer pagination。

把 TableAlignmentStyles.test.ts 从 MUI/DataGrid/grid-table 全局居中断言改为 FinanceTable column role contract：amount/quantity right + tabular nums、date/status/direction/selection center、identity/account/description left、DirectionTag 固定槽位、EmptyValue 文案统一、HeroUI/Tailwind table tokens 存在。可以新增 web/src/test/FinanceTableContract.test.ts 或等价测试文件；不得修改业务页面、CSS 实现、依赖、后端、API、read model、worker 或关联台内部工作区。

运行 targeted Vitest，预期在 FinanceTable primitives 未实现前失败；再运行 git diff --check 和 git status。更新 refactor_ui_state.md、refactor_ui_prompt.md 和 phase_5_table_system.md，记录失败断言和下一条 P018 implementation prompt 建议。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Runtime CSS/implementation untouched: yes。
- Workbench internals frozen: yes。
- Business page migration untouched: yes。
- Micro-JIT order preserved: yes，P016 discovery 后先写 characterization tests。
- Expected failure acceptable: yes，P018 primitives 未实现前 targeted tests 应暴露缺口。
- Verification defined: targeted Vitest expected fail、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `web/src/test/TableAlignmentStyles.test.ts` 已从 MUI theme/DataGrid/grid-table 全局居中断言改为 FinanceTable column role contract。
- 新测试读取 `web/src/app/styles.css`，断言 `.finance-table`、`.finance-table__cell[data-column-role="..."]`、`.finance-amount-cell`、`.finance-direction-tag` 和 `.finance-empty-value`。
- 本切片未实现 CSS 或 primitives，未改业务页面、后端、API、read model、worker 或关联台内部工作区。

#### Verification

- Status: verified expected-fail。
- Commands:
  - `cd web && npx vitest run TableAlignmentStyles.test.ts`
  - Result: expected fail。3 个失败分别缺少 `.finance-table`、`.finance-table__cell[data-column-role="identity"]`、`.finance-amount-cell`。

### P018-phase-5-finance-table-primitives

- Phase: `phase_5_table_system`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只实现 FinanceTable CSS contract 和共享 table cell primitives，让 P017 tests 通过；不迁业务页面。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/modules/phase_5_table_system.md、DESIGN.md、web/src/app/styles.css、web/src/test/TableAlignmentStyles.test.ts 和 web/src/components/common。使用 HeroUI MCP Table、Chip、Tooltip、Pagination docs 核对 API。只新增或修改共享表格 primitives 和 CSS：FinanceTable、FinanceTablePagination、TableCellStack、AmountCell、FinanceDirectionTag、FinanceStatusTag、EmptyValue 或等价命名；补齐 `.finance-table`、按 column role 的 `.finance-table__cell[data-column-role="..."]`、`.finance-amount-cell`、`.finance-direction-tag`、`.finance-empty-value` CSS contract。不得迁移业务页面、DataGrid 页面、后端、API、read model、worker 或关联台内部工作区。运行 `cd web && npx vitest run TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx`、`cd web && npm run build`、MUI import grep、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，记录下一条 P019 table session primitive prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Business page migration untouched: yes。
- Workbench internals frozen: yes。
- Micro-JIT order preserved: yes，P017 expected-fail 后实现 primitives。
- Verification defined: targeted Vitest、build、MUI import grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 新增 `web/src/components/common/FinanceTable.tsx`。
- 新增共享 primitives：`FinanceTable`、`FinanceTableColumn`、`FinanceTableCell`、`FinanceTablePagination`、`TableCellStack`、`AmountCell`、`FinanceDirectionTag`、`FinanceStatusTag`、`EmptyValue`、`TruncatedCellText`。
- `web/src/app/styles.css` 补齐 `.finance-table`、column role cells、amount cell、direction tag、status tag、empty value、pagination 和 truncation classes。
- `web/src/test/TableAlignmentStyles.test.ts` 从 expected-fail 转为 passed。
- 未迁移业务页面、DataGrid 页面、后端、API、read model、worker 或关联台内部工作区。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run TableAlignmentStyles.test.ts`
  - `cd web && npx vitest run TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/' web/src/components/common; then exit 1; else exit 0; fi`
  - `git diff --check`
  - `git status --short --branch`
  - Build passed with known HeroUI/Tailwind generated CSS minifier warnings and existing large chunk warning.

### P019-phase-5-table-session-primitive

- Phase: `phase_5_table_system`
- Status: `verified`
- Type: `characterization tests -> extraction/refactor`
- Scope: 新增 HeroUI table session primitive，替代 MUI DataGrid session 的用户可见状态；不迁业务页面。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/hooks/useMuiDataGridPageSession.ts、web/src/test/useMuiDataGridPageSession.test.tsx、web/src/contexts/PageSessionStateContext.tsx、web/src/contexts/pageSessionStorage.ts 和 web/src/components/common/FinanceTable.tsx。只新增 `useFinanceTableSession` 或等价 hook 及 tests，覆盖用户可见 table 状态：page/pageSize、sort descriptor、row selection、scroll position restore。不要迁移 CostStatistics、ImportWorkflow、settings DataGrid 或任何业务页面；不要删除 `useMuiDataGridPageSession`。运行新 table session tests、`useMuiDataGridPageSession.test.tsx` 回归、P018 table/common/platform tests、build、MUI import grep、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，记录下一条低风险 table pilot migration prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Business page migration untouched: yes。
- Existing MUI DataGrid hook untouched: yes，直到页面迁移时逐步替换。
- Workbench internals frozen: yes。
- Verification defined: new session tests、old MUI session regression、P018 tests、build、MUI import grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 新增 `web/src/hooks/useFinanceTableSession.ts`。
- 新增 `web/src/test/useFinanceTableSession.test.tsx`。
- Hook 复用 `PageSessionStateContext`，不依赖 MUI。
- 覆盖用户可见状态：1-based page/pageSize、sort descriptor、row selection、native scroll position restore。
- 保留旧 `useMuiDataGridPageSession`，未迁移业务页面或 DataGrid 页面。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run useFinanceTableSession.test.tsx`
  - `cd web && npx vitest run useFinanceTableSession.test.tsx useMuiDataGridPageSession.test.tsx TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/' web/src/hooks/useFinanceTableSession.ts web/src/test/useFinanceTableSession.test.tsx web/src/components/common/FinanceTable.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
  - Build passed with known HeroUI/Tailwind generated CSS minifier warnings and existing large chunk warning.

### P020-phase-5-app-health-table-pilot-discovery

- Phase: `phase_5_table_system`
- Status: `verified`
- Type: `discovery/planning`
- Scope: 只做 AppHealthOperationsPage 表格 pilot discovery；不迁移页面实现。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/AppHealthOperationsPage.tsx、web/src/test/AppHealthOperationsPage.test.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/hooks/useFinanceTableSession.ts。只做 AppHealthOperationsPage table pilot discovery/planning，记录旧页面表格清单、列角色、用户可见入口、loading/empty/error 状态、MUI imports、测试断言、应复用的 FinanceTable primitives 和下一条 P021 characterization/refactor prompt。不得迁移页面实现，不改后端/API/read model/worker/关联台。更新 docs/refactor-ui/modules/phase_5_table_system.md、refactor_ui_state.md、refactor_ui_prompt.md。运行文档/key grep、git diff --check、git status。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Runtime implementation untouched: yes。
- Workbench internals frozen: yes。
- Business page migration deferred: yes，P020 只做 pilot discovery。
- Verification defined: docs/key grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 读取 `web/src/pages/AppHealthOperationsPage.tsx` 和 `web/src/test/AppHealthOperationsPage.test.tsx`。
- 记录 7 组 table/table-like surfaces：Inventory sources、Request performance、Outbox、Queue、Read Model、Worker、PerformanceCell。
- 记录 AppHealth 无分页、无选择、无行点击、无抽屉、无导出；保留刷新、admin gate、loading/error 和 existing dashboard visible on refresh failure。
- 明确 P021 只迁移 AppHealth 表格 surfaces，不做整页 HeroUI 化。

#### Verification

- Status: verified。
- Commands:
  - `rg -n "P020-phase-5-app-health-table-pilot-discovery|AppHealth Table Inventory|Inventory sources|Request performance|P021-phase-5-app-health-table-pilot-refactor" docs/refactor-ui/modules/phase_5_table_system.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
  - `git diff --check`
  - `git status --short --branch`

### P021-phase-5-app-health-table-pilot-refactor

- Phase: `phase_5_table_system`
- Status: `verified`
- Type: `characterization tests -> extraction/refactor`
- Scope: 只迁移 AppHealthOperationsPage 的表格 surfaces 到 FinanceTable primitives；不做整页 HeroUI 化。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/AppHealthOperationsPage.tsx、web/src/test/AppHealthOperationsPage.test.tsx、web/src/components/common/FinanceTable.tsx。先补或调整 AppHealthOperationsPage.test.tsx 中表格语义/列入口断言，保留现有 admin gate、refresh failure、unknown metrics 和 data-tone 断言。然后只替换 AppHealth 的 MUI Table/TableContainer/TableHead/TableBody/TableRow/TableCell 为 FinanceTable primitives 和 table CSS classes；保留页面级 MUI Alert/Box/IconButton/Stack/Tooltip/Typography 到后续页面模块迁移。不得改后端/API/read model/worker/关联台。运行 AppHealthOperationsPage.test.tsx、TableAlignmentStyles.test.ts、CommonMuiComponents.test.tsx、build、AppHealth 表格 MUI import grep、git diff --check、git status。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Whole page HeroUI migration deferred: yes。
- Workbench internals frozen: yes。
- User-visible behavior preserved: yes，refresh/admin/loading/error/data-tone/table content assertions must remain。
- Verification defined: AppHealth tests、table/common tests、build、MUI table import grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `AppHealthOperationsPage.test.tsx` 新增 HeroUI Table 的 `role="grid"` + accessible name 断言。
- `AppHealthOperationsPage.tsx` 的 MUI Table/TableContainer/TableHead/TableBody/TableRow/TableCell surfaces 已迁到 FinanceTable primitives。
- `PerformanceCell` 改用 `FinanceStatusTag`，保留 nearest cell `data-tone` 断言。
- 页面级 MUI `Alert`、`Box`、`IconButton`、`Stack`、`Tooltip`、`Typography` 保留给后续页面模块迁移。
- 未改后端、API、read model、worker 或关联台内部工作区。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run AppHealthOperationsPage.test.tsx`
  - `cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/material/(Table|TableBody|TableCell|TableContainer|TableHead|TableRow)' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
  - Build passed with known HeroUI/Tailwind generated CSS minifier warnings and existing large chunk warning.

### P022-phase-6-tax-offset-discovery

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `discovery/planning`
- Scope: 只做 TaxOffsetPage 页面模块 discovery；不迁移页面实现。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/TaxOffsetPage.tsx、web/src/test/TaxOffsetPage.test.tsx、web/src/components/tax/*、web/src/components/common/FileDropzone.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/FinanceTable.tsx。只做 TaxOffsetPage discovery/planning，记录旧 UI 入口、表格/导入/月份/认证导入弹窗/结果右侧抽屉、MUI imports、已迁 common primitives、测试断言和风险。不得迁移实现，不改后端/API/read model/worker/关联台。按需在 docs/refactor-ui/modules/phase_6_tax_offset.md 新建或更新专项文档；更新 state/prompt docs；运行文档/key grep、git diff --check、git status。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Runtime implementation untouched: yes。
- Workbench internals frozen: yes。
- Micro-JIT phase transition: yes，Phase 5 pilot verified 后进入 Phase 6 page batches。
- Verification defined: docs/key grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 新增 `docs/refactor-ui/modules/phase_6_tax_offset.md`。
- 记录 TaxOffset 页面级 MUI、`components/tax/*` MUI、用户可见入口、现有测试覆盖和迁移切片。
- 确认 `FileDropzone`、`PageScaffold`、`StatePanel` 已迁移，可复用。
- 识别 MUI-specific test 断言：`modal.closest(".MuiDialog-root")`。
- 本切片未修改运行时代码、后端、API、read model、worker 或关联台内部工作区。

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_tax_offset.md`
  - `rg -n "P022-phase-6-tax-offset-discovery|Current MUI Inventory|User-visible Entrypoints|P023-phase-6-tax-offset-characterization-tests|MuiDialog-root" docs/refactor-ui/modules/phase_6_tax_offset.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
  - `git diff --check`
  - `git status --short --branch`

### P023-phase-6-tax-offset-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `characterization tests`
- Scope: 只调整 TaxOffsetPage tests，锁定新 primitives 的行为契约；不改实现。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_tax_offset.md、docs/refactor-ui/test_migration_strategy.md、web/src/test/TaxOffsetPage.test.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/FinanceTable.tsx、web/src/components/tax/CertifiedInvoiceImportModal.tsx、web/src/components/tax/TaxTable.tsx。将 TaxOffsetPage.test.tsx 中 `.MuiDialog-root` 断言改为项目 dialog primitive 语义；为认证导入预览表和 TaxTable 增加稳定的列/role/入口断言，避免 MUI class 断言。不得修改实现、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run TaxOffsetPage.test.tsx`，预期在实现未迁移前可 expected-fail；运行 git diff --check、git status。更新 state/prompt/module docs，生成 P024 import modal refactor prompt。
```

#### Review

- Single slice: yes。
- Runtime implementation untouched: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Expected failure acceptable: yes，new primitive contracts may fail before P024/P025。
- Verification defined: targeted TaxOffset test expected-fail or pass、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `TaxOffsetPage.test.tsx` 已从 `.MuiDialog-root` 和 MUI table role contract 迁到 `finance-dialog`、FinanceTable `grid`、column role 和 preview table contract。
- 初次运行 `cd web && npx vitest run TaxOffsetPage.test.tsx` expected-fail，6 个失败均来自 TaxOffset 仍渲染 MUI table/dialog surfaces。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run TaxOffsetPage.test.tsx`
  - Result: expected-fail before P024/P025 implementation。

### P024-phase-6-tax-offset-import-modal

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 `CertifiedInvoiceImportModal`，保留上传、预览、确认、后台 job polling、关闭和刷新行为。

#### Prompt

```text
读取 P023 测试、CertifiedInvoiceImportModal、AppDialog、FinanceTable 和 HeroUI Button/Alert/ProgressBar/Chip/Table docs。只迁移 CertifiedInvoiceImportModal 到 AppDialog、HeroUI feedback/buttons/chips/progress 和 FinanceTable preview rows；不得改 TaxTable、TaxResultPanel、CertifiedResultsDrawer、后端、API、read model、worker 或关联台内部工作区。运行 TaxOffset targeted tests，记录剩余 TaxTable expected failures。
```

#### Execution Notes

- `CertifiedInvoiceImportModal` 已无 MUI import。
- 已认证导入仍是 page modal，未改为路由或抽屉。
- `FileDropzone`、预览、确认、queued import job polling 和 `onImported` 回调保持原行为。
- Preview row table 迁到 `FinanceTable`，列角色为 quantity/identity/account/amount/status/status/description。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run TaxOffsetPage.test.tsx`
  - Result: remaining failures moved to TaxTable FinanceTable grid contract。

### P025-phase-6-tax-offset-tax-table

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 `TaxTable` 到 FinanceTable/HeroUI/native search，保留筛选、排序、选择、横向滚动和高亮行。

#### Prompt

```text
读取 P023 测试、TaxTable、FinanceTable、table_layout_system.md 和 HeroUI Button/Checkbox/Table docs。只迁移 TaxTable，不改后端/API/read model/worker，不改关联台内部工作区。不得继续依赖含 MUI 的 WorkbenchPaneSearch；可保留不含 MUI 的 WorkbenchColumnFilterMenu 使用但不修改其文件。保留表格 accessible name、checkbox aria-label、排序按钮 aria-label、搜索/清空入口、筛选 dialog、横向 scrollbar 和 data-certified-highlighted 行属性。运行 TaxOffset targeted tests、TaxOffset MUI grep、diff check。
```

#### Execution Notes

- `TaxTable` 已无 MUI import。
- `WorkbenchPaneSearch` 依赖已移除，TaxTable 使用本页原生 search control，保留旧 aria label。
- 表格迁到 `FinanceTable`，输出表列角色为 identity/amount/account/amount，进项表为 selection/identity/amount/account/amount。
- `FinanceTable` 增加可选 `scrollRef` 和 `dataCertifiedHighlighted` row attribute，保留 TaxOffset 横向滚动和高亮测试。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run TaxOffsetPage.test.tsx`
  - Result: passed, 17 tests。

### P026-phase-6-tax-offset-result-panel

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 `TaxResultPanel`、`TaxSummaryCards` 和 TaxOffset page-level shell/action MUI。

#### Execution Notes

- `TaxResultPanel` 和 `TaxSummaryCards` 已迁到 HeroUI/native token classes。
- `TaxOffsetPage.tsx` header action、feedback note、workspace containers、全选/清空按钮已迁出 MUI。
- 未改 API、read model、worker、权限或业务状态机。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run TaxOffsetPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`

### P027-phase-6-tax-offset-certified-results

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 `CertifiedResultsDrawer`，保持旧 complementary side panel、collapse/expand 和 row selection 行为。

#### Execution Notes

- `CertifiedResultsDrawer` 已迁到 HeroUI/native controls。
- 旧 `role="complementary"` / `aria-label="已认证结果"` 保留。
- 已匹配计划行点击仍定位对应进项计划行。
- 当前 `web/src/pages/TaxOffsetPage.tsx` 和 `web/src/components/tax/*` 无 `@mui/*` import。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run TaxOffsetPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `rg -n '@mui/' web/src/pages/TaxOffsetPage.tsx web/src/components/tax`
  - `git diff --check`

## Prompt History

| Prompt ID | Phase | Slice | Status | Verification | Notes |
| --- | --- | --- | --- | --- | --- |
| `P000-docs-bootstrap` | `phase_0_baseline` | docs bootstrap | `verified` | passed | 文档切片已验证 |
| `P001-baseline-doc-gap-fill` | `phase_0_baseline` | docs gap fill | `verified` | passed | 基线、平台栈、测试策略、模块队列、文档沉淀规则、完整重构路径、phase-to-prompt 规则、主控 goal prompt 已补齐 |
| `P002-phase-1-docs-and-tokens-discovery` | `phase_1_docs_and_tokens` | token discovery | `verified` | passed | Token 边界和 P003 characterization test 建议已记录 |
| `P003-phase-1-token-characterization-tests` | `phase_1_docs_and_tokens` | token tests | `verified` | expected fail | Ledger Calm 和 table token characterization tests 已新增 |
| `P004-phase-1-token-implementation` | `phase_1_docs_and_tokens` | token implementation | `verified` | passed | CSS token bridge 已落地，P003 tests 通过 |
| `P005-phase-2-platform-stack-migration` | `phase_2_platform_stack` | platform stack | `verified` | passed | React 19、HeroUI、Tailwind v4 和 Vite plugin 已接入 |
| `P011-phase-4-shell-discovery` | `phase_4_shell` | shell discovery | `verified` | passed | App Shell 迁移边界和切片计划已记录 |
| `P012-phase-4-shell-icon-dependency` | `phase_4_shell` | shell icons | `verified` | passed | lucide-react sidebar icon dependency 已迁移 |
| `P013-phase-4-shell-provider-runtime` | `phase_4_shell` | shell runtime provider | `verified` | passed | App.tsx 移出完整 MuiProviders，保留临时 MUI X date picker compat |
| `P014-phase-4-sidebar-topbar` | `phase_4_shell` | sidebar/topbar | `verified` | passed | AppSidebar/AppTopBar 已迁出 MUI，AppStatusIndicator 留到 P015 |
| `P015-phase-4-status-indicator` | `phase_4_shell` | status indicator | `verified` | passed | shell 目录已无 MUI import |
| `P016-phase-5-table-system-discovery` | `phase_5_table_system` | table discovery | `verified` | passed | 表格迁移队列、HeroUI Table 能力边界、排版契约和 P017 prompt 已记录 |
| `P017-phase-5-table-characterization-tests` | `phase_5_table_system` | table tests | `verified` | expected fail | 表格系统 characterization tests 已改写，暴露 FinanceTable CSS/primitive 缺口 |
| `P018-phase-5-finance-table-primitives` | `phase_5_table_system` | table primitives | `verified` | passed | FinanceTable primitives 和 CSS contract 已通过 tests/build |
| `P019-phase-5-table-session-primitive` | `phase_5_table_system` | table session | `verified` | passed | useFinanceTableSession 已新增，新旧 session tests 和 build 通过 |
| `P020-phase-5-app-health-table-pilot-discovery` | `phase_5_table_system` | app health table pilot discovery | `verified` | passed | AppHealth 表格 pilot 清单和 P021 refactor prompt 已记录 |
| `P021-phase-5-app-health-table-pilot-refactor` | `phase_5_table_system` | app health table pilot refactor | `verified` | passed | AppHealth 表格 surfaces 已迁到 FinanceTable primitives |
| `P022-phase-6-tax-offset-discovery` | `phase_6_page_batches` | tax offset discovery | `verified` | passed | TaxOffset 专项文档、迁移队列和 P023 prompt 已记录 |
| `P023-phase-6-tax-offset-characterization-tests` | `phase_6_page_batches` | tax offset tests | `verified` | expected fail | 新 dialog/FinanceTable contract 已锁定 |
| `P024-phase-6-tax-offset-import-modal` | `phase_6_page_batches` | tax offset import modal | `verified` | passed | 已认证导入弹窗和预览表已迁出 MUI |
| `P025-phase-6-tax-offset-tax-table` | `phase_6_page_batches` | tax offset tables | `verified` | passed | TaxTable 已迁到 FinanceTable/HeroUI/native search |
| `P026-phase-6-tax-offset-result-panel` | `phase_6_page_batches` | tax offset result cards/page shell | `verified` | passed | result panel、summary cards 和 page-level actions 已迁出 MUI |
| `P027-phase-6-tax-offset-certified-results` | `phase_6_page_batches` | tax offset certified results | `verified` | passed | 已认证结果 complementary panel 已迁出 MUI |
| `MG-P027-phase-6-tax-offset` | `phase_6_page_batches` | tax offset cumulative MG | `verified` | pushed | TaxOffset UI migration 已 push 到 refactor-ui |
| `P028-phase-6-app-health-discovery` | `phase_6_page_batches` | app health discovery | `verified` | passed | AppHealth page-level MUI inventory、用户入口和 P029 prompt 已记录 |
| `MG-P028-phase-6-app-health-discovery` | `phase_6_page_batches` | app health discovery MG | `verified` | pushed | AppHealth discovery 已 push 到 refactor-ui |
| `P029-phase-6-app-health-characterization-tests` | `phase_6_page_batches` | app health tests | `verified` | expected fail | AppHealth page shell/notice primitive contract 已锁定 |
| `P030-phase-6-app-health-page-shell` | `phase_6_page_batches` | app health page shell | `verified` | passed | AppHealth page-level MUI 已迁出 |
| `MG-P030-phase-6-app-health` | `phase_6_page_batches` | app health cumulative MG | `verified` | pushed | AppHealth UI migration 已 push 到 refactor-ui |
| `P031-phase-6-import-pages-discovery` | `phase_6_page_batches` | import pages discovery | `verified` | passed | 导入页族 MUI/DataGrid inventory、用户入口和 P032 prompt 已记录 |
| `MG-P031-phase-6-import-pages-discovery` | `phase_6_page_batches` | import pages discovery MG | `verified` | pushed | Import pages discovery 已 push 到 refactor-ui |
| `P032-phase-6-import-pages-characterization-tests` | `phase_6_page_batches` | import pages tests | `verified` | expected fail | Import pages primitive contract 已锁定 |
| `P033-phase-6-import-pages-shell-forms` | `phase_6_page_batches` | import pages shell/forms | `verified` | partial expected fail | Shell/forms/cards/notices/dialog 已迁；仅 DataGrid 断言失败 |
| `P034-phase-6-import-pages-preview-tables` | `phase_6_page_batches` | import pages preview tables | `reviewed` | pending | 下一条执行 prompt，迁移导入预览表格 |

## Next Prompt Draft Slot

下一条 prompt 应执行 `P034-phase-6-import-pages-preview-tables`。

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_import_pages.md、docs/refactor-ui/modules/phase_5_table_system.md、web/src/components/imports/ImportWorkflowPage.tsx、web/src/test/ImportCenterPage.test.tsx、web/src/components/common/FinanceTable.tsx、web/src/hooks/useFinanceTableSession.ts 和 web/src/app/styles.css。使用 FinanceTable primitives 替换 `DataGrid`、`GridColDef`、`importGridSx`、`useMuiDataGridPageSession` 和 `useMuiDataGridScrollSession` 在导入页族中的使用，覆盖三类 preview table：`导入预览结果`、`重复项明细`/`未导入项明细`、`ETC导入预览结果`。保留表格 accessible names、关键 columnheader 文案、row text、loading/pending 语义、preview/detail tab 切换和用户可见数据。不得改后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run ImportCenterPage.test.tsx`，本切片结束后允许只剩 detail tabs primitive assertion failure；运行 focused table/common/platform tests、build、import scope MUI grep、git diff --check、git status。更新 state/prompt/module docs，生成 P035 detail tabs prompt。
```

## Cumulative MG Prompts

最近完成的 MG 是 `MG-P028-phase-6-app-health-discovery`。下一条执行 prompt 是 `P029-phase-6-app-health-characterization-tests`。

### MG-P027-phase-6-tax-offset

- Status: `verified`
- Scope:
  - `web/src/pages/TaxOffsetPage.tsx`
  - `web/src/components/tax/CertifiedInvoiceImportModal.tsx`
  - `web/src/components/tax/TaxTable.tsx`
  - `web/src/components/tax/TaxResultPanel.tsx`
  - `web/src/components/tax/TaxSummaryCards.tsx`
  - `web/src/components/tax/CertifiedResultsDrawer.tsx`
  - `web/src/components/common/FinanceTable.tsx`
  - `web/src/app/styles.css`
  - `web/src/test/TaxOffsetPage.test.tsx`
  - `docs/refactor-ui/modules/phase_6_tax_offset.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_tax_offset.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 TaxOffset UI migration 文件。禁止 git add . 和 git add -A。只允许精确 git add 当前 MG scope 文件。验证命令：cd web && npx vitest run TaxOffsetPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；rg -n '@mui/' web/src/pages/TaxOffsetPage.tsx web/src/components/tax；git diff --check；git status --short --branch。提交信息使用 feat: migrate tax offset ui。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified；下一条 prompt 进入 phase 6 AppHealth page discovery。
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

- Commit: `4c7a99f5`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### P028-phase-6-app-health-discovery

- Phase: `phase_6_page_batches`
- Status: `reviewed`
- Type: `discovery/planning`
- Scope: 只做 AppHealth page-level UI migration discovery；不迁移实现。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/AppHealthOperationsPage.tsx、web/src/test/AppHealthOperationsPage.test.tsx 和相关 AppHealth feature files。只做 AppHealth page discovery/planning，不迁移实现。记录当前 page-level MUI imports、已迁 FinanceTable surfaces、仍需迁移的 Alert/Box/Button/Chip/Stack/Typography/状态面板/刷新入口、用户可见入口、loading/error/permission 状态、测试断言和风险。不得改后端/API/read model/worker/关联台。按需新建 docs/refactor-ui/modules/phase_6_app_health.md；更新 state/prompt docs；运行文档/key grep、git diff --check、git status。
```

#### Review

- Single slice: yes。
- Runtime implementation untouched: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Docs on demand: yes，AppHealth 已做 table pilot，但 page-level MUI discovery 需要独立承载。
- Verification defined: docs/key grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 新增 `docs/refactor-ui/modules/phase_6_app_health.md`。
- 记录 AppHealth page-level MUI inventory：Refresh icon、Alert、Box、CircularProgress、IconButton、Stack、Tooltip、Typography。
- 记录 Phase 5 已迁 `FinanceTable` surfaces：数据来源、请求性能、Outbox、RabbitMQ、Read Model 和 Worker grids。
- 记录用户可见入口：标题、生成时间、刷新、loading、permission、error、数据/请求/后台 sections、负向后台任务控制契约。
- 生成下一条 `P029-phase-6-app-health-characterization-tests` prompt。

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_app_health.md`
  - `rg -n "P028-phase-6-app-health-discovery|Current MUI Inventory|Already Migrated Surfaces|User-visible Entrypoints|P029-phase-6-app-health-characterization-tests|RefreshIcon" docs/refactor-ui/modules/phase_6_app_health.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
  - `git diff --check`
  - `git status --short --branch`

### P029-phase-6-app-health-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `reviewed`
- Type: `characterization tests`
- Scope: 只调整 AppHealthOperationsPage tests，锁定 page-level HeroUI/native primitive contract；不改实现。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_app_health.md、docs/refactor-ui/test_migration_strategy.md、web/src/test/AppHealthOperationsPage.test.tsx、web/src/pages/AppHealthOperationsPage.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/app/styles.css。只修改 `web/src/test/AppHealthOperationsPage.test.tsx`，新增或调整断言：刷新按钮仍名为 `刷新` 且不再依赖 `.MuiIconButton-root`；loading、permission 和 error notices 保留语义但不再是 `.MuiAlert-root`；section wrappers 使用 AppHealth/project classes；既有 FinanceTable grid role/name 断言保持。不得修改实现、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run AppHealthOperationsPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P030 AppHealth page shell refactor prompt。
```

#### Review

- Single slice: yes。
- Runtime implementation untouched: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Characterization before implementation: yes。
- Expected failure acceptable: yes，旧 MUI classes 仍存在时 tests 应暴露缺口。
- Verification defined: targeted AppHealth Vitest、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `AppHealthOperationsPage.test.tsx` 已新增 page shell、header、refresh button、section 和 notice primitive contract。
- Targeted Vitest expected-failed because current implementation still lacks `data-testid="app-health-page"` and still renders `.MuiAlert-root` for permission/error notices。
- 未修改 runtime implementation、后端、API、read model、worker、mock 或关联台。

#### Verification

- Status: verified expected-fail。
- Commands:
  - `cd web && npx vitest run AppHealthOperationsPage.test.tsx`

### P030-phase-6-app-health-page-shell

- Phase: `phase_6_page_batches`
- Status: `reviewed`
- Type: `extraction/refactor`
- Scope: 只迁移 AppHealthOperationsPage page-level shell、sections、notices、refresh button 和 inventory summary cards；保留已迁 FinanceTable surfaces。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_app_health.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/AppHealthOperationsPage.tsx、web/src/test/AppHealthOperationsPage.test.tsx、web/src/app/styles.css 和 web/src/components/common/FinanceTable.tsx。使用 HeroUI MCP Alert/Button/Spinner/Tooltip docs 核对 API。把 AppHealthOperationsPage.tsx 从 MUI Alert/Box/CircularProgress/IconButton/Stack/Tooltip/Typography/RefreshIcon 迁到 HeroUI Alert/Button/Spinner/Tooltip、lucide RefreshCw、native semantic elements 和 AppHealth token classes。新增必要 `.app-health-*` CSS classes 到 styles.css。保留 AppHealth API flow、权限判断、刷新 interval、error 保留现有 dashboard、所有 FinanceTable grid names、负向后台任务控制契约。不得改后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run AppHealthOperationsPage.test.tsx`、`cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`、`cd web && npm run build`、`if rg -n '@mui/' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- FinanceTable surfaces preserved: yes。
- User-visible behavior preserved: yes，标题、刷新、loading/error/permission、三段 sections 和负向后台任务控制契约保留。
- Verification defined: targeted AppHealth Vitest、focused regression suite、build、AppHealth MUI grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `AppHealthOperationsPage.tsx` 已迁出 MUI Alert/Box/CircularProgress/IconButton/Stack/Tooltip/Typography/RefreshIcon。
- Page shell、header、refresh button、notice、section、inventory summary 和 responsive grids 已使用 HeroUI/native token classes。
- Phase 5 已迁 `FinanceTable` surfaces 保留，grid names 未变。
- AppHealth API flow、admin permission、refresh interval、error 保留当前 dashboard、负向后台任务控制契约未变。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run AppHealthOperationsPage.test.tsx`
  - `cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`

### MG-P030-phase-6-app-health

- Status: `verified`
- Scope:
  - `web/src/pages/AppHealthOperationsPage.tsx`
  - `web/src/test/AppHealthOperationsPage.test.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/modules/phase_6_app_health.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_app_health.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 AppHealth UI migration 文件：web/src/pages/AppHealthOperationsPage.tsx、web/src/test/AppHealthOperationsPage.test.tsx、web/src/app/styles.css、docs/refactor-ui/modules/phase_6_app_health.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 当前 MG scope 文件。验证命令：cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate app health ui。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified；下一条 prompt 进入 phase 6 import pages discovery。
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

- Commit: `814ad25c`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### P031-phase-6-import-pages-discovery

- Phase: `phase_6_page_batches`
- Status: `reviewed`
- Type: `discovery/planning`
- Scope: 只做导入页族 page-level discovery；不迁移实现。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/imports/ImportWorkflowPage.tsx、相关 import page files、相关 import tests 和 web/src/app/styles.css。只做导入页族 discovery/planning，不迁移实现。记录当前 MUI/DataGrid imports、ImportWorkflowPage 旧入口、上传/预览/确认/错误/进度/详情预览、DataGrid session 依赖、用户可见按钮与 overlay 形态、loading/empty/error/permission 状态、测试断言和风险。不得改后端/API/read model/worker/关联台。按需新建 docs/refactor-ui/modules/phase_6_import_pages.md；更新 state/prompt docs；运行文档/key grep、git diff --check、git status。
```

#### Review

- Single slice: yes。
- Runtime implementation untouched: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Docs on demand: yes，导入页族含共享 workflow、DataGrid preview/session 和多个 route，需要专项文档承载。
- Verification defined: docs/key grep、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- 新增 `docs/refactor-ui/modules/phase_6_import_pages.md`。
- 记录导入页族 route wrappers、`ImportWorkflowPage.tsx` MUI/DataGrid inventory、用户可见入口、现有测试覆盖和迁移风险。
- 生成下一条 `P032-phase-6-import-pages-characterization-tests` prompt。

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_import_pages.md`
  - `rg -n "P031-phase-6-import-pages-discovery|Current MUI Inventory|User-visible Entrypoints|P032-phase-6-import-pages-characterization-tests|DataGrid|银行账户冲突确认" docs/refactor-ui/modules/phase_6_import_pages.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
  - `git diff --check`
  - `git status --short --branch`

### P032-phase-6-import-pages-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `reviewed`
- Type: `characterization tests`
- Scope: 只调整 ImportCenterPage tests，锁定导入页族 HeroUI/native primitive contract；不改实现。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_import_pages.md、docs/refactor-ui/test_migration_strategy.md、web/src/test/ImportCenterPage.test.tsx、web/src/components/imports/ImportWorkflowPage.tsx、web/src/components/common/FinanceTable.tsx、web/src/components/common/AppDialog.tsx 和 web/src/app/styles.css。只修改 `web/src/test/ImportCenterPage.test.tsx`，新增或调整断言：standalone import page shell 使用 project class 且不是 MUI root；action bar 按钮位置/名称保留；upload zone 使用 project class 且不是 MUI Box；feedback/error/confirm notices 不是 `.MuiAlert-root`；audit summary cards 使用 project class；preview tables 使用 project/FinanceTable contract 而不是 `.MuiDataGrid-root`；detail tabs 使用 project/HeroUI tabs contract；银行账户冲突确认仍是 dialog 且不是 `.MuiDialog-root`。不得修改实现、后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run ImportCenterPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P033 shell/forms refactor prompt。
```

#### Review

- Single slice: yes。
- Runtime implementation untouched: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Characterization before implementation: yes。
- Expected failure acceptable: yes，旧 MUI/DataGrid roots 仍存在时 tests 应暴露缺口。
- Verification defined: targeted import Vitest、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `ImportCenterPage.test.tsx` 已新增 import shell、upload zone、notice、audit card、preview table、detail tabs 和 conflict dialog primitive contract。
- Targeted Vitest expected-failed with 7 failures because current implementation still renders MUI `Box`/`Paper`/`Alert` roots。
- 未修改 runtime implementation、后端、API、read model、worker、mock 或关联台。

#### Verification

- Status: verified expected-fail。
- Commands:
  - `cd web && npx vitest run ImportCenterPage.test.tsx`

### P033-phase-6-import-pages-shell-forms

- Phase: `phase_6_page_batches`
- Status: `reviewed`
- Type: `extraction/refactor`
- Scope: 迁移 ImportWorkflowPage page shell、header actions、notices、upload zone、file cards、select controls、audit summary cards 和 conflict dialog；暂不迁 DataGrid preview tables。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_import_pages.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/imports/ImportWorkflowPage.tsx、web/src/test/ImportCenterPage.test.tsx、web/src/components/common/AppDialog.tsx、web/src/app/styles.css。使用 HeroUI MCP Alert/Button/Chip/Select/Spinner/Modal docs 核对 API。把 ImportWorkflowPage 的 page shell、action bar、feedback/error/info/warning notices、upload zone、selected file cards、ETC task metadata chips、bank/invoice/ETC select controls、audit summary cards 和 bank conflict dialog 从 MUI 迁到 HeroUI/native/project classes。保留 PageScaffold、导入 API flow、draft/session restore、drag/drop、file input labels、existing DataGrid preview surfaces 和 useMuiDataGridPageSession。不得改后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run ImportCenterPage.test.tsx`，本切片结束后允许仍因 DataGrid/table/tabs primitive assertions expected-fail，但 shell/forms/cards/notices/dialog 相关 failures 必须消失；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P034 preview tables prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- DataGrid migration deferred: yes，P033 保留 preview DataGrid surfaces。
- User-visible behavior preserved: yes，导入 API、draft/session restore、drag/drop 和 labels 保留。
- Verification defined: targeted import Vitest expected partial fail allowed only for DataGrid/table/tabs assertions、`git diff --check`、`git status --short --branch`。

#### Execution Notes

- `ImportWorkflowPage.tsx` page shell、action bar、notices、upload zone、selected file cards、native selects、audit cards 和 bank conflict dialog 已迁到 HeroUI/native/project classes。
- `PageScaffold`、导入 API flow、draft/session restore、drag/drop、file input labels、DataGrid preview surfaces 和 `useMuiDataGridPageSession` 保留。
- `ImportCenterPage.test.tsx` targeted run 从 7 个 expected failures 降到 4 个，剩余 failures 全部是 preview DataGrid 还不是 `FinanceTable`。

#### Verification

- Status: verified partial expected-fail。
- Commands:
  - `cd web && npx vitest run ImportCenterPage.test.tsx`
  - `cd web && npm run build`

### P034-phase-6-import-pages-preview-tables

- Phase: `phase_6_page_batches`
- Status: `reviewed`
- Type: `extraction/refactor`
- Scope: 迁移导入页族 main preview、detail preview 和 ETC preview table surfaces；保留 shell/forms 和业务 flow。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_import_pages.md、docs/refactor-ui/modules/phase_5_table_system.md、web/src/components/imports/ImportWorkflowPage.tsx、web/src/test/ImportCenterPage.test.tsx、web/src/components/common/FinanceTable.tsx、web/src/hooks/useFinanceTableSession.ts 和 web/src/app/styles.css。使用 FinanceTable primitives 替换 `DataGrid`、`GridColDef`、`importGridSx`、`useMuiDataGridPageSession` 和 `useMuiDataGridScrollSession` 在导入页族中的使用，覆盖三类 preview table：`导入预览结果`、`重复项明细`/`未导入项明细`、`ETC导入预览结果`。保留表格 accessible names、关键 columnheader 文案、row text、loading/pending 语义、preview/detail tab 切换和用户可见数据。不得改后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run ImportCenterPage.test.tsx`，本切片结束后允许只剩 detail tabs primitive assertion failure；运行 focused table/common/platform tests、build、import scope MUI grep、git diff --check、git status。更新 state/prompt/module docs，生成 P035 detail tabs prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Shell/forms preserved: yes。
- User-visible table names and headers preserved: yes。
- Verification defined: targeted import Vitest with only detail tabs failure allowed, focused table/common/platform tests, build, MUI grep, `git diff --check`, `git status --short --branch`。

### MG-P031-phase-6-import-pages-discovery

- Status: `verified`
- Scope:
  - `docs/refactor-ui/modules/phase_6_import_pages.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_import_pages.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P031 import pages discovery 文档：docs/refactor-ui/modules/phase_6_import_pages.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：test -f docs/refactor-ui/modules/phase_6_import_pages.md；rg -n "P031-phase-6-import-pages-discovery|Current MUI Inventory|User-visible Entrypoints|P032-phase-6-import-pages-characterization-tests|DataGrid|银行账户冲突确认" docs/refactor-ui/modules/phase_6_import_pages.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md；git diff --check；git status --short --branch。提交信息使用 docs: add import pages migration discovery。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `adc8ce62`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### MG-P028-phase-6-app-health-discovery

- Status: `verified`
- Scope:
  - `docs/refactor-ui/modules/phase_6_app_health.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_app_health.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P028 AppHealth discovery 文档：docs/refactor-ui/modules/phase_6_app_health.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：test -f docs/refactor-ui/modules/phase_6_app_health.md；rg -n "P028-phase-6-app-health-discovery|Current MUI Inventory|Already Migrated Surfaces|User-visible Entrypoints|P029-phase-6-app-health-characterization-tests|RefreshIcon" docs/refactor-ui/modules/phase_6_app_health.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md；git diff --check；git status --short --branch。提交信息使用 docs: add app health migration discovery。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `1a806eeb`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### MG-P022-phase-6-tax-offset-discovery

- Status: `verified`
- Scope:
  - `docs/refactor-ui/modules/phase_6_tax_offset.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_tax_offset.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P022 TaxOffset discovery 文档：docs/refactor-ui/modules/phase_6_tax_offset.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：test -f docs/refactor-ui/modules/phase_6_tax_offset.md；rg -n "P022-phase-6-tax-offset-discovery|Current MUI Inventory|User-visible Entrypoints|P023-phase-6-tax-offset-characterization-tests|MuiDialog-root" docs/refactor-ui/modules/phase_6_tax_offset.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md；git diff --check；git status --short --branch。提交信息使用 docs: add tax offset migration discovery。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `c9b64d4d`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### MG-P021-phase-5-app-health-table-pilot-refactor

- Status: `verified`
- Scope:
  - `web/src/components/common/FinanceTable.tsx`
  - `web/src/pages/AppHealthOperationsPage.tsx`
  - `web/src/test/AppHealthOperationsPage.test.tsx`
  - `docs/refactor-ui/modules/phase_5_table_system.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P021 AppHealth table pilot 文件：web/src/components/common/FinanceTable.tsx、web/src/pages/AppHealthOperationsPage.tsx、web/src/test/AppHealthOperationsPage.test.tsx、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx；cd web && npm run build；if rg -n '@mui/material/(Table|TableBody|TableCell|TableContainer|TableHead|TableRow)' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate app health tables。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified；Phase 5 可标记 completed，下一条 prompt 进入 P022 phase 6 tax offset discovery。
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

- Commit: `b47f0689`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### MG-P020-phase-5-app-health-table-pilot-discovery

- Status: `verified`
- Scope:
  - `docs/refactor-ui/modules/phase_5_table_system.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、验证结果和文档状态。确认 scope 只包含 P020 discovery 文档文件：docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：rg -n "P020-phase-5-app-health-table-pilot-discovery|AppHealth Table Inventory|Inventory sources|Request performance|P021-phase-5-app-health-table-pilot-refactor" docs/refactor-ui/modules/phase_5_table_system.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md；git diff --check；git status --short --branch。提交信息使用 docs: add app health table pilot discovery。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `b9213d67`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### MG-P019-phase-5-table-session-primitive

- Status: `verified`
- Scope:
  - `web/src/hooks/useFinanceTableSession.ts`
  - `web/src/test/useFinanceTableSession.test.tsx`
  - `docs/refactor-ui/modules/phase_5_table_system.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P019 table session 文件：web/src/hooks/useFinanceTableSession.ts、web/src/test/useFinanceTableSession.test.tsx、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run useFinanceTableSession.test.tsx useMuiDataGridPageSession.test.tsx TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx；cd web && npm run build；if rg -n '@mui/' web/src/hooks/useFinanceTableSession.ts web/src/test/useFinanceTableSession.test.tsx web/src/components/common/FinanceTable.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: add finance table session primitive。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `230ca704`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### MG-P018-phase-5-finance-table-primitives

- Status: `verified`
- Scope:
  - `web/src/components/common/FinanceTable.tsx`
  - `web/src/app/styles.css`
  - `web/src/test/TableAlignmentStyles.test.ts`
  - `docs/refactor-ui/modules/phase_5_table_system.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P017/P018 finance table 文件：web/src/components/common/FinanceTable.tsx、web/src/app/styles.css、web/src/test/TableAlignmentStyles.test.ts、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx；cd web && npm run build；if rg -n '@mui/' web/src/components/common; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: add finance table primitives。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `aa8cbccb`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### MG-P016-phase-5-table-system-discovery

- Status: `verified`
- Scope:
  - `docs/refactor-ui/modules/phase_5_table_system.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 refactor_ui_state.md、refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、验证结果和文档状态。确认 scope 只包含 P016 discovery 文档文件：docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：test -f docs/refactor-ui/modules/phase_5_table_system.md；rg -n "P016-phase-5-table-system-discovery|DataGrid-heavy|MUI Table Dense Finance Tables|DirectionTag|AmountCell|useFinanceTableSession|P017-phase-5-table-characterization-tests" docs/refactor-ui/modules/phase_5_table_system.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md；git diff --check；git status --short --branch。提交信息使用 docs: add table system migration discovery。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified。
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

- Commit: `599a3d15`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

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

### P034-phase-6-import-pages-preview-tables

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 ImportWorkflowPage main preview、detail preview 和 ETC preview table surfaces。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_import_pages.md、docs/refactor-ui/modules/phase_5_table_system.md、web/src/components/imports/ImportWorkflowPage.tsx、web/src/test/ImportCenterPage.test.tsx、web/src/components/common/FinanceTable.tsx、web/src/hooks/useFinanceTableSession.ts 和 web/src/app/styles.css。使用 FinanceTable primitives 替换 DataGrid、GridColDef、importGridSx、useMuiDataGridPageSession 和 useMuiDataGridScrollSession 在导入页族中的使用，覆盖三类 preview table：导入预览结果、重复项明细/未导入项明细、ETC导入预览结果。保留表格 accessible names、关键 columnheader 文案、row text、loading/pending 语义、preview/detail tab 切换和用户可见数据。不得改后端、API、read model、worker、mock 或关联台。运行 cd web && npx vitest run ImportCenterPage.test.tsx，本切片结束后允许只剩 detail tabs primitive assertion failure；运行 focused table/common/platform tests、build、import scope MUI grep、git diff --check、git status。更新 state/prompt/module docs，生成 P035 detail tabs prompt。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Business flow preserved: yes。
- Table scope only: yes，P035 tabs 单独处理。
- Verification defined: targeted ImportCenterPage test，expected-fail 只允许 detail tabs。

#### Execution Notes

- Removed import-page usage of MUI X DataGrid, GridColDef, importGridSx and MUI DataGrid session hooks。
- Added `FinanceTable` renderers for main import preview, duplicate/unimported detail preview and ETC preview。
- Adjusted import-page primitive test helper to assert the `FinanceTable` root around HeroUI Table's `role=grid` content。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run ImportCenterPage.test.tsx`
- Result: expected-fail with 17 passed and 2 failures; both failures are detail tabs still rendered by MUI Tabs, which is the planned P035 scope。

### P035-phase-6-import-pages-detail-tabs

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 ImportWorkflowPage 导入预览明细 tabs。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_import_pages.md、web/src/components/imports/ImportWorkflowPage.tsx、web/src/test/ImportCenterPage.test.tsx 和 web/src/app/styles.css。使用 HeroUI Tabs 或项目 native tabs primitive 替换 @mui/material/Tabs 与 @mui/material/Tab，保留 导入预览明细 tablist accessible name、重复项 <n> / 未导入项 <n> 文案、selected tab state、用户点击切换 detail table 的行为和键盘可访问语义。不得改后端、API、read model、worker、mock、FinanceTable 数据映射或关联台。运行 cd web && npx vitest run ImportCenterPage.test.tsx 必须通过；运行 focused table/common/platform tests、build、import scope MUI grep、git diff --check、git status。更新 state/prompt/module docs；若导入页 scope 已无非冻结 MUI 残留，生成 MG-P035-phase-6-import-pages。
```

#### Review

- Single slice: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Table data untouched: yes。
- Overlay shape not involved: yes。
- Verification defined: targeted import test must pass, plus platform/table/build and MUI grep before MG。

#### Execution Notes

- Removed `@mui/material/Tabs` and `@mui/material/Tab` from `ImportWorkflowPage.tsx`。
- Replaced detail tabs with HeroUI `Tabs` compound components and project classes。
- Preserved `导入预览明细` accessible tablist name, duplicate/unimported counts and selected tab state。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run ImportCenterPage.test.tsx`
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/|Mui[A-Z]|MuiDataGrid|DataGrid|GridColDef|useMuiDataGrid' web/src/components/imports web/src/pages/imports; then exit 1; else exit 0; fi`
  - `if rg -n '@mui/' web/src/test/ImportCenterPage.test.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
- Result: passed. ImportCenterPage still emits known HeroUI Tooltip focusable warnings from truncated text triggers, but all assertions pass and no MUI remains in import runtime scope。

### MG-P035-phase-6-import-pages

- Status: `verified`
- Scope:
  - `web/src/components/imports/ImportWorkflowPage.tsx`
  - `web/src/app/styles.css`
  - `web/src/test/ImportCenterPage.test.tsx`
  - `docs/refactor-ui/modules/phase_6_import_pages.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_import_pages.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 Import pages migration 文件：web/src/components/imports/ImportWorkflowPage.tsx、web/src/app/styles.css、web/src/test/ImportCenterPage.test.tsx、docs/refactor-ui/modules/phase_6_import_pages.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run ImportCenterPage.test.tsx；cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/|Mui[A-Z]|MuiDataGrid|DataGrid|GridColDef|useMuiDataGrid' web/src/components/imports web/src/pages/imports; then exit 1; else exit 0; fi；if rg -n '@mui/' web/src/test/ImportCenterPage.test.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate import workflow ui。push 到 refactor-ui 分支。完成后更新 refactor_ui_state.md、refactor_ui_prompt.md 和 Push Log，标记 MG verified，并从 refactor-ui 分支生成下一条 Phase 6 prompt。
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

- Commit: `9e3624a0`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。

### P036-phase-6-cost-statistics-discovery

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `discovery/planning`
- Scope: 成本统计 `/cost-statistics` 页面迁移 discovery，只读代码和测试并建立模块文档。

#### Prompt

```text
Prompt ID: P036-phase-6-cost-statistics-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: 只做 CostStatistics 页面 discovery，不改运行时代码。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、DESIGN.md、PRODUCT.md、web/src/pages/CostStatisticsPage.tsx、web/src/test/CostStatisticsPage.test.tsx、相关 cost-statistics 组件/feature 文件和当前 git status。梳理 `/cost-statistics` 的旧 UI 入口、MUI/DataGrid/session hook inventory、表格/详情弹窗/导出弹窗/筛选控件/月份或范围控件/loading empty error stale permission 状态、现有测试覆盖和迁移切片风险。不得修改实现、测试、后端、API、read model、worker 或关联台。若 discovery 需要跨后续切片复用，创建 docs/refactor-ui/modules/phase_6_cost_statistics.md。更新 refactor_ui_state.md、refactor_ui_prompt.md 和模块文档，生成下一条 P037 characterization tests prompt。验证命令：test -f docs/refactor-ui/modules/phase_6_cost_statistics.md；rg -n "P036-phase-6-cost-statistics-discovery|Current MUI Inventory|User-visible Entrypoints|P037-phase-6-cost-statistics-characterization-tests" docs/refactor-ui/modules/phase_6_cost_statistics.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md；git diff --check；git status --short --branch。
```

#### Review

- Single slice: yes。
- Discovery only: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- User-visible entry inventory required: yes。
- Docs on demand: yes，CostStatistics 是 high-risk DataGrid/dialog/export 页面，需要专项 md。
- Verification defined: docs existence/key phrase checks、diff check、status。

#### Execution Notes

- 新增 `docs/refactor-ui/modules/phase_6_cost_statistics.md`。
- 记录 CostStatistics runtime MUI inventory：`CostStatisticsTable` 的 MUI X DataGrid、page-level `useMuiDataGridPageSession` / `useMuiDataGridScrollSession`、test wrapper 的 `MuiProviders`。
- 记录已是 project-owned 的子组件：`CostExplorerList`、`CostStatisticsSummaryCards`、`CostTransactionDetailModal`、`ExportCenterModal`。
- 生成 P037 characterization tests prompt。

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_cost_statistics.md`
  - `rg -n "P036-phase-6-cost-statistics-discovery|Current MUI Inventory|User-visible Entrypoints|P037-phase-6-cost-statistics-characterization-tests" docs/refactor-ui/modules/phase_6_cost_statistics.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
  - `git diff --check`
  - `git status --short --branch`

### P037-phase-6-cost-statistics-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `characterization tests`
- Scope: 只更新 CostStatisticsPage tests，锁定成本统计页非 MUI/project primitive contract；不改实现。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_cost_statistics.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/CostStatisticsPage.tsx、web/src/components/cost-statistics/CostStatisticsTable.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/test/CostStatisticsPage.test.tsx。只修改 web/src/test/CostStatisticsPage.test.tsx，新增或调整断言：页面 shell/summary cards/view switcher/scope panels 保留 project classes；按时间统计表、项目对应流水表、银行对应流水表、按费用类型流水表 使用 project/FinanceTable contract 且不是 .MuiDataGrid-root；流水详情 和 导出中心 仍是 dialog 且不是 MUI dialog；测试渲染 wrapper 的 MUI provider 依赖作为待迁移缺口记录。不得修改实现、后端、API、read model、worker、mock 或关联台。运行 cd web && npx vitest run CostStatisticsPage.test.tsx，实现未迁移前 expected-fail 可接受；运行 git diff --check、git status --short --branch。更新 state/prompt/module docs，生成 P038 table migration prompt。
```

#### Review

- Single slice: yes。
- Test-only: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Behavior contract preserved: yes。
- Expected failure acceptable: yes，CostStatisticsTable still renders MUI X DataGrid before P038。

#### Execution Notes

- Updated `CostStatisticsPage.test.tsx` with project primitive assertions for cost shell, view switcher, scope controls, table surfaces and detail/export dialogs。
- Added table assertions that currently fail until `CostStatisticsTable` is migrated to `FinanceTable`。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run CostStatisticsPage.test.tsx`
- Result: expected-fail with 11 passed and 4 failures. All failures are `expectProjectCostTable` assertions because current tables are still MUI X DataGrid。

### P038-phase-6-cost-statistics-table-migration

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 CostStatisticsTable 从 MUI X DataGrid 到 FinanceTable，保留 CostStatisticsPage 业务 flow。

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_cost_statistics.md、docs/refactor-ui/table_layout_system.md、web/src/components/cost-statistics/CostStatisticsTable.tsx、web/src/pages/CostStatisticsPage.tsx、web/src/test/CostStatisticsPage.test.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/app/styles.css。只迁移 CostStatisticsTable.tsx 的表格实现和必要样式：移除 MUI X DataGrid、GridColDef、GridRowParams、.MuiDataGrid-* sx 和 MuiDataGridScrollSessionBinding prop；使用 FinanceTable primitives 保留 ariaLabel、column headers、empty label、row click、首列 查看流水 <id> action、amount/direction/account stack、row text 和 visible height/scroll behavior。暂不改 CostStatisticsPage 的 useMuiDataGridPageSession 调用，除非类型必须同步去除；如去除，必须不改变 view/scope page session state。不得改后端、API、read model、worker、mock 或关联台。运行 cd web && npx vitest run CostStatisticsPage.test.tsx，本切片结束后 P037 table primitive assertions 必须通过；如果只剩 test wrapper 的 MuiProviders/page session hook cleanup，记录为 P039。运行 focused table/common/platform tests、build、cost statistics runtime MUI grep、git diff --check、git status。更新 state/prompt/module docs，生成 P039 cleanup/MG prompt。
```

#### Review

- Single slice: yes。
- Runtime scope focused on one table component: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Business flow preserved: yes。
- Verification defined: CostStatistics targeted test, platform/table tests, build, scope grep, diff check。

#### Execution Notes

- Migrated `CostStatisticsTable.tsx` from MUI X DataGrid to `FinanceTable`。
- Removed `DataGrid`、`GridColDef`、`GridRowParams`、MUI DataGrid `sx` selectors and MUI scroll session type from the table component。
- Removed `useMuiDataGridPageSession` / `useMuiDataGridScrollSession` from `CostStatisticsPage.tsx` because the table no longer accepts MUI session binding。
- Preserved accessible grid names, column headers, empty label, first-column action button, row click, amount/direction/account stack and detail modal flow。
- Remaining `MuiProviders` in `CostStatisticsPage.test.tsx` is required by shared `MonthPicker`, not by CostStatistics table runtime; shared MonthPicker cleanup must be handled in a later shared/global prompt。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run CostStatisticsPage.test.tsx`
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`
  - `cd web && npm run build`
  - `if rg -n '@mui/|Mui[A-Z]|MuiDataGrid|DataGrid|GridColDef|useMuiDataGrid' web/src/pages/CostStatisticsPage.tsx web/src/components/cost-statistics; then exit 1; else exit 0; fi`
  - `if rg -n 'cost-data-grid-shell|\.cost-data-grid-shell|\.MuiDataGrid' web/src/components/cost-statistics web/src/pages/CostStatisticsPage.tsx web/src/test/CostStatisticsPage.test.tsx; then exit 1; else exit 0; fi`
  - `git diff --check`
- Result: passed. Build has known HeroUI/Tailwind CSS minifier warnings and chunk size warning。

### MG-P038-phase-6-cost-statistics-table-migration

- Status: `verified`
- Scope:
  - `web/src/components/common/FinanceTable.tsx`
  - `web/src/components/cost-statistics/CostStatisticsTable.tsx`
  - `web/src/pages/CostStatisticsPage.tsx`
  - `web/src/app/styles.css`
  - `web/src/test/CostStatisticsPage.test.tsx`
  - `docs/refactor-ui/modules/phase_6_cost_statistics.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`

#### Prompt

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_cost_statistics.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P037/P038 文件：web/src/components/common/FinanceTable.tsx、web/src/components/cost-statistics/CostStatisticsTable.tsx、web/src/pages/CostStatisticsPage.tsx、web/src/app/styles.css、web/src/test/CostStatisticsPage.test.tsx、docs/refactor-ui/modules/phase_6_cost_statistics.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run CostStatisticsPage.test.tsx；cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/|Mui[A-Z]|MuiDataGrid|DataGrid|GridColDef|useMuiDataGrid' web/src/pages/CostStatisticsPage.tsx web/src/components/cost-statistics; then exit 1; else exit 0; fi；if rg -n 'cost-data-grid-shell|\.cost-data-grid-shell|\.MuiDataGrid' web/src/components/cost-statistics web/src/pages/CostStatisticsPage.tsx web/src/test/CostStatisticsPage.test.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate cost statistics table ui。push 到 refactor-ui 分支。完成后更新 docs 状态和 Push Log，标记 MG verified，并生成下一条 Phase 6 module prompt。
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

- Commit: `4baffcff`
- Push: `refactor-ui -> origin/refactor-ui`
- Result: verified。
- Note: shared `MonthPicker` still uses MUI and keeps `CostStatisticsPage.test.tsx` on `MuiProviders`; this is not a CostStatistics table residue and must be handled by a shared/global cleanup prompt。

### P040-phase-6-bank-details-discovery

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `discovery/planning`
- Scope: 银行明细 `/bank-details` 页面迁移 discovery，只读代码和测试并建立模块文档。

#### Prompt

```text
Prompt ID: P040-phase-6-bank-details-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: 只做 BankDetails 页面 discovery，不改运行时代码。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、DESIGN.md、PRODUCT.md、web/src/pages/BankDetailsPage.tsx、web/src/features/bankDetails/*、web/src/test/BankDetailsPage.test.tsx、web/src/test/AutoTagRulesDrawer.test.tsx 和当前 git status。梳理 `/bank-details` 的旧 UI 入口、MUI inventory、表格/分页/日期筛选/导出菜单/分类筛选 popover/自动标签规则右侧抽屉/弹窗/loading empty error permission 状态、现有测试覆盖和迁移切片风险。不得修改实现、测试、后端、API、read model、worker 或关联台。若 discovery 需要跨后续切片复用，创建 docs/refactor-ui/modules/phase_6_bank_details.md。更新 refactor_ui_state.md、refactor_ui_prompt.md 和模块文档，生成下一条 P041 characterization tests prompt。验证命令：test -f docs/refactor-ui/modules/phase_6_bank_details.md；rg -n "P040-phase-6-bank-details-discovery|Current MUI Inventory|User-visible Entrypoints|P041-phase-6-bank-details-characterization-tests" docs/refactor-ui/modules/phase_6_bank_details.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md；git diff --check；git status --short --branch。
```

#### Review

- Single slice: yes。
- Discovery only: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Behavior equivalence required: yes，旧导出菜单/分类 popover/右侧抽屉形态必须记录。
- Docs on demand: yes，BankDetails 是 high-risk table + drawer + popover 页面，需要专项 md。
- Verification defined: docs existence/key phrase checks、diff check、status。

#### Execution Notes

- 新增 `docs/refactor-ui/modules/phase_6_bank_details.md`。
- 记录 BankDetails runtime MUI inventory：页面 layout/account list/date Popover/export menu/category filter Popper/transaction table/TablePagination/TypeCell Popper/Internal transfer tooltip/BankCategoryTag。
- 记录 AutoTagRulesDrawer runtime MUI inventory：right Drawer、wide rule table、form controls、active/archived tabs、condition editor dialog、archive confirmation dialog、MUI icons。
- 记录用户可见入口、现有测试覆盖、测试迁移缺口、后续 P041-P045 切片和 MG 边界。
- 本切片只改文档，不修改前端实现、测试、mock、后端、API、read model、worker 或关联台。

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_bank_details.md`
  - `rg -n "P040-phase-6-bank-details-discovery|Current MUI Inventory|User-visible Entrypoints|P041-phase-6-bank-details-characterization-tests" docs/refactor-ui/modules/phase_6_bank_details.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
  - `git diff --check`
  - `git status --short --branch`

### P041-phase-6-bank-details-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `characterization tests`
- Scope: 只更新 BankDetails 和 AutoTagRulesDrawer tests，锁定银行明细页非 MUI/project primitive contract；不改实现。

#### Prompt

```text
Prompt ID: P041-phase-6-bank-details-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只更新 BankDetails 和 AutoTagRulesDrawer tests，锁定银行明细页非 MUI/project primitive contract；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_bank_details.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BankDetailsPage.tsx、web/src/features/bankDetails/AutoTagRulesDrawer.tsx、web/src/features/bankDetails/BankCategoryTag.tsx、web/src/components/common/FinanceTable.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/test/BankDetailsPage.test.tsx 和 web/src/test/AutoTagRulesDrawer.test.tsx。只修改 `web/src/test/BankDetailsPage.test.tsx` 和 `web/src/test/AutoTagRulesDrawer.test.tsx`：把 source/CSS 中 MUI class assertions 改成 project primitive assertions；新增断言锁定 bank details root/account sidebar/transaction table/pagination/date Popover/export menu/category filter Popper/row type Popper/internal transfer tooltip/auto tag rules right drawer/condition dialog/archive dialog 均保留旧 accessible labels 和旧交互形态，且 migrated root 不再是 `.Mui*`。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P042 shell-toolbar-dates prompt。
```

#### Review

- Single slice: yes。
- Test-only: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Behavior contract preserved: yes，锁定旧 right drawer、dialogs、menus、Popper、table、pagination 和 date Popover 形态。
- Expected failure acceptable: yes，BankDetails runtime still renders MUI roots before P042-P045。
- Verification defined: targeted BankDetails/AutoTagRulesDrawer Vitest, diff check, status。

#### Execution Notes

- Updated `BankDetailsPage.test.tsx`:
  - Added `findBankTransactionSurface` to accept native `table` or HeroUI `grid` while preserving accessible name `交易流水`。
  - Replaced source-level MUI Table contract with target `FinanceTable` / non-MUI menu/date/drawer/dialog/tag source contract。
  - Replaced MUI chip class assertions with project class assertions。
  - Replaced BankDetails CSS MUI selectors with project selector contracts。
  - Stabilized custom date input test by firing `input` before `blur`。
- Updated `AutoTagRulesDrawer.test.tsx`:
  - Added `findAutoTagRuleSurface` to accept native `table` or HeroUI `grid` while preserving accessible name `自动标签规则表格`。
  - Added source-level `AppDrawer` / `AppDialog` / non-MUI table/form/icon contract。
  - Replaced MUI table/button/input CSS selector assertions with project selector contracts。

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run BankDetailsPage.test.tsx -t "selecting account and filters request accounts and transactions with the same date range"`: passed。
  - `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`: expected-fail with 47 passed and 5 failures. Failures are target project primitive contracts against current MUI runtime/CSS。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed。

### P042-phase-6-bank-details-shell-toolbar-dates

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 BankDetails 页面壳、账户列表、顶部工具栏、日期筛选、导出菜单和搜索输入；不迁移交易表格、TypeCell、BankCategoryTag 或 AutoTagRulesDrawer。

#### Prompt

```text
Prompt ID: P042-phase-6-bank-details-shell-toolbar-dates
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: 迁移 BankDetails 页面壳、账户列表、顶部工具栏、日期筛选、导出菜单和搜索输入；不迁移交易表格、TypeCell、BankCategoryTag 或 AutoTagRulesDrawer。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_bank_details.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BankDetailsPage.tsx、web/src/test/BankDetailsPage.test.tsx、web/src/components/common/StatePanel.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx 和 web/src/app/styles.css。只修改 `BankDetailsPage.tsx`、必要的 `styles.css` 和必要的 BankDetails test expectations：移除页面壳、账户 sidebar、header controls、date presets/date Popover、export menu/search toolbar 的 MUI layout/input/button/menu/date imports；使用 HeroUI/Tailwind/project primitives 或 native `input[type=month/date]` 保留旧布局、旧 labels、旧 query params、旧 export payload、旧 search behavior、旧 loading/empty/error feedback。不得迁移交易 table/TablePagination、TypeCell category Popper、BankCategoryTag、internal transfer tooltip、AutoTagRulesDrawer；不得修改后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run BankDetailsPage.test.tsx -t "loads all accounts|requests the current year|renders accounts|uses Chinese labels|selecting account and filters|exports all banks"`；运行完整 `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`，P041 中与 table/category/drawer 相关 failures 可以继续 expected-fail，但 shell/toolbar/date/export failures 必须清除；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P043 transaction table prompt。
```

#### Review

- Single slice: yes。
- Runtime scope limited to BankDetails shell/toolbar/date/export/search: yes。
- Excludes transaction table/pagination: yes，reserved for P043。
- Excludes category popovers/TypeCell/BankCategoryTag: yes，reserved for P044。
- Excludes AutoTagRulesDrawer: yes，reserved for P045。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Verification defined: focused BankDetails tests, full expected-fail target set, diff check, status。

#### Execution Notes

- Migrated BankDetails outer page shell, two-column workbench layout, account sidebar, transaction panel header, date presets/date popover, export menu and search field from MUI layout/input/menu/date primitives to native semantic markup plus project classes.
- Preserved old visible labels and behavior: `银行账户`, `自动标签规则`, `日期快捷筛选`, `年月筛选`, `开始日期`, `结束日期`, `导出银行明细`, `导出全部银行`, `导出当前账户` and `搜索流水`.
- Replaced MUI X DatePicker/dayjs path with native `input[type=month]` and `input[type=date]` inputs while preserving the existing request values and blur/input handlers.
- Left transaction table/TablePagination, category filter Popper, TypeCell menu internals, BankCategoryTag/internal transfer tooltip and AutoTagRulesDrawer unchanged for P043-P045.

#### Verification

- Status: verified。
- Commands:
  - `git diff --check`: passed。
  - `cd web && npx vitest run BankDetailsPage.test.tsx -t "loads all accounts|requests the current year|renders accounts|uses Chinese labels|selecting account and filters|exports all banks"`: passed, 6 passed / 32 skipped。
  - `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`: expected-fail with 47 passed and 5 failures. Remaining failures are assigned to P043 table/pagination, P044 category popovers and P045 auto tag drawer。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/material/(Popover|TextField|ToggleButton|ToggleButtonGroup)|@mui/x-date-pickers|dayjs|RuleIcon|exportMenuAnchorEl' web/src/pages/BankDetailsPage.tsx; then exit 1; else exit 0; fi`: passed。
  - Broad menu grep still finds `@mui/material/MenuList` for P044 `TypeCell`, which is outside P042 scope and deferred。

### P043-phase-6-bank-details-transaction-table

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 BankDetails 交易流水表格和分页；不迁移 category filter Popper、TypeCell、BankCategoryTag、internal transfer tooltip 或 AutoTagRulesDrawer。

#### Prompt

```text
Prompt ID: P043-phase-6-bank-details-transaction-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: 迁移 BankDetails 交易流水表格和分页；不迁移 category filter Popper、TypeCell、BankCategoryTag、internal transfer tooltip 或 AutoTagRulesDrawer。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_bank_details.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BankDetailsPage.tsx、web/src/test/BankDetailsPage.test.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/app/styles.css。只修改 BankDetailsPage.tsx、必要的 styles.css 和必要的 BankDetails test expectations：移除交易流水表格区域的 MUI Table/TableContainer/TableHead/TableBody/TableRow/TableCell/TablePagination imports 和 usage；使用 FinanceTable/project pagination 保留 accessible name `交易流水`、headers、loading row `正在加载流水。`、empty row `当前时间范围内没有流水。`、row classes、counterparty cell、TypeCell 嵌入位置、amount/balance tabular numeric alignment、direction/source chip vertical alignment、server page/pageSize/total behavior、pagination labels `每页行数`、`1-100 / 299`、`下一页` 和 page size options `[25, 50, 100]`。不得修改后端、API、read model、worker、mock 或关联台。不得迁移 category filter Popper、TypeCell menu internals、BankCategoryTag/internal transfer tooltip 或 AutoTagRulesDrawer；这些仍归属 P044/P045。运行 `cd web && npx vitest run BankDetailsPage.test.tsx -t "交易流水|pagination|searches current account|loads all accounts|uses Chinese labels"`；运行完整 `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`，P044/P045 category/drawer failures 可以继续 expected-fail，但 P043 table/pagination failures 必须清除；运行 `cd web && npm run build`；运行 BankDetails transaction-table MUI import grep、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P044 category popovers prompt。
```

#### Review

- Single slice: yes。
- Runtime scope limited to transaction table and pagination: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Preserves old table behavior: yes，headers、loading/empty、row layout、server pagination and page size options are explicit。
- Excludes category/type/tag/drawer surfaces: yes，reserved for P044/P045。
- Verification defined: focused table/pagination tests, full expected-fail target set, build, MUI import grep, diff check, status。

#### Execution Notes

- Replaced BankDetails transaction table MUI `Table`/`TableContainer`/`TableHead`/`TableBody`/`TableRow`/`TableCell` usage with `FinanceTable` primitives.
- Replaced MUI `TablePagination` with a BankDetails project pagination bar preserving `每页行数`, `1-100 / 299`, `上一页`, `下一页` and `pageSizeOptions={[25, 50, 100]}`.
- Preserved the original seven headers, accessible table name `交易流水`, loading text `正在加载流水。`, empty text `当前时间范围内没有流水。`, TypeCell placement, counterparty/time/relation stack, amount/direction/source stack, balance formatting and server pagination state.
- Left category filter Popper, TypeCell menu internals, BankCategoryTag/internal transfer tooltip and AutoTagRulesDrawer unchanged for P044/P045.

#### Verification

- Status: verified。
- Commands:
  - `if rg -n '@mui/material/(Table|TableBody|TableCell|TableContainer|TableHead|TablePagination|TableRow)' web/src/pages/BankDetailsPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run BankDetailsPage.test.tsx -t "交易流水|pagination|searches current account|loads all accounts|uses Chinese labels"`: passed, 4 passed / 34 skipped。
  - `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`: expected-fail with 48 passed and 4 failures. Remaining failures are assigned to P044 category popovers and P045 auto tag drawer。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests。
  - `if rg -n '@mui/material/(Table|TableBody|TableCell|TableContainer|TableHead|TablePagination|TableRow)|bank-transaction-pagination\.MuiTablePagination|bank-transaction-table .*MuiTable|\.bank-transaction-table .*MuiTable' web/src/pages/BankDetailsPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。

### P044-phase-6-bank-details-category-popovers

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 BankDetails category filter Popper、TypeCell category confirmation/assignment Popper、BankCategoryTag 和 internal transfer tooltip；不迁移 AutoTagRulesDrawer。

#### Prompt

```text
Prompt ID: P044-phase-6-bank-details-category-popovers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: 迁移 BankDetails category filter Popper、TypeCell category confirmation/assignment Popper、BankCategoryTag 和 internal transfer tooltip；不迁移 AutoTagRulesDrawer。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_bank_details.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BankDetailsPage.tsx、web/src/features/bankDetails/BankCategoryTag.tsx、web/src/test/BankDetailsPage.test.tsx 和 web/src/app/styles.css。只修改 BankDetailsPage.tsx、BankCategoryTag.tsx、必要 styles.css 和必要 BankDetails test expectations：移除 BankDetailsPage 中 category filter、TypeCell 和 internal transfer tooltip 相关的 MUI Popper/MenuList/List/ListItem/ListItemButton/ListItemText/IconButton/Paper/Divider/Button/Tooltip/Box/Typography/Stack 依赖中属于本切片的用法；使用 project/native popover/menu/button/tooltip/tag markup 或 HeroUI primitives 保留旧点击触发、Escape/外部点击关闭、`银行明细标签筛选` menu、`标签筛选：...` trigger、三列 dense hierarchy、`aria-current`、`data-level`、`待确认`/`待分类` staged save flow、`取消`/`保存`/`保存中`、third-level external turnover choices、`撤销`、`对应内部往来流水` tooltip rows 和 BankCategoryTag hierarchy tooltip。不得修改后端、API、read model、worker、mock、AutoTagRulesDrawer 或关联台。运行 `cd web && npx vitest run BankDetailsPage.test.tsx -t "category|internal transfer|manual classification|needs-confirmation|external turnover|targets project table|dense three-column"`；运行完整 `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`，P045 drawer failures 可以继续 expected-fail，但 P044 category/tag/popper failures 必须清除；运行 `cd web && npm run build`；运行 BankDetails category/tooltip MUI residue grep、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P045 auto tag drawer prompt。
```

#### Review

- Single slice: yes。
- Runtime scope limited to category filter, TypeCell category popovers, BankCategoryTag and internal transfer tooltip: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Preserves old overlay shape: yes，category filter and TypeCell remain click popovers/menus, internal transfer remains tooltip。
- Excludes AutoTagRulesDrawer: yes，reserved for P045。
- Verification defined: focused category/tooltip tests, full expected-fail target set, build, MUI residue grep, diff check, status。

#### Execution Notes

- Replaced BankDetails category filter MUI Popper/List/IconButton/Paper stack with project/native trigger, menu and dense three-column hierarchy markup.
- Replaced TypeCell MUI Popper/MenuList/ListItemButton flow with project/native popover menus while preserving staged choice, `待确认`/`待分类`, `取消`, `保存`, `保存中`, and third-level external turnover choices.
- Replaced internal transfer MUI Tooltip with project hover/focus tooltip keeping `role="tooltip"` and structured rows.
- Replaced `BankCategoryTag` MUI Chip/Tooltip with project span tag and project hierarchy tooltip.
- Left `AutoTagRulesDrawer` unchanged for P045.

#### Verification

- Status: verified。
- Commands:
  - `if rg -n '@mui/material/(Popper|MenuList|Menu|Tooltip)|@mui/icons-material/FilterListOutlined|@mui/material/(ClickAwayListener|IconButton|List|ListItem|ListItemButton|ListItemText|Paper)' web/src/pages/BankDetailsPage.tsx web/src/features/bankDetails/BankCategoryTag.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run BankDetailsPage.test.tsx -t "category|internal transfer|manual classification|needs-confirmation|external turnover|targets project table|dense three-column"`: expected-fail only on P045 drawer source assertion; all P044 category/tag/tooltip/TypeCell behavior tests passed。
  - `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`: expected-fail with 49 passed and 3 failures. Remaining failures are assigned to P045 AutoTagRulesDrawer。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests。
  - `git diff --check`: passed。

### P045-phase-6-bank-details-auto-tag-drawer

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 迁移 AutoTagRulesDrawer 到 AppDrawer/AppDialog、FinanceTable/project form controls 和 lucide/project icons；不改 BankDetails page 已迁移 surfaces。

#### Prompt

```text
Prompt ID: P045-phase-6-bank-details-auto-tag-drawer
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: 迁移 AutoTagRulesDrawer 到 AppDrawer/AppDialog、FinanceTable/project form controls 和 lucide/project icons；不改 BankDetails page 已迁移 surfaces。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_bank_details.md、docs/refactor-ui/table_layout_system.md、web/src/features/bankDetails/AutoTagRulesDrawer.tsx、web/src/test/AutoTagRulesDrawer.test.tsx、web/src/test/BankDetailsPage.test.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/app/styles.css。只修改 AutoTagRulesDrawer.tsx、必要 styles.css 和必要 tests：移除 AutoTagRulesDrawer 的 MUI Drawer/Dialog/Table/TextField/Select/Checkbox/Button/IconButton/Alert/Progress/Tooltip/icons 依赖；使用 AppDrawer 保留右侧抽屉、`自动标签规则` dialog name、关闭按钮、版本/readonly text、active/archived tabs、toolbar actions `新增标签`/`重新应用规则`/`保存`、loading/error/feedback；使用 FinanceTable/project table 保留 `自动标签规则表格`、system row priority 1、active rule wide editor columns、match fields `全选`/`清空`、condition editor dialog `取消`/`确定`、archive confirmation dialog `确认停用标签`、archived empty/re-enable flow、save/reapply payloads and dirty validation behavior。不得修改后端、API、read model、worker、mock、BankDetails page migrated surfaces 或关联台。运行 `cd web && npx vitest run AutoTagRulesDrawer.test.tsx`；运行 `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`，P045 结束后 full target set 必须通过；运行 `cd web && npm run build`；运行 BankDetails scope MUI grep、CSS MUI selector residue grep、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，并生成 `MG-P045-phase-6-bank-details` prompt。
```

#### Review

- Single slice: yes。
- Runtime scope limited to AutoTagRulesDrawer: yes。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Preserves old overlay shape: yes，right drawer stays right drawer; condition/archive overlays stay dialogs。
- Verification defined: drawer tests, full BankDetails target set, build, MUI residue grep, diff check, status。

#### Execution Notes

- Extended `AppDrawer` with optional class name, close label and string width support so migrated right drawers can keep old width and accessible close labels without custom drawer shells。
- Replaced `AutoTagRulesDrawer` MUI Drawer/Dialog/Table/TextField/Select/Checkbox/Button/IconButton/Alert/Progress/Tooltip/icons with `AppDrawer`, `AppDialog`, native/project table and form controls, and lucide icons。
- Kept the right drawer accessible name `自动标签规则`, close button `关闭自动标签规则抽屉`, active/archived tabs, toolbar actions, loading/error/feedback messages, wide rule table, condition editor dialog, archive confirmation dialog, archived restore flow, validation, save payload and reapply endpoint behavior。
- Removed the final BankDetails page MUI `Button`/`Chip`/`Stack`/`Typography` usages in ordinary table cells and manual category state while preserving class names and user-visible layout。
- Removed BankDetails/bank-auto-tag CSS MUI selector residue and replaced chip/table/form selectors with project classes。

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run AutoTagRulesDrawer.test.tsx`: passed, 14 tests。
  - `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`: passed, 52 tests。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui|Mui|<Button|<Chip|<Stack|<Typography' web/src/pages/BankDetailsPage.tsx web/src/features/bankDetails/AutoTagRulesDrawer.tsx web/src/features/bankDetails/BankCategoryTag.tsx; then exit 1; else exit 0; fi`: passed。
  - `if rg -n 'bank-details-page[^\n]*Mui|bank-[^\n]*Mui|Mui[^\n]*bank-|bank-auto-tag[^\n]*Mui|Mui[^\n]*bank-auto-tag' web/src/app/styles.css; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。

### MG-P045-phase-6-bank-details

- Phase: `phase_6_page_batches`
- Status: `mg_verified`
- Type: `cumulative MG`
- Scope: BankDetails module P040-P045 discovery, characterization tests, shell/toolbar/date/export/search, transaction table/pagination, category popovers/tags/tooltips, AutoTagRulesDrawer and associated styles/common drawer extension。

#### Prompt

```text
Prompt ID: MG-P045-phase-6-bank-details
Phase: phase_6_page_batches
Type: cumulative MG
Scope: BankDetails module P040-P045 only: docs/refactor-ui BankDetails state/prompt/module docs, AppDrawer compatibility extension, BankDetailsPage non-MUI UI, BankCategoryTag, AutoTagRulesDrawer, BankDetails tests and required styles. Do not include backend, API, read model, worker, reconciliation workbench internals, unrelated pages or unrelated generated files.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_bank_details.md、docs/refactor-ui/table_layout_system.md、当前 git status 和当前 diff。检查当前分支必须是 `refactor-ui`。确认 untracked files、diff scope、测试结果和文档状态；确认 BankDetails runtime scope no MUI grep 和 BankDetails CSS no MUI selector residue grep 已通过；确认 `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`、`cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`、`cd web && npm run build` 已通过。只允许精确 `git add docs/refactor-ui/refactor_ui_state.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/modules/phase_6_bank_details.md web/src/app/styles.css web/src/components/common/AppDrawer.tsx web/src/features/bankDetails/AutoTagRulesDrawer.tsx web/src/pages/BankDetailsPage.tsx`；如实际 diff 包含 BankDetails test 文档变更，也必须逐个精确列出，禁止 `git add .` 或 `git add -A`。commit message 使用 `feat: migrate bank details auto tag drawer` 或更准确的 BankDetails module message。push 到 `origin refactor-ui`。完成后更新 state/prompt/module docs 的 MG execution notes、verification、Push Log，标记 MG verified，并从 `refactor-ui` 分支继续生成下一条 Micro-JIT prompt。
```

#### Review

- Single MG boundary: yes，BankDetails module only。
- Scope guard: yes，explicit allowed files and exact staging only。
- Backend/API/read model/worker untouched: yes。
- Workbench internals frozen: yes。
- Verification required before push: yes，BankDetails target tests, common/table/platform regressions, build, MUI residue greps and diff check。
- Push target: `origin refactor-ui`。

#### Execution Notes

- Exact staged files: `docs/refactor-ui/refactor_ui_state.md`, `docs/refactor-ui/refactor_ui_prompt.md`, `docs/refactor-ui/modules/phase_6_bank_details.md`, `web/src/app/styles.css`, `web/src/components/common/AppDrawer.tsx`, `web/src/features/bankDetails/AutoTagRulesDrawer.tsx`, `web/src/pages/BankDetailsPage.tsx`。
- Commit: `9a0b74ea feat: migrate bank details auto tag drawer`。
- Push: `origin/refactor-ui` updated from `f6d96346` to `9a0b74ea`。

#### Verification

- Status: mg_verified。
- Commands:
  - `git diff --check`: passed before exact staging。
  - `git diff --cached --name-only`: confirmed only the seven BankDetails MG files were staged。
  - `git push origin refactor-ui`: passed。

### P046-phase-6-pending-invoices-discovery

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `discovery/planning`
- Scope: `/pending-invoices` module only. Discovery/planning for pending invoice UI migration; do not modify runtime implementation or tests except docs/state/prompt/module doc required for discovery.

#### Prompt

```text
Prompt ID: P046-phase-6-pending-invoices-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: `/pending-invoices` only: PendingInvoices page, pending invoice components/features/tests and UI migration documentation. Do not modify backend, API contracts, read models, workers, mocks, reconciliation workbench internals, or unrelated page modules.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、DESIGN.md、PRODUCT.md、web/src/pages/PendingInvoicesPage.tsx、web/src/components/pendingInvoices/*、相关 pending invoice feature/api/types 文件、相关 tests 和当前 git status。梳理 `/pending-invoices` 的旧 UI 入口、MUI/DataGrid/session hook inventory、表格/分页/筛选/搜索/详情右侧抽屉/关系右侧抽屉/规则右侧抽屉/导出弹窗/发票选择右侧抽屉/手工发票弹窗/loading empty error stale permission 状态、现有测试覆盖、API/read model 风险和迁移切片风险。不得修改实现、测试、后端、API、read model、worker、mock 或关联台。若 discovery 需要跨后续切片复用，创建 `docs/refactor-ui/modules/phase_6_pending_invoices.md`；更新 `docs/refactor-ui/refactor_ui_state.md`、`docs/refactor-ui/refactor_ui_prompt.md` 和模块文档，生成下一条 P047 characterization tests prompt。验证命令：`test -f docs/refactor-ui/modules/phase_6_pending_invoices.md`；`rg -n "P046-phase-6-pending-invoices-discovery|Current MUI Inventory|User-visible Entrypoints|P047-phase-6-pending-invoices-characterization-tests" docs/refactor-ui/modules/phase_6_pending_invoices.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`；`git diff --check`；`git status --short --branch`。
```

#### Review

- Single slice: yes，discovery/planning only。
- Runtime implementation untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Module doc allowed: yes，pending invoices has high risk and multiple drawers/dialogs/tables。
- Next prompt: P047 characterization tests only after discovery is implemented and verified。

#### Execution Notes

- Created `docs/refactor-ui/modules/phase_6_pending_invoices.md` as the module fact source for `/pending-invoices` migration.
- Recorded current MUI inventory for page shell, four-zone table, shared drawer frame, rules/relation/detail/export/invoice-picker drawers and manual invoice dialog.
- Recorded user-visible entrypoints, table headers, right drawer/dialog matrix, loading/empty/error/stale states, API boundaries, test coverage, risk list and migration slices P047-P052 plus MG.
- Generated the next single prompt: `P047-phase-6-pending-invoices-characterization-tests`.

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_pending_invoices.md`: passed。
  - `rg -n "P046-phase-6-pending-invoices-discovery|Current MUI Inventory|User-visible Entrypoints|P047-phase-6-pending-invoices-characterization-tests" docs/refactor-ui/modules/phase_6_pending_invoices.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed。
  - `git diff --check`: passed。

### P047-phase-6-pending-invoices-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `characterization tests`
- Scope: 只更新 pending invoices tests，锁定 `/pending-invoices` 非 MUI/project primitive contract；不改实现。

#### Prompt

```text
Prompt ID: P047-phase-6-pending-invoices-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只更新 pending invoices tests，锁定 `/pending-invoices` 非 MUI/project primitive contract；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/PendingInvoicesPage.tsx、web/src/components/pendingInvoices/*.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/test/PendingInvoicesPage.test.tsx。只修改 `web/src/test/PendingInvoicesPage.test.tsx`：把当前 “upgraded four-zone MUI table without DataGrid” 等 MUI wording/class assertions 改成 project primitive assertions；新增 source-level contracts 锁定 page shell/toolbar/status menu/pagination、main four-zone table、row action menu、shared right drawer frame、rules/relation/detail/export/invoice-picker drawers、OA print dialog 和 manual invoice dialog 未来均不再依赖 `@mui/*`；新增行为断言确保旧右侧抽屉仍是右侧抽屉、旧 dialog 仍是 dialog、主表仍是 `待找发票四区表` table、`发票候选`/`历史支付流水`/`导出样例` 表格语义保留、`打印选择` 和 `手工补录发票` dialog 名称保留。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P048 page shell toolbar prompt。
```

#### Review

- Single slice: yes，tests only。
- Runtime implementation untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，implementation still uses MUI before P048-P052。
- Next prompt: P048 page shell toolbar refactor only after P047 implemented and verified/expected-fail documented。

#### Execution Notes

- Updated `web/src/test/PendingInvoicesPage.test.tsx` only.
- Renamed the old “upgraded four-zone MUI table without DataGrid” wording to a project four-zone table contract.
- Added source-level contract coverage for pending invoice page shell, main table, shared drawer frame, rules/relation/detail/export/invoice-picker drawers, OA print dialog and manual invoice dialog.
- Added behavior assertions for `历史支付流水`, `发票候选` and `导出样例` table semantics, while preserving `打印选择` and `手工补录发票` dialog expectations already covered by existing tests.
- Did not modify runtime implementation, mocks, backend, API, read model, worker or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail with 14 passed and 1 failure. The only failure is the new project primitive source contract listing 9 current pending invoice files with `@mui/*` imports and missing PageScaffold/PageToolbar/FinanceTable/AppDrawer/AppDialog targets。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed。

### P048-phase-6-pending-invoices-page-shell-toolbar

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只迁移 PendingInvoices page shell、direction segmented control、status filter menu、toolbar actions/search/loading 和 pagination；不迁移 `PendingInvoicesTable` internals、drawer frame、drawers、rules drawer、invoice picker 或 manual invoice dialog。

#### Prompt

```text
Prompt ID: P048-phase-6-pending-invoices-page-shell-toolbar
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/pending-invoices` page shell/toolbar/pagination only. Do not migrate `PendingInvoicesTable` internals or any pending invoice drawer/dialog component.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/PendingInvoicesPage.tsx、web/src/test/PendingInvoicesPage.test.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/components/common/StatePanel.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/PendingInvoicesPage.tsx`、必要 `web/src/app/styles.css` 和必要的 `web/src/test/PendingInvoicesPage.test.tsx` expectation：移除 page shell/toolbar/status menu/pagination/search/loading 的 MUI imports/usages，包括 `KeyboardArrowDownOutlinedIcon`、`Box`、`Button`、`LinearProgress`、`Menu`、`MenuItem`、`Stack`、`TablePagination`、`TextField`、`ToggleButton`、`ToggleButtonGroup`、`Typography` 以及 `.MuiButton-endIcon`、`.MuiToggleButton-root` sx selector。使用 PageScaffold/PageToolbar、native/project buttons、project menu/listbox/popover、native search input、project pagination/loading/status markup 或 HeroUI primitives，保留旧 `data-testid="pending-invoices-page"`、route/sidebar link、direction counts/buttons `全部 <n>`/`支出 <n>`/`收入 <n>`、status menu trigger `筛选发票获取状态：<label>` 和 options、search `搜索流水`、refresh `刷新`、rules/export buttons、non-fresh read model disables export、loading `待找发票加载中`、server page/pageSize/total behavior and pagination labels。不得修改 pending invoices API/mock/read model/worker/backend/关联台；不得改 `web/src/components/pendingInvoices/*`，除非测试证明 page-only migration needs a prop-compatible no-op adjustment and the prompt must record why。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract|shows income rule-group filters|keeps row status actions available|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，P049-P052 table/drawer/dialog source contract failures 可以继续 expected-fail，但 P048 page shell/toolbar/pagination targets and page-level MUI import failure must clear；运行 `cd web && npm run build`；运行 page shell MUI grep：`if rg -n '@mui/|MuiButton-endIcon|MuiToggleButton-root|KeyboardArrowDownOutlinedIcon|TablePagination|ToggleButton|ToggleButtonGroup' web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P049 four-zone table prompt。
```

#### Review

- Single slice: yes，page shell/toolbar/pagination only。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Existing table/drawer/dialog components untouched: required for P048 scope control。
- User-visible entrypoints preserved: required，direction buttons, status filter, rules/export/search/refresh and pagination labels must remain。
- Expected failure allowed: yes，P049-P052 source contracts can continue failing after P048, but page shell/toolbar failures must clear。
- Next prompt: P049 four-zone table migration only after P048 implementation is verified/expected-fail documented。

#### Execution Notes

- Replaced `PendingInvoicesPage.tsx` page shell, direction segmented control, status filter trigger/menu, toolbar actions/search/loading and pagination with `PageScaffold`, `PageToolbar`, lucide icon, native/project controls and pending invoice CSS classes.
- Removed page-level MUI imports and sx selectors for `KeyboardArrowDownOutlinedIcon`, `Box`, `Button`, `LinearProgress`, `Menu`, `MenuItem`, `Stack`, `TablePagination`, `TextField`, `ToggleButton`, `ToggleButtonGroup`, `Typography`, `.MuiButton-endIcon` and `.MuiToggleButton-root`.
- Added `pending-invoices-*` styles for page shell, segmented buttons, status text, menu, search, loading bar and pagination.
- Did not modify `web/src/components/pendingInvoices/*`, backend, API, mocks, read model, worker or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract|shows income rule-group filters|keeps row status actions available|targets project primitives"`: expected-fail. Page source target cleared; remaining failure lists only 8 table/drawer/dialog files。
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail with 14 passed and 1 source-level failure. The remaining failure belongs to P049-P052。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|MuiButton-endIcon|MuiToggleButton-root|KeyboardArrowDownOutlinedIcon|TablePagination|ToggleButton|ToggleButtonGroup' web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed。

### P049-phase-6-pending-invoices-four-zone-table

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只迁移 `web/src/components/pendingInvoices/PendingInvoicesTable.tsx` 主四区表、排序 trigger、row action menu、tag/tooltip markup 和必要 table styles/tests；不迁移 shared drawer frame、rules/relation/detail/export/invoice-picker drawers 或 manual invoice dialog。

#### Prompt

```text
Prompt ID: P049-phase-6-pending-invoices-four-zone-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: PendingInvoices main four-zone table only. Do not migrate drawer frame, drawers, rules drawer, invoice picker drawer or manual invoice dialog.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、web/src/components/pendingInvoices/PendingInvoicesTable.tsx、web/src/pages/PendingInvoicesPage.tsx、web/src/components/common/FinanceTable.tsx、web/src/test/PendingInvoicesPage.test.tsx 和 web/src/app/styles.css。只修改 `PendingInvoicesTable.tsx`、必要 `styles.css` 和必要的 `PendingInvoicesPage.test.tsx` expectations：移除主四区表的 MUI imports/usages，包括 `InfoOutlinedIcon`、`MoreVertOutlinedIcon`、`Box`、`Button`、`Chip`、`IconButton`、`Menu`、`MenuItem`、`Stack`、`Table`、`TableBody`、`TableCell`、`TableHead`、`TableRow`、`TableSortLabel`、`Tooltip`、`Typography`、`SxProps`、`Theme` 和 `.MuiChip-label` selector。使用 FinanceTable/project native table markup、project buttons/menu/tooltip/tag classes 或 HeroUI primitives，保留 accessible table name `待找发票四区表`、`pending-invoices-table-shell` scroll container、group headers `支出流水/收入流水/流水`、`发票获取状态`、`进项发票/销项发票/发票`、`OA`、所有 subheaders、sticky header behavior、dense four-zone row layout、loading row `正在加载待找发票。`、empty row `当前条件下没有待找发票流水。`、row action button `<counterparty> 发票获取操作`、menu items `选择发票`/`补票`/`查看支付明细`/income status actions、object detail buttons such as `发票详情 DIG-001` and `OA详情 李四`、direction/status tags、amount/payment difference tabular numeric alignment and server sorting behavior。不得修改 page shell、pending invoice API/mock/read model/worker/backend/关联台；不得改 any drawer/dialog component。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract|shows income rule-group filters|keeps row status actions available|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，P050-P052 drawer/dialog source contract failures 可以继续 expected-fail，但 `PendingInvoicesTable.tsx` must disappear from the source-level failure list；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 table MUI grep：`if rg -n '@mui/|MuiChip-label|SxProps|TableSortLabel|MoreVertOutlinedIcon|InfoOutlinedIcon' web/src/components/pendingInvoices/PendingInvoicesTable.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P050 drawer frame/simple drawers prompt。
```

#### Review

- Single slice: yes，main four-zone table only。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Page shell untouched except necessary test expectation: required，P048 already owns it。
- Drawer/dialog components untouched: required for P049 scope control。
- User-visible table contract preserved: required，headers, row action menu, object detail buttons, loading/empty, sorting and amount/tag layout must remain。
- Expected failure allowed: yes，P050-P052 drawer/dialog source contracts can remain after P049, but `PendingInvoicesTable.tsx` must clear。
- Next prompt: P050 drawer frame and simple drawers only after P049 implementation is verified/expected-fail documented。

#### Execution Notes

- Replaced `PendingInvoicesTable.tsx` MUI table, MUI tags, MUI sort label, MUI tooltip/icons and MUI row action menu with a native/project four-zone table.
- Kept accessible table name `待找发票四区表`, `pending-invoices-table-shell`, group headers, subheaders, empty row, row action menu labels, object detail buttons and dense four-zone row layout.
- Used `AmountCell`, `FinanceDirectionTag`, `FinanceStatusTag`, `EmptyValue`, lucide icons and pending invoice CSS classes for amount/status/tag/action alignment.
- Updated `PendingInvoicesPage.test.tsx` table CSS expectations to assert project CSS contracts instead of forcing inline/computed style.
- Added pending invoice table CSS for sticky group headers, native table cells, column roles, amount alignment, row menu and inline actions.
- Did not modify page shell, pending invoice API/mock/read model/worker/backend, reconciliation workbench internals or any pending invoice drawer/dialog component.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract|shows income rule-group filters|keeps row status actions available|targets project primitives"`: expected-fail. Main table behavior tests passed; the only failure is the source-level drawer/dialog contract for P050-P052。
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail with 14 passed and 1 failure. The remaining failure lists only 7 drawer/dialog files: `PendingInvoiceDrawerFrame.tsx`, `PendingInvoiceRulesDrawer.tsx`, `PendingInvoiceRelationDrawer.tsx`, `PendingInvoiceInvoicePickerDrawer.tsx`, `PendingInvoiceDetailDrawer.tsx`, `PendingInvoiceExportDrawer.tsx`, `ManualInvoiceDialog.tsx`。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|MuiChip-label|SxProps|TableSortLabel|MoreVertOutlinedIcon|InfoOutlinedIcon' web/src/components/pendingInvoices/PendingInvoicesTable.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。

### P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只迁移 pending invoice shared drawer frame、relation drawer、detail drawer、export drawer 和 detail flow 内的 OA print dialog；不迁移 rules drawer、invoice picker drawer 或 manual invoice dialog。

#### Prompt

```text
Prompt ID: P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: PendingInvoices shared drawer frame plus simple drawers only: `PendingInvoiceDrawerFrame.tsx`, `PendingInvoiceRelationDrawer.tsx`, `PendingInvoiceDetailDrawer.tsx`, `PendingInvoiceExportDrawer.tsx`, necessary `web/src/app/styles.css` and necessary `PendingInvoicesPage.test.tsx` expectations. Do not migrate `PendingInvoiceRulesDrawer.tsx`, `PendingInvoiceInvoicePickerDrawer.tsx` or `ManualInvoiceDialog.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/FinanceTable.tsx、web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx、web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx、web/src/test/PendingInvoicesPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：用 `AppDrawer` 替换 shared MUI Drawer frame，保留右侧抽屉形态、title/subtitle/action/body 区域和 close labels；迁移 relation drawer，保留 `关系与支付明细`、metrics `已付合计`/`发票合计`/`待付金额`/`支付差额`、`选择发票` 和 `历史支付流水` table；迁移 detail drawer，保留 detail heading 如 `DIG-001`、发票字段、OA unavailable detail behavior，并用 `AppDialog` 保留 `打印选择` dialog 和 `打印下载`；迁移 export drawer，保留 `导出预览`、`预计导出 <n> 行`、`下载导出`、`已生成 pending-invoices.xlsx` 和 `导出样例` table。移除本 scope 内 MUI imports/usages，包括 MUI Drawer/Dialog/Alert/Button/CircularProgress/Paper/Stack/Table/Typography/Divider/IconButton 等。不得修改 pending invoice API/mock/read model/worker/backend/关联台；不得修改 rules drawer、invoice picker drawer 或 manual invoice dialog。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks|renders project four-zone table contract|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，P051-P052 rules/invoice-picker/manual-dialog source contract failures 可以继续 expected-fail，但 P050 scope files must disappear from the source-level failure list；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 P050 MUI grep：`if rg -n '@mui/' web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P051 rules drawer prompt。
```

#### Review

- Single slice: yes，shared frame plus relation/detail/export simple drawers only。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Rules drawer, invoice picker drawer and manual invoice dialog untouched: required for P050 scope control。
- Overlay equivalence preserved: required，old right drawers remain right drawers and OA print remains a dialog。
- Expected failure allowed: yes，P051-P052 source contracts can remain after P050, but P050 files must clear。
- Next prompt: P051 rules drawer only after P050 implementation is verified/expected-fail documented。

#### Execution Notes

- Extended `AppDrawer` with optional `subtitle` to preserve pending invoice drawer header information without changing existing callers.
- Replaced `PendingInvoiceDrawerFrame.tsx` MUI Drawer implementation with an `AppDrawer` wrapper while keeping the existing props used by not-yet-migrated drawers.
- Migrated `PendingInvoiceRelationDrawer.tsx` to project/native metrics, status messages and `历史支付流水` table.
- Migrated `PendingInvoiceDetailDrawer.tsx` to project/native field panels and `AppDialog` for the OA `打印选择` dialog.
- Migrated `PendingInvoiceExportDrawer.tsx` to project/native export summary, success/error/loading states and `导出样例` table.
- Added pending invoice drawer/panel/simple-table/print-layout CSS in `web/src/app/styles.css`.
- Did not modify pending invoice API/mock/read model/worker/backend, reconciliation workbench internals, rules drawer, invoice picker drawer or manual invoice dialog.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks|renders project four-zone table contract|targets project primitives"`: expected-fail. P050 behavior tests passed; the only failure is the source-level contract for P051-P052。
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail with 14 passed and 1 failure. The remaining failure lists only `PendingInvoiceRulesDrawer.tsx`, `PendingInvoiceInvoicePickerDrawer.tsx` and `ManualInvoiceDialog.tsx`。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/' web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。

### P051-phase-6-pending-invoices-rules-drawer

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只迁移 `PendingInvoiceRulesDrawer.tsx` 待找发票规则右侧抽屉、checkbox tree、loading/error/refresh/save/permission states 和必要 styles/tests；不迁移 invoice picker drawer 或 manual invoice dialog。

#### Prompt

```text
Prompt ID: P051-phase-6-pending-invoices-rules-drawer
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: PendingInvoices rules drawer only: `web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`, necessary `web/src/app/styles.css` and necessary `web/src/test/PendingInvoicesPage.test.tsx` expectations. Do not migrate `PendingInvoiceInvoicePickerDrawer.tsx` or `ManualInvoiceDialog.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx、web/src/test/PendingInvoicesPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 rules drawer 的 MUI imports/usages，包括 `Alert`、`Button`、`CircularProgress`、`Checkbox`、`FormControlLabel`、`Paper`、`Stack`、`Typography`、`Box` 和 checkbox label sx selectors。使用 existing `PendingInvoiceDrawerFrame` right drawer、native/project buttons、native checkboxes、project status messages 和 project rule block CSS。必须保留 `支出待找发票规则设置`/`收入待找发票规则设置` heading、`关闭规则抽屉`、subtitle `版本 <n>`、`保存规则`、loading label `正在加载待找发票规则`、readonly permission alert `当前账号只能查看规则，不能保存。`、save success `规则已保存，相关数据正在刷新。`/`规则已保存。`、stale conflict `规则已被其他人更新。请刷新规则后再保存，当前勾选内容已保留。`、tag refresh notices、checkbox group names such as `需要开票`/`无需开票`/`现金收入`、mutual exclusion behavior and tag refresh merge behavior。不得修改 pending invoice API/mock/read model/worker/backend/关联台；不得修改 invoice picker drawer 或 manual invoice dialog。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks|keeps pending invoice rule draft|preserves unsaved rule selections|shows income rule-group filters|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，P052 invoice-picker/manual-dialog source contract failures 可以继续 expected-fail，但 `PendingInvoiceRulesDrawer.tsx` must disappear from the source-level failure list；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 rules MUI grep：`if rg -n '@mui/|Mui[A-Z]|FormControlLabel|CircularProgress|Checkbox' web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P052 invoice picker/manual dialog prompt。
```

#### Review

- Single slice: yes，rules drawer only。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Invoice picker drawer and manual invoice dialog untouched: required for P051 scope control。
- Business-sensitive behavior preserved: required，mutual exclusion, stale conflict, tag refresh merge and readonly permission must stay covered。
- Expected failure allowed: yes，P052 source contracts can remain after P051, but `PendingInvoiceRulesDrawer.tsx` must clear。
- Next prompt: P052 invoice picker and manual dialog only after P051 implementation is verified/expected-fail documented。

#### Execution Notes

- Replaced `PendingInvoiceRulesDrawer.tsx` MUI alert/button/loading/checkbox/layout components with existing `PendingInvoiceDrawerFrame`, native/project buttons, native checkboxes, project status messages and rule block markup.
- Preserved the rules drawer right-side shape, headings, `关闭规则抽屉`, `保存规则`, version subtitle, loading label, readonly permission notice, save success/stale conflict/tag refresh notices, checkbox group names and mutual exclusion behavior.
- Added rules drawer grid, rule block, checkbox and readonly tag styles in `web/src/app/styles.css`.
- Did not modify pending invoice API/mock/read model/worker/backend, reconciliation workbench internals, invoice picker drawer or manual invoice dialog.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks|keeps pending invoice rule draft|preserves unsaved rule selections|shows income rule-group filters|targets project primitives"`: expected-fail. P051 behavior tests passed; the only failure is the source-level contract for P052。
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail with 14 passed and 1 failure. The remaining failure lists only `PendingInvoiceInvoicePickerDrawer.tsx` and `ManualInvoiceDialog.tsx`。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|Mui[A-Z]|FormControlLabel|CircularProgress|Checkbox' web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。

### P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: 只迁移 `PendingInvoiceInvoicePickerDrawer.tsx` 发票选择右侧抽屉、`ManualInvoiceDialog.tsx` 手工补录发票弹窗、必要 styles/tests；不迁移其他 pending invoice surfaces。

#### Prompt

```text
Prompt ID: P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: Final pending invoices UI migration slice: `web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`, `web/src/components/pendingInvoices/ManualInvoiceDialog.tsx`, necessary `web/src/app/styles.css` and necessary `web/src/test/PendingInvoicesPage.test.tsx` expectations. Do not modify backend, API contracts, read models, workers, mocks or reconciliation workbench internals.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、web/src/components/common/AppDialog.tsx、web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx、web/src/components/pendingInvoices/ManualInvoiceDialog.tsx、web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx、web/src/test/PendingInvoicesPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：迁移 invoice picker right drawer，移除 MUI Alert/Button/Chip/CircularProgress/Paper/Stack/Table/TablePagination/TextField/Typography，使用 existing `PendingInvoiceDrawerFrame`、native/project form controls、project status messages、native `发票候选` table、project pagination/buttons/status tags；必须保留 filters `关键词`/`销方`/`开票开始`/`开票结束`/`最小金额`/`最大金额`、`搜索`、candidate rows、status labels `可关联`/`已关联本流水`/`存在冲突`、`预览关联 <invoice>`、preview message、`确认建立关系` 和 server page/pageSize behavior。迁移 `ManualInvoiceDialog.tsx` 到 `AppDialog` 和 native/project inputs/buttons/status messages，保留 dialog name `手工补录发票`、row context text、所有 form labels、`预览`、`确认写入`、duplicate/preview feedback、disabled/busy behavior and confirm flow。不得修改 pending invoice API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens invoice picker from status column|manual invoice action still previews before confirm|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，source-level project primitive contract must pass fully；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 pending invoices MUI grep：`if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|TablePagination|TextField|Dialog' web/src/components/pendingInvoices web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 `MG-P052-phase-6-pending-invoices` cumulative MG prompt。
```

#### Review

- Single slice: yes，invoice picker drawer and manual invoice dialog only。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Overlay equivalence preserved: required，invoice picker remains right drawer and manual invoice remains dialog。
- Source contract target: after P052, `PendingInvoicesPage.test.tsx` source-level project primitive contract must pass fully。
- Next prompt: cumulative `MG-P052-phase-6-pending-invoices` only after P052 implementation is verified。

#### Execution Notes

- Migrated `PendingInvoiceInvoicePickerDrawer.tsx` from MUI forms/table/pagination/tags to `PendingInvoiceDrawerFrame`, native/project inputs, project status messages, native `发票候选` table, project pagination and project buttons/status tags.
- Migrated `ManualInvoiceDialog.tsx` from MUI Dialog/TextField/Button/Alert layout to `AppDialog`, native/project inputs/buttons/status messages.
- Preserved invoice picker filters, search request behavior, candidate rows, status labels, preview action, confirm action and server page/pageSize behavior.
- Preserved manual invoice dialog name `手工补录发票`, row context text, all form labels, preview feedback, duplicate check text and confirm flow.
- Did not modify pending invoice API/mock/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens invoice picker from status column|manual invoice action still previews before confirm|targets project primitives"`: passed, 3 focused tests passed。
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: passed, 15 tests passed. The source-level project primitive contract now passes fully。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|TablePagination|TextField' web/src/components/pendingInvoices web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。

### MG-P052-phase-6-pending-invoices

- Phase: `phase_6_page_batches`
- Status: `mg_verified`
- Type: `cumulative MG`
- Scope: PendingInvoices module P046-P052 only: pending invoices module docs/state/prompt docs, PendingInvoices page/table/drawer/dialog components, `AppDrawer` subtitle compatibility extension, PendingInvoices tests and required styles. Do not include backend, API contracts, read models, workers, reconciliation workbench internals, unrelated page modules or unrelated generated files.

#### Prompt

```text
Prompt ID: MG-P052-phase-6-pending-invoices
Phase: phase_6_page_batches
Type: cumulative MG
Scope: PendingInvoices module P046-P052 only. Confirm all pending invoice migration slices are implemented and verified; commit/push only the exact PendingInvoices MG files.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、当前 git status 和当前 diff。检查当前分支必须是 `refactor-ui`。确认 untracked files、diff scope、测试结果和文档状态；确认 `cd web && npx vitest run PendingInvoicesPage.test.tsx`、`cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`、`cd web && npm run build` 已通过；确认 pending invoices MUI/DataGrid residue grep 已通过：`if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|TablePagination|TextField' web/src/components/pendingInvoices web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`。只允许精确 `git add docs/refactor-ui/refactor_ui_state.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/modules/phase_6_pending_invoices.md web/src/app/styles.css web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx web/src/components/pendingInvoices/ManualInvoiceDialog.tsx`；如果当前 diff 还包含本模块此前未提交的 P052 scope 文件，必须逐个精确列出；禁止 `git add .` 或 `git add -A`。commit message 使用 `feat: complete pending invoices ui migration` 或更准确的 PendingInvoices module message。push 到 `origin refactor-ui`。完成后更新 state/prompt/module docs 的 MG execution notes、verification、Push Log，标记 MG verified，并从 `refactor-ui` 分支继续生成下一条 Micro-JIT prompt。
```

#### Review

- Single MG boundary: yes，PendingInvoices module only。
- Scope guard: yes，explicit allowed files and exact staging only。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Verification required before push: yes，PendingInvoices target tests, common/table/platform regressions, build, scoped MUI/DataGrid residue grep and diff check。
- Push target: `origin refactor-ui`。

#### Execution Notes

- Exact staged files for the final P052/MG commit:
  - `docs/refactor-ui/refactor_ui_state.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/modules/phase_6_pending_invoices.md`
  - `web/src/app/styles.css`
  - `web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`
  - `web/src/components/pendingInvoices/ManualInvoiceDialog.tsx`
- Commit: `369e480c feat: complete pending invoices ui migration`。
- Push: `origin/refactor-ui` updated from `22a204fa` to `369e480c`。

#### Verification

- Status: mg_verified。
- Commands:
  - `git diff --cached --name-only`: confirmed exact staged files before commit。
  - `git push origin refactor-ui`: passed。

### P053-phase-6-input-invoice-usage-discovery

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `discovery/planning`
- Scope: `/input-invoice-usage` module only. Discovery/planning for input invoice usage UI migration; do not modify runtime implementation or tests except docs/state/prompt/module doc required for discovery.

#### Prompt

```text
Prompt ID: P053-phase-6-input-invoice-usage-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: `/input-invoice-usage` only: InputInvoiceUsage page, input invoice usage components/features/tests and UI migration documentation. Do not modify backend, API contracts, read models, workers, mocks, reconciliation workbench internals, or unrelated page modules.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、DESIGN.md、PRODUCT.md、web/src/pages/InputInvoiceUsagePage.tsx、web/src/components/inputInvoiceUsage/*、web/src/features/inputInvoiceUsage/api.ts、web/src/features/inputInvoiceUsage/types.ts、web/src/test/InputInvoiceUsagePage.test.tsx、web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx 和当前 git status。梳理 `/input-invoice-usage` 的旧 UI 入口、MUI/DataGrid/session hook inventory、主表/筛选菜单/搜索/详情右侧抽屉/导出右侧抽屉/规则右侧抽屉/OA 反查 workspace drawer/loading empty error stale permission 状态、现有测试覆盖、API/read model 风险和迁移切片风险。不得修改实现、测试、后端、API、read model、worker、mock 或关联台。若 discovery 需要跨后续切片复用，创建 `docs/refactor-ui/modules/phase_6_input_invoice_usage.md`；更新 `docs/refactor-ui/refactor_ui_state.md`、`docs/refactor-ui/refactor_ui_prompt.md` 和模块文档，生成下一条 P054 characterization tests prompt。验证命令：`test -f docs/refactor-ui/modules/phase_6_input_invoice_usage.md`；`rg -n "P053-phase-6-input-invoice-usage-discovery|Current MUI Inventory|User-visible Entrypoints|P054-phase-6-input-invoice-usage-characterization-tests" docs/refactor-ui/modules/phase_6_input_invoice_usage.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`；`git diff --check`；`git status --short --branch`。
```

#### Review

- Single slice: yes，discovery/planning only。
- Runtime implementation untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Module doc allowed: yes，input invoice usage has high-risk table, filters and multiple drawers。
- Next prompt: P054 characterization tests only after P053 is implemented and verified。

#### Execution Notes

- Created `docs/refactor-ui/modules/phase_6_input_invoice_usage.md` as the module fact source for `/input-invoice-usage`.
- Recorded scope, non-goals, user-visible entrypoints, current MUI inventory, dense main table contract, shared filter menu contract, detail/export/payment-rules/OA-reverse right drawer contracts, loading/empty/error/stale/permission states, existing tests, API boundaries, migration slices and risks.
- Confirmed `InputInvoiceUsageFilterMenu` is not currently mounted by `/input-invoice-usage`; it is a shared component consumed by `OaPendingPaymentsTable`, so migration must preserve prop compatibility without adding new page filters.
- Did not modify runtime implementation, tests, backend, API contracts, read models, workers, mocks or reconciliation workbench internals.

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_input_invoice_usage.md`: passed。
  - `rg -n "P053-phase-6-input-invoice-usage-discovery|Current MUI Inventory|User-visible Entrypoints|P054-phase-6-input-invoice-usage-characterization-tests" docs/refactor-ui/modules/phase_6_input_invoice_usage.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed。

### P054-phase-6-input-invoice-usage-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `characterization tests`
- Scope: 只更新 input invoice usage tests，锁定 `/input-invoice-usage` 非 MUI/project primitive contract；不改实现。

#### Prompt

```text
Prompt ID: P054-phase-6-input-invoice-usage-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只更新 input invoice usage tests，锁定 `/input-invoice-usage` 非 MUI/project primitive contract；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/InputInvoiceUsagePage.tsx、web/src/components/inputInvoiceUsage/*.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/FinanceTable.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx。只修改 `web/src/test/InputInvoiceUsagePage.test.tsx` 和 `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`：把当前 `dense MUI Table layout without DataGrid`、`.MuiDataGrid-root`、`.MuiChip-root` 等 MUI wording/class assertions 改成行为和 project primitive assertions；新增 source-level contracts，锁定 page shell/toolbar/search/loading、main dense table、ExpandableCellText、shared filter menu、detail/export/payment-rules/OA-reverse right drawers 未来均不再依赖 `@mui/*`、`Mui[A-Z]`、`TablePagination`、`TextField`、`Drawer`、`Dialog`、`Menu`、`Chip` 等旧 MUI surface；新增或保留行为断言确保旧右侧抽屉仍是右侧抽屉，`进项发票使用情况表`、`进项发票使用情况导出样例`、`Sheet4 支付状态规则`、`反提 OA 候选发票清单` 表格语义保留，`筛选 支付状态` menu、`关闭详情抽屉`、`关闭进项发票使用情况导出`、`关闭支付状态规则抽屉`、`关闭以发票反提 OA 工作流` 标签保留。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P055 page shell toolbar prompt。
```

#### Review

- Single slice: yes，tests only。
- Runtime implementation untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level no-MUI contract should fail until P055-P060/P061 implement migration。
- Next prompt: P055 page shell/toolbar only after P054 is implemented and verified/expected-fail documented。

#### Execution Notes

- Updated `web/src/test/InputInvoiceUsagePage.test.tsx` with source-level project primitive contracts for page shell, dense table, expandable cell, shared filter menu and workflow drawers.
- Updated the main page behavior test wording from old MUI terminology to project dense table contract.
- Replaced `.MuiDataGrid-root` and `.MuiChip-root` assertions with user-observable table/text assertions.
- Updated `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` with workflow source-level contracts for the shared filter menu and right drawer surfaces.
- Did not modify runtime implementation, mocks, backend, API contracts, read models, workers or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 failed. Both failures are the intended source-level contracts listing remaining MUI imports/selectors and missing project primitive targets.
  - `git diff --check`: passed。
  - `git status --short --branch`: passed。

### P055-phase-6-input-invoice-usage-page-shell-toolbar

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: `/input-invoice-usage` page shell/actions/search/loading/error only. Do not migrate `InputInvoiceUsageTable`, `ExpandableCellText`, `InputInvoiceUsageFilterMenu` or any input invoice usage drawer/workflow component.

#### Prompt

```text
Prompt ID: P055-phase-6-input-invoice-usage-page-shell-toolbar
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/input-invoice-usage` page shell/actions/search/loading/error only. Do not migrate `InputInvoiceUsageTable`, `ExpandableCellText`, `InputInvoiceUsageFilterMenu` or any input invoice usage drawer/workflow component.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/InputInvoiceUsagePage.tsx、web/src/test/InputInvoiceUsagePage.test.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/components/common/StatePanel.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/InputInvoiceUsagePage.tsx`、必要 `web/src/app/styles.css` 和必要的 `web/src/test/InputInvoiceUsagePage.test.tsx` expectation：移除 page shell/actions/search/loading/error scope 的 MUI imports/usages，包括 `FileDownloadOutlinedIcon`、`RefreshOutlinedIcon`、`Alert`、`Box`、`Button`、`Skeleton`、`Stack`、`TextField`。使用 existing `PageScaffold`、`PageToolbar` 或等价 project toolbar、native/project buttons、native/project search input、project loading skeleton/status message 和 lucide icons。必须保留 `data-testid="input-invoice-usage-page"`、heading `进项发票使用情况`、description `以进项发票为主对象反查支付状态、OA 和银行流水。`、toolbar buttons `以发票反提 OA`、`发票与支付状态规则设置`、`筛选内容导出`、`刷新`、search input label `关键字`、submit button `查询`、Enter submit、refresh disabled while refreshing、error feedback、loading label `进项发票使用情况加载中`、empty state `当前条件下暂无记录。`、query/page reset and read model retry behavior。不得修改 input invoice usage API/mock/read model/worker/backend/关联台；不得修改 `web/src/components/inputInvoiceUsage/*`。运行 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives|uses a standard empty state|pauses read model retry|adds sidebar route|drops legacy column filters|loads export preview"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P056-P060/P061 table/filter/drawer source contract failures 可以继续 expected-fail，但 `src/pages/InputInvoiceUsagePage.tsx` must disappear from the source-level failure list；运行 `cd web && npm run build`；运行 page shell MUI grep：`if rg -n '@mui/|Mui[A-Z]|FileDownloadOutlinedIcon|RefreshOutlinedIcon|Skeleton|TextField' web/src/pages/InputInvoiceUsagePage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P056 main table and expandable cell prompt。
```

#### Review

- Single slice: yes，page shell/actions/search/loading/error only。
- Runtime table/filter/drawers untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P056-P060/P061 source-level failures can remain, but page source must clear。
- Next prompt: P056 main table and expandable cell only after P055 implementation is verified/expected-fail documented。

#### Execution Notes

- Migrated `InputInvoiceUsagePage.tsx` page shell/actions/search/loading/error scope from MUI controls to project/native controls.
- Added `PageToolbar` usage for toolbar source contract.
- Replaced MUI icons with `lucide-react` `Download` and `RefreshCw`.
- Replaced MUI search `TextField` with native labelled input preserving `关键字`, Enter submit and `查询`.
- Replaced page-level MUI `Alert`/`Skeleton`/layout with `StatePanel` and project loading skeleton markup.
- Added page-level styles in `web/src/app/styles.css`.
- Did not modify `web/src/components/inputInvoiceUsage/*`, input invoice usage API/mock/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives|uses a standard empty state|pauses read model retry|adds sidebar route|drops legacy column filters|loads export preview"`: expected-fail. Five behavior tests passed; the only failure is the source-level contract for P056-P060/P061.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures. `src/pages/InputInvoiceUsagePage.tsx` no longer appears in the failure lists.
  - `if rg -n '@mui/|Mui[A-Z]|FileDownloadOutlinedIcon|RefreshOutlinedIcon|Skeleton|TextField' web/src/pages/InputInvoiceUsagePage.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### P056-phase-6-input-invoice-usage-main-table-and-expandable-cell

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: `/input-invoice-usage` main dense table and expandable cell only: `InputInvoiceUsageTable.tsx`, `ExpandableCellText.tsx`, necessary `web/src/app/styles.css` and necessary `InputInvoiceUsagePage.test.tsx` expectations. Do not migrate `InputInvoiceUsageFilterMenu` or any input invoice usage drawer/workflow component.

#### Prompt

```text
Prompt ID: P056-phase-6-input-invoice-usage-main-table-and-expandable-cell
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/input-invoice-usage` main dense table and expandable cell only: `InputInvoiceUsageTable.tsx`, `ExpandableCellText.tsx`, necessary `web/src/app/styles.css` and necessary `InputInvoiceUsagePage.test.tsx` expectations. Do not migrate `InputInvoiceUsageFilterMenu` or any input invoice usage drawer/workflow component.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、docs/refactor-ui/table_layout_system.md、web/src/components/common/FinanceTable.tsx、web/src/pages/InputInvoiceUsagePage.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx、web/src/components/inputInvoiceUsage/ExpandableCellText.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 `InputInvoiceUsageTable.tsx` 和 `ExpandableCellText.tsx` 的 MUI imports/usages，包括 `InfoOutlinedIcon`、`ExpandLessOutlinedIcon`、`ExpandMoreOutlinedIcon`、`Box`、`Button`、`Chip`、`IconButton`、`Paper`、`Stack`、`Table*`、`TablePagination`、`Tooltip`、`Typography` 和 `.MuiChip-label`/`.MuiTablePagination-*` selectors。使用 `FinanceTable`/project dense table primitives 或 native project table shell、project tags/buttons/tooltips、lucide icons 和 project pagination。必须保留 `aria-label="进项发票使用情况表"`、四个列组 `进项发票`/`支付状态`/`OA`/`流水`、10 列 header、amount right alignment/tabular nums、payment status class or equivalent project class contract、date/status/application/bank direction tags with stable height、detail button labels `查看发票 <invoice> 详情` / `查看OA <applicant/id> 详情` / `查看流水 <counterparty/id> 详情`、long-text expand/collapse labels、empty row `当前条件下没有进项发票使用记录。`、server page/pageSize/total pagination labels `每页行数` and `<from>-<to> / <count>`。不得修改 page shell、filter menu、detail/export/payment-rules/OA-reverse drawers、input invoice usage API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives|adds sidebar route"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P057-P060/P061 filter/drawer source contract failures 可以继续 expected-fail，但 `InputInvoiceUsageTable.tsx` and `ExpandableCellText.tsx` must disappear from the source-level failure list；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 table MUI grep：`if rg -n '@mui/|Mui[A-Z]|TablePagination|InfoOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon' web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx web/src/components/inputInvoiceUsage/ExpandableCellText.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P057 filter menu prompt。
```

#### Review

- Single slice: yes，main table and expandable cell only。
- Page shell already migrated: do not widen scope back into P055 files except necessary test expectation updates。
- Filter menu and workflow drawers untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P057-P060/P061 source failures can remain, but table and expandable cell source must clear。
- Next prompt: P057 shared filter menu only after P056 implementation is verified/expected-fail documented。

#### Execution Notes

- Migrated `InputInvoiceUsageTable.tsx` from MUI table/chip/button/tooltip/pagination components to a native project dense table shell.
- Migrated `ExpandableCellText.tsx` from MUI icon button/tooltip/text layout to `lucide-react` chevrons and project/native buttons.
- Preserved `进项发票使用情况表`, four table groups, 10-column header, amount formatting, payment status class contract, date/status tags, detail button labels, long-text expand/collapse labels, empty row and pagination labels.
- Added input invoice usage table, tag, action, expandable text and pagination CSS.
- Corrected P055 page shell CSS token names to use existing `--fp-primary` variables.
- Did not modify page shell behavior, shared filter menu, detail/export/payment-rules/OA-reverse drawers, API/mock/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|TablePagination|InfoOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon' web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx web/src/components/inputInvoiceUsage/ExpandableCellText.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives|adds sidebar route"`: expected-fail. Main table behavior passed; source failure now lists only filter menu and drawers.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures. `InputInvoiceUsageTable.tsx` and `ExpandableCellText.tsx` no longer appear in failure lists.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### P057-phase-6-input-invoice-usage-filter-menu

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: Shared `InputInvoiceUsageFilterMenu.tsx` only, plus necessary styles/tests. Preserve its external consumer `OaPendingPaymentsTable`; do not add new `/input-invoice-usage` table filter entrypoints.

#### Prompt

```text
Prompt ID: P057-phase-6-input-invoice-usage-filter-menu
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: Shared `InputInvoiceUsageFilterMenu.tsx` only, plus necessary styles/tests. Preserve its external consumer `OaPendingPaymentsTable`; do not add new `/input-invoice-usage` table filter entrypoints.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/app/styles.css。只修改 `InputInvoiceUsageFilterMenu.tsx`、必要 `web/src/app/styles.css` 和必要测试 expectation：移除 filter menu 的 MUI imports/usages，包括 `ArrowDownwardOutlinedIcon`、`ArrowUpwardOutlinedIcon`、`FilterListOutlinedIcon`、`Button`、`Checkbox`、`Divider`、`ListItemIcon`、`ListItemText`、`Menu`、`MenuItem`、`Radio`、`Stack`、`Typography` 和 `.MuiButton-startIcon` selector。使用 project/native popover/menu、native checkbox/radio semantics and lucide icons。必须保持 prop contract for `OaPendingPaymentsTable`，保留 trigger label `筛选 <field label>`、menu accessible name `<field label>筛选与排序`、heading/subtitle text、`升序排序`、`降序排序`、`全选`、`清空`、`暂无可选项`、`该字段的输入控件由页面查询区提供`、`menuitemcheckbox` checked state、`menuitemradio` checked state、API-provided option labels/counts and no fabricated options。不得修改 page shell、main table、detail/export/payment-rules/OA-reverse drawers、input invoice usage API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "InputInvoiceUsageFilterMenu|workflow primitive targets"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P058-P060/P061 drawer source contract failures 可以继续 expected-fail，但 `InputInvoiceUsageFilterMenu.tsx` must disappear from the source-level failure lists；运行 `cd web && npm run build`；运行 filter menu MUI grep：`if rg -n '@mui/|Mui[A-Z]|FilterListOutlinedIcon|ArrowDownwardOutlinedIcon|ArrowUpwardOutlinedIcon|MenuItem|ListItemText|Checkbox|Radio' web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P058 detail/export drawers prompt。
```

#### Review

- Single slice: yes，shared filter menu only。
- External consumer preserved: required，`OaPendingPaymentsTable` prop contract must remain compatible。
- Do not add page filters: required。
- Drawers untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P058-P060/P061 drawer source failures can remain, but filter menu source must clear。
- Next prompt: P058 detail/export drawers only after P057 implementation is verified/expected-fail documented。

#### Execution Notes

- Migrated `InputInvoiceUsageFilterMenu.tsx` from MUI button/menu/item/check/radio/list/icon components to project/native trigger and menu.
- Preserved the component prop contract for `OaPendingPaymentsTable`.
- Preserved trigger label `筛选 <field label>`, menu name `<field label>筛选与排序`, sort actions, multi-select, single-select, empty options and non-enum placeholder behavior.
- Added filter menu styles in `web/src/app/styles.css`.
- Did not modify page shell, main table, detail/export/payment-rules/OA-reverse drawers, API/mock/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|FilterListOutlinedIcon|ArrowDownwardOutlinedIcon|ArrowUpwardOutlinedIcon|MenuItem|ListItemText|Checkbox|Radio' web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "InputInvoiceUsageFilterMenu|workflow primitive targets"`: expected-fail. Filter menu behavior tests passed; source failure now lists only drawers.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures. `InputInvoiceUsageFilterMenu.tsx` no longer appears in failure lists.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### P058-phase-6-input-invoice-usage-detail-and-export-drawers

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: Input invoice usage detail drawer and export drawer only: `InputInvoiceUsageDetailDrawer.tsx`, `InputInvoiceUsageExportDrawer.tsx`, necessary styles/tests. Do not migrate `PaymentStatusRulesDrawer.tsx` or `OaReverseWorkspaceDrawer.tsx`.

#### Prompt

```text
Prompt ID: P058-phase-6-input-invoice-usage-detail-and-export-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: Input invoice usage detail drawer and export drawer only: `InputInvoiceUsageDetailDrawer.tsx`, `InputInvoiceUsageExportDrawer.tsx`, necessary styles/tests. Do not migrate `PaymentStatusRulesDrawer.tsx` or `OaReverseWorkspaceDrawer.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、web/src/components/common/AppDrawer.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx、web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 detail/export drawers 的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Box`、`Button`、`CircularProgress`、`Divider`、`Drawer`、`IconButton`、`Paper`、`Stack`、`Table*`、`Typography`。使用 `AppDrawer`、project/native status messages/loading、project detail section cards、project sample table and project action buttons。必须保留 detail drawer right placement、`aria-label="详情"` 或 equivalent drawer accessible label、close button `关闭详情抽屉`、lazy load on open、progress label `正在加载详情`、text `正在加载完整详情`、error text、`详情暂不可用` and unavailable reason behavior、empty detail `暂无更多详情。`、field section labels and values。必须保留 export drawer right placement、drawer label `进项发票使用情况导出`、close `关闭进项发票使用情况导出`、title `筛选内容导出`、preview loading `正在加载导出预览` / `正在计算导出范围`、refreshing notice `导出数据准备中，请稍后再试。`、success `已生成 <file>`、`预计导出 <n> 行`、sample table `进项发票使用情况导出样例`、empty sample `暂无样例。`、`关闭` and `下载导出` buttons and actual download trigger behavior。不得修改 page shell、main table、filter menu、payment-rules/OA-reverse drawers、input invoice usage API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx -t "detail drawer|loads export preview|workflow primitive targets"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P059-P060/P061 payment-rules/OA-reverse source contract failures 可以继续 expected-fail，但 detail/export drawer files must disappear from source-level failure lists；运行 `cd web && npm run build`；运行 detail/export drawer MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|Drawer|TableCell|TableRow|TableHead|TableBody' web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P059 payment status rules drawer prompt。
```

#### Review

- Single slice: yes，detail and export drawers only。
- Right drawer equivalence preserved: required。
- Payment rules and OA reverse drawers untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P059-P060/P061 source failures can remain, but detail/export drawer source must clear。
- Next prompt: P059 payment status rules drawer only after P058 implementation is verified/expected-fail documented。

#### Execution Notes

- Migrated `InputInvoiceUsageDetailDrawer.tsx` and `InputInvoiceUsageExportDrawer.tsx` from MUI Drawer/table/status/action components to `AppDrawer` plus project/native markup.
- Preserved detail lazy loading, progress label, unavailable detail state, detail sections and empty detail message.
- Preserved export preview loading, refreshing notice, success message, sample table and download trigger.
- Added detail/export drawer styles in `web/src/app/styles.css`.
- Did not modify payment rules drawer, OA reverse drawer, page shell, main table, filter menu, API/mock/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|@mui/material/Drawer|TableCell|TableRow|TableHead|TableBody' web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx -t "detail drawer|loads export preview|workflow primitive targets"`: expected-fail. Detail/export selected behavior passed; source failure now lists only payment rules and OA reverse drawers.
  - `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "lazy-loads full invoice detail|supports invoice, bank, OA and relation-list detail payloads"`: passed, 2 tests passed。
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures. Detail/export drawer files no longer appear in failure lists.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### P059-phase-6-input-invoice-usage-payment-rules-drawer

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: `PaymentStatusRulesDrawer.tsx` only, plus necessary styles/tests. Do not migrate `OaReverseWorkspaceDrawer.tsx`.

#### Prompt

```text
Prompt ID: P059-phase-6-input-invoice-usage-payment-rules-drawer
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `PaymentStatusRulesDrawer.tsx` only, plus necessary styles/tests. Do not migrate `OaReverseWorkspaceDrawer.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、web/src/components/common/AppDrawer.tsx、web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx、web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 payment rules drawer 的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Box`、`Button`、`Chip`、`CircularProgress`、`Divider`、`Drawer`、`IconButton`、`Paper`、`Stack`、`Table*`、`TextField`、`Typography`。使用 `AppDrawer`、project/native status messages/loading/tags/table/inputs/buttons。必须保留 drawer title `发票与支付状态规则设置`、close label `关闭支付状态规则抽屉`、loading progress label `正在加载支付状态规则` and text `正在读取规则`、error text、success `规则已保存，读模型会按后端返回的刷新状态更新。`、version chip `版本 <n>`、read-only/no-save mode、editable `支付状态`/`规则`/`优先级` inputs、pending direction inputs/chips、`还原`、`保存规则`、dirty disabled behavior、versioned save payload with idempotency key and conflict text `规则已被其他人更新，请重新加载后再编辑。`。不得修改 page shell、main table、filter menu、detail/export drawers、OA-reverse drawer、input invoice usage API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "payment status rules|workflow primitive targets"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P060/P061 OA-reverse source contract failure 可以继续 expected-fail，但 `PaymentStatusRulesDrawer.tsx` must disappear from source-level failure lists；运行 `cd web && npm run build`；运行 payment rules MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|@mui/material/Drawer|TextField|TableCell|TableRow|TableHead|TableBody|Chip' web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P060 OA reverse workspace drawer prompt。
```

#### Review

- Single slice: yes，payment status rules drawer only。
- OA reverse drawer untouched: required。
- Versioned save and permission behavior preserved: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P060/P061 OA reverse source failure can remain, but payment rules source must clear。
- Next prompt: P060 OA reverse workspace drawer only after P059 implementation is verified/expected-fail documented。

#### Execution Notes

- Migrated `PaymentStatusRulesDrawer.tsx` from MUI Drawer/table/form/tag/status/action components to `AppDrawer` plus native/project markup.
- Preserved drawer title, close label, loading state, read-only mode, editable rule and pending-direction fields, save/reset actions, versioned/idempotent save payload and conflict message.
- Added payment rules table, tag, input and action styles in `web/src/app/styles.css`.
- Did not modify OA reverse drawer, page shell, main table, filter menu, detail/export drawers, API/mock/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|@mui/material/Drawer|TextField|TableCell|TableRow|TableHead|TableBody|Chip' web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "payment status rules|workflow primitive targets"`: expected-fail. Payment rules behavior passed; source failure now lists only OA reverse drawer.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures. `PaymentStatusRulesDrawer.tsx` no longer appears in failure lists.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。

### P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: `OaReverseWorkspaceDrawer.tsx` only, plus necessary styles/tests. This is the last input invoice usage workflow drawer slice before the module MG.

#### Prompt

```text
Prompt ID: P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `OaReverseWorkspaceDrawer.tsx` only, plus necessary styles/tests. This is the last input invoice usage workflow drawer slice before the module MG.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、web/src/components/common/AppDrawer.tsx、web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx、web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 OA reverse workspace drawer 的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Box`、`Button`、`Checkbox`、`Chip`、`CircularProgress`、`Divider`、`Drawer`、`IconButton`、`MenuItem`、`Paper`、`Stack`、`Table*`、`TextField`、`Typography`。使用 `AppDrawer`、project/native status messages/loading/metrics/sections/tags/table/checkbox/select/inputs/buttons/links。必须保留 right drawer accessible label `以发票反提 OA 工作流`、close label `关闭以发票反提 OA 工作流`、title `以发票反提 OA`、subtitle text meaning、loading progress label `正在加载反提 OA 预览` and text `正在读取后端预览`、backend-only preview totals/groups/rejections/warnings/unavailable reason, target applicant select label `目标 OA 申请人`, candidate controls `全选候选`/`清空选择`/`已选 <n> 张`, table `反提 OA 候选发票清单`, candidate checkbox labels `选择候选发票 <display no>`, empty candidate row `当前预览未返回候选发票。`, batch section `批次与 OA 草稿`, batch status fields, action buttons `创建本地批次`、`创建 OA 草稿`、`打开 OA 草稿`、`刷新 OA 状态`、`撤销本地草稿绑定`、`标记已进入 OA`、`标记未进入 OA`, reason labels `撤销原因` and `人工处理原因`, versioned/idempotent request payload behavior and manual fallback visibility。不得修改 page shell、main table、filter menu、detail/export/payment-rules drawers、input invoice usage API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "OA reverse drawer|workflow primitive targets|parent state can keep|opening and closing workflow drawers"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，now all input invoice usage source-level no-MUI contract failures must clear；运行 `cd web && npm run build`；运行 OA reverse MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|@mui/material/Drawer|TextField|TableCell|TableRow|TableHead|TableBody|Checkbox|Chip|MenuItem' web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx; then exit 1; else exit 0; fi`；运行 full input invoice usage residue grep：`if rg -n '@mui/|Mui[A-Z]' web/src/pages/InputInvoiceUsagePage.tsx web/src/components/inputInvoiceUsage; then exit 1; else exit 0; fi`。运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 InputInvoiceUsage cumulative MG prompt。
```

#### Review

- Single slice: yes，OA reverse workspace drawer only。
- Right drawer equivalence preserved: required。
- Backend-driven preview and no fabricated draft success preserved: required。
- Versioned/idempotent batch/draft/manual payloads preserved: required。
- Other input invoice usage surfaces untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: no，after P060 the input invoice usage source-level no-MUI contracts should pass.
- Next prompt: InputInvoiceUsage cumulative MG after P060 implementation is verified.

#### Execution Notes

- Migrated `OaReverseWorkspaceDrawer.tsx` from MUI Drawer/table/form/selection/tag/status/action components to `AppDrawer` plus native/project markup.
- Added optional `AppDrawer modal={false}` persistent mode with default `modal=true` unchanged. This was required to preserve the old OA workflow drawer behavior where page-level workflow buttons remain reachable while the right drawer is open.
- Preserved backend-driven preview totals/groups/rejections/warnings/unavailable reason, target applicant preview refresh, candidate selection, create batch/draft, refresh status, revoke binding, manual fallback and versioned/idempotent payload behavior.
- Added OA reverse drawer metrics, group, action, candidate table, target applicant option, form and batch styles in `web/src/app/styles.css`.
- Did not modify page shell, main table, filter menu, detail/export/payment-rules drawers, API/mock/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|@mui/material/Drawer|TextField|TableCell|TableRow|TableHead|TableBody|Checkbox|Chip|MenuItem' web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx; then exit 1; else exit 0; fi`: passed。
  - `if rg -n '@mui/|Mui[A-Z]' web/src/pages/InputInvoiceUsagePage.tsx web/src/components/inputInvoiceUsage; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "OA reverse drawer|workflow primitive targets|parent state can keep|opening and closing workflow drawers"`: passed, 6 tests passed。
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: passed, 21 tests passed。
  - `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 12 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### MG-P060-phase-6-input-invoice-usage

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `cumulative_mg`
- Scope: completed `/input-invoice-usage` page batch P053-P060.

#### Prompt

```text
Prompt ID: MG-P060-phase-6-input-invoice-usage
Scope: completed `/input-invoice-usage` page batch P053-P060.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、docs/refactor-ui/module_inventory.md、web/src/pages/InputInvoiceUsagePage.tsx、web/src/components/inputInvoiceUsage/*、web/src/components/common/AppDrawer.tsx、web/src/app/styles.css 和当前 git status。检查当前分支必须是 `refactor-ui`。检查 untracked files、diff scope、测试结果和文档状态。确认已通过：`if rg -n '@mui/|Mui[A-Z]' web/src/pages/InputInvoiceUsagePage.tsx web/src/components/inputInvoiceUsage; then exit 1; else exit 0; fi`、`cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`、`cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`、`cd web && npm run build`、`git diff --check`。只允许精确 `git add docs/refactor-ui/refactor_ui_state.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/modules/phase_6_input_invoice_usage.md web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx web/src/components/common/AppDrawer.tsx web/src/app/styles.css`；如果当前 diff 还包含本模块此前未提交的 P060 scope 文件，必须逐个精确列出；禁止 `git add .` 或 `git add -A`。commit message 使用 `feat: complete input invoice usage ui migration` 或更准确的 InputInvoiceUsage module message。push 到 `origin refactor-ui`。完成后更新 state/prompt/module docs 的 MG execution notes、verification、Push Log，标记 MG verified，并从 `refactor-ui` 分支继续生成下一条 Micro-JIT prompt。
```

#### Review

- Current branch must be `refactor-ui`.
- Scope is cumulative for the completed InputInvoiceUsage module slice; current unstaged P060 diff must be exact-staged only.
- Backend/API/read model/worker untouched: required.
- Workbench internals frozen: required.
- Verification is available and passing: source grep, focused workflow tests, full module tests, common/HeroUI smoke tests, build and diff check.
- After MG push, generate the next Micro-JIT prompt from `refactor-ui` branch.

#### Execution Notes

- Status: verified and pushed。
- Commit: `21c79cea feat: complete input invoice usage ui migration`。
- Push: `origin/refactor-ui` updated from `b076a4f3` to `21c79cea`。
- Scope committed: P060 OA reverse workspace drawer, optional `AppDrawer modal={false}` persistent mode, OA drawer styles, and state/prompt/module docs.
- Verification confirmed before push:
  - `if rg -n '@mui/|Mui[A-Z]' web/src/pages/InputInvoiceUsagePage.tsx web/src/components/inputInvoiceUsage; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: passed, 21 tests。
  - `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 12 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### P061-phase-6-oa-pending-payments-discovery

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `discovery/planning`
- Scope: `/oa-pending-payments` discovery only. Do not modify implementation or tests in this prompt.

#### Prompt

```text
Prompt ID: P061-phase-6-oa-pending-payments-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: `/oa-pending-payments` discovery only. Do not modify implementation or tests in this prompt.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、DESIGN.md、PRODUCT.md、web/src/pages/OaPendingPaymentsPage.tsx、web/src/components/oaPendingPayments/*、web/src/features/oaPendingPayments/*、web/src/test/*OaPendingPayments*.test.tsx、web/src/test/OaPendingPaymentsPage.test.tsx（如果存在）和当前 git status。梳理 `/oa-pending-payments` 的旧 UI 入口、MUI/DataGrid/Table/session hook inventory、页面 shell/toolbar/filter/status/表格/异常反馈/loading empty error stale permission 状态、复用的 `InputInvoiceUsageFilterMenu` 合同、现有测试覆盖、API/read model 风险和迁移切片风险。不得修改实现、测试、后端、API、read model、worker、mock 或关联台。若 discovery 需要跨后续切片复用，创建 `docs/refactor-ui/modules/phase_6_oa_pending_payments.md`；更新 `docs/refactor-ui/refactor_ui_state.md`、`docs/refactor-ui/refactor_ui_prompt.md` 和模块文档，生成下一条 P062 characterization tests prompt。验证命令：`test -f docs/refactor-ui/modules/phase_6_oa_pending_payments.md`；`rg -n "P061-phase-6-oa-pending-payments-discovery|Current MUI Inventory|User-visible Entrypoints|P062-phase-6-oa-pending-payments-characterization-tests" docs/refactor-ui/modules/phase_6_oa_pending_payments.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`；`git diff --check`；`git status --short --branch`。
```

#### Review

- Single slice: yes，discovery only。
- No implementation/test changes: required。
- Shared filter menu risk called out: required because `OaPendingPaymentsTable` already consumes `InputInvoiceUsageFilterMenu`。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Module doc likely warranted because this module has table/filter/status/API risk and may require multiple prompts.
- Next prompt: P062 characterization tests only after P061 discovery is verified.

#### Execution Notes

- Created `docs/refactor-ui/modules/phase_6_oa_pending_payments.md`.
- Recorded current files, MUI inventory, user-visible entrypoints, API/read model boundary, existing test coverage, slice plan and risks.
- Implementation/tests/backend/API/read model/worker/workbench unchanged.
- Next prompt generated: `P062-phase-6-oa-pending-payments-characterization-tests`.

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_oa_pending_payments.md`: passed。
  - `rg -n "P061-phase-6-oa-pending-payments-discovery|Current MUI Inventory|User-visible Entrypoints|P062-phase-6-oa-pending-payments-characterization-tests" docs/refactor-ui/modules/phase_6_oa_pending_payments.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P061/P062 docs files changed。

### P062-phase-6-oa-pending-payments-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `characterization tests`
- Scope: `/oa-pending-payments` tests only. Do not modify runtime implementation.

#### Prompt

```text
Prompt ID: P062-phase-6-oa-pending-payments-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/oa-pending-payments` tests only. Do not modify runtime implementation.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_oa_pending_payments.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/OaPendingPaymentsPage.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx 和 web/src/test/OaPendingPaymentsPage.test.tsx。只修改 `web/src/test/OaPendingPaymentsPage.test.tsx`：把 “compact grouped MUI table” wording 和 MUI/DataGrid/class-based expectations 改成 behavior/project primitive assertions；新增 source-level contracts，锁定 `OaPendingPaymentsPage.tsx` 和 `OaPendingPaymentsTable.tsx` 未来不再依赖 `@mui/*`、`Mui[A-Z]`、`TablePagination`、`TextField`、`Skeleton`、`Chip`、`IconButton`、`TableCell`、`TableRow`、`TableHead`、`TableBody`；新增或保留行为断言确保 route/sidebar、page heading、query controls、refresh/rules buttons、group headers、10 leaf columns、shared `InputInvoiceUsageFilterMenu` trigger `筛选 OA申请人`、sort button `交易时间 排序`、detail right drawer labels、rules drawer endpoint `direction=expense`、empty state and refreshing detail unavailable state保留。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P063 page shell toolbar prompt。
```

#### Review

- Single slice: yes，tests only。
- Expected failure allowed: yes，runtime still imports MUI until P063/P064.
- Must not modify implementation/mock/API/backend/read model/worker/workbench.
- Source-level contracts should fail on current page/table and guide P063/P064.
- Next prompt: P063 page shell toolbar only after P062 is verified/expected-fail documented.

#### Execution Notes

- Updated `web/src/test/OaPendingPaymentsPage.test.tsx` only.
- Renamed the main behavior test away from MUI wording.
- Replaced the `.MuiDataGrid-root` absence assertion with the user-observable table role `OA待付款核对表格`.
- Added source-level contracts for `OaPendingPaymentsPage.tsx` and `OaPendingPaymentsTable.tsx`.
- Runtime implementation, mocks, backend/API/read model/worker and workbench internals unchanged.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`: expected-fail, 5 behavior tests passed and 1 source-level contract failed. Current failure lists page/table MUI imports, table `.MuiChip-label`, legacy table/form surfaces, and missing project table primitive/class.
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P062 test and docs files changed。

### P063-phase-6-oa-pending-payments-page-shell-toolbar

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: `/oa-pending-payments` page shell/actions/query/loading/error only. Do not migrate `OaPendingPaymentsTable.tsx`.

#### Prompt

```text
Prompt ID: P063-phase-6-oa-pending-payments-page-shell-toolbar
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/oa-pending-payments` page shell/actions/query/loading/error only. Do not migrate `OaPendingPaymentsTable.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_oa_pending_payments.md、web/src/pages/OaPendingPaymentsPage.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/components/common/StatePanel.tsx、web/src/test/OaPendingPaymentsPage.test.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/OaPendingPaymentsPage.tsx`、必要 `web/src/app/styles.css` 和必要测试 expectation：移除 page shell/actions/query/loading/error scope 的 MUI imports/usages，包括 `RefreshOutlinedIcon`、`TuneOutlinedIcon`、`Alert`、`Button`、`MenuItem`、`Skeleton`、`Stack`、`TextField`。使用 project/native toolbar controls、native text/month/date/select inputs、project loading skeleton/status message and lucide icons。必须保留 `data-testid="oa-pending-payments-page"`、heading `OA 待付款核对`、buttons `支出流水无需开票规则设置` and `刷新`、search label `全页面检索`、`查询` button、Enter submit、date labels `月份`/`交易开始`/`交易结束`、payment status label `支付状态` and old options `全部`/`未支付`/`已支付`/`合并支付`/`支付少了`/`支付多了`/`待核对`、refresh disabled while refreshing、error text `OA 待付款核对加载失败。`、loading label `OA待付款核对加载中`、empty state `当前条件下暂无记录。`、detail/rules drawer wiring and API query behavior。不得修改 `OaPendingPaymentsTable.tsx`、shared filter/detail/rules drawers、mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OaPendingPaymentsPage.test.tsx -t "targets project primitives|adds sidebar route|keeps pending invoice rules drawer|uses a standard empty state|shows neutral unavailable detail"`；运行完整 `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`，P064 table source contract failure 可以继续 expected-fail，但 `src/pages/OaPendingPaymentsPage.tsx` must disappear from source-level failure lists；运行 `cd web && npm run build`；运行 page shell MUI grep：`if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|TuneOutlinedIcon|Skeleton|TextField|MenuItem' web/src/pages/OaPendingPaymentsPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P064 grouped table prompt。
```

#### Review

- Single slice: yes，page shell/query/loading/error only。
- Table untouched: required。
- Shared drawers untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P064 table source failure can remain, but page source must clear。
- Next prompt: P064 grouped table only after P063 implementation is verified/expected-fail documented.

#### Execution Notes

- Migrated `OaPendingPaymentsPage.tsx` page actions, query toolbar, loading skeleton and error alert from MUI to project/native controls.
- Replaced MUI page action icons with `lucide-react`.
- Preserved route/sidebar, heading, refresh disabling while refreshing, rules drawer trigger, query labels, Enter submit, payment status options, empty state, detail drawer wiring and expense rules drawer wiring.
- Adjusted the status text assertion in `OaPendingPaymentsPage.test.tsx` because the native select option duplicates the table text `支付少了`.
- Did not modify `OaPendingPaymentsTable.tsx`, shared filter/detail/rules drawers, API/mock/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|TuneOutlinedIcon|Skeleton|TextField|MenuItem' web/src/pages/OaPendingPaymentsPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run OaPendingPaymentsPage.test.tsx -t "targets project primitives|adds sidebar route|keeps pending invoice rules drawer|uses a standard empty state|shows neutral unavailable detail"`: expected-fail，4 behavior tests passed；remaining source-level failure lists only `src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`。
  - `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`: expected-fail，5 behavior tests passed and 1 source-level contract failed，limited to table residue。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P063 implementation/test/docs files changed。

### P064-phase-6-oa-pending-payments-grouped-table

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: `/oa-pending-payments` grouped dense table only: `OaPendingPaymentsTable.tsx`, necessary `web/src/app/styles.css` and necessary `OaPendingPaymentsPage.test.tsx` expectation updates. Do not modify page shell, shared drawers or shared `InputInvoiceUsageFilterMenu`.

#### Prompt

```text
Prompt ID: P064-phase-6-oa-pending-payments-grouped-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/oa-pending-payments` grouped dense table only: `OaPendingPaymentsTable.tsx`, necessary `web/src/app/styles.css` and necessary `OaPendingPaymentsPage.test.tsx` expectation updates. Do not modify page shell, shared drawers or shared `InputInvoiceUsageFilterMenu`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_oa_pending_payments.md、docs/refactor-ui/table_layout_system.md、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx、web/src/components/common/FinanceTable.tsx、web/src/test/OaPendingPaymentsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 `OaPendingPaymentsTable.tsx` 的 MUI imports/usages，包括 `InfoOutlinedIcon`、`SortOutlinedIcon`、`Box`、`Button`、`Chip`、`IconButton`、`Paper`、`Stack`、`Table*`、`TablePagination`、`Tooltip`、`Typography` 和 `.MuiChip-label` selector。使用 `FinanceTable`/project dense table primitives or native project table shell、project tags/buttons/tooltips、lucide icons and project pagination。必须保留 `aria-label="OA待付款核对表格"`、group headers `OA情况`/`支付状态`/`支出流水`/`发票情况`、10 leaf columns、shared `InputInvoiceUsageFilterMenu` trigger `筛选 OA申请人` and prop contract、sort button `交易时间 排序` and `bank_trade_time` query behavior、status cell project class or equivalent contract, amount right alignment/tabular nums, date/status/direction/account tags stable height, detail button labels `查看 OA <applicant> 详情` / `查看流水 <applicant> 详情` / `查看发票 <applicant> 详情` / relation-list labels, empty row `暂无 OA 待付款核对数据`, server pagination labels/options `每页`, `[20, 50, 100]` and total behavior。不得修改 page shell, shared filter/detail/rules drawers, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`，now all OA pending payments source-level no-MUI contracts must pass；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 table MUI grep：`if rg -n '@mui/|Mui[A-Z]|TablePagination|InfoOutlinedIcon|SortOutlinedIcon|TableCell|TableRow|TableHead|TableBody|Chip|IconButton' web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx; then exit 1; else exit 0; fi`；运行 full OA pending payments residue grep：`if rg -n '@mui/|Mui[A-Z]' web/src/pages/OaPendingPaymentsPage.tsx web/src/components/oaPendingPayments; then exit 1; else exit 0; fi`。运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 OA pending payments cumulative MG prompt。
```

#### Review

- Single slice: yes，grouped dense table only。
- Page shell untouched: required。
- Shared filter menu contract preserved: required。
- Shared detail/rules drawers untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: no，after P064 all OA pending payments source-level no-MUI contracts should pass。
- Next prompt: OA pending payments cumulative MG after P064 implementation is verified。

#### Execution Notes

- Migrated `OaPendingPaymentsTable.tsx` from MUI `Table*`, MUI tags/buttons/tooltips and MUI pagination to a project-owned native grouped dense table.
- Preserved `InputInvoiceUsageFilterMenu` usage and prop contract for `筛选 OA申请人`.
- Preserved accessible table name `OA待付款核对表格`, group headers, 10 leaf columns, `交易时间 排序`, `bank_trade_time` sort behavior, detail button labels and relation-list targets.
- Preserved empty row text `暂无 OA 待付款核对数据`, server pagination labels/options `每页` and `[20, 50, 100]`, and total range display.
- Added OA pending payments table, tag, action and pagination CSS using project tokens and table layout rules.
- Did not modify page shell, shared filter/detail/rules drawers, API/mock/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|TablePagination|InfoOutlinedIcon|SortOutlinedIcon|TableCell|TableRow|TableHead|TableBody|Chip|IconButton' web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx; then exit 1; else exit 0; fi`: passed。
  - `if rg -n '@mui/|Mui[A-Z]' web/src/pages/OaPendingPaymentsPage.tsx web/src/components/oaPendingPayments; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`: passed，6 tests。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed，15 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P064 table/style files changed before docs。

### MG-P064-phase-6-oa-pending-payments

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `cumulative_mg`
- Scope: completed `/oa-pending-payments` page batch P061-P064.

#### Prompt

```text
Prompt ID: MG-P064-phase-6-oa-pending-payments
Scope: completed `/oa-pending-payments` page batch P061-P064.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_oa_pending_payments.md、web/src/pages/OaPendingPaymentsPage.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx、web/src/app/styles.css 和当前 git status。检查当前分支必须是 `refactor-ui`。检查 untracked files、diff scope、测试结果和文档状态。确认已通过：`if rg -n '@mui/|Mui[A-Z]' web/src/pages/OaPendingPaymentsPage.tsx web/src/components/oaPendingPayments; then exit 1; else exit 0; fi`、`cd web && npx vitest run OaPendingPaymentsPage.test.tsx`、`cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`、`cd web && npm run build`、`git diff --check`。只允许精确 `git add docs/refactor-ui/refactor_ui_state.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/modules/phase_6_oa_pending_payments.md web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx web/src/app/styles.css`；禁止 `git add .` 或 `git add -A`。commit message 使用 `feat: complete oa pending payments ui migration`。push 到 `origin refactor-ui`。完成后更新 state/prompt/module docs 的 MG execution notes、verification、Push Log，标记 MG verified，并从 `refactor-ui` 分支继续生成下一条 Micro-JIT prompt。
```

#### Review

- Current branch must be `refactor-ui`.
- Scope is cumulative for the completed OaPendingPayments module slice; current unstaged P064 diff must be exact-staged only.
- Backend/API/read model/worker untouched: required.
- Workbench internals frozen: required.
- Verification is available and passing: source greps, full module tests, table/platform smoke tests, build and diff check.
- After MG push, generate the next Micro-JIT prompt from `refactor-ui` branch.

#### Execution Notes

- Status: verified and pushed。
- Commit: `94efb866 feat: complete oa pending payments ui migration`。
- Push: `origin/refactor-ui` updated from `24506bda` to `94efb866`。
- Scope committed: P064 grouped dense table migration, OA pending payments table styles, and state/prompt/module docs.
- Verification confirmed before push:
  - `if rg -n '@mui/|Mui[A-Z]' web/src/pages/OaPendingPaymentsPage.tsx web/src/components/oaPendingPayments; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`: passed，6 tests。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed，15 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。

### P065-phase-6-output-invoice-collections-discovery

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `discovery/planning`
- Scope: `/output-invoice-collections` discovery only. Do not modify implementation or tests in this prompt.

#### Prompt

```text
Prompt ID: P065-phase-6-output-invoice-collections-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: `/output-invoice-collections` discovery only. Do not modify implementation or tests in this prompt.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、DESIGN.md、PRODUCT.md、docs/dev/api-contracts.md#销项发票收款情况 API、docs/app-architecture/pages.md、web/src/pages/OutputInvoiceCollectionsPage.tsx、web/src/components/outputInvoiceCollections/*、web/src/features/outputInvoiceCollections/*、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和当前 git status。梳理 `/output-invoice-collections` 的旧 UI 入口、MUI/DataGrid/Table/session hook inventory、页面 shell/toolbar/query/status/表格/右侧抽屉族/弹窗/菜单/Popover/loading empty error stale permission 状态、现有测试覆盖、API/read model 风险和迁移切片风险。必须重点记录这些用户可见入口并保持行为等价：路由/sidebar label `销项发票收款情况`、page heading、rows/filter-options/status-rules/receipt-settings/receipt-preview/receipt history/detail endpoints、表格 `销项发票收款情况表`、详情右侧抽屉 `销项发票收款情况详情`、回款状态/提醒右侧抽屉、红票关系右侧抽屉、收据预览右侧抽屉、收据设置右侧抽屉、收据历史右侧抽屉、所有旧按钮/菜单/确认操作的位置和语义。不得修改实现、测试、mock、后端、API、read model、worker 或关联台。若 discovery 需要跨后续切片复用，创建 `docs/refactor-ui/modules/phase_6_output_invoice_collections.md`；更新 `docs/refactor-ui/refactor_ui_state.md`、`docs/refactor-ui/refactor_ui_prompt.md` 和模块文档，生成下一条 P066 characterization tests prompt。验证命令：`test -f docs/refactor-ui/modules/phase_6_output_invoice_collections.md`；`rg -n "P065-phase-6-output-invoice-collections-discovery|Current MUI Inventory|User-visible Entrypoints|P066-phase-6-output-invoice-collections-characterization-tests" docs/refactor-ui/modules/phase_6_output_invoice_collections.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`；`git diff --check`；`git status --short --branch`。
```

#### Review

- Single slice: yes，discovery only。
- No implementation/test changes: required。
- Module doc warranted because this module has a grouped table plus multiple right drawers, receipt lifecycle operations, settings and history surfaces.
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Next prompt: P066 characterization tests only after P065 discovery is verified.

#### Execution Notes

- Created `docs/refactor-ui/modules/phase_6_output_invoice_collections.md`.
- Recorded current files, MUI inventory, user-visible entrypoints, API/read model boundary, existing test coverage, slice plan and risks.
- Implementation/tests/backend/API/read model/worker/workbench unchanged.
- Next prompt generated: `P066-phase-6-output-invoice-collections-characterization-tests`.

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_output_invoice_collections.md`: passed。
  - `rg -n "P065-phase-6-output-invoice-collections-discovery|Current MUI Inventory|User-visible Entrypoints|P066-phase-6-output-invoice-collections-characterization-tests" docs/refactor-ui/modules/phase_6_output_invoice_collections.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P065 docs files changed。

### P066-phase-6-output-invoice-collections-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `characterization tests`
- Scope: `/output-invoice-collections` tests only. Do not modify runtime implementation.

#### Prompt

```text
Prompt ID: P066-phase-6-output-invoice-collections-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/output-invoice-collections` tests only. Do not modify runtime implementation.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/OutputInvoiceCollectionsPage.tsx、web/src/components/outputInvoiceCollections/*、web/src/features/outputInvoiceCollections/* 和 web/src/test/OutputInvoiceCollectionsPage.test.tsx。只修改 `web/src/test/OutputInvoiceCollectionsPage.test.tsx`：把 “grouped MUI Table” wording 和 MUI/DataGrid/class-based expectations 改成 behavior/project primitive assertions；新增 source-level contracts，锁定 page/table/filter/expandable/drawer files 未来不再依赖 `@mui/*`、`Mui[A-Z]`、`TablePagination`、`TextField`、`Skeleton`、`Chip`、`IconButton`、`TableCell`、`TableRow`、`TableHead`、`TableBody`、`Drawer`、`Dialog`；新增或保留行为断言确保 route/sidebar、page heading、query controls、summary tiles、refresh/status-rules/settings buttons、group headers、10 leaf columns、filter menu labels and operators、sort query, expand/collapse controls, detail right drawer labels, status/reminder/red relation/receipt history/receipt preview/receipt settings right drawers, receipt void/reissue dialogs, empty/loading/error/read-model refreshing behavior and lifecycle write payloads保留。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P067 page shell prompt。
```

#### Review

- Single slice: yes，tests only。
- Expected failure allowed: yes，runtime still imports MUI until P067-P072。
- Must not modify implementation/mock/API/backend/read model/worker/workbench.
- Source-level contracts should fail on current page/table/filter/drawer files and guide subsequent slices.
- Next prompt: P067 page shell only after P066 is verified/expected-fail documented.

#### Execution Notes

- Updated `web/src/test/OutputInvoiceCollectionsPage.test.tsx` only.
- Renamed the main behavior test away from MUI wording.
- Replaced the `.MuiDataGrid-root` absence assertion with the user-observable table role `销项发票收款情况表`.
- Added source-level contracts for page shell, grouped table, filter menu, expandable text and all output invoice collection drawers.
- Runtime implementation, mocks, backend/API/read model/worker and workbench internals unchanged.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail，5 behavior tests passed and 1 source-level contract failed. Current failure lists page/table/filter/expandable/drawer MUI imports, `.MuiButton-startIcon`, legacy MUI surfaces, missing project table class, missing `AppDrawer` and missing `AppDialog`。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P066 test file changed before docs。

### P067-phase-6-output-invoice-collections-page-shell

- Phase: `phase_6_page_batches`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: `/output-invoice-collections` page shell/actions/query/summary/loading/error only. Do not migrate table, filter menu, expandable text or drawer internals.

#### Prompt

```text
Prompt ID: P067-phase-6-output-invoice-collections-page-shell
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/output-invoice-collections` page shell/actions/query/summary/loading/error only. Do not migrate table, filter menu, expandable text or drawer internals.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、web/src/pages/OutputInvoiceCollectionsPage.tsx、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/components/common/StatePanel.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/OutputInvoiceCollectionsPage.tsx`、必要 `web/src/app/styles.css` 和必要测试 expectation：移除 page shell/actions/query/summary/loading/error scope 的 MUI imports/usages，包括 `RefreshOutlinedIcon`、`Alert`、`Box`、`Button`、`MenuItem`、`Paper`、`Skeleton`、`Stack`、`TextField`、`Typography`。使用 project/native toolbar controls、native text/month/select inputs、project summary tiles/loading skeleton/status message and lucide icons。必须保留 `data-testid="output-invoice-collections-page"`、heading `销项发票收款情况`、description、buttons `收款状态规则`/admin-only `收据编号设置`/`刷新`、refresh disabled while refreshing、query labels `关键字`/`查询`/`月份`/`收款状态`、Enter submit、quick status options from backend rules/options, summary labels `销项发票数`/`待收款金额`/`已收金额`/`待出收据数`、loading label `销项发票收款情况加载中`、empty state `当前条件下暂无记录。`、error text, table props and all drawer wiring。不得修改 `OutputInvoiceCollectionsTable.tsx`、filter menu、expandable text、drawer internals、mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route|uses a standard empty state|pauses read model"`；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`，P068-P072 source contract failures 可以继续 expected-fail，但 `src/pages/OutputInvoiceCollectionsPage.tsx` must disappear from source-level failure lists；运行 `cd web && npm run build`；运行 page shell MUI grep：`if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|Skeleton|TextField|MenuItem|Paper|Typography' web/src/pages/OutputInvoiceCollectionsPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P068 filter and expandable prompt。
```

#### Review

- Single slice: yes，page shell/query/summary/loading/error only。
- Table/filter/expandable/drawers untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P068-P072 source failures can remain, but page source must clear。
- Next prompt: P068 filter menu and expandable text only after P067 implementation is verified/expected-fail documented.

#### Execution Notes

- Migrated `OutputInvoiceCollectionsPage.tsx` page actions, query toolbar, summary tiles, loading skeleton and error alert from MUI to project/native controls.
- Replaced the refresh icon with `lucide-react`.
- Preserved route/sidebar, heading, description, refresh behavior, status rules/settings actions, query labels, Enter submit, quick status options, summary labels, empty/loading/error text, table props and all drawer wiring.
- Adjusted the status text assertion in `OutputInvoiceCollectionsPage.test.tsx` because the native quick-status option duplicates the table status text `待收款，已收部分款`.
- Did not modify table, filter menu, expandable text, drawer internals, mock/API/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|Skeleton|TextField|MenuItem|Paper|Typography' web/src/pages/OutputInvoiceCollectionsPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route|uses a standard empty state|pauses read model"`: expected-fail，selected behavior tests passed；remaining source-level failure lists only table/filter/expandable/drawer files。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail，5 behavior tests passed and 1 source-level contract failed，limited to table/filter/expandable/drawer residue。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P067 files and docs changed。

### P068-phase-6-output-invoice-collections-filter-and-expandable

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `OutputInvoiceCollectionFilterMenu.tsx` and `ExpandableCellText.tsx` only, plus necessary styles/tests. Do not migrate page shell, table or drawer internals.

#### Prompt

```text
Prompt ID: P068-phase-6-output-invoice-collections-filter-and-expandable
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `OutputInvoiceCollectionFilterMenu.tsx` and `ExpandableCellText.tsx` only, plus necessary styles/tests. Do not migrate page shell, table or drawer internals.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx、web/src/components/outputInvoiceCollections/ExpandableCellText.tsx、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 filter menu 和 expandable text 的 MUI imports/usages，包括 `ArrowDownwardOutlinedIcon`、`ArrowUpwardOutlinedIcon`、`FilterListOutlinedIcon`、`ExpandLessOutlinedIcon`、`ExpandMoreOutlinedIcon`、`Button`、`Checkbox`、`Divider`、`ListItemIcon`、`ListItemText`、`Menu`、`MenuItem`、`Radio`、`Stack`、`TextField`、`Typography`、`Box`、`IconButton`、`Tooltip` 和 `.MuiButton-startIcon` selector。使用 project/native popover/menu controls, native checkbox/radio/input/select/button controls, lucide icons and project text clamp/expand control。必须保留 trigger aria-label `筛选 <field label>`、menu aria-label `<field label>筛选与排序`、sort actions `升序排序`/`降序排序`、enum actions `全选`/`清空`/`暂无可选项`、checkbox/radio menuitem roles and option labels with counts、text mode labels `匹配方式`/`包含`/`等于`/`<label>筛选值`、money/date mode labels `区间`/`<label>最小值`/`<label>最大值`/`<label>开始日期`/`<label>结束日期`、`应用筛选`、Enter apply behavior, clear behavior, onApply/onClear/onSort prop contracts, expandable aria-label `展开 <preview>` / `收起 <preview>` and collapsed two-line behavior。不得修改 `OutputInvoiceCollectionsPage.tsx`、`OutputInvoiceCollectionsTable.tsx` except import compatibility if required, drawer internals, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route"`，P069-P072 source failures 可以继续 expected-fail，但 filter/expandable files must disappear from source-level failure lists；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` expected-fail only for table/drawers；运行 `cd web && npm run build`；运行 filter/expandable MUI grep：`if rg -n '@mui/|Mui[A-Z]|FilterListOutlinedIcon|ArrowDownwardOutlinedIcon|ArrowUpwardOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon|TextField|MenuItem|Checkbox|Radio|IconButton|Tooltip|MuiButton-startIcon' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx web/src/components/outputInvoiceCollections/ExpandableCellText.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P069 grouped table prompt。
```

#### Review

- Single slice: yes，filter menu and expandable text only。
- Page shell, table and drawers untouched: required。
- Filter prop contract preserved: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P069-P072 source failures can remain, but filter/expandable source must clear。
- Next prompt: P069 grouped table only after P068 implementation is verified/expected-fail documented.

#### Execution Notes

- Replaced MUI filter menu imports/usages with native trigger/menu controls and `lucide-react` icons.
- Preserved trigger aria-label `筛选 <field label>`、menu aria-label `<field label>筛选与排序`、sort actions、enum selection roles、option labels with counts、text/money/date labels、clear/apply behavior and onApply/onClear/onSort contracts.
- Replaced MUI expandable text stack/tooltip/icon button with project class-based clamp text and `lucide-react` chevrons.
- Added output invoice collection filter/expandable styles in `web/src/app/styles.css`.
- Did not modify page shell, grouped table runtime, drawer internals, mock/API/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|FilterListOutlinedIcon|ArrowDownwardOutlinedIcon|ArrowUpwardOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon|TextField|MenuItem|Checkbox|Radio|IconButton|Tooltip|MuiButton-startIcon' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx web/src/components/outputInvoiceCollections/ExpandableCellText.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route"`: expected-fail，main behavior test passed；remaining source-level failure lists only table and drawer files。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail，5 behavior tests passed and 1 source-level contract failed，limited to table/drawer residue。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P068 implementation files changed before docs。

### P069-phase-6-output-invoice-collections-grouped-table

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `OutputInvoiceCollectionsTable.tsx` grouped dense table only, plus necessary styles/tests. Do not migrate drawer internals.

#### Prompt

```text
Prompt ID: P069-phase-6-output-invoice-collections-grouped-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `OutputInvoiceCollectionsTable.tsx` grouped dense table only, plus necessary styles/tests. Do not migrate drawer internals.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、docs/refactor-ui/table_layout_system.md、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx、web/src/components/outputInvoiceCollections/ExpandableCellText.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 grouped table 的 MUI imports/usages，包括 `SortOutlinedIcon`、`Box`、`Button`、`Chip`、`IconButton`、`Paper`、`Stack`、`Table*`、`TablePagination`、`Tooltip`、`Typography`、`SxProps`、`Theme` 和 inline `col style`。使用 project/native grouped dense table, project tags/buttons, native/project pagination, lucide icons and tokenized table styles。必须保留 `aria-label="销项发票收款情况表"`、group headers `销项发票`/`收款状态`/`收入流水`/`收据`、10 leaf columns, filter menu prop contract, sort button labels such as `发票号码 排序`, backend sort/filter behavior, expanded cell controls, status cell class `.output-invoice-collection-status-cell`, row buttons `详情`/`状态/提醒`/`红蓝票`/`已出收据`/`待出收据`, detail/workflow target mapping, empty row `当前条件下没有销项发票收款记录。`, pagination label `每页行数`, options `[20, 50, 100]` and displayed range。不得修改 page shell, filter menu/expandable except import compatibility if required, drawer internals, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route|opens the three right-side workflow drawers"`，P070-P072 drawer source failures 可以继续 expected-fail，但 table file must disappear from source-level failure lists；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` expected-fail only for drawers；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 table MUI grep：`if rg -n '@mui/|Mui[A-Z]|TablePagination|SortOutlinedIcon|TableCell|TableRow|TableHead|TableBody|Chip|IconButton|SxProps|Theme' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P070 simple drawers prompt。
```

#### Review

- Single slice: yes，grouped table only。
- Page shell, filter menu, expandable text and drawers untouched except compatibility if required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Table layout system applies: yes，group headers, dense row content, numeric alignment and stable pagination must use project tokens。
- Expected failure allowed: yes，P070-P072 drawer source failures can remain, but table source must clear。
- Next prompt: P070 simple drawers only after P069 implementation is verified/expected-fail documented.

#### Execution Notes

- Replaced the MUI grouped table, tags, row action buttons, sort icon button and pagination with a native/project dense table.
- Preserved table aria-label、4 group headers、10 leaf columns, filter menu prop contract, sort labels, backend sort/filter behavior, expanded cell controls, `.output-invoice-collection-status-cell`, row buttons and detail/workflow target mapping.
- Replaced inline column styles with project column classes and tokenized table styles in `web/src/app/styles.css`.
- Preserved empty row text and pagination label/options/range/actions.
- Did not modify page shell, filter menu/expandable text, drawer internals, mock/API/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|TablePagination|SortOutlinedIcon|TableCell|TableRow|TableHead|TableBody|Chip|IconButton|SxProps|Theme' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route|opens the three right-side workflow drawers"`: expected-fail，selected behavior tests passed；remaining source-level failure lists only seven drawer files。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail，5 behavior tests passed and 1 source-level contract failed，limited to drawer residue。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed，15 tests passed。
  - `cd web && npm run build`: passed after fixing sort button field narrowing；known HeroUI/Tailwind CSS minifier warnings and chunk size warning remain。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P069 table/style files changed before docs。

### P070-phase-6-output-invoice-collections-simple-drawers

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `OutputInvoiceCollectionDetailDrawer.tsx`, `CollectionStatusRulesDrawer.tsx` and `ReceiptSettingsDrawer.tsx` only, plus necessary styles/tests. Do not migrate status reminder, red relation, receipt history or receipt preview drawers.

#### Prompt

```text
Prompt ID: P070-phase-6-output-invoice-collections-simple-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `OutputInvoiceCollectionDetailDrawer.tsx`, `CollectionStatusRulesDrawer.tsx` and `ReceiptSettingsDrawer.tsx` only, plus necessary styles/tests. Do not migrate status reminder, red relation, receipt history or receipt preview drawers.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、web/src/components/common/AppDrawer.tsx、web/src/components/common/StatePanel.tsx、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx、web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx、web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除这三个简单抽屉的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Box`、`Button`、`Chip`、`CircularProgress`、`Divider`、`Drawer`、`IconButton`、`MenuItem`、`Paper`、`Stack`、`Table*`、`TextField` 和 `Typography`。使用 `AppDrawer` 保持右侧抽屉形态，使用 project/native loading/error panels, native buttons, native inputs/selects, native table/card layouts and lucide close icon。必须保留 `aria-label`：详情抽屉 `销项发票收款情况详情`、规则抽屉 `收款状态规则`、设置抽屉 `收据编号设置`；保留关闭按钮 labels `关闭详情抽屉`、`关闭收款状态规则`、`关闭收据编号设置`；保留 loading labels `正在加载详情`、`正在加载收款状态规则`；保留详情 unavailable/empty 文案、规则表 `Sheet6 销项发票收款情况规则` 与 columns `收款状态`/`识别方式`/`规则`/`必要事实`/`优先级`、版本/只读 tag、后续服务边界；保留设置表单 labels `编号前缀`/`重置周期`、options `每月重置`/`每年重置`/`不按日期重置`、buttons `取消`/`保存收据编号设置`、loading/submitting disabled behavior and uppercase prefix transform。不得修改 page shell/table/filter/expandable, status reminder/red relation/receipt history/receipt preview drawers, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|opens the three right-side workflow drawers|closes lifecycle actions"`，P071-P072 drawer source failures 可以继续 expected-fail，但 these three simple drawer files must disappear from source-level failure lists；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` expected-fail only for status reminder/red relation/receipt history/receipt preview drawers；运行 `cd web && npm run build`；运行 simple drawer MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|TextField|MenuItem|TableCell|TableRow|TableHead|TableBody|Chip|IconButton|DialogTitle|DialogContent|DialogActions' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P071 workflow drawers prompt。
```

#### Review

- Single slice: yes，three simple drawers only。
- Right-side drawer shape preserved via AppDrawer: required。
- Workflow drawers and receipt lifecycle dialog untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P071-P072 source failures can remain, but these three simple drawer sources must clear。
- Next prompt: P071 status reminder and red relation workflow drawers only after P070 implementation is verified/expected-fail documented.

#### Execution Notes

- Migrated detail, collection status rules and receipt settings drawers from MUI Drawer/components to `AppDrawer`, `StatePanel`, native controls and project classes.
- Preserved right-side drawer shape, close labels, loading labels, detail unavailable/empty text, rules table columns, version/read-only tags, settings labels/options/buttons and uppercase prefix transform.
- Added output invoice collection drawer/detail/rules/settings styles in `web/src/app/styles.css`.
- Did not modify page shell/table/filter/expandable, status reminder/red relation/receipt history/receipt preview drawers, mock/API/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|TextField|MenuItem|TableCell|TableRow|TableHead|TableBody|Chip|IconButton|DialogTitle|DialogContent|DialogActions' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|opens the three right-side workflow drawers|closes lifecycle actions"`: expected-fail，selected behavior tests passed；remaining source-level failure lists only four workflow/lifecycle drawer files。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail，5 behavior tests passed and 1 source-level contract failed，limited to four drawer files。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P070 implementation files changed before docs。

### P071-phase-6-output-invoice-collections-workflow-drawers

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `CollectionStatusReminderDrawer.tsx` and `RedInvoiceRelationDrawer.tsx` only, plus necessary styles/tests. Do not migrate receipt history or receipt preview drawers.

#### Prompt

```text
Prompt ID: P071-phase-6-output-invoice-collections-workflow-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `CollectionStatusReminderDrawer.tsx` and `RedInvoiceRelationDrawer.tsx` only, plus necessary styles/tests. Do not migrate receipt history or receipt preview drawers.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、web/src/components/common/AppDrawer.tsx、web/src/components/common/StatePanel.tsx、web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx、web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除这两个 workflow 抽屉的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Button`、`Divider`、`Drawer`、`FormControlLabel`、`IconButton`、`MenuItem`、`Radio`、`RadioGroup`、`Stack`、`TextField` 和 `Typography`。使用 `AppDrawer` 保持右侧抽屉形态，使用 project/native fields, selects, textarea, radio inputs, buttons and StatePanel error。必须保留 `aria-label`/accessible name：`收款状态和提醒`、`红蓝票关系`；保留关闭 labels `关闭收款状态抽屉`、`关闭红蓝票关系抽屉`；保留字段 labels `手动状态`、`预计收款日期`、`状态备注`、`提醒时间`、`提醒备注`、`搜索关联发票`、`关联发票候选`、`关系类型`、`确认依据`；保留 buttons `撤销手动状态`、`取消提醒`、`取消`、`保存`、`撤销人工关系 <invoiceNo>`、`确认关系`；保留 status submit payload、reminder submit payload、clear/cancel reminder calls、candidate search/filter, radio candidate labels, relation type options `红字发票`/`蓝字发票`, evidence validation, confirm/revoke payloads and disabled/submitting behavior。不得修改 page shell/table/filter/expandable, simple drawers, receipt history/receipt preview drawers, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|closes lifecycle actions"`，P072 receipt source failures 可以继续 expected-fail，但 these two workflow drawer files must disappear from source-level failure lists；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` expected-fail only for receipt history/receipt preview drawers；运行 `cd web && npm run build`；运行 workflow drawer MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|TextField|MenuItem|FormControlLabel|RadioGroup|Radio|IconButton|DialogTitle|DialogContent|DialogActions' web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P072 receipt history and preview prompt。
```

#### Review

- Single slice: yes，two workflow drawers only。
- Right-side drawer shape preserved via AppDrawer: required。
- Receipt lifecycle/history/preview untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，P072 receipt drawer source failures can remain, but these two workflow drawer sources must clear。
- Next prompt: P072 receipt history and receipt preview only after P071 implementation is verified/expected-fail documented.

#### Execution Notes

- Migrated collection status/reminder and red/blue invoice relation workflow drawers from MUI to `AppDrawer`, native form controls, native radio inputs and `StatePanel`.
- Preserved right-side drawer shape, close labels, field labels, workflow buttons, status/reminder payloads, clear/cancel calls, candidate search/filter, radio candidate labels, relation type options, confirm/revoke payloads and disabled/submitting behavior.
- Added textarea, section, relation list and candidate list styles in `web/src/app/styles.css`.
- Did not modify page shell/table/filter/expandable, simple drawers, receipt history/receipt preview drawers, mock/API/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|TextField|MenuItem|FormControlLabel|RadioGroup|Radio|IconButton|DialogTitle|DialogContent|DialogActions' web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|closes lifecycle actions"`: expected-fail，lifecycle behavior test passed；remaining source-level failure lists only receipt history/preview。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail，5 behavior tests passed and 1 source-level contract failed，limited to receipt history/preview。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P071 implementation files changed before docs。

### P072-phase-6-output-invoice-collections-receipt-history-and-preview

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `ReceiptHistoryDrawer.tsx` and `ReceiptPreviewDrawer.tsx` only, plus necessary styles/tests. Do not migrate unrelated modules.

#### Prompt

```text
Prompt ID: P072-phase-6-output-invoice-collections-receipt-history-and-preview
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `ReceiptHistoryDrawer.tsx` and `ReceiptPreviewDrawer.tsx` only, plus necessary styles/tests. Do not migrate unrelated modules.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/StatePanel.tsx、web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx、web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 receipt history/preview 的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Box`、`Button`、`Chip`、`CircularProgress`、`Divider`、`Dialog*`、`Drawer`、`FormControl`、`FormControlLabel`、`IconButton`、`Paper`、`Radio`、`RadioGroup`、`Stack`、`TextField` 和 `Typography`。使用 `AppDrawer` 保持右侧抽屉形态，使用 `AppDialog` 保持作废/重开确认弹窗形态，使用 project/native cards, receipt preview grid/table, native radio inputs, native buttons and StatePanel。必须保留 accessible names：`已出收据历史`、`待出收据预览`、dialog labels `作废收据原因`/`重开收据原因`；保留关闭 labels `关闭已出收据历史`、`关闭待出收据预览`；保留 loading labels `正在加载已出收据历史`、`正在加载待出收据预览`；保留 history source unavailable/empty messages, receipt cards, buttons `作废收据 <no>`、`重开收据 <no>`、dialog fields `作废原因`/`重开原因`、buttons `取消`/`确认作废`/`确认重开`, reason validation, void/reissue calls, reload/onChanged behavior；保留 preview bank selection required warning, candidate radio list, receipt preview title `收 据`, company/date/payer/summary/amount/remark/uppercase/lowercase display, `创建正式收据` button disabled/submitting behavior and createReceipt call。不得修改 page shell/table/filter/expandable, previous drawers, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|opens the three right-side workflow drawers|closes lifecycle actions"`，source-level project primitive contract must fully pass；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`，must pass；运行 `cd web && npm run build`；运行 receipt drawer MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|TextField|FormControlLabel|RadioGroup|Radio|IconButton|DialogTitle|DialogContent|DialogActions|Dialog\\b|Drawer\\b|Chip' web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx; then exit 1; else exit 0; fi`；运行 full module no-MUI grep：`if rg -n '@mui/|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 `MG-P072-phase-6-output-invoice-collections` cumulative MG prompt。
```

#### Review

- Single slice: yes，receipt history and preview only。
- Right-side drawer shape preserved via AppDrawer: required。
- Confirmation dialog shape preserved via AppDialog: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: no，after P072 the OutputInvoiceCollections project primitive source contract and module tests must pass。
- Review correction: the draft receipt drawer grep included `Dialog\b|Drawer\b`, which would incorrectly fail approved `AppDialog`/`AppDrawer` imports. The executed grep blocks real MUI imports/usages and JSX `<Dialog>/<Drawer>` surfaces while allowing project primitives。
- Next prompt: MG-P072 cumulative module gate after P072 implementation is verified.

#### Execution Notes

- Migrated receipt history and receipt preview drawers from MUI to `AppDrawer`, `AppDialog`, `StatePanel`, native form controls, native radio inputs and project classes.
- Preserved right-side drawer accessible names `已出收据历史` and `待出收据预览`, close labels, loading labels, source unavailable/empty messages, receipt cards, void/reissue dialog labels and fields, lifecycle write calls, reload/onChanged behavior, receipt preview content and disabled create behavior.
- Added receipt history card and receipt preview grid/card styles in `web/src/app/styles.css`.
- Did not modify page shell/table/filter/expandable, previous drawers, mock/API/read model/worker/backend or reconciliation workbench internals.

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|opens the three right-side workflow drawers|closes lifecycle actions"`: passed，3 selected tests passed including source-level project primitive contract。
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: passed，6 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|TextField|FormControlLabel|RadioGroup|IconButton|DialogTitle|DialogContent|DialogActions|<Dialog|</Dialog|<Drawer|</Drawer|Chip' web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx; then exit 1; else exit 0; fi`: passed。
  - `if rg -n '@mui/|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P072 implementation files changed before docs。

### MG-P072-phase-6-output-invoice-collections

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `cumulative MG`
- Scope: Completed and verified output invoice collections migration slice P066-P072 plus related docs only.

#### Prompt

```text
Prompt ID: MG-P072-phase-6-output-invoice-collections
Phase: phase_6_page_batches
Type: cumulative MG
Scope: OutputInvoiceCollections P066-P072 completed migration only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、docs/refactor-ui/table_layout_system.md、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 `git status --short --branch`。确认当前分支必须是 `refactor-ui` 且 tracking `origin/refactor-ui`。检查 untracked files、diff、测试结果和文档状态。Scope 只允许本 MG 的 P072 implementation/docs 文件以及此前已提交的 P066-P071 历史；当前未提交 diff 应仅包含 `web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx`、`web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx`、`web/src/app/styles.css`、`docs/refactor-ui/refactor_ui_state.md`、`docs/refactor-ui/refactor_ui_prompt.md`、`docs/refactor-ui/modules/phase_6_output_invoice_collections.md`。禁止 `git add .` 和 `git add -A`；只允许精确 `git add <file...>`。

执行验证：`cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`；`cd web && npm run build`；`if rg -n '@mui/|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi`；`git diff --check`；`git status --short --branch`。如验证通过，精确 stage 上述文件，commit message 使用 `feat: migrate output invoice collection receipt drawers`，push 到 `origin refactor-ui`。push 完成后更新 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md 和 docs/refactor-ui/modules/phase_6_output_invoice_collections.md，标记 MG verified、记录 commit/push、并从最新 `refactor-ui` 状态单独生成下一条 prompt。下一条 prompt 必须基于当前状态机分析，不得预生成多个模块 prompt。
```

#### Review

- Single module boundary: yes，OutputInvoiceCollections cumulative gate only。
- Scope check required: yes，current uncommitted diff must be limited to P072 implementation/docs files。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Exact staging required: yes，no `git add .` or `git add -A`。
- Push required after verified MG: yes，push to `origin refactor-ui`。
- Next prompt generation: after push, generate exactly one next prompt from latest state。

#### Execution Notes

- Confirmed current branch `refactor-ui` and tracking `origin/refactor-ui`.
- Confirmed current uncommitted diff is limited to P072 implementation/docs files.
- Reran full module verification and no-MUI grep.
- Exact staging only; no `git add .` or `git add -A`.
- Committed and pushed `60f9593b feat: migrate output invoice collection receipt drawers` to `origin/refactor-ui`.

#### Verification

- Status: verified。
- Commands:
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: passed，6 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only allowed P072 implementation/docs files changed before exact staging。

### P073-phase-6-no-oa-bank-batches-discovery

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `discovery/planning`
- Scope: `/no-oa-bank-batches` only. Do not modify runtime implementation.

#### Prompt

```text
Prompt ID: P073-phase-6-no-oa-bank-batches-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: `/no-oa-bank-batches` only. Do not modify runtime implementation.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/baseline_inventory.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/features/noOaBankBatches/api.ts、web/src/features/noOaBankBatches/types.ts、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/test/NoOaBankBatchApi.test.ts。只做 discovery/planning：梳理当前 MUI imports/usages、用户可见入口、表格/批量选择/标签管理右侧抽屉/确认弹窗/Snackbar/状态提示、API/read model 边界、现有测试覆盖和迁移风险。若该模块需要跨后续切片复用的入口矩阵和测试策略，创建 `docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`；否则直接在现有文档记录。不得修改页面实现、测试实现、mock、API client、backend、read model、worker 或关联台内部工作区。运行 `test -f docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`；运行 `rg -n "P073-phase-6-no-oa-bank-batches-discovery|Current MUI Inventory|User-visible Entrypoints|P074-phase-6-no-oa-bank-batches-characterization-tests" docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成且只生成下一条 `P074-phase-6-no-oa-bank-batches-characterization-tests` prompt。
```

#### Review

- Single module boundary: yes，NoOaBankBatches discovery only。
- Runtime implementation untouched: required。
- Characterization before refactor: required，next prompt must be P074 tests。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Docs on demand: yes，this module is high risk and has table, batch selection, right drawer, dialogs and API/read model interactions, so module doc is required。
- Verification defined: module doc exists, key discovery terms recorded, diff/status clean for doc-only slice。

#### Execution Notes

- Created `docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`.
- Documented current MUI imports/usages, user-visible entrypoints, API/read model boundary, existing test coverage, migration slice plan, risks and next characterization prompt.
- Runtime implementation changed: no.
- Tests changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Committed and pushed `ac9a18ac docs: add no oa bank batches migration discovery` to `origin/refactor-ui`.

#### Verification

- Status: verified。
- Commands:
  - `test -f docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`: passed。
  - `rg -n "P073-phase-6-no-oa-bank-batches-discovery|Current MUI Inventory|User-visible Entrypoints|P074-phase-6-no-oa-bank-batches-characterization-tests" docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P073 docs changed。

### P074-phase-6-no-oa-bank-batches-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `characterization tests`
- Scope: `/no-oa-bank-batches` tests only. Do not modify runtime implementation.

#### Prompt

```text
Prompt ID: P074-phase-6-no-oa-bank-batches-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/no-oa-bank-batches` tests only. Do not modify runtime implementation.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/features/noOaBankBatches/api.ts、web/src/features/noOaBankBatches/types.ts、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/test/NoOaBankBatchApi.test.ts。只修改 `web/src/test/NoOaBankBatchPage.test.tsx`：新增或调整 characterization tests，锁定 `/no-oa-bank-batches` 的 project primitive 目标和旧行为。新增 source-level contract，未来 runtime 不得依赖 `@mui/*`、`Mui[A-Z]`、`RefreshOutlinedIcon`、`CloseIcon`、`ToggleButton`、`TextField`、`TableCell`、`TableRow`、`TableHead`、`TableBody`、`Drawer`、`DialogTitle`、`DialogContent`、`DialogActions`、`Snackbar`、`Chip`、`IconButton`；要求页面继续使用 `PageScaffold`、`StatePanel`，后续 drawer/dialog 使用 project primitives 或 native equivalents。行为断言必须继续覆盖 route/sidebar、heading、description/top actions、status buttons `未提交`/`已提交`/`历史`、fields `月份`/`银行账户`、main/sub rail region names and keyboard activation、transaction region/table labels, selection guard, selected-row submit payload, internal-transfer submit payload, tag drawer open/refetch/save payload/live update, withdraw dialog reason payload, snackbar messages, read model stale retry and keep-alive pause。不得修改页面实现、API client、mock data shape、backend、read model、worker 或关联台内部工作区。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx`，实现未迁移前 source-level contract expected-fail 可接受，但 existing behavior tests must pass；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P075 page shell filters prompt。
```

#### Review

- Single module boundary: yes，NoOaBankBatches tests only。
- Runtime implementation untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract should fail before runtime migration, while existing behavior tests must keep passing。
- Next prompt: P075 page shell/filter migration only after P074 tests are verified as expected-fail。

#### Execution Notes

- Added source-level project primitive/no-MUI contract to `web/src/test/NoOaBankBatchPage.test.tsx`.
- Existing behavior tests continue to cover route/sidebar, page heading, tag management, status buttons, fields, rails, transaction detail table, selected-row submit, internal-transfer submit, withdraw dialog, tag drawer refresh/save/live update, snackbar feedback and stale read model polling.
- Runtime implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Committed and pushed `4a958ce8 test: characterize no oa bank batch ui migration` to `origin/refactor-ui`.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: expected-fail，19 behavior tests passed and 1 source-level contract failed against current MUI runtime。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P074 test file changed before docs。

### P075-phase-6-no-oa-bank-batches-page-shell-filters

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/no-oa-bank-batches` page shell actions and filter region only. Do not migrate label rails, transaction region, tag drawer, withdraw dialog or snackbar.

#### Prompt

```text
Prompt ID: P075-phase-6-no-oa-bank-batches-page-shell-filters
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/no-oa-bank-batches` page shell actions and filter region only. Do not migrate label rails, transaction region, tag drawer, withdraw dialog or snackbar.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/NoOaBankBatchPage.tsx`、必要 `web/src/app/styles.css` 和必要测试 expectation：迁移 page shell actions and filter region，包括 top actions `免OA流水标签管理`/`刷新`、region `批次筛选`、status segmented buttons `未提交 <count>`/`已提交 <count>`/`历史 <count>`、fields `月份`/`银行账户`、unsubmitted `提交批次` and selected count `已选 <n> 条`。移除本 slice 的 `RefreshOutlinedIcon`、MUI `ToggleButtonGroup`、`ToggleButton` and filter `TextField` usages，使用 lucide refresh icon, project/native buttons, native segmented controls and native month/text inputs with project classes。必须保留 PageScaffold title/description/actions, tag drawer open/refetch trigger, refresh loading disabled behavior, status bucket state reset/clearSelection behavior, labels and aria pressed/current selected semantics, month/account query behavior, selected-row submit button disabled/mutating behavior and selected count text。不得修改 `LabelRail` implementation, transaction region/table/cards, tag drawer, withdraw dialog, snackbar, API client, mock data shape, backend, read model, worker or reconciliation workbench internals。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|main and child label rails"`，source-level contract expected-fail can remain but selected behavior tests must pass；运行完整 `cd web && npx vitest run NoOaBankBatchPage.test.tsx` expected-fail only for remaining source-level contract；运行 `cd web && npm run build`；运行 page-shell/filter grep：`if rg -n 'RefreshOutlinedIcon|ToggleButton|ToggleButtonGroup|<TextField[^\\n]*(label=\"月份\"|label=\"银行账户\")' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P076 label rails prompt。
```

#### Review

- Single slice: yes，page shell actions and filter region only。
- Runtime scope excludes rails/table/drawer/dialog/snackbar: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract can continue failing for rails/table/overlays until P076-P078。
- Next prompt: P076 label rails only after P075 implementation is verified as expected-fail。

#### Execution Notes

- Migrated page shell actions and filter region from MUI controls to native/project controls.
- Replaced `RefreshOutlinedIcon` with `lucide-react` `RefreshCw`.
- Replaced status `ToggleButtonGroup` / `ToggleButton` with native segmented buttons preserving labels and `aria-pressed`.
- Replaced filter `TextField` controls for `月份` and `银行账户` with labeled native inputs.
- Preserved tag drawer open/refetch trigger, refresh disabled behavior, bucket reset/clearSelection behavior, selected-row submit disabled logic and selected count text.
- Did not modify `LabelRail`, transaction region/table/cards, tag drawer, withdraw dialog, snackbar, API client, backend, read model, worker or workbench internals.
- Committed and pushed `1c872bfe feat: migrate no oa bank batch filters` to `origin/refactor-ui`.

#### Verification

- Status: verified as expected-fail。
- Commands:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|main and child label rails"`: expected-fail，4 selected behavior tests passed and 1 source-level contract failed。
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: expected-fail，19 behavior tests passed and 1 source-level contract failed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n 'RefreshOutlinedIcon|ToggleButton|ToggleButtonGroup|<TextField[^\\n]*(label="月份"|label="银行账户")' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed，only P075 implementation files changed before docs。

### P076-phase-6-no-oa-bank-batches-label-rails

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `LabelRail` and main/sub rail surfaces in `NoOaBankBatchPage.tsx` only, plus necessary styles/tests. Do not migrate transaction region, tag drawer, withdraw dialog or snackbar.

#### Prompt

```text
Prompt ID: P076-phase-6-no-oa-bank-batches-label-rails
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `LabelRail` and main/sub rail surfaces in `NoOaBankBatchPage.tsx` only, plus necessary styles/tests. Do not migrate transaction region, tag drawer, withdraw dialog or snackbar.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：迁移 `LabelRail` 以及 `主标签`/`子标签` rail surfaces，移除该 slice 的 MUI `Paper`、`List`、`ListItemButton`、`Divider`、`Box`、`Stack`、`Typography` and `.Mui-selected` rail selector usage，使用 native/project region, header, button list, count meta and project rail classes。必须保留 regions `主标签`/`子标签`、empty titles `请先在标签管理中选择免OA标签`/`暂无子标签`、titles/subtitles、button accessible names `<label> <countMeta>`、`aria-pressed` selected state, Enter/Space keyboard activation, selected main/sub state behavior and clearSelection behavior on rail selection。不得修改 page shell/filter controls, transaction region/table/cards, tag drawer, withdraw dialog, snackbar, API client, mock data shape, backend, read model, worker or reconciliation workbench internals。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|main and child label rails"`，source-level contract expected-fail can remain for table/overlays but selected behavior tests must pass；运行完整 `cd web && npx vitest run NoOaBankBatchPage.test.tsx` expected-fail only for remaining source-level contract；运行 `cd web && npm run build`；运行 rail grep：`if rg -n 'ListItemButton|<List\\b|Mui-selected' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P077 transaction region prompt。
```

#### Review

- Single slice: yes，LabelRail/main-sub rails only。
- Runtime scope excludes transaction region/table/drawer/dialog/snackbar: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract can continue failing for table/overlays until P077-P078。
- Next prompt: P077 transaction region only after P076 implementation is verified as expected-fail。

#### Execution Notes

- Status: verified as expected-fail.
- Changed `web/src/pages/NoOaBankBatchPage.tsx` and `web/src/app/styles.css`.
- Replaced `LabelRail` MUI rail structure with native section/header/button list markup and project rail classes.
- Preserved `主标签`/`子标签` region names, empty states, `<label> <countMeta>` button names, `aria-pressed`, click and Enter/Space activation, and selection-clearing behavior.
- Did not modify transaction region, tag drawer, withdraw dialog, snackbar, API client, backend, read model, worker or workbench internals.
- Committed and pushed `379d24cd feat: migrate no oa bank batch label rails` to `origin/refactor-ui`.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|main and child label rails"`: expected-fail; 4 selected behavior tests passed and 1 source-level contract failed.
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: expected-fail; 19 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n 'ListItemButton|<List\\b|Mui-selected' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P076 implementation files changed before docs.

### P077-phase-6-no-oa-bank-batches-transaction-region

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: transaction region in `NoOaBankBatchPage.tsx` only: region `流水`, batch cards, batch actions, blocking/detail/audit states, detail dense table, row checkboxes, direction/bank/source tags and amount alignment. Do not migrate tag drawer, withdraw dialog or snackbar.

#### Prompt

```text
Prompt ID: P077-phase-6-no-oa-bank-batches-transaction-region
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: transaction region in `NoOaBankBatchPage.tsx` only: region `流水`, batch cards, batch actions, blocking/detail/audit states, detail dense table, row checkboxes, direction/bank/source tags and amount alignment. Do not migrate tag drawer, withdraw dialog or snackbar.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：迁移 `流水` region、batch cards and detail table，移除该 slice 的 MUI `Paper`、`Stack`、`Divider`、`Alert`、`Button`、`Box`、`TableContainer`、`Table`、`TableHead`、`TableBody`、`TableRow`、`TableCell`、`Checkbox`、`Chip`、`Typography` 用法，使用 native/project section, card, alert/status, buttons, dense table classes, native checkboxes and project tags。必须保留 region `流水`、标题 fallback `流水`、selected label title `<主标签> / <子标签>`、bucket hint copy、`当前选择账户：...`、loading/empty/detail loading/detail empty/error states、batch account/status/row count/total amount/audit items/blocking reason、按钮 `查看流水`/`全选`/`清空`/`提交内部往来批次`/`撤回批次` 的位置、accessible labels and disabled/mutating behavior、selected batch highlighting、detail table aria-label `<账户>流水`、headers `交易时间`/`对方户名`/`金额`/`摘要/用途/备注`/`分类来源`、select-all aria label `<账户>全选`、row checkbox aria label `选择流水 <transactionId>`、single-account selection guard, `setRegionSelection`, `toggleTransaction`, `handleSubmitBatch`, `setWithdrawTarget`, amount right alignment, direction/bank tags and source labels。不得修改 page shell/filter controls, `LabelRail`, tag drawer, withdraw dialog, snackbar, API client, mock data shape, backend, read model, worker or reconciliation workbench internals。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|selects transactions|submits selected transaction|submits internal transfer|withdraw"`，source-level contract expected-fail can remain for overlays but transaction behavior tests must pass；运行完整 `cd web && npx vitest run NoOaBankBatchPage.test.tsx` expected-fail only for remaining overlay/source-level contract；运行 `cd web && npm run build`；运行 transaction grep：`if rg -n 'TableContainer|<Table\\b|TableHead|TableBody|TableRow|TableCell|<Checkbox\\b|<Chip\\b|BatchStatusChip' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P078 overlays feedback prompt。
```

#### Review

- Single slice: yes，transaction region only。
- Runtime scope excludes tag drawer, withdraw dialog and snackbar: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract can continue failing for overlays until P078。
- Next prompt: P078 overlays feedback only after P077 implementation is verified as expected-fail。

#### Execution Notes

- Status: verified as expected-fail.
- Changed `web/src/pages/NoOaBankBatchPage.tsx` and `web/src/app/styles.css`.
- Replaced transaction-region MUI table/card/status surfaces with native/project section, card, notice, button, dense table, native checkbox and project tag classes.
- Preserved region `流水`, title/hint/account copy, loading/empty/detail states, batch actions, submit/withdraw handlers, table aria-labels, checkbox labels, single-account guard, amount alignment, tags and source labels.
- Corrected the P077 residue grep to the transaction region because P078 still owns drawer `<Checkbox>` usage.
- Did not modify tag drawer, withdraw dialog, snackbar, API client, backend, read model, worker or workbench internals.
- Committed and pushed `00e0ca44 feat: migrate no oa bank batch transactions` to `origin/refactor-ui`.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|selects transactions|submits selected transaction|submits internal transfer|withdraw"`: expected-fail; 6 transaction/withdraw behavior tests passed and 1 source-level contract failed.
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: expected-fail; 19 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `sed -n '930,1096p' web/src/pages/NoOaBankBatchPage.tsx | if rg -n 'TableContainer|<Table\\b|TableHead|TableBody|TableRow|TableCell|<Checkbox\\b|<Chip\\b|BatchStatusChip'; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P077 implementation files changed before docs.

### P078-phase-6-no-oa-bank-batches-overlays-feedback

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: final `/no-oa-bank-batches` UI migration slice: tag-management right drawer, withdraw dialog, snackbar/feedback, remaining MUI page wrapper/layout imports in `NoOaBankBatchPage.tsx`, plus necessary styles/tests. This is the final runtime cleanup before MG-P078.

#### Prompt

```text
Prompt ID: P078-phase-6-no-oa-bank-batches-overlays-feedback
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: final `/no-oa-bank-batches` UI migration slice: tag-management right drawer, withdraw dialog, snackbar/feedback, remaining MUI page wrapper/layout imports in `NoOaBankBatchPage.tsx`, plus necessary styles/tests. This is the final runtime cleanup before MG-P078.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：迁移标签管理右侧抽屉、撤回确认弹窗、snackbar/feedback 和剩余页面 MUI wrapper/layout，移除 `NoOaBankBatchPage.tsx` 所有 `@mui/*` imports and MUI legacy surfaces (`Alert`, `Box`, `Button`, `Checkbox`, `Dialog*`, `Divider`, `Drawer`, `FormControlLabel`, `IconButton`, `Paper`, `Snackbar`, `Stack`, `TextField`, `Typography`, `CloseIcon`)。使用 `AppDrawer`/`AppDialog` 或 project/native equivalents、native form controls、project buttons/notices/classes and lucide close icon as needed。必须保留 tag drawer 右侧抽屉形态、dialog accessible shape、labels `免OA流水标签管理`/`关闭免OA流水标签管理`/`全选`/`清空`/`保存`、版本显示、inactive selected warning、group checkbox indeterminate semantics、child checkbox labels, tag drawer open/refetch/save payload/live update behavior, withdraw warning copy、撤回原因 field、取消/确认撤回 disabled/mutating behavior and payload, snackbar messages and close behavior, top-level page error/loading/empty behavior, current page shell/filter/rail/transaction behavior。不得修改 API client、mock data shape、backend、read model、worker or reconciliation workbench internals。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx` 必须全部通过；运行 `cd web && npx vitest run NoOaBankBatchApi.test.ts`；运行 `cd web && npm run build`；运行 no-MUI grep：`if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|Drawer\\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 MG-P078 cumulative merge gate prompt。
```

#### Review

- Single slice: yes，final overlays/feedback/runtime cleanup only。
- Runtime scope includes final no-MUI cleanup for this page because P078 is the last NoOaBankBatches runtime slice。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: no，page source-level contract should pass after P078。
- Next prompt: MG-P078 cumulative merge gate only after P078 is verified。

#### Execution Notes

- Status: verified.
- Changed `web/src/pages/NoOaBankBatchPage.tsx` and `web/src/app/styles.css`.
- Removed all direct `@mui/*` imports and legacy MUI source surfaces from `NoOaBankBatchPage.tsx`.
- Replaced final MUI wrapper/layout, tag drawer, withdraw dialog and snackbar surfaces with native/project markup, `AppDialog`, native checkboxes/textarea and project CSS classes.
- Preserved tag-management right-side shape, labels, version display, inactive warning, group indeterminate semantics, child labels, open/refetch/save/live update behavior, withdraw reason payload, feedback messages and current page shell/filter/rail/transaction behavior.
- Did not modify API client, backend, read model, worker or workbench internals.
- Committed and pushed `87b92e20 feat: complete no oa bank batch ui migration` to `origin/refactor-ui`.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: passed; 20 tests passed.
  - `cd web && npx vitest run NoOaBankBatchApi.test.ts`: passed; 7 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|Drawer\\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P078 implementation files changed before docs.

### MG-P078-phase-6-no-oa-bank-batches

- Phase: `phase_6_page_batches`
- Status: `mg_verified`
- Type: `cumulative merge gate`
- Scope: completed `/no-oa-bank-batches` UI migration slices P073-P078 only.

#### Prompt

```text
Prompt ID: MG-P078-phase-6-no-oa-bank-batches
Phase: phase_6_page_batches
Type: cumulative merge gate
Scope: completed `/no-oa-bank-batches` UI migration slices P073-P078 only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx、web/src/test/NoOaBankBatchApi.test.ts 和当前 git status/diff。检查当前分支必须是 `refactor-ui`。确认 untracked files、diff scope、测试结果和文档状态；确认 P073-P078 已记录且 P078 后 `NoOaBankBatchPage.tsx` 无 direct MUI import/source residue。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx NoOaBankBatchApi.test.ts`；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 no-MUI grep：`if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|Drawer\\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。确认 scope 只包含 `docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`、`docs/refactor-ui/refactor_ui_prompt.md`、`docs/refactor-ui/refactor_ui_state.md`、`web/src/app/styles.css`、`web/src/pages/NoOaBankBatchPage.tsx` 及必要 test docs；禁止 `git add .` 和 `git add -A`，只允许精确 git add。MG 通过后提交并 push 到 `origin/refactor-ui`，再更新 state/prompt/module docs 的 MG execution notes 和 Push Log，标记 MG verified，并从 `refactor-ui` 分支生成下一条 Micro-JIT prompt。
```

#### Review

- Cumulative boundary reached: yes，P073-P078 completed for `/no-oa-bank-batches`。
- Scope excludes backend/API/read model/worker and workbench internals: required。
- Exact staging required: yes。
- Push required: yes，push to `origin refactor-ui`。

#### Execution Notes

- Status: mg_verified.
- Worktree before MG docs update: clean on `refactor-ui`.
- Scope checked: P073-P078 `/no-oa-bank-batches` only.
- Runtime result: `NoOaBankBatchPage.tsx` has no direct MUI import or legacy MUI source residue.
- Backend/API/read model/worker and workbench internals unchanged.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx NoOaBankBatchApi.test.ts`: passed; 27 tests passed.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed; 15 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|Drawer\\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; clean before MG docs update.
- Committed and pushed `f5736c0c docs: record no oa bank batch merge gate` to `origin/refactor-ui`.
- Next prompt generated: `P079-phase-6-batch-accounting-discovery`.

### P079-phase-6-batch-accounting-discovery

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `discovery/planning`
- Scope: `/batch-accounting` only. Do not modify runtime implementation or tests.

#### Prompt

```text
Prompt ID: P079-phase-6-batch-accounting-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: `/batch-accounting` only. Do not modify runtime implementation or tests.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/baseline_inventory.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BatchAccountingPage.tsx、web/src/features/batchAccounting/api.ts、web/src/features/batchAccounting/types.ts、web/src/test/BatchAccountingPage.test.tsx、docs/app-architecture/pages.md 和当前 git status。只做 discovery/planning：梳理 `/batch-accounting` 当前 MUI imports/usages、用户可见入口、表格/双栏选择/提交/撤回弹窗/Snackbar/状态提示、API/read model 边界、现有测试覆盖和迁移风险。必须重点记录这些用户可见入口并保持行为等价：route `/batch-accounting`、sidebar label `批量账务`、page heading `日常报销批量账务管理`、description、年份字段 `银行年份`/`OA 年份`、状态切换 `未提交`/`已提交`、region `批量账务流水`、OA/relation detail region、bank row accessible names、OA row checkboxes、金额一致/差异提示、提交按钮、撤回批次弹窗、feedback messages、loading/empty/error states and stale/refresh behavior if present。不得修改页面实现、测试实现、mock、API client、backend、read model、worker 或关联台内部工作区。若该模块需要跨后续切片复用的入口矩阵和测试策略，创建 `docs/refactor-ui/modules/phase_6_batch_accounting.md`；否则直接在现有文档记录。运行 `test -f docs/refactor-ui/modules/phase_6_batch_accounting.md`；运行 `rg -n "P079-phase-6-batch-accounting-discovery|Current MUI Inventory|User-visible Entrypoints|P080-phase-6-batch-accounting-characterization-tests" docs/refactor-ui/modules/phase_6_batch_accounting.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成且只生成下一条 `P080-phase-6-batch-accounting-characterization-tests` prompt。
```

#### Review

- Single slice: yes，discovery only。
- Runtime/test implementation excluded: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Next prompt: P080 characterization tests only after P079 is verified。

#### Execution Notes

- Status: verified.
- Created `docs/refactor-ui/modules/phase_6_batch_accounting.md`.
- Runtime implementation changed: no.
- Test implementation changed: no.
- Backend/API/read model/worker and workbench internals changed: no.
- Discovery recorded current MUI inventory, user-visible entrypoints, API/read model boundary, existing test coverage, migration slice plan and risks.
- Committed and pushed `e113d6e6 docs: add batch accounting migration discovery` to `origin/refactor-ui`.
- Verification:
  - `test -f docs/refactor-ui/modules/phase_6_batch_accounting.md`: passed.
  - `rg -n "P079-phase-6-batch-accounting-discovery|Current MUI Inventory|User-visible Entrypoints|P080-phase-6-batch-accounting-characterization-tests" docs/refactor-ui/modules/phase_6_batch_accounting.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P079 docs changed.

### P080-phase-6-batch-accounting-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `characterization tests`
- Scope: `/batch-accounting` tests only. Do not modify runtime implementation.

#### Prompt

```text
Prompt ID: P080-phase-6-batch-accounting-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/batch-accounting` tests only. Do not modify runtime implementation.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_batch_accounting.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BatchAccountingPage.tsx、web/src/features/batchAccounting/api.ts、web/src/features/batchAccounting/types.ts 和 web/src/test/BatchAccountingPage.test.tsx。只修改 `web/src/test/BatchAccountingPage.test.tsx`：新增 source-level contract，未来 `BatchAccountingPage.tsx` 不得依赖 `@mui/*`、`Mui[A-Z]`、MUI icons (`ClearOutlinedIcon`/`RefreshOutlinedIcon`/`SearchOutlinedIcon`/`WarningAmberRoundedIcon`)、`ToggleButton`、`TextField`、`TableCell`、`TableRow`、`TableHead`、`TableBody`、`DialogTitle`、`DialogContent`、`DialogActions`、`Snackbar`、`Chip`、`IconButton`、`Tooltip`；要求页面继续使用 `PageScaffold`、`StatePanel` and project/native table/panel/dialog/feedback classes or primitives。保留并必要补强行为断言：route/sidebar label `批量账务`、heading `日常报销批量账务管理`、refresh、status buttons `未提交`/`已提交`、fields `流水年份`/`OA年份`/`搜索OA内容`/`差额说明`、region `批量账务流水`、bank row accessible names and `aria-pressed`, table aria-label `可关联OA项`/`已关联OA项`, OA checkbox labels, search clear button, amount summary and mismatch tooltip, submit payload/event, withdraw dialog payload, feedback messages, loading/empty/error states, and selection/note reset behavior。不得修改页面实现、API client、mock data shape、backend、read model、worker 或关联台内部工作区。运行 `cd web && npx vitest run BatchAccountingPage.test.tsx`，实现未迁移前 source-level contract expected-fail 可接受，但 existing behavior tests must pass；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P081 page shell filters prompt。
```

#### Review

- Single slice: yes，tests only。
- Runtime implementation excluded: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract should fail against current MUI runtime until P081-P084.
- Next prompt: P081 page shell filters only after P080 behavior tests are preserved.

#### Execution Notes

- Added `web/src/test/BatchAccountingPage.test.tsx` source-level no-MUI/project primitive contract for `BatchAccountingPage.tsx`.
- Added behavior coverage for loading/empty states and page-level API error fallback.
- Preserved existing behavior coverage for heading, route/sidebar entry, refresh, status buttons, year fields, bank region, OA table labels, OA checkbox labels, search clear, amount summary, mismatch note, submit payload/event, withdraw payload, feedback messages and selection/note reset behavior.
- Runtime implementation changed: no.
- Backend/API/read model/worker and workbench internals changed: no.
- Committed and pushed `cae1d091 test: characterize batch accounting ui migration` to `origin/refactor-ui`.
- Verification:
  - `cd web && npx vitest run BatchAccountingPage.test.tsx`: expected-fail; 12 behavior tests passed and 1 source-level contract failed against current MUI runtime.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P080 test file changed before docs.
- Next prompt generated: `P081-phase-6-batch-accounting-page-shell-filters`.

### P081-phase-6-batch-accounting-page-shell-filters

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/batch-accounting` page shell, refresh action, status switch and year/search filters only.

#### Prompt

```text
Prompt ID: P081-phase-6-batch-accounting-page-shell-filters
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/batch-accounting` page shell, refresh action, status switch and year/search filters only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_batch_accounting.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BatchAccountingPage.tsx、web/src/test/BatchAccountingPage.test.tsx 和 web/src/app/styles.css。只迁移 `BatchAccountingPage.tsx` 的页面头部刷新按钮、`批量账务状态` 状态切换、`流水年份`、`OA年份`、`搜索OA内容` 和 `清空搜索` 控件到项目/Tailwind/native controls；必要时只补 `web/src/app/styles.css` 中的 `batch-accounting-*` shell/filter classes。不得迁移银行流水列表、金额 summary、差额说明、OA table、OA checkbox、AmountMismatchWarning tooltip、withdraw dialog、Snackbar/Alert 反馈、API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：`刷新` disabled while loading、`未提交`/`已提交` exclusive `aria-pressed`、bucket switch clears selected bank/OA rows and difference note、year/search labels and values、OA search filtering and `清空搜索` button。运行 `cd web && npx vitest run BatchAccountingPage.test.tsx -t "targets project primitives|renders controls|filters right side OA rows|clears difference note when switching submitted and unsubmitted buckets|keeps selected bank and OA rows"`，预期 source-level contract 仍 expected-fail 但 selected behavior tests must pass；运行 `cd web && npx vitest run BatchAccountingPage.test.tsx`，预期 12 behavior tests pass and source-level contract remains expected-fail until P082-P084；运行 `cd web && npm run build`；运行 scoped grep：`if rg -n 'RefreshOutlinedIcon|SearchOutlinedIcon|ClearOutlinedIcon|ToggleButton|ToggleButtonGroup|InputAdornment|label="流水年份"|label="OA年份"|label="搜索OA内容"' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P082 bank list and summary prompt。
```

#### Review

- Single slice: yes，page shell/filter only。
- Runtime implementation limited: yes，only page shell/filter controls and necessary CSS classes。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Overlay/table/bank-list migration excluded: yes，reserved for P082-P084。
- Expected failure allowed: yes，source-level contract remains expected-fail until remaining MUI surfaces are cleared。
- Next prompt: P082 bank list and summary only after P081 scoped behavior and grep pass。

#### Execution Notes

- Replaced header `刷新` action with project native button and lucide `RefreshCw`.
- Replaced MUI status ToggleButtonGroup/ToggleButton with native project segmented buttons preserving `批量账务状态`, `未提交`/`已提交` labels and `aria-pressed`.
- Replaced MUI year/search TextFields, InputAdornment, IconButton and MUI search/clear icons for `流水年份`, `OA年份`, `搜索OA内容` and `清空搜索` with native labelled controls and `batch-accounting-*` CSS classes.
- Added `web/src/app/styles.css` `batch-accounting-*` shell/filter classes.
- Did not migrate bank list, amount summary, OA table, withdraw dialog, snackbar/alert feedback, API client, backend, read model, worker or workbench internals.
- Committed and pushed `64aa7da3 feat: migrate batch accounting page shell` to `origin/refactor-ui`.
- Verification:
  - `cd web && npx vitest run BatchAccountingPage.test.tsx -t "targets project primitives|renders controls|filters right side OA rows|clears difference note when switching submitted and unsubmitted buckets|keeps selected bank and OA rows"`: expected-fail; selected behavior tests passed and source-level contract failed as expected.
  - `cd web && npx vitest run BatchAccountingPage.test.tsx`: expected-fail; 12 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n 'RefreshOutlinedIcon|SearchOutlinedIcon|ClearOutlinedIcon|ToggleButton|ToggleButtonGroup|InputAdornment|label="流水年份"|label="OA年份"|label="搜索OA内容"' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P081 page/style files changed before docs.
- Current expected source-level failure now lists remaining OA table, withdraw dialog and mutation feedback/toast targets.
- Next prompt generated: `P082-phase-6-batch-accounting-bank-list-and-summary`.

### P082-phase-6-batch-accounting-bank-list-and-summary

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/batch-accounting` bank row region/list, amount summary, mismatch note field and submitted amount-mismatch warning only.

#### Prompt

```text
Prompt ID: P082-phase-6-batch-accounting-bank-list-and-summary
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/batch-accounting` bank row region/list, amount summary, mismatch note field and submitted amount-mismatch warning only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_batch_accounting.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BatchAccountingPage.tsx、web/src/test/BatchAccountingPage.test.tsx 和 web/src/app/styles.css。只迁移 `BatchAccountingPage.tsx` 中 `批量账务流水` region/list rows, bank row selected styling, bank row date/direction/account tags, amount summary tags (`银行流水金额`/`已选 OA`/`已选 OA 金额`/`差额`/`金额不一致`), `差额说明` field, and `查看金额不一致差额说明` warning affordance 到项目/Tailwind/native controls；必要时只补 `web/src/app/styles.css` 中的 `batch-accounting-*` bank/summary/warning classes。不得迁移 OA table、OA checkbox、ExpandableText、withdraw dialog、Snackbar/Alert 反馈、API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：bank region aria-label `批量账务流水`, copy `对方户名精确匹配批量账务集中处理`, bank row accessible name and `aria-pressed`, selecting bank clears OA selection and difference note, amount summary text/format, mismatch note required/trim behavior, submitted mismatch `金额不一致` and hover/focus/click access to bank amount/OA amount/delta/note. 运行 `cd web && npx vitest run BatchAccountingPage.test.tsx -t "targets project primitives|renders controls|updates selected totals|submits mismatched|clears difference note when switching bank rows|renders submitted bucket"`，预期 source-level contract 仍 expected-fail 但 selected behavior tests must pass；运行 `cd web && npx vitest run BatchAccountingPage.test.tsx`，预期 12 behavior tests pass and source-level contract remains expected-fail until P083-P084；运行 `cd web && npm run build`；运行 scoped grep：`if rg -n 'WarningAmberRoundedIcon|Tooltip|IconButton|<TextField[^\\n]*(label="差额说明")|银行流水金额.*<Chip|已选 OA.*<Chip|差额.*<Chip' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P083 OA table prompt。
```

#### Review

- Single slice: yes，bank list and summary only。
- Runtime implementation limited: yes，only bank region/list, amount summary, mismatch note and mismatch warning with necessary CSS。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- OA table/dialog/feedback migration excluded: yes，reserved for P083-P084。
- Expected failure allowed: yes，source-level contract remains expected-fail until remaining MUI surfaces are cleared。
- Next prompt: P083 OA table only after P082 scoped behavior and grep pass。

#### Execution Notes

- Replaced `批量账务流水` region/list rows with project native panel/list/tag classes.
- Replaced amount summary chips and `差额说明` field with project native summary tags and labelled input.
- Replaced submitted amount mismatch warning with native warning button, tooltip container and lucide `AlertTriangle`.
- Added `web/src/app/styles.css` `batch-accounting-*` bank/list/summary/warning classes.
- Preserved bank row accessible names, `aria-pressed`, bank selection reset, amount summary text/format, mismatch note trim requirement, submitted mismatch `金额不一致`, and hover/focus/click access to mismatch details.
- Did not migrate OA table, withdraw dialog, snackbar/alert feedback, API client, backend, read model, worker or workbench internals.
- Committed and pushed `7dd51d20 feat: migrate batch accounting bank summary` to `origin/refactor-ui`.
- Verification:
  - `cd web && npx vitest run BatchAccountingPage.test.tsx -t "targets project primitives|renders controls|updates selected totals|submits mismatched|clears difference note when switching bank rows|renders submitted bucket"`: expected-fail; selected behavior tests passed and source-level contract failed as expected.
  - `cd web && npx vitest run BatchAccountingPage.test.tsx`: expected-fail; 12 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n 'WarningAmberRoundedIcon|Tooltip|IconButton|<TextField[^\\n]*(label="差额说明")|银行流水金额.*<Chip|已选 OA.*<Chip|差额.*<Chip' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P082 page/style files changed before docs.
- Current expected source-level failure now lists remaining OA table, withdraw dialog and mutation feedback/toast targets.
- Next prompt generated: `P083-phase-6-batch-accounting-oa-table`.

### P083-phase-6-batch-accounting-oa-table

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/batch-accounting` OA/relation table, native checkbox selection, ExpandableText and table empty states only.

#### Prompt

```text
Prompt ID: P083-phase-6-batch-accounting-oa-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/batch-accounting` OA/relation table, native checkbox selection, ExpandableText and table empty states only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_batch_accounting.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BatchAccountingPage.tsx、web/src/test/BatchAccountingPage.test.tsx 和 web/src/app/styles.css。只迁移 `BatchAccountingPage.tsx` 中 `可关联OA项`/`已关联OA项` table, table header/body/row/cell, OA row checkbox, applicant/date cell, project/reason `ExpandableText`, amount cell, and OA empty states 到项目/Tailwind/native table controls；必要时只补 `web/src/app/styles.css` 中的 `batch-accounting-*` OA table/expandable text/checkbox classes。不得迁移 withdraw dialog、Snackbar/Alert 反馈、submit/withdraw action buttons outside the table panel、API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：table aria-label switches between `可关联OA项` and `已关联OA项`, unsubmitted bucket shows checkbox labels `选择 <申请人> <申请时间>`, submitted bucket is read-only and hides checkbox column, applicant/apply time/project/amount/reason text remains visible, project/reason expand/collapse remains available for long text, amount column remains right-aligned/tabular, empty text `暂无可关联 OA`/`暂无已关联 OA` remains in table area, OA search filtering still works, selected OA rows and submit payload remain stable. 运行 `cd web && npx vitest run BatchAccountingPage.test.tsx -t "targets project primitives|renders controls|filters right side OA rows|keeps selected bank and OA rows|renders submitted bucket|shows loading and empty states"`，预期 source-level contract 仍 expected-fail 但 selected behavior tests must pass；运行 `cd web && npx vitest run BatchAccountingPage.test.tsx`，预期 12 behavior tests pass and source-level contract remains expected-fail until P084；运行 `cd web && npm run build`；运行 scoped grep：`if rg -n '<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Checkbox|<Chip|MuiTable|MuiCheckbox|MuiChip' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P084 overlays feedback prompt。
```

#### Review

- Single slice: yes，OA table only。
- Runtime implementation limited: yes，only OA/relation table, checkbox, ExpandableText, amount cell and empty states with necessary CSS。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Withdraw dialog and feedback migration excluded: yes，reserved for P084。
- Expected failure allowed: yes，source-level contract remains expected-fail until remaining overlay/feedback surfaces are cleared。
- Next prompt: P084 overlays feedback only after P083 scoped behavior and grep pass。

#### Execution Notes

- Implemented: `BatchAccountingPage.tsx` OA relation table migrated from MUI `Table`/`Checkbox`/`Chip` surfaces to native table, native checkbox and `batch-accounting-*` classes。
- Implemented: `ExpandableText` migrated from MUI layout/text/button primitives to native text and button controls while preserving expand/collapse copy。
- Implemented: OA table empty states remain inside the table area and preserve `暂无可关联 OA` / `暂无已关联 OA` behavior。
- Verification:
  - `cd web && npx vitest run BatchAccountingPage.test.tsx -t "targets project primitives|renders controls|filters right side OA rows|keeps selected bank and OA rows|renders submitted bucket|shows loading and empty states"`: expected-fail；selected behavior tests passed，source-level contract failed as expected for remaining dialog/feedback targets。
  - `cd web && npx vitest run BatchAccountingPage.test.tsx`: expected-fail；12 behavior tests passed，1 source-level contract failed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Checkbox|<Chip|MuiTable|MuiCheckbox|MuiChip' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P083 page/style files changed before docs。
- Commit: `1ae9068d feat: migrate batch accounting oa table`, pushed to `origin/refactor-ui`.
- Current expected source-level failure now lists remaining withdraw dialog and mutation feedback/toast targets。
- Next prompt generated: `P084-phase-6-batch-accounting-overlays-feedback`.

### P084-phase-6-batch-accounting-overlays-feedback

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/batch-accounting` withdraw dialog, mutation feedback, remaining action buttons/layout wrappers and final page MUI cleanup only.

#### Prompt

```text
Prompt ID: P084-phase-6-batch-accounting-overlays-feedback
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/batch-accounting` withdraw dialog, mutation feedback, remaining action buttons/layout wrappers and final page MUI cleanup only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_batch_accounting.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BatchAccountingPage.tsx、web/src/components/common/AppDialog.tsx、web/src/test/BatchAccountingPage.test.tsx 和 web/src/app/styles.css。迁移 `BatchAccountingPage.tsx` 剩余 MUI surfaces：submit/withdraw action buttons, OA panel wrapper/layout, withdraw dialog (`撤回关联`/`撤回原因`/`取消`/`确认撤回`), snackbar/alert feedback (`已关联批量账务流水与 2 项 OA。`/`已撤回批量账务关联。`/error fallbacks), and any remaining MUI Box/Paper/Button/Dialog/TextField/Snackbar/Alert/Stack/Divider imports 到 `AppDialog`、native/project controls and `batch-accounting-*` classes。不得修改 API client、mock data shape、backend、read model、worker、domain event name/payload 或关联台内部工作区。保留用户可见行为：submit disabled/enabled rules, submitted withdraw button disabled rules, modal dialog role/name `撤回关联`, `撤回原因` accessible label, confirm disabled without trimmed reason, cancel/close behavior, withdraw payload `{ expected_version, reason }`, feedback messages and close/autohide-equivalent behavior, and `FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated` source `batch_accounting_mutation`. 运行 `cd web && npx vitest run BatchAccountingPage.test.tsx`，现在 source-level contract must pass and all behavior tests must pass；运行 `cd web && npm run build`；运行 no-MUI grep：`if rg -n '@mui/|Mui[A-Z]|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|TextField|<Button|<Dialog|<Stack|<Paper|<Box|<Divider' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 MG-P084 cumulative merge gate prompt。
```

#### Review

- Single slice: yes，only remaining overlay/feedback/action/layout cleanup for `/batch-accounting`。
- Runtime implementation limited: yes，no API/mocks/backend/read model/worker/domain event changes。
- Workbench internals frozen: required。
- Behavior preservation explicit: yes，dialog role/name, reason field, disabled rules, feedback messages and domain event source are locked。
- Verification strictness: full `BatchAccountingPage.test.tsx` must pass；source-level no-MUI/project primitive contract must pass。
- Next prompt: MG-P084 only after P084 tests, build, no-MUI grep and docs pass。

#### Execution Notes

- Implemented: remaining `BatchAccountingPage.tsx` MUI imports and legacy surfaces removed, including Box/Paper/Stack/Divider/Button/Dialog/TextField/Snackbar/Alert。
- Implemented: right-side OA panel wrapper/layout and submit/withdraw action buttons migrated to native/project controls and `batch-accounting-*` classes。
- Implemented: withdraw confirmation migrated to `AppDialog` with native labelled textarea while preserving `撤回关联`, `撤回原因`, confirm disabled rule and withdraw payload。
- Implemented: mutation feedback migrated to `batch-accounting-feedback` with close and 4000ms auto-hide behavior。
- Verification:
  - `cd web && npx vitest run BatchAccountingPage.test.tsx`: passed；13 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|Mui[A-Z]|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|TextField|<Button|<Dialog|<Stack|<Paper|<Box|<Divider' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
- Commit: `ef41572f feat: migrate batch accounting overlays`, pushed to `origin/refactor-ui`.
- Next prompt generated: `MG-P084-phase-6-batch-accounting`.

### MG-P084-phase-6-batch-accounting

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `cumulative merge gate`
- Scope: `/batch-accounting` P080-P084 characterization and UI migration only.

#### Prompt

```text
Prompt ID: MG-P084-phase-6-batch-accounting
Type: cumulative merge gate
Scope: `/batch-accounting` P080-P084 characterization and UI migration only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_batch_accounting.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BatchAccountingPage.tsx、web/src/test/BatchAccountingPage.test.tsx 和 web/src/app/styles.css。检查当前分支必须是 `refactor-ui`。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 BatchAccounting P080-P084：characterization tests, page shell/filters, bank list/summary, OA table, overlays/feedback and final page MUI cleanup。不得包含 backend/API/read model/worker、mock data shape、domain event semantic changes 或关联台内部工作区。运行 `cd web && npx vitest run BatchAccountingPage.test.tsx`、`cd web && npm run build`、no-MUI grep `if rg -n '@mui/|Mui[A-Z]|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|TextField|<Button|<Dialog|<Stack|<Paper|<Box|<Divider' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`、`git diff --check`、`git status --short --branch`。只允许精确 `git add web/src/pages/BatchAccountingPage.tsx web/src/app/styles.css docs/refactor-ui/modules/phase_6_batch_accounting.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`；禁止 `git add .` 和 `git add -A`。提交并 push 到 `origin/refactor-ui`。完成后更新 state/prompt/module docs 和 Push Log，标记 MG verified。
```

#### Review

- Merge boundary reached: yes，BatchAccounting source-level contract now passes and final page no-MUI grep is clean。
- Scope limited: yes，only page/style and refactor-ui docs。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Exact staging required: yes，no `git add .` or `git add -A`。

#### Execution Notes

- Merge gate status: verified.
- Scope check: passed；worktree was clean before MG docs and current branch was `refactor-ui...origin/refactor-ui`.
- Verification:
  - `cd web && npx vitest run BatchAccountingPage.test.tsx`: passed；13 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|Mui[A-Z]|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|TextField|<Button|<Dialog|<Stack|<Paper|<Box|<Divider' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；clean worktree before MG docs。
- Commit: `5747bf90 docs: verify batch accounting mg and add turnover discovery`, pushed to `origin/refactor-ui`.
- Next prompt generated: `P085-phase-6-turnover-ledger-discovery`.

### P085-phase-6-turnover-ledger-discovery

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `discovery/planning`
- Scope: `/turnover-ledger` only.

#### Prompt

```text
Prompt ID: P085-phase-6-turnover-ledger-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: `/turnover-ledger` only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/TurnoverLedgerPage.tsx、web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx、web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx、web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx、web/src/test/TurnoverLedgerPage.test.tsx、web/src/test/TurnoverLedgerApi.test.ts、web/src/features/turnoverLedger/api.ts 和 web/src/features/turnoverLedger/types.ts。只做 discovery/planning：生成或更新 docs/refactor-ui/modules/phase_6_turnover_ledger.md，记录当前 MUI inventory、用户可见入口、表格/左右双栏排版风险、右侧抽屉和导出弹窗边界、现有测试覆盖、需要新增的 characterization tests、推荐 Micro-JIT 切片队列和 P086 prompt。不得修改 runtime code、tests、API client、backend、read model、worker、domain event semantics 或关联台内部工作区。保留原则：大布局和使用感不变，旧右侧抽屉仍为右侧抽屉，旧导出弹窗仍为弹窗，旧按钮/选择/展开/补充信息/导出入口位置保持等价。运行 `test -f docs/refactor-ui/modules/phase_6_turnover_ledger.md`、`rg -n "P085-phase-6-turnover-ledger-discovery|Current MUI Inventory|User-visible Entrypoints|Recommended Micro-JIT Queue|P086-phase-6-turnover-ledger-characterization-tests" docs/refactor-ui/modules/phase_6_turnover_ledger.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs。完成后提交并 push 到 `origin/refactor-ui`，再写入 Push Log。
```

#### Review

- Single slice: yes，discovery only。
- Runtime/test implementation excluded: yes。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Next prompt: P086 characterization tests only after P085 discovery doc and grep pass。

#### Execution Notes

- Discovery doc created: `docs/refactor-ui/modules/phase_6_turnover_ledger.md`.
- Runtime implementation changed: no.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - `test -f docs/refactor-ui/modules/phase_6_turnover_ledger.md`: passed。
  - `rg -n "P085-phase-6-turnover-ledger-discovery|Current MUI Inventory|User-visible Entrypoints|Recommended Micro-JIT Queue|P086-phase-6-turnover-ledger-characterization-tests" docs/refactor-ui/modules/phase_6_turnover_ledger.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P085/MG docs changed。
- Commit: `5747bf90 docs: verify batch accounting mg and add turnover discovery`, pushed to `origin/refactor-ui`.
- Next prompt generated: `P086-phase-6-turnover-ledger-characterization-tests`.

### P086-phase-6-turnover-ledger-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `characterization tests`
- Scope: `/turnover-ledger` source-level and behavior guardrails only.

#### Prompt

```text
Prompt ID: P086-phase-6-turnover-ledger-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/turnover-ledger` source-level and behavior guardrails only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/TurnoverLedgerPage.tsx、web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx、web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx、web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx、web/src/test/TurnoverLedgerPage.test.tsx、web/src/test/TurnoverLedgerApi.test.ts、web/src/features/turnoverLedger/api.ts 和 web/src/features/turnoverLedger/types.ts。只修改 `web/src/test/TurnoverLedgerPage.test.tsx`，新增 source-level no-MUI/project primitive contract 和必要的用户可见行为 characterization tests。不得修改 runtime code、API client、backend、read model、worker、domain event semantics 或关联台内部工作区。测试必须覆盖：page shell actions, family tabs, summary cards, grouped table accessible name and row selection, closure right drawer, extra right drawer, export dialog, feedback messages and relevant domain events。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 source-level contract against current MUI runtime is expected-fail while existing/new behavior tests must pass；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P087 page shell/tabs/summary prompt。
```

#### Review

- Single slice: yes，tests only。
- Runtime implementation excluded: yes。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level no-MUI contract should fail until P087-P091 clear runtime MUI surfaces。

#### Execution Notes

- Test implementation changed: yes，only `web/src/test/TurnoverLedgerPage.test.tsx`.
- Runtime implementation changed: no.
- Added source-level no-MUI/project primitive contract for `TurnoverLedgerPage.tsx`, `TurnoverLedgerGroupedTable.tsx`, `TurnoverLedgerExtraDrawer.tsx` and `TurnoverLedgerExportDialog.tsx`.
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail；11 behavior tests passed，1 source-level contract failed against current MUI runtime。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P086 test file changed before docs。
- Commit: `e8b462a7 test: characterize turnover ledger ui migration`, pushed to `origin/refactor-ui`.
- Next prompt generated: `P087-phase-6-turnover-ledger-page-shell-tabs-summary`.

### P087-phase-6-turnover-ledger-page-shell-tabs-summary

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/turnover-ledger` page shell actions, family tabs and summary cards only.

#### Prompt

```text
Prompt ID: P087-phase-6-turnover-ledger-page-shell-tabs-summary
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/turnover-ledger` page shell actions, family tabs and summary cards only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/pages/TurnoverLedgerPage.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。只迁移 `TurnoverLedgerPage.tsx` 的 outer `Box`, page action buttons (`外部往来款标签设置`, `下载表格`), family tabs (`全部`/`个人往来`/`公司往来`/`银行往来`/`业务往来`) and summary cards (`当前待还款金额`/`累计已还款金额`/`当前待收款金额`/`累计已收款金额`) 到 native/project controls and `turnover-ledger-*` classes；必要时只补 `web/src/app/styles.css` 中的 turnover ledger shell/tabs/summary classes。不得迁移 grouped table、tag settings drawer、closure drawer、extra drawer、export dialog、feedback/Snackbar、API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：page heading, action button labels and disabled states, family tab accessible roles/selected state, family switch clears closure selection, summary card labels/amounts/family breakdown text, grouped table still renders and existing behavior tests still pass。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|renders grouped|opens tag selection drawer|reloads on category updates"`，预期 source-level contract remains expected-fail but selected behavior tests must pass；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 11 behavior tests pass and source-level contract remains expected-fail until P088-P091；运行 scoped grep `if rg -n 'DownloadOutlinedIcon|<Box|<Tabs|<Tab|label=\"全部\"|label=\"个人往来\"|label=\"公司往来\"|label=\"银行往来\"|label=\"业务往来\"' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P088 grouped table prompt。
```

#### Review

- Single slice: yes，only page shell actions, family tabs and summary cards。
- Runtime implementation limited: yes，does not touch table/drawers/dialog/feedback/API。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract remains expected-fail until later slices clear table/drawer/dialog/feedback surfaces。

#### Execution Notes

- Implemented: page outer container, page action buttons, family tabs and summary cards migrated to native/project controls and `turnover-ledger-*` classes。
- Runtime implementation changed: yes，only `web/src/pages/TurnoverLedgerPage.tsx`。
- CSS changed: yes，only `web/src/app/styles.css` `turnover-ledger-*` shell/tabs/summary classes。
- Scoped grep correction: excluded bare `<Box` during execution because P087 explicitly excludes tag/closure drawer internals that still use MUI `Box` for later slices。
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|renders grouped|opens tag selection drawer|reloads on category updates"`: expected-fail；selected behavior tests passed，source-level contract failed as expected。
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail；11 behavior tests passed，1 source-level contract failed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n 'DownloadOutlinedIcon|<Tabs|<Tab|label="全部"|label="个人往来"|label="公司往来"|label="银行往来"|label="业务往来"' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
- Commit: `e9a464b5 feat: migrate turnover ledger page shell`, pushed to `origin/refactor-ui`.
- Next prompt generated: `P088-phase-6-turnover-ledger-grouped-table`.

### P088-phase-6-turnover-ledger-grouped-table

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/turnover-ledger` grouped ledger table only.

#### Prompt

```text
Prompt ID: P088-phase-6-turnover-ledger-grouped-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/turnover-ledger` grouped ledger table only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。只迁移 `TurnoverLedgerGroupedTable.tsx` 的 MUI table/container/row/cell/checkbox/chip/icon/button/typography/layout surfaces 到 native/project table controls and `turnover-ledger-*`/existing `turnover-*` classes；必要时只补 `web/src/app/styles.css` 中 grouped table classes。不得迁移 `TurnoverLedgerPage.tsx` drawers, `TurnoverLedgerExtraDrawer.tsx`, `TurnoverLedgerExportDialog.tsx`, feedback/Snackbar, API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：table accessible name `往来款左右双栏台账`, sticky left group/header classes, no status column, grouped summary rows, expandable flow rows, real flow rows instead of lot rows, checkbox labels and disabled states, edit button labels, amount tone classes, loading/empty rows and high-density alignment。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|renders grouped|expands Jia Xiaohua|confirms a manual zero-difference|blocks cross-group selection|shows bank-detail tags"`，预期 source-level contract remains expected-fail but selected behavior tests must pass；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 11 behavior tests pass and source-level contract remains expected-fail until P089-P091；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|KeyboardArrowDownIcon|KeyboardArrowRightIcon|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Checkbox|<Chip|<IconButton|<Button|<Paper|<Stack|<Typography' web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P089 tag and closure drawers prompt。
```

#### Review

- Single slice: yes，grouped table only。
- Runtime implementation limited: yes，no page drawers, export dialog, feedback, API or backend changes。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract remains expected-fail until drawer/dialog/feedback slices clear remaining surfaces。

#### Execution Notes

- Implemented: `TurnoverLedgerGroupedTable.tsx` migrated from MUI table/container/row/cell/checkbox/chip/icon/button/typography/layout surfaces to native table controls and project classes。
- Runtime implementation changed: yes，only `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`。
- CSS changed: yes，only `web/src/app/styles.css` grouped table classes。
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|renders grouped|expands Jia Xiaohua|confirms a manual zero-difference|blocks cross-group selection|shows bank-detail tags"`: expected-fail；selected behavior tests passed，source-level contract failed as expected。
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail；11 behavior tests passed，1 source-level contract failed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|Mui[A-Z]|KeyboardArrowDownIcon|KeyboardArrowRightIcon|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Checkbox|<Chip|<IconButton|<Button|<Paper|<Stack|<Typography' web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
- Commit: `db426030 feat: migrate turnover ledger grouped table`, pushed to `origin/refactor-ui`.
- Next prompt generated: `P089-phase-6-turnover-ledger-tag-and-closure-drawers`.

### P089-phase-6-turnover-ledger-tag-and-closure-drawers

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/turnover-ledger` page-owned tag settings right drawer and closure right drawer only.

#### Prompt

```text
Prompt ID: P089-phase-6-turnover-ledger-tag-and-closure-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/turnover-ledger` page-owned tag settings right drawer and closure right drawer only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/pages/TurnoverLedgerPage.tsx、web/src/components/common/AppDrawer.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。只迁移 `TurnoverLedgerPage.tsx` 内 page-owned drawers：`外部往来款标签设置` right drawer and `确认外部往来闭环` right drawer，以及这些 drawer 内部的 MUI layout/buttons/checkbox chips/close icon/alerts 到 `AppDrawer`、native/project controls and `turnover-ledger-*` classes。不得迁移 `TurnoverLedgerExtraDrawer.tsx`, `TurnoverLedgerExportDialog.tsx`, page feedback/Snackbar, API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：old right drawers remain right drawers, dialog role/name, close buttons, tag checkbox labels and selected state, `全选`/`清空`/`保存` disabled rules and save payload, inactive tag warning text, closure selected rows preview, income/expense totals, delta test id `turnover-closure-delta`, cancel/confirm buttons, confirm disabled when delta is non-zero, closure POST payload and domain events。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|opens tag selection drawer|confirms a manual zero-difference|confirms closure when cash direction crosses|blocks cross-group selection"`，预期 source-level contract remains expected-fail but selected behavior tests must pass；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 11 behavior tests pass and source-level contract remains expected-fail until P090-P091；运行 scoped grep `if rg -n '<Drawer|<IconButton|CloseIcon|FormControlLabel|<Checkbox|<Button|<Alert|<Box|<Stack|<Typography' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P090 extra drawer prompt。
```

#### Review

- Single slice: yes，only page-owned tag settings and closure right drawers。
- Runtime implementation limited: yes，does not touch extra drawer component, export dialog, page feedback, API or backend。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract remains expected-fail until extra drawer, export dialog and feedback slices clear remaining surfaces。

#### Execution Notes

- Runtime implementation changed: yes，only `web/src/pages/TurnoverLedgerPage.tsx`。
- CSS changed: yes，only `web/src/app/styles.css` drawer/tag/closure classes。
- Test implementation changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Migrated page-owned `外部往来款标签设置` and `确认外部往来闭环` right drawers from MUI Drawer/layout/buttons/checkboxes to `AppDrawer` and native/project controls。
- Preserved drawer role/name, close buttons, tag checkbox labels and selected state, save payload, closure preview, totals, `turnover-closure-delta`, confirm disabled rule and closure domain events。
- Scoped grep was corrected during execution to exclude `<Alert` because page status/feedback MUI Alert/Snackbar are reserved for P091 closeout。
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|opens tag selection drawer|confirms a manual zero-difference|confirms closure when cash direction crosses|blocks cross-group selection"`: expected-fail；selected behavior tests passed and source-level contract failed as expected。
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail；11 behavior tests passed and 1 source-level contract failed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '<Drawer|<IconButton|CloseIcon|FormControlLabel|<Checkbox|<Button|<Box|<Stack|<Typography|<Paper|<Divider' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
- Commit: `3675bed3 feat: migrate turnover ledger drawers`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P090-phase-6-turnover-ledger-extra-drawer`。

### P090-phase-6-turnover-ledger-extra-drawer

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/turnover-ledger` extra info right drawer component only。

#### Prompt

```text
Prompt ID: P090-phase-6-turnover-ledger-extra-drawer
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/turnover-ledger` extra info right drawer component only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx、web/src/components/common/AppDrawer.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。只迁移 `TurnoverLedgerExtraDrawer.tsx` 的 MUI Drawer/layout/buttons/chips/text fields/menu items/alerts 到 `AppDrawer`、native/project controls and `turnover-ledger-*` classes；必要时只补 `web/src/app/styles.css` 中 extra drawer classes。不得迁移 `TurnoverLedgerExportDialog.tsx`, page feedback/Snackbar, API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：old extra info drawer remains right drawer, dialog role/name `编辑流水补充信息`, technical relation IDs remain hidden, loading/error states, overview text, form labels (`利率值` 等), dirty/save disabled rule, save payload, relation action buttons (`确认归并`/`撤销归并`) and disabled rules。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|opens the extra drawer|shows a business error|disables turnover write actions"`，预期 source-level contract remains expected-fail but selected behavior tests must pass；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 11 behavior tests pass and source-level contract remains expected-fail until P091；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|<Drawer|<IconButton|CloseIcon|<Button|<Chip|<TextField|<MenuItem|<Alert|<Box|<Stack|<Typography|<Divider' web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P091 export dialog and feedback closeout prompt。
```

#### Review

- Single slice: yes，only TurnoverLedger extra info right drawer component。
- Runtime implementation limited: yes，does not touch export dialog, page feedback, API or backend。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract remains expected-fail until P091 export dialog and feedback closeout clears remaining surfaces。

#### Execution Notes

- Runtime implementation changed: yes，only `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx`。
- CSS changed: yes，only `web/src/app/styles.css` extra drawer classes and button/notice variants。
- Test implementation changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Migrated `编辑流水补充信息` right drawer from MUI Drawer/layout/buttons/chips/text fields/select/menu items/alerts to `AppDrawer`, native form controls and `turnover-ledger-*` classes。
- Preserved dialog role/name, subtitle, technical relation ID hiding, loading/error states, overview text, form labels, dirty/save disabled rule, save payload, `确认归并`/`撤销归并` actions and disabled rules。
- Source-level contract now clears ExtraDrawer MUI import and missing drawer primitive target；remaining expected failures are page Alert/Snackbar, ExportDialog MUI import/dialog target, and over-broad legacy regex matching project primitive names such as `AppDrawer`。
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|opens the extra drawer|shows a business error|disables turnover write actions"`: expected-fail；selected behavior tests passed and source-level contract failed as expected。
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail；11 behavior tests passed and 1 source-level contract failed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/|Mui[A-Z]|<Drawer|<IconButton|CloseIcon|<Button|<Chip|<TextField|<MenuItem|<Alert|<Box|<Stack|<Typography|<Divider' web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
- Commit: `30fde5ad feat: migrate turnover ledger extra drawer`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P091-phase-6-turnover-ledger-export-dialog-feedback-closeout`。

### P091-phase-6-turnover-ledger-export-dialog-feedback-closeout

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor + contract closeout`
- Scope: `/turnover-ledger` export dialog, page-level feedback/status surfaces, and source-level migration contract false-positive cleanup only。

#### Prompt

```text
Prompt ID: P091-phase-6-turnover-ledger-export-dialog-feedback-closeout
Phase: phase_6_page_batches
Type: extraction/refactor + contract closeout
Scope: `/turnover-ledger` export dialog, page-level feedback/status surfaces, and source-level migration contract false-positive cleanup only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx、web/src/pages/TurnoverLedgerPage.tsx、web/src/components/common/AppDialog.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。迁移 `TurnoverLedgerExportDialog.tsx` 的 MUI Dialog/layout/table/select/alert/buttons 到 `AppDialog`、native/project table/form controls and `turnover-ledger-*` classes；迁移 `TurnoverLedgerPage.tsx` page-level MUI `Alert`/`Snackbar` feedback/status surfaces 到 project/native notice/toast classes。允许只为修正迁移合约 false positive 更新 `web/src/test/TurnoverLedgerPage.test.tsx` 的 source-level no-MUI contract：禁止 `@mui/*` imports、MUI selectors and legacy MUI JSX/import names；不得把 `AppDrawer`/`AppDialog`、文件名中的 `Drawer`/`Dialog` 或项目 primitive class 当成 legacy。不得修改导出 API client、mock response shape、backend、read model、worker、权限语义或关联台内部工作区。保留用户可见行为：旧导出入口仍为 `下载表格` button；旧导出确认仍为 modal dialog `下载往来款台账`；下载范围选项和默认 family behavior 不变；预览 table accessible name `往来款导出预览`、loading/empty/error 文案、summary text、`取消`/`确认下载` buttons and disabled rules 不变；mutation feedback messages and close behavior 不变；只读和 stale read model notices remain visible and semantically announced。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|reloads on category updates and downloads a previewed export|opens the extra drawer|shows a business error|disables turnover write actions"`，预期全部通过；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期全部通过；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|<Dialog\\b|<Button|<TextField|<MenuItem|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Stack|<Typography' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 TurnoverLedger cumulative MG prompt。
```

#### Review

- Single slice: yes，only export dialog, page-level feedback/status surfaces and test contract false-positive cleanup。
- Runtime implementation limited: yes，does not touch API client, backend, read model or worker。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected outcome: TurnoverLedger source-level contract and all behavior tests pass after this closeout。

#### Execution Notes

- Runtime implementation changed: yes，`web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx` and `web/src/pages/TurnoverLedgerPage.tsx`。
- CSS changed: yes，only `web/src/app/styles.css` export dialog/page notice/toast classes。
- Test implementation changed: yes，only source-level no-MUI contract false-positive cleanup in `web/src/test/TurnoverLedgerPage.test.tsx`。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Migrated export dialog from MUI Dialog/layout/table/select/alert/buttons to `AppDialog`, native select/table/buttons and project classes。
- Migrated page-level read-only/stale notices and mutation feedback from MUI Alert/Snackbar to native project notices/toast with 4-second auto close and manual close button。
- Preserved download entry, modal dialog name, download range options, export preview table accessible name, loading/empty/error text, summary text, cancel/download buttons, disabled rules and download request family。
- Source-level migration contract now passes and still forbids MUI imports, MUI selectors and legacy MUI JSX/import names without flagging project primitives。
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|reloads on category updates and downloads a previewed export|opens the extra drawer|shows a business error|disables turnover write actions"`: passed。
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: passed，12 tests。
  - `if rg -n '@mui/|Mui[A-Z]|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|<Dialog\\b|<Button|<TextField|<MenuItem|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Stack|<Typography' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
- Commit: `8a3eb3cb feat: complete turnover ledger ui migration`, pushed to `origin/refactor-ui`。
- Next prompt generated: `MG-P091-phase-6-turnover-ledger`。

### MG-P091-phase-6-turnover-ledger

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `cumulative merge gate`
- Scope: TurnoverLedger P085-P091 only。

#### Prompt

```text
Prompt ID: MG-P091-phase-6-turnover-ledger
Phase: phase_6_page_batches
Type: cumulative merge gate
Scope: TurnoverLedger P085-P091 only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/pages/TurnoverLedgerPage.tsx、web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx、web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx、web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx、web/src/test/TurnoverLedgerPage.test.tsx、web/src/test/TurnoverLedgerApi.test.ts 和当前 git status/diff。检查当前分支必须是 `refactor-ui`。确认 untracked files、diff scope、测试结果和文档状态；确认 P085-P091 已记录并且 TurnoverLedger runtime no-MUI contract passed。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx TurnoverLedgerApi.test.ts`；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 no-MUI grep：`if rg -n '@mui/|Mui[A-Z]|DownloadOutlinedIcon|KeyboardArrowDownIcon|KeyboardArrowRightIcon|CloseIcon|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|<Dialog\\b|<Drawer\\b|<Button|<TextField|<MenuItem|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Checkbox|<Chip|<IconButton|<Stack|<Typography|<Paper|<Divider|FormControlLabel|Tabs|Tab' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。确认 scope 只包含 TurnoverLedger runtime/tests/docs files and `web/src/app/styles.css`；禁止 `git add .` 和 `git add -A`，只允许精确 git add。MG 通过后提交并 push 到 `origin/refactor-ui`，再更新 state/prompt/module docs 的 MG execution notes 和 Push Log，标记 MG verified，并从 `refactor-ui` 分支生成下一条 Micro-JIT prompt。
```

#### Review

- Cumulative boundary: yes，TurnoverLedger P085-P091 complete and source-level contract now passes。
- Runtime implementation limited: yes，only TurnoverLedger runtime/test/docs and app styles。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected outcome: TurnoverLedger module committed, pushed and ready to move to next Phase 6 module。

#### Execution Notes

- Runtime implementation changed during MG: no。
- Test implementation changed during MG: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- MG grep was corrected during execution to use JSX-tag boundaries for `<Tab>`/`<Table>` so project names like `TurnoverLedgerGroupedTable` are not false positives。
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx TurnoverLedgerApi.test.ts`: passed，21 tests。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed，15 tests。
  - `if rg -n '@mui/|Mui[A-Z]|DownloadOutlinedIcon|KeyboardArrowDownIcon|KeyboardArrowRightIcon|CloseIcon|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|<Dialog\\b|<Drawer\\b|<Button\\b|<TextField\\b|<MenuItem\\b|<Table\\b|<TableHead\\b|<TableBody\\b|<TableRow\\b|<TableCell\\b|<TableContainer\\b|<Checkbox\\b|<Chip\\b|<IconButton\\b|<Stack\\b|<Typography\\b|<Paper\\b|<Divider\\b|<FormControlLabel\\b|<Tabs\\b|<Tab\\b' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger; then exit 1; else exit 0; fi`: passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: clean before MG docs update。
- Next prompt generated: `P092-phase-6-etc-tickets-discovery`。

### P092-phase-6-etc-tickets-discovery

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `discovery/planning`
- Scope: `/etc-tickets` ETC ticket management discovery only。

#### Prompt

```text
Prompt ID: P092-phase-6-etc-tickets-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: `/etc-tickets` ETC ticket management discovery only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx、web/src/test/EtcApi.test.ts、web/src/test/EtcOaNavigation.test.ts、web/src/features/etc/api.ts、web/src/features/etc/types.ts 和 web/src/features/etc/oaNavigation.ts。只做 discovery/planning：生成 docs/refactor-ui/modules/phase_6_etc_tickets.md，记录当前 MUI inventory、用户可见入口、表格/导入/对账/确认/空错误状态、弹窗/抽屉/菜单边界、现有测试覆盖、需要新增的 characterization tests、推荐 Micro-JIT 切片队列和 P093 prompt。不得修改 runtime code、tests、API client、backend、read model、worker、domain event semantics 或关联台内部工作区。保留原则：大布局和使用感不变，旧按钮/表格/导入/对账/确认入口位置保持等价，旧弹窗仍为弹窗，旧右侧抽屉仍为右侧抽屉。运行 `test -f docs/refactor-ui/modules/phase_6_etc_tickets.md`、`rg -n "P092-phase-6-etc-tickets-discovery|Current MUI Inventory|User-visible Entrypoints|Recommended Micro-JIT Queue|P093-phase-6-etc-tickets-characterization-tests" docs/refactor-ui/modules/phase_6_etc_tickets.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs。完成后提交并 push 到 `origin/refactor-ui`，再写入 Push Log。
```

#### Review

- Single slice: yes，ETC ticket management discovery only。
- Runtime implementation limited: yes，no runtime/test/API/backend changes。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Next prompt: P093 characterization tests only after P092 discovery doc and grep pass。

#### Execution Notes

- Discovery doc created: `docs/refactor-ui/modules/phase_6_etc_tickets.md`。
- Runtime implementation changed: no。
- Test implementation changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Recorded current MUI inventory, user-visible entrypoints, existing test coverage, table layout risks, migration risks, recommended Micro-JIT queue and P093 prompt。
- Verification:
  - `test -f docs/refactor-ui/modules/phase_6_etc_tickets.md`: passed。
  - `rg -n "P092-phase-6-etc-tickets-discovery|Current MUI Inventory|User-visible Entrypoints|Recommended Micro-JIT Queue|P093-phase-6-etc-tickets-characterization-tests" docs/refactor-ui/modules/phase_6_etc_tickets.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P092 docs changed。
- Next prompt generated: `P093-phase-6-etc-tickets-characterization-tests`。

### P093-phase-6-etc-tickets-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `characterization tests`
- Scope: `/etc-tickets` characterization tests only。

#### Prompt

```text
Prompt ID: P093-phase-6-etc-tickets-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/etc-tickets` characterization tests only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx、web/src/test/EtcApi.test.ts、web/src/test/EtcOaNavigation.test.ts 和 web/src/features/etc/types.ts。只修改 `web/src/test/EtcTicketManagementPage.test.tsx`，新增 source-level no-MUI/project primitive contract 和必要的用户可见 form-factor characterization assertions。不得修改 runtime code、API client、backend、read model、worker、domain event semantics 或关联台内部工作区。测试必须覆盖：page shell heading/actions, status segmented controls, batch/task list accessible names, upload/drop controls, reconciliation workspace/table accessible names, dialogs remain dialogs, OA detection actions, feedback/status surfaces, and existing table alignment expectations。运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx`，预期 source-level contract against current MUI runtime is expected-fail while existing/new behavior tests must pass；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P094 shell/filters/lists prompt。
```

#### Review

- Single slice: yes，ETC characterization tests only。
- Runtime implementation limited: yes，no runtime/API/backend changes。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract fails until ETC runtime slices clear MUI。

#### Execution Notes

- Test implementation changed: yes，only `web/src/test/EtcTicketManagementPage.test.tsx`。
- Runtime implementation changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Added source-level no-MUI/project primitive contract for ETC ticket management page。
- Added form-factor assertions for status segmented controls, batch list region, reconciliation workspace, upload/drop control label and reconciliation table accessible name。
- Stabilized the OA draft creation behavior test by removing a brittle import-attempt precheck unrelated to the actual submit flow。
- Verification:
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx`: expected-fail；41 behavior tests passed and 1 source-level contract failed against current MUI runtime。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P093 test file changed before docs。
- Commit: `1d0773cc test: characterize etc tickets ui migration`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P094-phase-6-etc-tickets-shell-filters-lists`。

### P094-phase-6-etc-tickets-shell-filters-lists

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/etc-tickets` page shell, status/filter bar, and batch/task list panels only。

#### Prompt

```text
Prompt ID: P094-phase-6-etc-tickets-shell-filters-lists
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/etc-tickets` page shell, status/filter bar, and batch/task list panels only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx、web/src/app/styles.css 和 web/src/components/common/PageScaffold.tsx。只迁移 `EtcTicketManagementPage.tsx` 中 page shell local wrapper、top action icons、status segmented controls、月份/车牌/信用卡任务筛选输入、左侧 `ETC批次列表区`、`ETC批次列表` 和 `ETC对账任务列表` 的 MUI icons/layout/forms/list items/buttons/chips 到 lucide icons、native/project controls and `etc-*` classes；必要时只补 `web/src/app/styles.css` 中该切片 classes。不得迁移 upload/drop blocks、reconciliation workspace tables、business batch detail tables、manual review panel、dialog contents、OA status/detection panels、feedback Alert surfaces、API client、backend、read model、worker、domain event semantics 或关联台内部工作区。保留用户可见行为：page heading `ETC票据`、import link `导入发票`、primary action `提交OA`、status controls `未提交 2`/`已提交 1`、filter labels `月份`/`车牌`/`信用卡任务`、batch/task list accessible names, selected row behavior, task row delete/view actions, batch row delete/reopen/open-draft actions and disabled rules。运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|unsubmitted mode shows batch list|submitted mode hides submit action|creates OA draft through the selected business batch"`，预期 source-level contract remains expected-fail but selected behavior tests pass；运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx`，预期 41 behavior tests pass and 1 source-level contract remains expected-fail until later ETC slices；运行 scoped grep `if rg -n 'AddOutlinedIcon|ArrowForwardOutlinedIcon|DeleteOutlineOutlinedIcon|OpenInNewOutlinedIcon|RefreshOutlinedIcon|UndoOutlinedIcon|UploadFileOutlinedIcon|<ToggleButton\\b|<ToggleButtonGroup\\b|<List\\b|<ListItem\\b|<ListItemButton\\b|<ListItemText\\b|<Paper\\b|<TextField[^\\n]*(label="月份"|label="车牌"|label="信用卡任务")' web/src/pages/EtcTicketManagementPage.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P095 upload/source panels prompt。
```

#### Review

- Single slice: yes，only page shell/status/filter/list panel surfaces。
- Runtime implementation limited: yes，upload/workspace tables/detail tables/dialogs/OA feedback remain later slices。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract remains expected-fail until all ETC runtime slices clear MUI。

#### Execution Notes

- Runtime implementation changed: yes，only `web/src/pages/EtcTicketManagementPage.tsx` and `web/src/app/styles.css`。
- Test implementation changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Migrated ETC top import link, status segmented controls, filters, submit action, batch/task list panels and row delete actions to lucide icons, native buttons/inputs/lists and `etc-*` classes。
- Cleared page-level MUI icons, MUI `Paper`, and MUI `List`/`ListItem` wrappers；uploaded source-file list was converted to native `ul/li` only to satisfy the P094 scoped no-list grep without changing upload/delete behavior。
- Preserved page heading, `导入发票`, `提交OA`, status button names, filter labels, batch/task list accessible names, selected row behavior, delete dialog triggers and disabled rules。
- Verification:
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|unsubmitted mode shows batch list|submitted mode hides submit action|creates OA draft through the selected business batch"`: expected-fail；selected behavior tests passed and source-level contract failed as expected。
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx`: expected-fail；41 behavior tests passed and 1 source-level contract failed against remaining ETC MUI runtime。
  - `if rg -n 'AddOutlinedIcon|ArrowForwardOutlinedIcon|DeleteOutlineOutlinedIcon|OpenInNewOutlinedIcon|RefreshOutlinedIcon|UndoOutlinedIcon|UploadFileOutlinedIcon|<ToggleButton\\b|<ToggleButtonGroup\\b|<List\\b|<ListItem\\b|<ListItemButton\\b|<ListItemText\\b|<Paper\\b|<TextField[^\\n]*(label="月份"|label="车牌"|label="信用卡任务")' web/src/pages/EtcTicketManagementPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P094 page/style files changed before docs。
- Commit: `47a2d993 feat: migrate etc tickets shell and lists`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P095-phase-6-etc-tickets-upload-and-source-panels`。

### P095-phase-6-etc-tickets-upload-and-source-panels

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/etc-tickets` upload/drop blocks, source-file context, and upload/source notices only。

#### Prompt

```text
Prompt ID: P095-phase-6-etc-tickets-upload-and-source-panels
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/etc-tickets` upload/drop blocks, source-file context, and upload/source notices only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx 和 web/src/app/styles.css。只迁移 `EtcTicketManagementPage.tsx` 中 `UploadDropBox`、`ETC对账文件上传`、`ETC导入动作`、信用卡账单/补充凭证/票根网 TXT 上传块、source file context/issues/status notices and source upload lists 的 MUI Button/Stack/Typography/Chip/Tooltip/IconButton/Alert usages 到 native/project controls and `etc-*` classes；必要时只补 `web/src/app/styles.css` 中 upload/source classes。不得迁移 reconciliation detail table, manual review form, business batch detail/invoice tables, dialog contents, OA status/detection panels, API client、backend、read model、worker、domain event semantics 或关联台内部工作区。保留用户可见行为：file input labels `上传信用卡账单`/`上传补充凭证`/`上传票根网`, drag/drop upload behavior, accepted file types, disabled reasons, legacy non-TXT/PDF blocking notices, source issue visibility, delete source file action label and payload, fresh task source issue isolation。运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|shows the reconciliation workspace with upload blocks|uploads ticket-root TXT files|uploads ticket-root TXT files by dropping|shows source file context|removes legacy ticket-root mode controls|disables ticket-root TXT upload"`，预期 source-level contract remains expected-fail but selected behavior tests pass；运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx`，预期 41 behavior tests pass and 1 source-level contract remains expected-fail until later ETC slices；运行 scoped grep for upload/source slice `if rg -n 'etc-upload-drop-box[^\\n]*MuiButton|MuiButton-root|Mui-disabled|<Alert\\b|<Tooltip\\b|<IconButton\\b|<Stack[^\\n]*etc-upload|<Typography[^\\n]*(上传|legacy|source)|<Chip\\b' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`，若 grep 过宽命中未迁移的 table/detail/OA surfaces，必须收窄到 upload/source classes and document why；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P096 reconciliation table prompt。
```

#### Review

- Single slice: yes，only upload/drop/source panels and source notices。
- Runtime implementation limited: yes，tables/manual review/detail/dialog/OA surfaces remain later slices。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract remains expected-fail until all ETC runtime slices clear MUI。

#### Execution Notes

- Runtime implementation changed: yes，only `web/src/pages/EtcTicketManagementPage.tsx` and `web/src/app/styles.css`。
- Test implementation changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Migrated `UploadBlock` from MUI Button/Stack/Typography to native label/input and project upload classes while preserving aria-labels, drag/drop handlers, accepted file types, disabled state and hidden file input behavior。
- Migrated uploaded source-file heading/list tags and parse issue notices to native/project classes。
- Draft grep was over-broad and matched frozen workbench CSS plus future ETC table/detail/OA/dialog surfaces；execution used narrowed upload/source-class grep and documented the reason。
- Verification:
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|shows the reconciliation workspace with upload blocks|uploads ticket-root TXT files|uploads ticket-root TXT files by dropping|shows source file context|removes legacy ticket-root mode controls|disables ticket-root TXT upload"`: expected-fail；selected upload/source behavior tests passed and source-level contract failed as expected。
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx`: expected-fail；41 behavior tests passed and 1 source-level contract failed against remaining ETC MUI runtime。
  - `if rg -n 'etc-upload-drop-box[^\\n]*MuiButton|\\.etc-upload-drop-box\\.Mui|\\.etc-upload-drop-box[^\\n]*Mui-disabled|<Stack[^\\n]*etc-upload|<Typography[^\\n]*etc-upload|etc-source-file-title[^\\n]*<Chip|etc-source-issue[^\\n]*<Chip|etc-source-file-row[^\\n]*<Tooltip|etc-source-file-row[^\\n]*<IconButton' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`: passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P095 page/style files changed before docs。
- Commit: `a58e74c3 feat: migrate etc tickets upload panels`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P096-phase-6-etc-tickets-reconciliation-table`。

### P096-phase-6-etc-tickets-reconciliation-table

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/etc-tickets` reconciliation detail table, row selection controls, expandable descriptions, and manual review panel only。

#### Prompt

```text
Prompt ID: P096-phase-6-etc-tickets-reconciliation-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/etc-tickets` reconciliation detail table, row selection controls, expandable descriptions, and manual review panel only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx 和 web/src/app/styles.css。只迁移 `ETC双侧核对明细` table block, reconciliation metric cards, selection buttons (`全选`/`仅保留已配对`/`清空`), row checkboxes, expandable description button, evidence chips, unmatched supplement upload action, manual review panel/form controls and confirm buttons 的 MUI Table/TableContainer/TableHead/TableBody/TableRow/TableCell/Checkbox/Button/IconButton/Tooltip/Chip/Stack/Typography/TextField usages 到 native table/form/button/project classes and table layout system classes。不得迁移 business batch detail/invoice tables, imported invoice section, dialog contents, OA status/detection panels, API client、backend、read model、worker、domain event semantics 或关联台内部工作区。保留用户可见行为：table accessible name `ETC双侧核对明细`, `etc-reconciliation-row-*` and cell test ids, row highlight states, local row selection behavior, all/paired-only/clear actions, one-line collapsed descriptions and expand control, selected metrics, `接受推荐票根`, `关联所选记录`, `手工确认`, selected card/evidence payloads and disabled rules。运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|renders paired reconciliation table|keeps long reconciliation descriptions|selects reconciliation rows locally|updates confirmation metrics|submits the checked card item ids|manual reconciliation accepts"`，预期 source-level contract remains expected-fail but selected behavior tests pass；运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx`，预期 41 behavior tests pass and 1 source-level contract remains expected-fail until later ETC slices；运行 scoped grep for reconciliation/manual slice `if rg -n '<Table(Container|Head|Body|Row|Cell)?\\b|<Checkbox\\b|<Tooltip\\b|<IconButton\\b|<Chip\\b|etc-reconciliation-description-toggle\\.MuiButton-root|etc-reconciliation-table .*Mui|etc-reconciliation-[^\\n]*Mui|<TextField[^\\n]*(选择票根|处理说明)' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`，若 grep 命中 future detail/OA/dialog surfaces, narrow to reconciliation/manual classes and document why；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P097 detail/imported invoice tables prompt。
```

#### Review

- Single slice: yes，only reconciliation table/manual review surface。
- Runtime implementation limited: yes，business detail/imported invoice/dialog/OA surfaces remain later slices。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract remains expected-fail until all ETC runtime slices clear MUI。

#### Execution Notes

- Runtime implementation changed: yes，only `web/src/pages/EtcTicketManagementPage.tsx` and `web/src/app/styles.css`。
- Test implementation changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Migrated reconciliation description cell, amount/time/evidence helper cells, unmatched supplement upload action, reconciliation toolbar, `ETC双侧核对明细` native table/checkboxes and manual review form/actions to native/project classes。
- Preserved table accessible name, row/cell test ids, row highlight states, local selection actions, one-line description expansion, selected-card/evidence payloads and manual review disabled rules。
- Draft grep was over-broad because it matched P097 invoice/detail tables and future imported-invoice/detail chips；execution used a narrowed reconciliation/manual-class grep and documented the reason。
- Verification:
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|renders paired reconciliation table|keeps long reconciliation descriptions|selects reconciliation rows locally|updates confirmation metrics|submits the checked card item ids|manual reconciliation accepts"`: expected-fail；selected reconciliation/manual behavior tests passed and source-level contract failed as expected。
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx`: expected-fail；41 behavior tests passed and 1 source-level contract failed against remaining ETC MUI runtime。
  - `if rg -n 'etc-reconciliation-description-toggle\\.MuiButton-root|etc-reconciliation-table .*Mui|etc-reconciliation-[^\\n]*Mui|<TextField[^\\n]*(选择票根|处理说明)|<Table(Container|Head|Body|Row|Cell)?\\b[^\\n]*etc-reconciliation|<Checkbox\\b|<Tooltip[^\\n]*(重新计算匹配|上传补充凭证)|<IconButton[^\\n]*(aria-label=\\{label\\}|上传补充)|etc-reconciliation-chip-line[^\\n]*<Chip' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`: passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P096 page/style files changed before docs。
- Commit: `64341c3c feat: migrate etc tickets reconciliation table`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P097-phase-6-etc-tickets-detail-and-invoice-tables`。

### P097-phase-6-etc-tickets-detail-and-invoice-tables

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/etc-tickets` business batch detail, imported invoice section, import attempts, vehicle summaries, and ETC invoice tables only。

#### Prompt

```text
Prompt ID: P097-phase-6-etc-tickets-detail-and-invoice-tables
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/etc-tickets` business batch detail, imported invoice section, import attempts, vehicle summaries, and ETC invoice tables only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx 和 web/src/app/styles.css。只迁移 `renderEtcInvoiceTable`, `已导入ETC发票`, `ETC批次详情`, `批次指标`, `车牌汇总`, `导入记录`, batch detail collapse button, revoke/not-submitted actions and related table/detail tags 的 MUI Table/TableContainer/TableHead/TableBody/TableRow/TableCell/Button/Chip/Stack/Typography/Box usages 到 native table/button/project classes and table layout system classes。不得迁移 dialog contents, OA status/detection panel, page-level remaining feedback, API client、backend、read model、worker、domain event semantics 或关联台内部工作区。保留用户可见行为：invoice table accessible names (`ETC批次发票明细`, `已导入ETC发票明细`), native table expectation, loading/empty text, amount/date alignment, imported invoice remove action, batch detail collapse state, import attempt visibility, vehicle summary text, revoke/not-submitted action labels and disabled rules。运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|renders batch invoice details with a native table|shows imported task invoices|submitted mode hides submit action|creates OA draft from the selected imported reconciliation task batch"`，预期 source-level contract remains expected-fail but selected behavior tests pass；运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx`，预期 41 behavior tests pass and 1 source-level contract remains expected-fail until P098 closeout；运行 scoped grep for detail/invoice slice `if rg -n '<Table(Container|Head|Body|Row|Cell)?\\b|<Chip\\b|<Button[^\\n]*(移除发票|撤销草稿|未提交OA)|etc-invoice-[^\\n]*Mui|etc-import-attempt-row .*Mui|etc-plate-summary[^\\n]*Mui' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`，若 grep 命中 P098 dialog/OA/feedback surfaces, narrow to detail/invoice classes and document why；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P098 dialogs/OA/feedback closeout prompt。
```

#### Review

- Single slice: yes，only business detail/imported invoice/invoice tables。
- Runtime implementation limited: yes，dialogs/OA/feedback closeout remains P098。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level contract remains expected-fail until P098 closeout clears remaining ETC MUI。

#### Execution Notes

- Runtime implementation changed: yes，only `web/src/pages/EtcTicketManagementPage.tsx` and `web/src/app/styles.css`。
- Test implementation changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Migrated `renderEtcInvoiceTable`, imported invoice summary/action, batch detail headings, status/count tags, batch detail metrics, vehicle summaries, import attempts and related detail actions to native/project classes。
- Preserved invoice table accessible names, loading/empty text, amount/date alignment, imported invoice remove action, batch detail collapse state, import attempt visibility, vehicle summary text and revoke action disabled rules。
- Verification:
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|renders batch invoice details with a native table|shows imported task invoices|submitted mode hides submit action|creates OA draft from the selected imported reconciliation task batch"`: expected-fail；selected detail/invoice behavior tests passed and source-level contract failed as expected。
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx`: expected-fail；41 behavior tests passed and 1 source-level contract failed against remaining ETC MUI runtime。
  - `if rg -n '<Table(Container|Head|Body|Row|Cell)?\\b|<Chip\\b|<Button[^\\n]*(移除发票|撤销草稿|未提交OA)|etc-invoice-[^\\n]*Mui|etc-import-attempt-row .*Mui|etc-plate-summary[^\\n]*Mui' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`: passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P097 page/style files changed before docs。
- Commit: `35d55842 feat: migrate etc tickets detail tables`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout`。

### P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor + contract closeout`
- Scope: `/etc-tickets` dialog contents, OA status/detection panel, page feedback, remaining layout wrappers, and source-level contract closeout only。

#### Prompt

```text
Prompt ID: P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout
Phase: phase_6_page_batches
Type: extraction/refactor + contract closeout
Scope: `/etc-tickets` dialog contents, OA status/detection panel, page feedback, remaining layout wrappers, and source-level contract closeout only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx 和 web/src/app/styles.css。迁移剩余 MUI surfaces：dialog action/content buttons and fields, supplement upload dialog content, delete/source/revoke/create/manual OA dialogs, `renderOaStatusPanel`, page feedback/status Alert surfaces, remaining Collapse/Box/Stack/Typography/Button/IconButton/Tooltip/TextField imports and MUI CSS selectors。允许只为修正 source-level no-MUI contract false positive 更新 `web/src/test/EtcTicketManagementPage.test.tsx`，但不得放宽实际 MUI 禁止项。不得修改 API client、mock response shape、backend、read model、worker、domain event semantics、OA URL construction 或关联台内部工作区。保留用户可见行为：all dialogs remain modal dialogs with same names, supplement file upload and difference note payload, delete/revoke/create OA/manual OA action labels and disabled/loading states, OA draft open/refresh/manual fallback actions, submitted/unsubmitted feedback, stale/source status messages, and all previous ETC page behavior. 运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx`，预期全部通过；运行 `cd web && npx vitest run EtcApi.test.ts EtcOaNavigation.test.ts`；运行 no-MUI grep `if rg -n '@mui/|Mui[A-Z]|<(Alert|Box|Button|Checkbox|Chip|Collapse|Divider|IconButton|List|ListItem|ListItemButton|ListItemText|Paper|Stack|Table|TableBody|TableCell|TableContainer|TableHead|TableRow|TextField|ToggleButton|ToggleButtonGroup|Tooltip|Typography)\\b|AddOutlinedIcon|ArrowForwardOutlinedIcon|DeleteOutlineOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon|OpenInNewOutlinedIcon|RefreshOutlinedIcon|ReportProblemOutlinedIcon|UndoOutlinedIcon|UploadFileOutlinedIcon' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 `MG-P098-phase-6-etc-tickets` cumulative merge gate prompt。
```

#### Review

- Single slice: yes，ETC closeout only。
- Runtime implementation limited: yes，does not modify API/client/backend/read model/worker。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected outcome: ETC source-level contract and behavior tests pass, and remaining page MUI imports/selectors are cleared。

#### Execution Notes

- Runtime implementation changed: yes，only `web/src/pages/EtcTicketManagementPage.tsx` and `web/src/app/styles.css`。
- Test implementation changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Migrated remaining ETC dialog action/content controls, supplement upload picker and difference note, delete/remove/revoke/create OA dialog contents, OA status/manual fallback panel, remaining layout wrappers and ETC-scoped CSS selectors to native/project classes。
- Preserved modal dialog form factor, supplement upload aria-label and payload fields, delete/revoke/create/manual OA action labels, loading/disabled states and OA draft open/refresh actions。
- Draft grep was over-broad because `web/src/app/styles.css` still has frozen workbench and historical non-ETC MUI selectors；execution used page no-MUI grep plus ETC-scoped CSS grep。
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|<(Alert|Box|Button|Checkbox|Chip|Collapse|Divider|IconButton|List|ListItem|ListItemButton|ListItemText|Paper|Stack|Table|TableBody|TableCell|TableContainer|TableHead|TableRow|TextField|ToggleButton|ToggleButtonGroup|Tooltip|Typography)\\b|AddOutlinedIcon|ArrowForwardOutlinedIcon|DeleteOutlineOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon|OpenInNewOutlinedIcon|RefreshOutlinedIcon|ReportProblemOutlinedIcon|UndoOutlinedIcon|UploadFileOutlinedIcon' web/src/pages/EtcTicketManagementPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `if rg -n 'etc-[^\\n]*Mui|Mui[^\\n]*etc-' web/src/app/styles.css; then exit 1; else exit 0; fi`: passed。
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx`: passed；42 tests passed。
  - `cd web && npx vitest run EtcApi.test.ts EtcOaNavigation.test.ts`: passed；17 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；only P098 page/style files changed before docs。
- Commit: `071e3f98 feat: complete etc tickets ui migration`, pushed to `origin/refactor-ui`。
- Next prompt generated: `MG-P098-phase-6-etc-tickets`。

### MG-P098-phase-6-etc-tickets

- Phase: `phase_6_page_batches`
- Status: `mg_verified`
- Type: `cumulative merge gate`
- Scope: `/etc-tickets` P092-P098 migration closeout only。

#### Prompt

```text
Prompt ID: MG-P098-phase-6-etc-tickets
Phase: phase_6_page_batches
Type: cumulative merge gate
Scope: `/etc-tickets` P092-P098 migration closeout only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx、web/src/test/EtcApi.test.ts、web/src/test/EtcOaNavigation.test.ts 和 web/src/app/styles.css。确认当前分支是 refactor-ui，检查 untracked files、diff 和 scope。只允许 ETC 页面、ETC 样式和 refactor-ui 文档进入 MG。不得修改 API client、mock response shape、backend、read model、worker、domain event semantics、OA URL construction 或关联台内部工作区。运行 ETC 页面/API/navigation tests、common/table/HeroUI smoke tests、build、page no-MUI grep、ETC-scoped CSS grep、git diff --check 和 git status。若全部通过，精确 git add 本 MG 文件，commit/push 到 origin/refactor-ui，更新 state/prompt/module docs，把 `MG-P098-phase-6-etc-tickets` 标记为 verified，并生成下一个 phase_6 模块 discovery prompt。
```

#### Review

- MG boundary: yes，covers only ETC P092-P098 closeout。
- Scope check required: yes，must include only ETC page/style/docs files。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Exact staging required: yes，no `git add .` or `git add -A`。

#### Execution Notes

- Scope checked: yes，ETC P092-P098 only。
- Runtime changed during MG: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - `git status --short --branch`: passed；clean on `refactor-ui...origin/refactor-ui`。
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx EtcApi.test.ts EtcOaNavigation.test.ts`: passed；59 tests passed。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed；15 tests passed。
  - page no-MUI grep for `EtcTicketManagementPage.tsx`: passed。
  - ETC-scoped CSS MUI grep for `web/src/app/styles.css`: passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
  - `git status --short --branch`: passed；clean before MG docs update。
- Next prompt generated: `P099-phase-6-settings-discovery`。

### P099-phase-6-settings-discovery

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `discovery/planning`
- Scope: `/settings` discovery only。

#### Prompt

```text
Prompt ID: P099-phase-6-settings-discovery
Phase: phase_6_page_batches
Type: discovery/planning
Scope: `/settings` discovery only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/SettingsPage.tsx、web/src/components/settings/*、web/src/test/SettingsPage.test.tsx、web/src/test/SettingsOaManualSearchImportTable.test.tsx、web/src/features/settings/* 或实际 settings API/types 文件。只做 discovery/planning：生成 docs/refactor-ui/modules/phase_6_settings.md，记录当前 MUI inventory、用户可见入口、左侧设置导航、设置 section 矩阵、DataGrid/native table 风险、导入表格、弹窗/菜单/确认操作、loading/empty/error/permission 状态、现有测试覆盖、需要新增的 characterization tests、推荐 Micro-JIT 切片队列和 P100 prompt。不得修改 runtime code、tests、API client、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留原则：大布局和使用感不变，旧左侧设置导航仍为左侧导航，旧 DataGrid/table 仍保持表格形态，旧弹窗仍为弹窗，旧按钮/导入/删除/恢复/权限入口位置保持等价。运行 `test -f docs/refactor-ui/modules/phase_6_settings.md`、`rg -n "P099-phase-6-settings-discovery|Current MUI Inventory|User-visible Entrypoints|Recommended Micro-JIT Queue|P100-phase-6-settings-characterization-tests" docs/refactor-ui/modules/phase_6_settings.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs。完成后提交并 push 到 `origin/refactor-ui`，再写入 Push Log。
```

#### Review

- Single slice: yes，settings discovery only。
- Runtime implementation untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- New module doc justified: yes，settings has multiple sections, DataGrid/table surfaces, destructive reset flows, permission surfaces and OA import workflow。

#### Execution Notes

- Created `docs/refactor-ui/modules/phase_6_settings.md`.
- Runtime implementation changed: no.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Recorded Settings MUI inventory, user-visible entrypoints, existing test coverage, test gaps, API/contract risks, table layout risks, overlay/menu risks and recommended Micro-JIT queue.
- Existing test issue recorded: `SettingsPage.test.tsx` still asserts `MuiList-root`; P100 must convert that to semantic/form-factor assertions plus source-level no-MUI contract.
- Existing OA manual import table test issue recorded: test name protects "MUI table semantics"; P100 must migrate it to native/user-observable table semantics.
- Verification:
  - `test -f docs/refactor-ui/modules/phase_6_settings.md`: passed.
  - `rg -n "P099-phase-6-settings-discovery|Current MUI Inventory|User-visible Entrypoints|Recommended Micro-JIT Queue|P100-phase-6-settings-characterization-tests" docs/refactor-ui/modules/phase_6_settings.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P099 docs changed.
- Next prompt generated: `P100-phase-6-settings-characterization-tests`.

### P100-phase-6-settings-characterization-tests

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `characterization tests`
- Scope: `/settings` characterization tests only。

#### Prompt

```text
Prompt ID: P100-phase-6-settings-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/settings` characterization tests only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/SettingsPage.tsx、web/src/components/settings/*、web/src/test/SettingsPage.test.tsx、web/src/test/SettingsOaManualSearchImportTable.test.tsx 和 web/src/features/workbench/types.ts。只修改 Settings 相关测试，不改 runtime code、API client、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。添加 source-level no-MUI/project primitive contract，覆盖 `SettingsPage.tsx` 和 `web/src/components/settings`；更新现有 MUI class/theme 断言为用户可观察语义、ARIA、table/dialog/menu form-factor 断言，不得保护旧 MUI class。测试必须覆盖：left settings nav remains tree, content sections remain regions, Settings page does not show extra legacy title/dialog, read-only save disabled, data reset remains two modal dialogs, pending invoice tag menu remains menu, DataGrid/table surfaces remain table form factor, OA manual search/import keeps table, nested detail table, selection, refresh/import payload and shell-status isolation。运行 `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level no-MUI contract fails against current MUI runtime；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P101 settings shell/navigation prompt。
```

#### Review

- Single slice: yes，tests only。
- Runtime implementation untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level no-MUI contract should fail against current Settings MUI runtime while behavior tests pass。

#### Execution Notes

- Runtime implementation changed: no。
- Test implementation changed:
  - `SettingsPage.test.tsx` now has a source-level no-MUI/project primitive contract for `SettingsPage.tsx` and `web/src/components/settings`。
  - Removed the legacy `MuiList-root` assertion and replaced it with treeitem/region/aria-controls assertions。
  - Stabilized async Settings render assertions by waiting for the tree and read-only notice。
  - `SettingsOaManualSearchImportTable.test.tsx` now names the table contract as native table semantics rather than MUI table semantics。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail；12 behavior tests passed, 1 source-level contract failed as expected against current Settings MUI runtime。
  - `git diff --check`: passed。
- Next prompt generated: `P101-phase-6-settings-shell-navigation`。

### P101-phase-6-settings-shell-navigation

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/settings` page shell, save feedback, loading/error wrappers and left settings navigation only。

#### Prompt

```text
Prompt ID: P101-phase-6-settings-shell-navigation
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` page shell, save feedback, loading/error wrappers and left settings navigation only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/SettingsPage.tsx、web/src/components/settings/SettingsPageContent.tsx、web/src/components/settings/SettingsTreeNav.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移 Settings page shell、loading/error/read-only/save feedback、primary save button、left settings nav/tree 和 content wrapper classes；不得迁移 section bodies、DataGrid/native table bodies、pending tag menu、data reset dialogs、OA manual search/import table 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留用户可见行为：`settings-page` test id, no extra legacy `关联台设置` page title/dialog, left nav remains `设置导航`, tree remains `role="tree"` with `设置分类`, treeitems keep names/selection/aria-controls, content region remains `设置内容`, section regions keep the same accessible names, read-only notice and `保存设置` disabled state stay visible, loading/error/save status messages stay equivalent. 运行 `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|renders as a tree-and-panel page|switches the content panel|keeps workbench-only header actions|keeps read-only settings users"`，预期 selected behavior tests pass and source-level contract still fails for remaining section bodies；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails for remaining Settings MUI runtime；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|ThemeProvider|settingsTheme|settingsButtonSx|settingsSectionSx|<(Alert|Box|Button|CircularProgress|List|ListItem|ListItemButton|ListItemText|Stack|Typography)\\b' web/src/pages/SettingsPage.tsx web/src/components/settings/SettingsPageContent.tsx web/src/components/settings/SettingsTreeNav.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P102 projects/bank accounts prompt。
```

#### Review

- Single slice: yes，Settings shell/navigation only。
- Section body migration deferred: yes，P102-P105。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- User-visible behavior preserved: required，left nav/tree, content regions, save/read-only/loading/error states remain equivalent。
- Expected source-level failure allowed: yes，remaining Settings section bodies still use MUI after P101。

#### Execution Notes

- Runtime implementation changed:
  - `SettingsPage.tsx` page feedback moved from MUI Alert/Box/Stack to project `StatePanel` and native layout.
  - `SettingsTreeNav.tsx` moved from MUI List/ListItemButton/Typography to native `aside`/`ul role="tree"`/button `role="treeitem"` with preserved names, counts, selected state and `aria-controls`.
  - `SettingsPageContent.tsx` shell/header/save/read-only feedback moved off MUI and `ThemeProvider`.
  - `SettingsDataResetDialogs.tsx` was extracted to preserve existing destructive modal dialogs while keeping them visible to later source-level contract checks.
  - `web/src/app/styles.css` added Settings shell/nav/header/save/inline status classes with existing `--fp-*` tokens.
- Test implementation changed:
  - `SettingsPage.test.tsx` includes `SettingsDataResetDialogs.tsx` in the source-level contract.
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - scoped page/content/nav no-MUI grep: passed。
  - `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|renders as a tree-and-panel page|switches the content panel|keeps workbench-only header actions|keeps read-only settings users"`: expected-fail；selected behavior tests passed, source-level contract failed only for remaining section/dialog/table/settingsDesign files。
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail；12 behavior tests passed, 1 source-level contract failed for remaining Settings MUI runtime。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
- Next prompt generated: `P102-phase-6-settings-projects-and-bank-accounts`。

### P102-phase-6-settings-projects-and-bank-accounts

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/settings` project status and bank account mapping sections only。

#### Prompt

```text
Prompt ID: P102-phase-6-settings-projects-and-bank-accounts
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` project status and bank account mapping sections only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/SettingsProjectsSection.tsx、web/src/components/settings/SettingsBankAccountsSection.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移项目状态 section 和银行账户映射 section：移除 MUI DataGrid、MUI Buttons/TextFields/Alerts/IconButtons/icons、settingsDataGridSx/settingsButtonSx 在这两个 section 的使用，改为原生/project table/form/button/status classes，并保持表格 form factor。不得迁移 pending invoice tags、access accounts、OA retention/import、OA invoice offset、data reset section/dialogs、OA manual search/import table 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留用户可见行为：`项目状态管理` region、`银行账户映射` region、从 OA 同步项目、新增本地项目、进行中/已完成项目双表格、完成/恢复/删除行操作、银行名称/简称/尾号输入、新增账户映射、行内编辑/删除、disabled/loading/status/error states、表格内容高密度对齐、金额/数字列若出现必须 tabular/right align。运行 selected tests `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|renders as a tree-and-panel page|switches the content panel|keeps read-only settings users"`，预期 behavior tests pass and source-level contract still fails for later Settings sections；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails only for remaining later sections/dialogs/table/settingsDesign；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|settingsDataGridSx|settingsButtonSx|DeleteOutlined|CheckCircleOutlineIcon|UndoIcon|<(Alert|Box|Button|IconButton|TextField|Typography)\\b' web/src/components/settings/SettingsProjectsSection.tsx web/src/components/settings/SettingsBankAccountsSection.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P103 access/pending tags prompt。
```

#### Review

- Single slice: yes，only Settings project and bank account sections。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Table form factor preserved: required，do not turn editable tables into card lists。
- Expected source-level failure allowed: yes，later Settings sections/dialogs/table/settingsDesign still use MUI after P102。

#### Execution Notes

- Runtime implementation changed:
  - `SettingsProjectsSection.tsx` moved from MUI DataGrid/TextField/Button/IconButton/Alert/icons to native forms, native tables and lucide action icons.
  - `SettingsBankAccountsSection.tsx` moved from MUI DataGrid/session hooks/TextField/Button/IconButton/Alert to a native editable table preserving row inputs and delete actions.
  - `web/src/app/styles.css` added Settings form/table/action/source-tag classes using existing `--fp-*` tokens.
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - scoped projects/bank no-MUI/DataGrid grep: passed。
  - `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|renders as a tree-and-panel page|switches the content panel|keeps read-only settings users"`: expected-fail；selected behavior tests passed, source-level contract failed only for later Settings section/dialog/table/settingsDesign files。
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail；12 behavior tests passed, 1 source-level contract failed for remaining Settings MUI runtime。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
- Next prompt generated: `P103-phase-6-settings-access-and-pending-tags`。

### P103-phase-6-settings-access-and-pending-tags

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/settings` access accounts and pending invoice tag sections only。

#### Prompt

```text
Prompt ID: P103-phase-6-settings-access-and-pending-tags
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` access accounts and pending invoice tag sections only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/SettingsAccessAccountsSection.tsx、web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移访问账户 section 和待找发票筛选 section：移除 MUI DataGrid、Select/Menu/MenuItem/List/ListItem/Button/TextField/Alert/Chip/Tooltip/IconButton/icons、settingsDataGridSx/settingsButtonSx/settingsSectionSx/settingsTokens 在这两个 section 的使用，改为原生/project table、select、menu/popover-like surface、tag、button、status classes。不得迁移 OA retention/import、OA invoice offset、data reset section/dialogs、OA manual search/import table 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留用户可见行为：`访问账户` region、管理员账号提示、新增账户用户名和 `新增账户权限` select、访问账户行内编辑/删除、`待找发票筛选` region、分组列表 `需要开票`/`流水代替发票`/`无需开票`、`选择现有标签` menu/popover trigger、active tags 可选、移除按钮、invalid historical mappings `标签不存在` / `标签已停用` 保持可见且继续阻止保存。运行 selected tests `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|manages pending invoice tag mappings|keeps invalid historical pending invoice mappings|keeps read-only settings users"`，预期 behavior tests pass and source-level contract still fails for later Settings sections；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails only for OA/data reset/manual table/settingsDesign；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|settingsDataGridSx|settingsButtonSx|settingsSectionSx|settingsTokens|DeleteOutlined|<(Alert|Box|Button|Chip|FormControl|IconButton|InputLabel|List|ListItem|ListItemButton|ListItemText|Menu|MenuItem|Select|Stack|TextField|Tooltip|Typography)\\b' web/src/components/settings/SettingsAccessAccountsSection.tsx web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P104 OA rules and data reset prompt。
```

#### Review

- Single slice: yes，only Settings access accounts and pending invoice tag sections。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Menu/popover form factor preserved: required，`选择现有标签` must stay a trigger-driven selection surface。
- Expected source-level failure allowed: yes，OA/data reset/manual table/settingsDesign remain after P103。

#### Execution Notes

- Runtime implementation changed:
  - `SettingsAccessAccountsSection.tsx` moved from MUI DataGrid/FormControl/Select/TextField/Button/IconButton/Alert/icons to native table/select/input controls and lucide delete action。
  - `SettingsPendingInvoiceTagsSection.tsx` moved from MUI List/Menu/MenuItem/Chip/Button/TextField/Tooltip/IconButton/icons to native group buttons, native select, trigger-driven `role="menu"`/`role="menuitem"` surface and project tag rows。
  - `web/src/app/styles.css` added access account, pending invoice tag, menu, select and tag classes, and removed obsolete access `.MuiAlert` selectors。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - scoped access/pending no-MUI grep: passed。
  - `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|manages pending invoice tag mappings|keeps invalid historical pending invoice mappings|keeps read-only settings users"`: expected-fail；selected behavior tests passed, source-level contract failed only for OA/data reset/manual table/settingsDesign files。
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail；12 behavior tests passed, 1 source-level contract failed for remaining Settings MUI runtime。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - access scoped CSS MUI grep: passed。
  - `git diff --check`: passed。
- Next prompt generated: `P104-phase-6-settings-oa-rules-and-data-reset`。

### P104-phase-6-settings-oa-rules-and-data-reset

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/settings` OA retention/import, OA invoice offset, data reset section and data reset dialogs only。

#### Prompt

```text
Prompt ID: P104-phase-6-settings-oa-rules-and-data-reset
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` OA retention/import, OA invoice offset, data reset section and data reset dialogs only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/SettingsOaRetentionSection.tsx、web/src/components/settings/SettingsOaInvoiceOffsetSection.tsx、web/src/components/settings/SettingsDataResetSection.tsx、web/src/components/settings/SettingsDataResetDialogs.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移 OA 导入设置、冲账规则、高风险数据重置 section 和两个数据重置 modal dialogs：移除 MUI TextField/FormControl/FormGroup/FormLabel/FormControlLabel/Checkbox/Alert/Card/LinearProgress/Button/Dialog/DialogTitle/DialogContent/DialogActions/CircularProgress/Typography/Stack/Box 以及 settingsSectionSx/settingsTokens 在这些文件的使用，改为原生/project fieldset/checkbox/input/status/progress/dialog classes。不得迁移 OA manual search/import table、settingsDesign.ts closeout 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留用户可见行为：`OA导入设置` region、cutoff date、form type/status checkboxes、`冲账规则` region/applicant textarea、`高风险数据重置` region、三个数据重置 actions、progress text such as `正在清理 app 内部状态。 25%`、modal dialog `确认数据重置`、modal dialog `OA 密码复核`、password field `当前 OA 用户密码`、`继续`/`确认清理`/`取消` labels and disabled/loading states。运行 selected tests `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|keeps data reset behind impact confirmation|keeps read-only settings users"`，预期 behavior tests pass and source-level contract still fails for OA manual table/settingsDesign；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails only for OA manual table/settingsDesign；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|settingsSectionSx|settingsTokens|<(Alert|Box|Button|Card|Checkbox|CircularProgress|Dialog|DialogActions|DialogContent|DialogTitle|FormControl|FormControlLabel|FormGroup|FormLabel|LinearProgress|Stack|TextField|Typography)\\b' web/src/components/settings/SettingsOaRetentionSection.tsx web/src/components/settings/SettingsOaInvoiceOffsetSection.tsx web/src/components/settings/SettingsDataResetSection.tsx web/src/components/settings/SettingsDataResetDialogs.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P105 OA manual search/import table prompt。
```

#### Review

- Single slice: yes，only OA settings, data reset section and data reset dialogs。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Modal form factor preserved: required，old destructive dialogs remain modal dialogs with same labels。
- Expected source-level failure allowed: yes，OA manual search/import table and settingsDesign remain after P104。

#### Execution Notes

- Runtime implementation changed:
  - `SettingsOaRetentionSection.tsx` moved from MUI field/checkbox/status/layout primitives to native fieldsets, checkboxes, date input and status panel while keeping OA manual import table embedded for P105。
  - `SettingsOaInvoiceOffsetSection.tsx` moved from MUI TextField/Alert/layout primitives to native input and status panel。
  - `SettingsDataResetSection.tsx` moved from MUI Alert/Card/LinearProgress/Button/layout primitives to native risk/status panels, cards, progress and danger buttons。
  - `SettingsDataResetDialogs.tsx` moved from MUI Dialog/TextField/Button/layout primitives to project `AppDialog` with native password field and actions。
  - `web/src/app/styles.css` added OA import, checkbox, data reset, danger button and dialog content classes。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - scoped OA/data reset no-MUI grep: passed。
  - `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|keeps data reset behind impact confirmation|keeps read-only settings users"`: expected-fail；selected behavior tests passed, source-level contract failed only for `OaManualSearchImportTable.tsx` and `settingsDesign.ts`。
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail；12 behavior tests passed, 1 source-level contract failed for remaining Settings MUI runtime。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
- Next prompt generated: `P105-phase-6-settings-oa-manual-search-import-table`。

### P105-phase-6-settings-oa-manual-search-import-table

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/settings` OA manual search/import table only。

#### Prompt

```text
Prompt ID: P105-phase-6-settings-oa-manual-search-import-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` OA manual search/import table only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/OaManualSearchImportTable.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsOaManualSearchImportTable.test.tsx、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移 OA manual search/import table：移除 MUI Table/TableContainer/TableHead/TableBody/TableRow/TableCell/TablePagination/Checkbox/Collapse/Alert/CircularProgress/Button/TextField/FormControl/FormLabel/FormGroup/FormControlLabel/Chip/Tooltip/IconButton/icons、settingsButtonSx/settingsTokens 在该文件的使用，改为原生/project filters、checkboxes、table、pagination、detail expansion、status、buttons and tags。不得迁移 settingsDesign.ts closeout 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、OA 手工导入语义、附件刷新语义、导入 payload 或关联台内部工作区。保留用户可见行为：heading `OA全量搜索导入`、filters `搜索关键字`/`开始日期`/`结束日期`、form type/status filter groups、`搜索`、`导入已选OA项`、`清空选择`、table `OA全量搜索导入结果`、row selection `选择 OA <row_id>`、current page selection `选择当前页可导入OA`、detail toggle `展开 OA <row_id> 明细`、refresh action `刷新 OA <row_id> 附件解析`、pagination、nested detail table、disabled non-importable rows、selected import payload and global shell status isolation。运行 `cd web && npx vitest run SettingsOaManualSearchImportTable.test.tsx`，必须通过；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails only for settingsDesign.ts；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|settingsButtonSx|settingsTokens|<(Alert|Box|Button|Checkbox|Chip|CircularProgress|Collapse|FormControl|FormControlLabel|FormGroup|FormLabel|IconButton|Table|TableBody|TableCell|TableContainer|TableHead|TablePagination|TableRow|TextField|Tooltip|Typography)\\b|ExpandMoreIcon|ExpandLessIcon|RefreshIcon' web/src/components/settings/OaManualSearchImportTable.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P106 settings closeout prompt。
```

#### Review

- Single slice: yes，only OA manual search/import table。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Table and pagination form factor preserved: required。
- Expected source-level failure allowed: yes，settingsDesign closeout remains after P105。

#### Execution Notes

- Runtime implementation changed:
  - `OaManualSearchImportTable.tsx` moved from MUI table, pagination, checkbox, collapse, alert, text field, form control, chip, tooltip, icon button and MUI icons to native/project filters, checkboxes, dense tables, pagination controls, expansion rows, status panels, buttons and tags。
  - The OA manual search/import table keeps the accessible name `OA全量搜索导入结果`, filters, current-page selection, per-row selection, nested detail table, attachment refresh, import action, clear-selection action and global shell status isolation。
  - `web/src/app/styles.css` added OA manual import filter, toolbar, pagination, selected-row and table alignment classes using existing `--fp-*` tokens。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - scoped OA manual table no-MUI grep: passed。
  - `cd web && npx vitest run SettingsOaManualSearchImportTable.test.tsx`: passed；5 tests passed。
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail；13 behavior tests passed, source-level contract failed only for `src/components/settings/settingsDesign.ts`。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
- Commit: `6648341e feat: migrate settings oa manual table`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P106-phase-6-settings-closeout`。

### P106-phase-6-settings-closeout

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: `/settings` closeout for `settingsDesign.ts` only。

#### Prompt

```text
Prompt ID: P106-phase-6-settings-closeout
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` closeout for `settingsDesign.ts` only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/settingsDesign.ts、web/src/pages/SettingsPage.tsx、web/src/components/settings/*、web/src/test/SettingsPage.test.tsx、web/src/test/SettingsOaManualSearchImportTable.test.tsx 和 web/src/app/styles.css。只处理 Settings closeout：检查 `settingsDesign.ts` 是否仍有 runtime 使用；如果未使用则删除该 MUI theme bridge；如果仍有使用则转换为纯 project token module，必须移除 MUI `createTheme`、`SxProps`、`Theme`、DataGrid theme augmentation、`settingsTheme`、`settingsDataGridSx`、`settingsButtonSx`、`settingsSectionSx` 等 MUI bridge。不得迁移 `MonthPicker`、不得修改 frozen workbench legacy MUI、不得修改 Settings API/client/mock response/backend/read model/worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留 Settings 用户可见行为和 P100-P105 已锁定的 tree, regions, tables, menu, dialogs, OA manual import table form factor。运行 `rg -n "settingsDesign|settingsTokens|settingsTheme|settingsButtonSx|settingsDataGridSx|settingsPageSx|settingsHeaderSx|settingsLayoutSx|settingsNavShellSx|settingsContentSx|settingsSectionSx" web/src` 确认引用边界；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，必须通过；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|settingsTheme|settingsButtonSx|settingsDataGridSx|settingsSectionSx|<(Alert|Box|Button|Checkbox|Chip|CircularProgress|Collapse|Dialog|FormControl|IconButton|List|Menu|Select|Table|TextField|Tooltip|Typography)\\b' web/src/pages/SettingsPage.tsx web/src/components/settings; then exit 1; else exit 0; fi`，必须通过；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 `MG-P106-phase-6-settings` prompt。
```

#### Review

- Single slice: yes，only Settings closeout for `settingsDesign.ts`。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- MonthPicker/frozen legacy MUI untouched: required。
- Expected source-level failure allowed: no，Settings source-level contract must pass after P106。

#### Execution Notes

- Runtime implementation changed:
  - Deleted unused `web/src/components/settings/settingsDesign.ts`; Settings no longer carries a MUI theme/DataGrid/Sx bridge。
  - Removed the deleted file from the Settings source-level no-MUI contract file list in `SettingsPage.test.tsx`。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- MonthPicker/frozen legacy MUI changed: no。
- Verification:
  - runtime settingsDesign/settingsTokens/settingsTheme/settingsButtonSx/settingsDataGridSx/settingsSectionSx reference grep excluding tests: passed。
  - scoped Settings no-MUI grep for `SettingsPage.tsx` and `web/src/components/settings`: passed。
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: passed；13 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
- Commit: `ad8b3d40 feat: close settings mui bridge`, pushed to `origin/refactor-ui`。
- Next prompt generated: `MG-P106-phase-6-settings`。

### MG-P106-phase-6-settings

- Phase: `phase_6_page_batches`
- Status: `verified`
- Type: `cumulative merge gate`
- Scope: `/settings` P099-P106 migration only。

#### Prompt

```text
Prompt ID: MG-P106-phase-6-settings
Phase: phase_6_page_batches
Type: cumulative merge gate
Scope: `/settings` P099-P106 migration only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、web/src/pages/SettingsPage.tsx、web/src/components/settings/*、web/src/test/SettingsPage.test.tsx、web/src/test/SettingsOaManualSearchImportTable.test.tsx 和当前 git status/diff。检查当前分支必须是 `refactor-ui`。确认 untracked files、diff scope、测试结果和文档状态；确认 P099-P106 已记录并且 Settings source-level no-MUI contract passed。运行 `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 no-MUI grep：`if rg -n '@mui/|Mui[A-Z]|settingsTheme|settingsButtonSx|settingsDataGridSx|settingsSectionSx|<(Alert|Box|Button|Checkbox|Chip|CircularProgress|Collapse|Dialog|FormControl|IconButton|List|Menu|Select|Table|TextField|Tooltip|Typography)\\b' web/src/pages/SettingsPage.tsx web/src/components/settings; then exit 1; else exit 0; fi`；运行 runtime settingsDesign reference grep：`if rg -n "settingsDesign|settingsTokens|settingsTheme|settingsButtonSx|settingsDataGridSx|settingsPageSx|settingsHeaderSx|settingsLayoutSx|settingsNavShellSx|settingsContentSx|settingsSectionSx" web/src --glob '!**/*.test.tsx' --glob '!**/*.test.ts'; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。确认 scope 只包含 Settings P106 closeout files and docs files：`web/src/components/settings/settingsDesign.ts` deletion, `web/src/test/SettingsPage.test.tsx`, `docs/refactor-ui/modules/phase_6_settings.md`, `docs/refactor-ui/refactor_ui_prompt.md`, `docs/refactor-ui/refactor_ui_state.md`。禁止 `git add .` 和 `git add -A`，只允许精确 git add。MG 通过后提交并 push 到 `origin/refactor-ui`，再更新 state/prompt/module docs 的 MG execution notes 和 Push Log，标记 MG verified，并从 `refactor-ui` 分支生成下一条 Micro-JIT prompt。
```

#### Review

- Single MG scope: yes，only Settings P099-P106。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Exact staging required: yes。
- Expected outcome: Settings module committed, pushed and ready to move to next Phase 6 module。

#### Execution Notes

- Scope verified:
  - Settings P099 discovery through P106 closeout.
  - No backend/API/read model/worker changes.
  - No workbench internals changes.
- Verification:
  - `git status --short --branch`: clean before MG docs update。
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: passed；13 tests passed。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed；15 tests passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - Scoped Settings no-MUI grep: passed。
  - Runtime settingsDesign/settingsTokens/settingsTheme/settingsButtonSx/settingsDataGridSx/settingsSectionSx reference grep excluding tests: passed。
  - `git diff --check`: passed。
- Result:
  - Settings module is ready to leave Phase 6。
  - Next prompt generated: `P107-phase-7-mui-containment-discovery`。
- Commit: `2a30a7b0 docs: verify settings mg and add mui containment discovery`, pushed to `origin/refactor-ui`。

### P107-phase-7-mui-containment-discovery

- Phase: `phase_7_mui_containment`
- Status: `verified`
- Type: `discovery/planning`
- Scope: MUI containment discovery only。

#### Prompt

```text
Prompt ID: P107-phase-7-mui-containment-discovery
Phase: phase_7_mui_containment
Type: discovery/planning
Scope: MUI containment discovery only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/baseline_inventory.md、docs/refactor-ui/platform_stack_migration.md、docs/refactor-ui/test_migration_strategy.md、DESIGN.md、PRODUCT.md、web/package.json、web/src/app/App.tsx、web/src/app/MuiProviders.tsx、web/src/app/MuiDatePickerCompatProvider.tsx、web/src/app/muiTheme.ts、web/src/components/MonthPicker.tsx、web/src/hooks/useMuiDataGridPageSession.ts、web/src/app/styles.css、web/src/test/renderHelpers.tsx、web/src/test/MonthPicker.test.tsx、web/src/test/useMuiDataGridPageSession.test.tsx 和当前 MUI grep inventory。只做 discovery/planning，不改 runtime code、tests、CSS、依赖、后端、API、read model、worker 或关联台内部工作区。生成 `docs/refactor-ui/modules/phase_7_mui_containment.md`，记录当前所有 MUI 命中并分类为：允许的冻结关联台内部工作区、必须迁移的非关联台 runtime、必须替换/隔离的测试 harness、只用于负向 contract 的测试字符串、全局 CSS 中允许/禁止的 MUI selector、可删除的 MUI DataGrid session hook、MonthPicker/date compat 迁移边界。必须明确后续 Micro-JIT 队列，至少包含 MonthPicker/date compat、MuiProviders/test harness、DataGrid session cleanup、global CSS containment、final no-MUI contract 和 MG。不得把关联台内部工作区纳入视觉迁移。验证命令：`test -f docs/refactor-ui/modules/phase_7_mui_containment.md`；`rg -n "P107-phase-7-mui-containment-discovery|Current MUI Inventory|Allowed Workbench Legacy|Non-workbench Runtime Targets|Recommended Micro-JIT Queue|P108-phase-7" docs/refactor-ui/modules/phase_7_mui_containment.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`；`git diff --check`；`git status --short --branch`。更新 state/prompt docs。
```

#### Review

- Single slice: yes，discovery/planning only。
- Runtime code untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Docs on demand: yes，Phase 7 containment needs a reusable inventory and allowed-list。
- Expected outcome: phase 7 inventory doc created and P108 generated just-in-time。

#### Execution Notes

- Created `docs/refactor-ui/modules/phase_7_mui_containment.md`.
- Runtime implementation changed: no。
- Tests changed: no。
- CSS changed: no。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Discovery findings:
  - Allowed workbench legacy is restricted to frozen `web/src/components/workbench/*` MUI usage.
  - Non-workbench runtime targets are `MonthPicker.tsx`, `MuiDatePickerCompatProvider.tsx`, `App.tsx` date compat wrapper, `MuiProviders.tsx`, `muiTheme.ts`, `useMuiDataGridPageSession.ts` and non-workbench/global MUI selectors in `styles.css`.
  - Test harness still imports `MuiProviders`; non-workbench tests need a project provider helper and explicit workbench legacy provider only where required.
  - MUI-only session hook and MonthPicker tests need characterization before cleanup.
- Verification:
  - `test -f docs/refactor-ui/modules/phase_7_mui_containment.md`: passed。
  - `rg -n "P107-phase-7-mui-containment-discovery|Current MUI Inventory|Allowed Workbench Legacy|Non-workbench Runtime Targets|Recommended Micro-JIT Queue|P108-phase-7" docs/refactor-ui/modules/phase_7_mui_containment.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed。
  - `git diff --check`: passed。
- Commit: `f135e4bd docs: add mui containment discovery`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P108-phase-7-month-picker-characterization-tests`。

### P108-phase-7-month-picker-characterization-tests

- Phase: `phase_7_mui_containment`
- Status: `verified`
- Type: `characterization tests`
- Scope: MonthPicker/date compat characterization tests only。

#### Prompt

```text
Prompt ID: P108-phase-7-month-picker-characterization-tests
Phase: phase_7_mui_containment
Type: characterization tests
Scope: MonthPicker/date compat characterization tests only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_7_mui_containment.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/MonthPicker.tsx、web/src/test/MonthPicker.test.tsx、web/src/app/App.tsx、web/src/app/MuiDatePickerCompatProvider.tsx 和 web/src/app/styles.css。只修改 MonthPicker/date compat 相关测试，不改 runtime code、CSS、依赖、backend、API、read model、worker 或关联台内部工作区。把 `MonthPicker.test.tsx` 中保护 MUI X field/class 的断言改成用户可见行为和 ARIA 合约：普通模式显示当前 `YYYY-MM` 对应年月、点击 `年月选择` 后可选择年份和月份并 emit `YYYY-MM`、inline 模式可直接选择月份、`formatMonthLabel` 保持中文年月、invalid month fallback 保持可预测。添加 source-level no-MUI/date-compat contract，覆盖 `MonthPicker.tsx`、`MuiDatePickerCompatProvider.tsx` 和 `App.tsx` date compat wrapper，预期 contract 失败但行为测试通过。运行 `cd web && npx vitest run MonthPicker.test.tsx`，预期 behavior tests pass and source-level contract fails against current MUI X runtime；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P109 month picker/date compat implementation prompt。
```

#### Review

- Single slice: yes，tests only。
- Runtime untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected failure allowed: yes，source-level no-MUI/date-compat contract should fail until P109。

#### Execution Notes

- Runtime implementation changed: no。
- Test implementation changed:
  - `MonthPicker.test.tsx` now reads source files for `MonthPicker.tsx`, `MuiDatePickerCompatProvider.tsx` and `App.tsx`。
  - Replaced the old `.MuiFormControl-root` assertion with user-visible month field semantics。
  - Added inline month selection coverage。
  - Added `formatMonthLabel` coverage for normal and invalid values。
  - Added a source-level no-MUI/date-compat contract that currently fails against the MUI X MonthPicker runtime。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - `cd web && npx vitest run MonthPicker.test.tsx`: expected-fail；4 behavior tests passed, 1 source-level contract failed。
  - Expected failure files: `src/components/MonthPicker.tsx`, `src/app/MuiDatePickerCompatProvider.tsx`。
  - `git diff --check`: passed。
- Commit: `eb6049ec test: characterize month picker containment`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P109-phase-7-month-picker-and-date-compat`。

### P109-phase-7-month-picker-and-date-compat

- Phase: `phase_7_mui_containment`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: MonthPicker/date compat implementation only。

#### Prompt

```text
Prompt ID: P109-phase-7-month-picker-and-date-compat
Phase: phase_7_mui_containment
Type: extraction/refactor
Scope: MonthPicker/date compat implementation only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_7_mui_containment.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/MonthPicker.tsx、web/src/test/MonthPicker.test.tsx、web/src/app/App.tsx、web/src/app/MuiDatePickerCompatProvider.tsx 和 web/src/app/styles.css。只迁移 MonthPicker/date compat：把 `MonthPicker.tsx` 从 MUI Box、MUI X DatePicker、StaticDatePicker、SxProps/Theme 改为 native/project month picker；移除 `MuiDatePickerCompatProvider` 文件和 `App.tsx` 中的 wrapper/import；保留 `formatMonthLabel`、`YYYY-MM` external contract、invalid fallback、默认 aria label `年月选择`、caption `月份`、inline 和 non-inline modes、用户选择年份/月后 emit `YYYY-MM`。不得修改 MonthProvider、路由、业务 providers 顺序、backend、API、read model、worker 或关联台内部工作区。运行 `cd web && npx vitest run MonthPicker.test.tsx`，必须通过；运行 `cd web && npx vitest run App.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`，必须通过；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|MuiDatePickerCompatProvider|LocalizationProvider|DatePicker|StaticDatePicker|MuiInputBase|MuiFormControl' web/src/components/MonthPicker.tsx web/src/app/App.tsx web/src/app/MuiDatePickerCompatProvider.tsx; then exit 1; else exit 0; fi`，必须通过（若 `MuiDatePickerCompatProvider.tsx` 被删除，用 `test ! -f web/src/app/MuiDatePickerCompatProvider.tsx` 记录）；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P110 DataGrid session cleanup prompt。
```

#### Review

- Single slice: yes，only MonthPicker/date compat runtime。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Provider order preserved except removing the obsolete date picker compat wrapper: required。
- Expected source-level failure allowed: no，P109 must make MonthPicker/date compat contract pass。

#### Execution Notes

- Runtime implementation changed:
  - `MonthPicker.tsx` now uses native/project button, radio-group and popover markup; no MUI or MUI X imports remain。
  - `MuiDatePickerCompatProvider.tsx` was deleted。
  - `App.tsx` no longer imports or wraps the app in `MuiDatePickerCompatProvider`; all other business provider ordering remains unchanged。
- Test implementation changed:
  - `MonthPicker.test.tsx` now treats deleted date compat files as the passing state。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - `cd web && npx vitest run MonthPicker.test.tsx`: passed；5 tests passed。
  - `cd web && npx vitest run App.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed；26 tests passed。
  - `test ! -f web/src/app/MuiDatePickerCompatProvider.tsx` plus scoped no-MUI/date-compat grep for `MonthPicker.tsx` and `App.tsx`: passed。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
- Commit: `f8799863 feat: migrate month picker containment`, pushed to `origin/refactor-ui`。
- Next prompt generated: `P110-phase-7-datagrid-session-cleanup`。

### P110-phase-7-datagrid-session-cleanup

- Phase: `phase_7_mui_containment`
- Status: `verified`
- Type: `extraction/refactor`
- Scope: obsolete MUI DataGrid session hook cleanup only。

#### Prompt

```text
Prompt ID: P110-phase-7-datagrid-session-cleanup
Phase: phase_7_mui_containment
Type: extraction/refactor
Scope: obsolete MUI DataGrid session hook cleanup only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_7_mui_containment.md、docs/refactor-ui/test_migration_strategy.md、web/src/hooks/useMuiDataGridPageSession.ts、web/src/test/useMuiDataGridPageSession.test.tsx、web/src/hooks/useFinanceTableSession.ts、web/src/test/useFinanceTableSession.test.tsx 和当前 `rg -n "useMuiDataGridPageSession|useMuiDataGridScrollSession|MuiDataGridPageSession|@mui/x-data-grid" web/src` 结果。只处理 MUI DataGrid session cleanup：如果 runtime references 只剩该 hook/test，则删除 `useMuiDataGridPageSession.ts` 和 `useMuiDataGridPageSession.test.tsx`；确认 `useFinanceTableSession` 仍覆盖 native table session persistence；如发现 runtime 页面仍引用 MUI DataGrid session，停止删除并生成更小迁移 prompt。不得修改页面 UI、backend、API、read model、worker 或关联台内部工作区。运行 reference grep，运行 `cd web && npx vitest run useFinanceTableSession.test.tsx TableAlignmentStyles.test.ts`，运行 `if rg -n 'useMuiDataGridPageSession|useMuiDataGridScrollSession|MuiDataGridPageSession|@mui/x-data-grid' web/src --glob '!**/*.test.tsx' --glob '!**/*.test.ts'; then exit 1; else exit 0; fi`，运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P111 test provider containment prompt。
```

#### Review

- Single slice: yes，obsolete MUI DataGrid session hook cleanup only。
- Runtime page UI untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected source-level failure allowed: no，runtime MUI DataGrid session references must be gone after P110。

#### Execution Notes

- Runtime implementation changed:
  - Deleted obsolete `web/src/hooks/useMuiDataGridPageSession.ts`。
  - Removed MUI DataGrid locale layer from `web/src/app/muiTheme.ts`。
- Test implementation changed:
  - Deleted obsolete `web/src/test/useMuiDataGridPageSession.test.tsx`。
- Backend/API/read model/worker changed: no。
- Workbench internals changed: no。
- Verification:
  - Reference grep showed no runtime page references to the MUI DataGrid session hook before deletion。
  - `cd web && npx vitest run useFinanceTableSession.test.tsx TableAlignmentStyles.test.ts`: passed；7 tests passed。
  - Runtime `useMuiDataGridPageSession|useMuiDataGridScrollSession|MuiDataGridPageSession|@mui/x-data-grid` grep excluding tests: passed。
  - Full reference grep only finds a negative test string in `BankDetailsPage.test.tsx`。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning。
  - `git diff --check`: passed。
- Next prompt generated: `P111-phase-7-test-provider-containment`。

### P111-phase-7-test-provider-containment

- Phase: `phase_7_mui_containment`
- Status: `approved_for_execution`
- Type: `extraction/refactor`
- Scope: non-workbench test provider containment only。

#### Prompt

```text
Prompt ID: P111-phase-7-test-provider-containment
Phase: phase_7_mui_containment
Type: extraction/refactor
Scope: non-workbench test provider containment only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_7_mui_containment.md、docs/refactor-ui/test_migration_strategy.md、web/src/test/renderHelpers.tsx、web/src/app/MuiProviders.tsx、web/src/app/muiTheme.ts、web/src/test/CommonMuiComponents.test.tsx、web/src/test/SettingsOaManualSearchImportTable.test.tsx、web/src/test/MonthPicker.test.tsx、web/src/test/WorkbenchExceptionModal.test.tsx 和当前 `rg -n "import MuiProviders|<MuiProviders|MuiProviders" web/src/test` 结果。只处理测试 provider containment：新增或调整 project test provider helper，使非关联台 tests 不再默认 import/wrap `MuiProviders`；如冻结 workbench tests still need MUI provider, expose an explicitly named legacy helper or keep direct `MuiProviders` only in workbench test scope and document it。不得修改 runtime UI、backend、API、read model、worker 或关联台内部工作区。运行 targeted tests for changed harness users（至少 `cd web && npx vitest run CommonMuiComponents.test.tsx MonthPicker.test.tsx SettingsOaManualSearchImportTable.test.tsx WorkbenchExceptionModal.test.tsx`）；运行 provider grep to prove non-workbench test provider no longer defaults to MUI and only workbench legacy remains；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P112 global CSS containment prompt。
```

#### Review

- Single slice: yes，test provider containment only。
- Runtime UI untouched: required。
- Backend/API/read model/worker untouched: required。
- Workbench internals frozen: required。
- Expected source-level failure allowed: no，non-workbench tests should no longer default to MUI provider after P111。

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
