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

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_bank_details.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BankDetailsPage.tsx、web/src/test/BankDetailsPage.test.tsx、web/src/components/common/FinanceTable.tsx、web/src/components/common/FinanceTag.tsx、web/src/components/common/AmountCell.tsx 和 web/src/app/styles.css。只修改 BankDetailsPage.tsx、必要的 styles.css 和必要的 BankDetails test expectations：移除交易流水表格区域的 MUI Table/TableContainer/TableHead/TableBody/TableRow/TableCell/TablePagination imports 和 usage；使用 FinanceTable/project pagination 保留 accessible name `交易流水`、headers、loading row `正在加载流水。`、empty row `当前时间范围内没有流水。`、row classes、counterparty cell、TypeCell 嵌入位置、amount/balance tabular numeric alignment、direction/source chip vertical alignment、server page/pageSize/total behavior、pagination labels `每页行数`、`1-100 / 299`、`下一页` 和 page size options `[25, 50, 100]`。不得修改后端、API、read model、worker、mock 或关联台。不得迁移 category filter Popper、TypeCell menu internals、BankCategoryTag/internal transfer tooltip 或 AutoTagRulesDrawer；这些仍归属 P044/P045。运行 `cd web && npx vitest run BankDetailsPage.test.tsx -t "交易流水|pagination|searches current account|loads all accounts|uses Chinese labels"`；运行完整 `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`，P044/P045 category/drawer failures 可以继续 expected-fail，但 P043 table/pagination failures 必须清除；运行 `cd web && npm run build`；运行 BankDetails transaction-table MUI import grep、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P044 category popovers prompt。
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
- Status: `approved_for_execution`
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
