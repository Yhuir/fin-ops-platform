# 应用壳与导航

入口：`全局前端入口`。

负责页面注册、按需路由、侧栏、会话与全局任务状态。业务数据和写入归页面模块。

## 边界与 I/O

输入：pageRegistry、当前 route、session allowed_page_keys 和任务摘要。输出：当前页挂载、菜单过滤、标题/焦点、全局操作和任务入口。

## 当前业务约定

- 页面路由使用独立错误边界；懒加载或渲染失败保留侧栏，切换路由清除页面错误。手动“重新加载页面”重新取得入口，不自动刷新或无限重试。
- 预加载及页面异常诊断仅记录构建版本、路由路径、错误类别和静态资源路径，不记录原始异常内容、查询参数或业务值。
- 只挂载当前 route；切换按注册信息更新标题与主内容焦点，菜单可见性不能替代后端授权。
- 页面会话保存非敏感查询/布局，不保存业务事实；现金使用可卸载的局部状态。
- focus、visibility、BFCache 不触发全站业务查询；普通写入不广播隐藏页面刷新。
- 共享导入任务可显式打开独立工作流实例，不覆盖当前未保存草稿；任务轮询复用现有 owner。
- 全局任务入口先关闭运行状态弹层，再由弹层外的稳定宿主展示任务；通知消失不卸载正在查看的详情。列表、详情和预览在同一外层抽屉中切换，关闭界面不取消或结束任务。
- 导入完全成功的结果留在导入页面，不作为全局活动通知反复展示；部分成功、失败、待确认和待复核仍保留入口。只读任务视图支持 Esc/遮罩关闭，提交中禁止关闭，预览保留显式关闭。
- 当前导入页面保留本次提交的任务编号，复用全局任务轮询；任务退出活动列表后按编号读取最终结果，完成后停止读取。结果读取失败明确展示并允许手动重读，不伪造成功、不增加独立轮询。
- 页面默认日期由各模块约定，普通财务列表重新进入清理日期为全部，税金保持业务月，普通刷新保留本次选择。

## 依赖方向

[权限与审计](../permissions-and-audit/README.md)、[后台任务](../runtime-workers/README.md)、[公共财务表格](../finance-table-system/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/app/App.tsx](../../../web/src/app/App.tsx)
- [web/src/contexts/GlobalOperationOverlayContext.tsx](../../../web/src/contexts/GlobalOperationOverlayContext.tsx)
- [web/src/app/pageRegistry.tsx](../../../web/src/app/pageRegistry.tsx)
- [web/src/app/router.tsx](../../../web/src/app/router.tsx)
- [web/src/app/PageRouteErrorBoundary.tsx](../../../web/src/app/PageRouteErrorBoundary.tsx)
- [web/e2e/frontend-release.spec.ts](../../../web/e2e/frontend-release.spec.ts)
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
