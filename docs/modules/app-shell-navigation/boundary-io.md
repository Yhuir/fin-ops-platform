# App Shell 与导航模块边界与 I/O

日期：2026-07-22

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：App shell 只负责页面注册、路由、导航、session/runtime context 和全局操作状态，不承载业务页面逻辑。
- 当前缺口：页面业务 freshness 仍由各模块自行实现；shell 只统一提供 active/generation 信号，变更时必须防止 UI 状态污染业务模块。
- 旧代码删除条件：旧路由或 sidebar 配置不再被 App/PageRouteHost 引用。

## 职责边界

### 负责

- 页面注册、路由 host、sidebar/topbar、session context、page runtime context。
- 统一监听页面进入、window focus 与 document hidden→visible，向当前 route owner 提供 `active` 与单调递增的 `activationGeneration`。
- 全局 operation overlay、app health indicator、页面 session state。
- 为页面提供通用壳体，不解释业务数据。

### 不负责

- 不拥有页面业务状态机。
- 不直接调用业务写 API。
- 不决定 read model freshness，只展示来自页面/API 的状态。
- 隐藏状态不缓冲或重放跨页面 domain event，不在 shell 内调用任何业务 load/rebuild API。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Page registry | `pageRegistry.tsx` | 页面 key、route、component、权限元数据 |
| Session payload | session API/context | 只传递权限和身份状态 |
| Browser lifecycle | `focus`、`visibilitychange`、route mount | 只有当前 route 可变为 active；hidden 时 active=false，重新可见/focus 时 generation 递增 |
| Page runtime events | page runtime context | 只传递 page key、active 与 activation generation，不携带业务 DTO |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Route rendering | `PageRouteHost` | 根据 registry 渲染页面 |
| Navigation | sidebar/topbar | 不硬编码业务查询 |
| Runtime context | pages/components | 提供 `{pageKey, active, activationGeneration}`；页面用 generation 触发自己的 freshness/load，排序、分页、筛选不得被误判成页面激活 |

## 持久化与投影

- Own read model：无。
- Worker：无。
- Persistence：仅前端 session/local UI state，例如 page session storage。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| App root | `web/src/app/App.tsx`、`main.tsx` |
| Routing | `web/src/app/pageRegistry.tsx`、`router.tsx`、`PageRouteHost.tsx`、`runtime.ts` |
| Shell components | `web/src/components/shell/AppSidebar.tsx`、`AppTopBar.tsx`、`sidebarItems.ts`、`AppStatusIndicator.tsx` |
| Shell styles | `web/src/app/styles.css` 中 `.app-sidebar-*` 导航样式 |
| Contexts | `GlobalOperationOverlayContext.tsx`、`PageRuntimeContext.tsx`、`PageSessionStateContext.tsx`、`SessionContext.tsx` |
| Hooks | `web/src/hooks/useFinanceTableSession.ts` |
| Tests | `web/src/test/App*.test.*`、`PageRouteHost.test.tsx`、`AppSidebar.test.tsx`、`web/e2e/app-shell*.spec.ts` |

## 依赖方向

- 允许依赖：session API, app health context, page registry。
- 必须通过：registered page metadata。
- 禁止绕过：shell 直接 import 页面 service business logic；sidebar 硬编码权限外业务规则。

## 测试与验证

- `web/src/test/App.test.tsx`
- `web/src/test/PageRouteHost.test.tsx`（17 route owner 注册、hidden 零 I/O、visible/focus 再激活、route mount 单次加载）
- `web/src/test/AppSidebar.test.tsx`
- `web/e2e/app-shell.spec.ts`

## 当前缺口和删除条件

- 新增页面必须同步 page registry、docs/modules、权限和 e2e routing smoke。
