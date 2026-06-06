# Phase 6 AppHealth Discovery

本文档记录 AppHealth 运维状态页面的 page-level UI migration discovery。Phase 5 已把该页面的表格 surfaces 迁到 `FinanceTable`，本阶段只收口剩余 page shell、状态提示、刷新入口和布局 primitives。

Last updated: 2026-06-07

## Boundary

- Scope: `/operations/app-health` 页面、`web/src/pages/AppHealthOperationsPage.tsx`、`web/src/test/AppHealthOperationsPage.test.tsx` 和 AppHealth 前端测试契约。
- Non-scope: 不改后端、API contract、read model、worker、后台任务、权限语义、dashboard payload shape、关联台内部工作区。
- Behavior equivalence:
  - 旧页面仍是只读运维状态 dashboard，不新增后台任务 retry/acknowledge 操作。
  - 旧刷新入口仍位于页面标题右侧，按钮名称仍为 `刷新`。
  - 旧 loading、error、permission 状态仍以页面内提示呈现，不改为抽屉、弹窗或新路由。
  - 旧三段信息层级 `数据`、`请求`、`后台` 不重排为新的业务模块。
  - 旧表格仍是表格；Phase 5 已迁为 `FinanceTable` grid surfaces，本阶段不改变表格业务内容。

## Current MUI Inventory

| File | MUI usage | Migration target | Notes |
| --- | --- | --- | --- |
| `AppHealthOperationsPage.tsx` | `@mui/icons-material/Refresh` | `lucide-react` `RefreshCw` or equivalent | App Shell 已引入 lucide；不再新增 MUI icon。 |
| `AppHealthOperationsPage.tsx` | `Alert` | HeroUI `Alert` or project state primitive | Preserve `role="alert"` for error and visible info/warning messages。 |
| `AppHealthOperationsPage.tsx` | `Box` | Native `div/section/header` + token classes | Remove `sx` layout and `sectionSx` hard-coded styles。 |
| `AppHealthOperationsPage.tsx` | `CircularProgress` | HeroUI `Spinner` | Refresh button loading indicator must remain visible while disabled。 |
| `AppHealthOperationsPage.tsx` | `IconButton` | HeroUI `Button` with icon-only size | Preserve accessible name `刷新`。 |
| `AppHealthOperationsPage.tsx` | `Stack` | Native flex/grid classes | Preserve page spacing and responsive grids。 |
| `AppHealthOperationsPage.tsx` | `Tooltip` | HeroUI `Tooltip` or native title if behavior remains equivalent | Trigger remains the refresh button。 |
| `AppHealthOperationsPage.tsx` | `Typography` | Semantic headings/text with classes | Preserve heading and generated timestamp text。 |

No AppHealth feature API files are part of this migration unless a test helper type import requires it.

## Already Migrated Surfaces

Phase 5 table pilot already migrated these AppHealth table surfaces to shared `FinanceTable` primitives:

- `InventorySourceRows`: `银行流水来源`、`发票来源`、`OA来源`。
- `RequestPerformance`: `请求性能`。
- `OutboxTable`: `Outbox 状态`。
- `QueueTable`: `RabbitMQ 队列`。
- `ReadModelTable`: `Read Model 刷新`。
- `WorkerTable`: `Worker 心跳`。

Current tests already assert these surfaces as accessible role `grid` with their existing names. Do not regress them to MUI table or card lists.

## User-visible Entrypoints

- Page heading: `AppHealth 运维状态`。
- Generated timestamp below heading; empty or missing payload displays `--`。
- Refresh button: `aria-label="刷新"`，visible in the title row, disabled while loading。
- Loading message: `正在加载。`。
- Permission warning: `当前账号没有管理员权限，不能查看 AppHealth 运维状态。`。
- Error message: dashboard fetch failure text remains visible as `role="alert"` while current dashboard stays visible when available。
- Sections:
  - `data-testid="app-health-data"` with section title `数据`。
  - `data-testid="app-health-requests"` with section title `请求`。
  - `data-testid="app-health-runtime"` with section title `后台`。
- Negative contract: no `app-health-summary` panel, no `app-health-background-jobs`, no `Retry`/`Acknowledge` buttons, and no background-job POST。

## Existing Test Coverage

`web/src/test/AppHealthOperationsPage.test.tsx` covers:

- Admin dashboard render and initial fetch。
- Data/request/runtime sections and accessible grid names。
- Unknown metrics render `--` instead of zero。
- `data-tone` for performance cells。
- Non-admin users are blocked without fetching dashboard data。
- Refresh failure keeps the existing dashboard visible。
- Negative assertions for removed legacy background job controls。

Testing gap for page-level migration:

- Tests do not yet assert AppHealth page shell is no longer MUI-backed。
- Tests do not yet lock refresh button primitive shape beyond accessible name。
- Tests do not yet lock warning/info/error alert primitive class contract away from `.MuiAlert-root`。
- Tests do not yet lock section shell/token classes away from MUI `Box`/`sx`。

## Migration Slices

Recommended Micro-JIT sequence:

1. `P029-phase-6-app-health-characterization-tests`
   - Update `AppHealthOperationsPage.test.tsx` only。
   - Add user-observable and primitive-contract assertions for:
     - refresh button remains named `刷新` and is not `.MuiIconButton-root`。
     - loading/permission/error notices are not `.MuiAlert-root` and keep message semantics。
     - section wrappers use project AppHealth classes, not MUI root classes。
     - existing `FinanceTable` grid assertions remain unchanged。
   - Expected fail is acceptable before implementation if old MUI classes are still present。
2. `P030-phase-6-app-health-page-shell`
   - Migrate `AppHealthOperationsPage.tsx` page shell, sections, inventory summaries, grids, alerts, tooltip, refresh button and spinner from MUI to HeroUI/Tailwind/native classes。
   - Preserve `FinanceTable` surfaces and AppHealth API flow。
   - Add AppHealth-specific token classes to `web/src/app/styles.css` only if shared primitives are insufficient。
3. `MG-phase-6-app-health`
   - Run targeted AppHealth tests, table/common/platform regression tests, build, AppHealth MUI import grep, docs update, exact stage, commit and push。

## Execution Update

- `P028-phase-6-app-health-discovery`: AppHealth page-level MUI inventory、已迁 `FinanceTable` surfaces、用户可见入口和迁移切片已记录。
- `P029-phase-6-app-health-characterization-tests`: updated `AppHealthOperationsPage.test.tsx` to lock AppHealth page shell, refresh button, section and notice primitive contracts away from MUI classes. Targeted test expected-failed with 3 failures because current implementation still lacks `data-testid="app-health-page"` and still renders MUI Alert roots for permission/error notices。
- `P030-phase-6-app-health-page-shell`: migrated AppHealth page shell, header, refresh button, notices, sections, inventory cards and responsive grids from MUI to HeroUI/native token classes. All AppHealth `FinanceTable` grid surfaces and API/permission/refresh behavior are preserved。
- `MG-P030-phase-6-app-health`: pushed `814ad25c` to `refactor-ui`。

## Verification

- `cd web && npx vitest run AppHealthOperationsPage.test.tsx`: passed, 4 tests。
- `cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 19 tests。
- `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning。
- `if rg -n '@mui/' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi`: passed。
- `git diff --check`: passed。

## P030 Prompt Draft

```text
Prompt ID: P030-phase-6-app-health-page-shell
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: 只迁移 AppHealthOperationsPage page-level shell、sections、notices、refresh button 和 inventory summary cards；保留已迁 FinanceTable surfaces。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_app_health.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/AppHealthOperationsPage.tsx、web/src/test/AppHealthOperationsPage.test.tsx、web/src/app/styles.css 和 web/src/components/common/FinanceTable.tsx。使用 HeroUI MCP Alert/Button/Spinner/Tooltip docs 核对 API。把 AppHealthOperationsPage.tsx 从 MUI Alert/Box/CircularProgress/IconButton/Stack/Tooltip/Typography/RefreshIcon 迁到 HeroUI Alert/Button/Spinner/Tooltip、lucide RefreshCw、native semantic elements 和 AppHealth token classes。新增必要 `.app-health-*` CSS classes 到 styles.css。保留 AppHealth API flow、权限判断、刷新 interval、error 保留现有 dashboard、所有 FinanceTable grid names、负向后台任务控制契约。不得改后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run AppHealthOperationsPage.test.tsx`、`cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`、`cd web && npm run build`、`if rg -n '@mui/' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs。
```

## Verification For P028

- `test -f docs/refactor-ui/modules/phase_6_app_health.md`
- `rg -n "P028-phase-6-app-health-discovery|Current MUI Inventory|Already Migrated Surfaces|User-visible Entrypoints|P029-phase-6-app-health-characterization-tests|RefreshIcon" docs/refactor-ui/modules/phase_6_app_health.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
- `git diff --check`
- `git status --short --branch`

## P029 Prompt Draft

```text
Prompt ID: P029-phase-6-app-health-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只调整 AppHealthOperationsPage tests，锁定 page-level HeroUI/native primitive contract；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_app_health.md、docs/refactor-ui/test_migration_strategy.md、web/src/test/AppHealthOperationsPage.test.tsx、web/src/pages/AppHealthOperationsPage.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/app/styles.css。只修改 `web/src/test/AppHealthOperationsPage.test.tsx`，新增或调整断言：刷新按钮仍名为 `刷新` 且不再依赖 `.MuiIconButton-root`；loading、permission 和 error notices 保留语义但不再是 `.MuiAlert-root`；section wrappers 使用 AppHealth/project classes；既有 FinanceTable grid role/name 断言保持。不得修改实现、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run AppHealthOperationsPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P030 AppHealth page shell refactor prompt。
```
