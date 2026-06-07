# Phase 4 App Shell

本文档记录 App Shell 迁移切片。App Shell 会迁到 HeroUI/Tailwind，但关联台内部工作区继续冻结。

## Phase 4 Boundary

### In Scope

- `web/src/app/App.tsx`
- `web/src/app/MuiProviders.tsx`
- `web/src/app/muiTheme.ts`
- `web/src/app/pageRegistry.tsx`
- `web/src/components/shell/AppSidebar.tsx`
- `web/src/components/shell/AppTopBar.tsx`
- `web/src/components/shell/AppStatusIndicator.tsx`
- `web/src/components/shell/sidebarItems.ts`
- App Shell 相关 CSS 和 shell tests

### Out Of Scope

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/components/workbench/*`
- 非 shell 业务页面批量迁移
- tax/import/cost/pending 等业务子组件迁移
- 后端、API contract、read model、worker、权限语义、业务状态机

## Existing Shell Contracts

- 左侧菜单栏是 App Shell 的主导航。
- 桌面端保留展开/折叠宽度：`expandedSidebarWidth = 232`，`collapsedSidebarWidth = 72`。
- 移动端保留可打开/关闭的临时侧边栏。
- OA embedded mode 默认折叠，保留 `embedded-shell` / `embedded-header` 语义。
- 工作台页面模式继续隐藏 global header。
- `--sidebar-width` CSS variable 继续供 workbench popover 定位读取。
- 关联台内部工作区只被新 shell 包住，内部三栏、行交互、弹窗和专用 CSS 不改。

## MUI Usage To Remove In Phase 4

### App Runtime

- `App.tsx`: `Alert`、`Box`、`useMediaQuery`、`useTheme`。
- `MuiProviders.tsx`: `ThemeProvider`、`CssBaseline`。
- `muiTheme.ts`: MUI theme definition；非关联台迁完前暂不删除文件，先从 shell runtime 中移除依赖。

### Shell Components

- `AppSidebar.tsx`: MUI Drawer/List/ListItem/ListItemButton/ListItemIcon/ListItemText/Stack/Collapse/Tooltip/IconButton/Divider/Typography 和 Chevron icons。
- `AppTopBar.tsx`: MUI AppBar/Toolbar/Stack/Tooltip/IconButton 和 Menu icon。
- `AppStatusIndicator.tsx`: MUI Popper/ClickAwayListener/Paper/Chip/Divider/LinearProgress/Stack/Typography/SvgIcon/Box。
- `pageRegistry.tsx`: MUI icon imports for sidebar items。

## Icon Decision

MUI icons must be removed from non-workbench shell. HeroUI v3 does not provide the full business icon set used by the sidebar. Use `lucide-react` as the replacement icon library for shell/navigation icons because it is tree-shakable, React-native, broadly maintained, and matches the requested button/icon guidance.

`lucide-react` must be introduced in a dedicated platform/shell slice with package and lockfile changes, not hidden inside a page migration.

## Micro-JIT Slice Plan

1. `P011-phase-4-shell-discovery`: this discovery doc and next prompt generation only.
2. `P012-phase-4-shell-icon-dependency`: add `lucide-react`, migrate `pageRegistry` and sidebar icon type/tests.
3. `P013-phase-4-shell-provider-runtime`: remove `MuiProviders` from `App.tsx`, replace `useMediaQuery/useTheme/Box/Alert` with React/CSS/HeroUI primitives while keeping shell behavior.
4. `P014-phase-4-sidebar-topbar`: migrate `AppSidebar` and `AppTopBar` to HeroUI/Tailwind/native markup while preserving desktop/mobile/embedded behavior.
5. `P015-phase-4-status-indicator`: migrate status popover/chips/progress to HeroUI/Tailwind/native behavior.
6. `MG-phase-4-shell`: run shell tests/build/MUI containment checks and push.

Each implementation prompt must preserve user-visible entry points: if a menu item exists before, it exists after with the same label/path/active behavior.

## Verification Targets

- `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageRouteHost.test.tsx HeroUIPlatformSmoke.test.tsx`
- `cd web && npm run build`
- `if rg -n '@mui/' web/src/app/App.tsx web/src/components/shell web/src/app/pageRegistry.tsx; then exit 1; else exit 0; fi`
- During P013 only, `App.tsx` must contain no direct `@mui/*` imports. A temporary date picker compatibility provider is allowed until `MonthPicker` and page date pickers migrate.
- `git diff --check`
- `git status --short --branch`

## Slice P012: Shell Icon Dependency

### Scope

- `web/package.json`
- `web/package-lock.json`
- `web/src/app/pageRegistry.tsx`
- `web/src/components/shell/AppSidebar.tsx`
- `web/src/test/App.test.tsx`

### Result

- Status: verified。
- Installed `lucide-react@1.17.0`.
- Replaced MUI sidebar icon imports and `SvgIconComponent` typing with `LucideIcon`.
- Updated sidebar icon tests to assert lucide components.
- Updated `AppSidebar` icon rendering from MUI `fontSize` to lucide `size/strokeWidth`.
- Did not migrate AppSidebar layout, AppTopBar, AppStatusIndicator, App runtime provider, backend, or workbench internals.
- `npm install` still reports 9 vulnerabilities already present in the dependency tree; no `npm audit fix` was run because it is outside this scoped shell icon slice.
- Build passes with known HeroUI/Tailwind generated CSS minifier warnings and existing chunk size warning.

## Slice P013: Shell Provider Runtime

### Scope

- `web/src/app/App.tsx`
- `web/src/app/MuiDatePickerCompatProvider.tsx`
- `web/src/app/styles.css`

### Result

- Status: verified。
- Removed `MuiProviders` from `App.tsx`; App Shell no longer receives MUI ThemeProvider/CssBaseline as the root UI runtime.
- Replaced `useTheme`/`useMediaQuery` with a small shell-local `matchMedia` hook.
- Replaced App Shell `Box` layout wrappers with semantic `div`/`section`/`main` markup and token CSS classes.
- Replaced the shell operation error `Alert` with HeroUI `Alert` plus an explicit close button that preserves the old dismiss action.
- Added `MuiDatePickerCompatProvider` as a temporary, narrowly scoped compatibility layer for MUI X date pickers still used by non-shell pages. This keeps `adapterLocale="zh-cn"` and date picker `localeText` so MonthPicker keeps the existing Chinese accessible labels.
- The first verification run failed after removing the full `MuiProviders` because MUI X DatePicker lost localization context; the fix is the narrow compatibility provider, not restoring the full MUI theme runtime.
- Did not migrate `AppSidebar`, `AppTopBar`, `AppStatusIndicator`, business pages, backend, API, read model, worker, or workbench internals.
- Build passes with known HeroUI/Tailwind generated CSS minifier warnings and existing chunk size warning.

## Slice P014: Sidebar And Topbar

### Scope

- `web/src/components/shell/AppSidebar.tsx`
- `web/src/components/shell/AppTopBar.tsx`
- `web/src/app/styles.css`
- `web/src/test/App.test.tsx`

### Result

- Status: verified。
- Added a compact/mobile sidebar characterization test that stubs shell `matchMedia`, verifies the topbar menu button, opens the left navigation drawer, confirms the `设置` entry remains available, and navigates to `/settings`.
- Migrated `AppSidebar` from MUI Drawer/List/ListItem/ListItemButton/ListItemIcon/ListItemText/Stack/Collapse/Tooltip/IconButton/Divider/Typography to HeroUI Drawer/Button/Tooltip/Separator plus semantic `aside/nav/section/ul/li/a` markup.
- Migrated `AppTopBar` from MUI AppBar/Toolbar/Stack/Tooltip/IconButton/Menu icon to HeroUI Button/Tooltip plus semantic header markup and lucide `Menu` icon.
- Preserved desktop expanded/collapsed behavior, compact mobile drawer open/close, embedded mode brand availability, `aria-current="page"`, link labels, href/path behavior, and existing sidebar widths 232/72.
- Updated sidebar CSS to use project-owned classes (`.app-sidebar-link.active`, `.app-sidebar-list`, `.app-sidebar-dialog`, `.global-menu-button`) instead of MUI selected/collapse/list text classes.
- Did not migrate `AppStatusIndicator`; it remains the only MUI usage under `web/src/components/shell` and is the next P015 target.
- Did not migrate business pages, backend, API, read model, worker, or workbench internals.
- Build passes with known HeroUI/Tailwind generated CSS minifier warnings and existing chunk size warning.

## Slice P015: Status Indicator

### Scope

- `web/src/components/shell/AppStatusIndicator.tsx`
- `web/src/app/styles.css`

### Result

- Status: verified。
- Migrated the global app status indicator from MUI Box/Chip/ClickAwayListener/Divider/LinearProgress/Paper/Popper/Stack/SvgIcon/Typography to HeroUI Chip/ProgressBar/Separator plus native SVG, portal, and semantic markup.
- Preserved `role="status"`, `aria-label`, `data-status-reason`, hover/focus/click open behavior, delayed pointer-leave close, Escape close, outside click close, route-change stability while interacting inside the popover, and admin-only `App Health` link.
- Replaced MUI Popper with project-owned portal positioning so the popover is not clipped by the sidebar and keeps the existing right-side placement behavior.
- Preserved domain links, task links, task percent progress, scope diagnostics, summary chips, and status text labels.
- `web/src/components/shell` now has no `@mui/*` imports.
- Did not migrate business pages, backend, API, read model, worker, or workbench internals.
- Build passes with known HeroUI/Tailwind generated CSS minifier warnings and existing chunk size warning.
