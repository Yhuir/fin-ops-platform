# App Shell 与导航模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：App shell 只负责页面注册、路由、导航、session/runtime context 和全局操作状态，不承载业务页面逻辑。
- 当前缺口：部分页面 runtime/freshness/operation barrier 状态通过 shell/context 传播，变更时必须防止 UI 状态污染业务模块。
- 旧代码删除条件：旧路由或 sidebar 配置不再被 App/PageRouteHost 引用。

## 职责边界

### 负责

- 页面注册、路由 host、sidebar/topbar、session context、page runtime context。
- 全局 operation overlay、app health indicator、页面 session state。
- 为页面提供通用壳体，不解释业务数据。

### 不负责

- 不拥有页面业务状态机。
- 不直接调用业务写 API。
- 不决定 read model freshness，只展示来自页面/API 的状态。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Page registry | `pageRegistry.tsx` | 页面 key、route、component、权限元数据 |
| Session payload | session API/context | 只传递权限和身份状态 |
| Page runtime events | page runtime context | 页面级 loading/operation 状态 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Route rendering | `PageRouteHost` | 根据 registry 渲染页面 |
| Navigation | sidebar/topbar | 不硬编码业务查询 |
| Runtime context | pages/components | 只提供 shell 状态 |

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
| Contexts | `GlobalOperationOverlayContext.tsx`、`PageRuntimeContext.tsx`、`PageSessionStateContext.tsx`、`SessionContext.tsx` |
| Hooks | `web/src/hooks/useFinanceTableSession.ts` |
| Tests | `web/src/test/App*.test.*`、`PageRouteHost.test.tsx`、`AppSidebar.test.tsx`、`web/e2e/app-shell*.spec.ts` |

## 依赖方向

- 允许依赖：session API, app health context, page registry。
- 必须通过：registered page metadata。
- 禁止绕过：shell 直接 import 页面 service business logic；sidebar 硬编码权限外业务规则。

## 测试与验证

- `web/src/test/App.test.tsx`
- `web/src/test/PageRouteHost.test.tsx`
- `web/src/test/AppSidebar.test.tsx`
- `web/e2e/app-shell.spec.ts`

## 当前缺口和删除条件

- 新增页面必须同步 page registry、docs/modules、权限和 e2e routing smoke。
