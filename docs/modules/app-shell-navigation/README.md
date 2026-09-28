# 应用壳与导航

入口：`全局前端入口`。

负责页面注册、按需路由、侧栏、会话与全局任务状态。业务数据和写入归页面模块。

## 边界与 I/O

输入：pageRegistry、当前 route、session allowed_page_keys 和任务摘要。输出：当前页挂载、菜单过滤、标题/焦点、全局操作和任务入口。

## 当前业务约定

- 只挂载当前 route；切换按注册信息更新标题与主内容焦点，菜单可见性不能替代后端授权。
- 页面会话保存非敏感查询/布局，不保存业务事实；现金使用可卸载的局部状态。
- focus、visibility、BFCache 不触发全站业务查询；普通写入不广播隐藏页面刷新。
- 共享导入任务可显式打开独立工作流实例，不覆盖当前未保存草稿；任务轮询复用现有 owner。
- 页面默认日期由各模块约定，普通财务列表重新进入清理日期为全部，税金保持业务月，普通刷新保留本次选择。

## 依赖方向

[权限与审计](../permissions-and-audit/README.md)、[后台任务](../runtime-workers/README.md)、[公共财务表格](../finance-table-system/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/app/App.tsx](../../../web/src/app/App.tsx)
- [web/src/contexts/GlobalOperationOverlayContext.tsx](../../../web/src/contexts/GlobalOperationOverlayContext.tsx)
- [web/src/app/pageRegistry.tsx](../../../web/src/app/pageRegistry.tsx)
- [web/src/app/router.tsx](../../../web/src/app/router.tsx)
- [web/src/app/PageRouteHost.tsx](../../../web/src/app/PageRouteHost.tsx)
- [web/src/components/shell/AppSidebar.tsx](../../../web/src/components/shell/AppSidebar.tsx)
- [web/src/components/shell/AppSidebarAccount.tsx](../../../web/src/components/shell/AppSidebarAccount.tsx)
- [web/src/components/shell/AppStatusIndicator.tsx](../../../web/src/components/shell/AppStatusIndicator.tsx)
- [web/src/components/shell/sidebarItems.ts](../../../web/src/components/shell/sidebarItems.ts)
- [web/src/components/shell/AppTopBar.tsx](../../../web/src/components/shell/AppTopBar.tsx)
- [web/src/test/PageRouteHost.test.tsx](../../../web/src/test/PageRouteHost.test.tsx)
- [web/src/test/AppSidebar.test.tsx](../../../web/src/test/AppSidebar.test.tsx)
- [web/src/test/App.test.tsx](../../../web/src/test/App.test.tsx)
- [web/src/test/GlobalOperationOverlayContext.test.tsx](../../../web/src/test/GlobalOperationOverlayContext.test.tsx)
- [web/src/test/SessionGate.test.tsx](../../../web/src/test/SessionGate.test.tsx)
- [web/src/test/PageSessionStateContext.test.tsx](../../../web/src/test/PageSessionStateContext.test.tsx)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
