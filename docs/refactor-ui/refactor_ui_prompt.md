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
- Status: `reviewed`
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
| `P022-phase-6-tax-offset-discovery` | `phase_6_page_batches` | tax offset discovery | `reviewed` | pending | 下一条执行 prompt，进入 Phase 6 第一个页面模块 discovery |

## Next Prompt Draft Slot

下一条 prompt 应执行 `P022-phase-6-tax-offset-discovery`。

```text
读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/module_inventory.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/TaxOffsetPage.tsx、web/src/test/TaxOffsetPage.test.tsx、web/src/components/tax/*、web/src/components/common/FileDropzone.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/FinanceTable.tsx。只做 TaxOffsetPage discovery/planning，记录旧 UI 入口、表格/导入/月份/认证导入弹窗/结果右侧抽屉、MUI imports、已迁 common primitives、测试断言和风险。不得迁移实现，不改后端/API/read model/worker/关联台。按需在 docs/refactor-ui/modules/phase_6_tax_offset.md 新建或更新专项文档；更新 state/prompt docs；运行文档/key grep、git diff --check、git status。
```

## Cumulative MG Prompts

最近完成的 MG 是 `MG-P021-phase-5-app-health-table-pilot-refactor`。下一条执行 prompt 是 `P022-phase-6-tax-offset-discovery`。

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
