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

- `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx`
- `cd web && npm run build`
- `if rg -n '@mui/' web/src/app/App.tsx web/src/components/shell web/src/app/pageRegistry.tsx; then exit 1; else exit 0; fi`
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
