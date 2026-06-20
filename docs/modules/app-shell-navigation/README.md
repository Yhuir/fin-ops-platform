# App Shell 与导航模块维护入口

- Module key: `app-shell-navigation`
- 类型: 资源模块
- Route: `N/A`
- Page key: `N/A`

## 修改前必读

- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/modules/permissions-and-audit/README.md`
- `docs/modules/app-health-operations/README.md`
- `docs/modules/domain-events-lifecycle/README.md`
- `docs/refactor-ui/module_inventory.md`

## 代码入口

- `web/src/app/App.tsx`：provider 组合、BrowserRouter、shell layout、compact sidebar、本地 sidebar 展开状态。
- `web/src/contexts/GlobalOperationOverlayContext.tsx`：写操作级全屏 overlay provider；页面通过 hook 包裹 mutating action。
- `web/src/app/pageRegistry.tsx`：页面注册表、route chunks、sidebar groups 的唯一事实源。
- `web/src/app/router.tsx`：把 `appPageRoutes` 交给 `PageRouteHost`。
- `web/src/app/PageRouteHost.tsx`：route match、未知路由 redirect、当前页面挂载、lazy fallback、`PageRuntimeProvider`。
- `web/src/components/shell/AppSidebar.tsx`：桌面/移动侧栏、active route、icon-only collapse、hover/focus/touch preload。
- `web/src/components/shell/sidebarItems.ts`：只重导出 `pageRegistry` 的 `sidebarGroups`，不能维护第二份导航事实。
- `web/src/components/shell/AppTopBar.tsx`：compact top bar 和移动端打开菜单。
- `web/src/contexts/PageRuntimeContext.tsx`：当前页面激活上下文、active page event 订阅。
- `web/src/contexts/PageSessionStateContext.tsx`：用户隔离的页面轻量 session state。
- `web/src/hooks/useFinanceTableSession.ts`：表格分页、排序、选择、滚动位置的页面 session 绑定。

## 当前边界

- 页面注册表是 route、page key、lazy chunk preload 和侧栏导航项的唯一事实源；侧栏不能维护第二份路由清单。
- `PageRouteHost` 每次只挂载当前匹配 route。离开页面会卸载旧页面 React tree，不保留隐藏 DOM frame、mounted cache、TTL/LRU snapshot 或旧页面 data payload。
- `PageRuntimeProvider` 对当前页面提供 `active: true` 和 `pageKey`。inactive 页面不被保留；跨页面事件不 replay 给旧页面，依赖卸载时 listener cleanup。
- `AppPageRoute.preload()` 和 sidebar item `preload()` 只预加载 lazy route chunk。预加载失败不能改变当前 route，也不能阻塞点击导航。
- 页面 session state 只保存当前浏览器标签页内的轻量 UI 状态，例如查询、筛选、分页、排序、tab、选中行、展开行和详情 drawer target；不保存 read model payload、业务事实、权限事实、loading/error/toast 或失败中的提交。
- `SessionGate` 是 shell 级入口。会话 loading/forbidden/expired/error 会阻止业务 route 渲染，但侧栏和全局 shell 仍按现有布局显示。
- `AppStatusIndicator` 在 shell 中消费后端 app status projection；路由切换不能改变全局状态事实。
- `GlobalOperationOverlayProvider` 是 shell 级交互保护层。它只承载写操作后的短暂等待和错误反馈，不保存业务 payload，不决定 freshness，不替代 App Status 或页面 read boundary。页面不得各自实现第二套全屏操作阻塞层。
- import pages 是独立 route，但其侧栏入口设置 `active: false`，避免进入导入页时误把导入入口高亮为当前业务页面。

## 影响面

| 改动点 | 可能影响 |
| --- | --- |
| `pageRegistry.tsx` 新增/删除/改 route | 页面入口、侧栏分组、App Status domain registry、测试里 route/sidebar 数量、未知路由 redirect |
| `PageRouteHost.tsx` route match/mount 策略 | 页面状态清理、domain event listener、旧页面 API 请求和 toast、lazy fallback |
| `AppSidebar.tsx` active/preload/mobile drawer | 侧栏高亮、移动端导航关闭、hover/focus 预加载、导入页 active 行为 |
| `App.tsx` provider 顺序 | session、page session、import draft、background jobs、App Health、MonthProvider |
| `GlobalOperationOverlayContext.tsx` 语义 | 所有接入页面的写操作 loading/error 体验；不能污染普通页面 loading、App Status 或业务事实 |
| `PageSessionStateContext.tsx` key/scope/TTL | 所有页面筛选/分页/排序/选中状态恢复、用户切换隔离 |
| `PageRuntimeContext.tsx` event activation | 跨页面刷新提示、旧页面卸载后的事件清理 |

## 测试入口

- `web/src/test/PageRouteHost.test.tsx`
- `web/src/test/AppSidebar.test.tsx`
- `web/src/test/App.test.tsx`
- `web/src/test/GlobalOperationOverlayContext.test.tsx`
- `web/src/test/SessionGate.test.tsx`
- `web/src/test/PageSessionStateContext.test.tsx`
- `web/src/test/useFinanceTableSession.test.tsx`
- `web/src/test/domainEvents.test.ts`

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护 App Shell 与导航的 Spec-first Browser E2E 合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/Vitest 证据的覆盖矩阵和外部风险。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
