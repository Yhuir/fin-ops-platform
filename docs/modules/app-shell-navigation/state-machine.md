# App Shell 与导航状态机

> 修改 `App Shell 与导航` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

本模块不定义业务事实状态。它只承载 app shell、route、navigation、session gate 和页面轻量 UI state。

- 状态事实源：`pageRegistry.tsx`、`SessionContext`、`PageRuntimeContext`、`PageSessionStateContext`。
- 允许流转：route 匹配后只挂载当前页面；页面离开后卸载；返回页面重新 mount 并通过页面自己的 API/read boundary 重新加载。
- 禁止流转：旧页面隐藏保活、旧页面继续响应 domain event、侧栏维护第二套路由事实、页面 session 保存业务事实或 read model payload。

## Session Gate 状态

| 状态 | 来源 | UI 行为 | 允许流转 |
| --- | --- | --- | --- |
| `loading` | `SessionProvider` 初次请求 `/api/session/me` | 显示 OA 会话校验页；业务 route 不渲染 | authenticated / forbidden / expired / error |
| `authenticated` | `/api/session/me` 成功且 allowed | 渲染 `AppRouter` 和当前业务页面 | 后续 refresh 可进入其他 session 状态 |
| `forbidden` | 当前 OA 账号无访问权限 | 显示无权访问页；业务 route 不渲染 | refresh 后重新判断 |
| `expired` | token invalid/expired | 显示会话失效页；页面 session state 清理当前用户 scope | 用户回 OA 重新登录后 reload |
| `error` | session request timeout/network/error | 显示会话校验失败和重试按钮 | 点击重试回到 loading |

禁止：页面在 `loading/forbidden/expired/error` 时自行绕过 `SessionGate` 调业务 route；前端权限展示不能替代后端 API guard。

## Route 状态

| 状态 | 行为 |
| --- | --- |
| `matched` | `PageRouteHost` 用 `matchPath({ path, end })` 找到 route，提供 `PageRuntimeProvider({ pageKey, active: true, activationGeneration: 1 })`。 |
| `unknown` | 未匹配时 `<Navigate replace to="/" />`。 |
| `mounting` | route component lazy chunk pending，显示 `page-route-loading-<pageKey>`。 |
| `mounted` | 当前页面组件渲染。 |
| `unmounted` | location 切换后旧页面 React tree 卸载；旧页面 local state、effect listener 和 DOM 消失。 |

允许：`matched -> mounting -> mounted`、`mounted -> unmounted -> matched`、`unknown -> /`。

禁止：

- route switch 由 animation timer、hidden frame、mounted cache 或 delayed unmount gate 控制。
- 返回页面时复用旧页面 local React state。
- 旧页面卸载后仍响应 window/domain event。

## Sidebar 状态

| 状态 | 行为 |
| --- | --- |
| desktop expanded | `expanded=true`，显示文字和 icon；宽度 `expandedSidebarWidth`。 |
| desktop collapsed | `expanded=false`，保留文本节点但隐藏 label，icon-only；宽度 `collapsedSidebarWidth`。 |
| compact closed | `isCompact=true` 且 `mobileOpen=false`，侧栏 drawer 关闭。 |
| compact open | top bar 点击“打开菜单”后 `mobileOpen=true`，侧栏 drawer 打开。 |
| active item | 当前 path/search 匹配 item `to`，且 `item.active !== false`。 |
| inactive shortcut | import shortcut 等 `active:false` 项即使路径匹配也不显示 `aria-current`。 |

允许：hover/focus/touch start 调用 `item.preload()`；点击 compact drawer 中的 link 后关闭 drawer 并交给 React Router 导航。

禁止：preload 改变 route、preload 失败阻塞点击、侧栏内部维护独立 route 清单。

## Preload 状态

| 状态 | 行为 |
| --- | --- |
| `idle` | 未触发 preload。 |
| `loading` | hover/focus/touch start 或 route lazy render 调用 loader。 |
| `loaded` | lazy chunk resolve；后续导航可复用 chunk。 |
| `failed` | preload promise reject 被 sidebar catch；当前 UI 不报错、不切 route。真正导航时仍由 React lazy/Suspense/error boundary 处理。 |

## Page Session 状态

| 状态 | 行为 |
| --- | --- |
| `idle` | 无可恢复值，使用 initial value。 |
| `restored` | 从 sessionStorage 或 memory store 恢复。 |
| `invalid` | version/shape/validate 失败，清理旧值并回 initial value。 |
| `expired` | TTL 到期，清理旧值并回 initial value。 |
| `unavailable` | sessionStorage 不可用，回退 memory store。 |

隔离规则：

- key 由 `userScope/pageKey/stateKey` 组成。
- 用户 scope 变化时清理旧用户 prefix。
- session expired 时清理当前用户 scope。
- 可保存轻量 UI state；禁止保存 rows、read model payload、权限事实、业务事实、loading/error/toast 或失败中的提交。

## Domain Event 状态

- `useActivePageEvent` 在当前页面 active 时处理事件。
- 因为当前实现不保留 inactive 页面，route 切换后旧页面 listener 必须通过 unmount cleanup 移除。
- 前端 event 只是同一浏览器会话刷新提示，不是事实源；跨页面一致性必须由后端 dirty scope/read model/worker 保证。

禁止：inactive/已卸载页面延迟 replay 旧事件；前端 event 替代后端 lifecycle。

## Read Model / Worker 状态

本模块不拥有 read model 或 worker。

- `fresh/missing/refreshing/stale/failed/unavailable` 由各页面 API、`ReadModelQueryGateway`、App Status 和具体模块维护。
- shell 只展示 `AppStatusIndicator` 和背景任务提示，不自行推导 read model freshness。
- 路由切换不能把全局 App Status 过滤成当前页面状态，也不能把页面 loading 写入 runtime facts。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐 shell/navigation 状态机 | route、sidebar、session gate、page session、domain event | `cd web && npm test -- --run src/test/PageRouteHost.test.tsx src/test/AppSidebar.test.tsx src/test/PageSessionStateContext.test.tsx src/test/useFinanceTableSession.test.tsx src/test/SessionGate.test.tsx src/test/App.test.tsx src/test/domainEvents.test.ts` |
