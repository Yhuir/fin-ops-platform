# App Shell 与导航 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- `pageRegistry.tsx` 是 route、sidebar、preload 和 pageKey 的唯一事实源。
- `PageRouteHost` 保持“只挂载当前 route”的策略；旧页面必须卸载，不引入页面保活 frame、TTL/LRU mounted cache 或动画 gate。
- 当前页面永远通过 `PageRuntimeProvider` 暴露 `active: true`；inactive 页面不存在。旧页面不接收事件依赖 React unmount cleanup。
- sidebar preload 只优化 lazy chunk，不改变导航、不阻塞点击、不承载业务数据预取。
- 页面 session state 只保存轻量 UI 状态；业务 facts、read model payload、权限、loading/error/toast 不进入页面 session。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-11 - App Shell 与导航首轮测试闭环

- 目标：完成 app shell/navigation 模块 CodeGraph 审计、测试矩阵、状态机、实施记录和回归测试补强。
- 影响范围：`PageRouteHost`、`pageRegistry`、`AppSidebar`、`App` provider 组合、`SessionGate`、`PageRuntimeContext`、`PageSessionStateContext`、`useFinanceTableSession`、`domainEvents`。
- 关键决策：不改实现；保留当前单页面挂载策略，通过新增测试保护 route unmount cleanup、sidebar active/import shortcut 和 compact drawer close。
- 文档影响：补齐本模块 `README.md`、`tests.md`、`state-machine.md` 和全局 dependency map。
- 测试覆盖：
  - `web/src/test/PageRouteHost.test.tsx` 新增 route unmount 后旧页面 event listener 不再响应的回归测试。
  - `web/src/test/AppSidebar.test.tsx` 新增 nested route active、import shortcut inactive、compact drawer link close 回归测试。
- 验证命令：
  - `cd web && npm test -- --run src/test/PageRouteHost.test.tsx src/test/AppSidebar.test.tsx src/test/PageSessionStateContext.test.tsx src/test/useFinanceTableSession.test.tsx src/test/SessionGate.test.tsx src/test/App.test.tsx src/test/domainEvents.test.ts`
- 未测风险：真实浏览器/OA iframe 视觉、触摸 drawer 手势、真实 chunk 网络失败后浏览器缓存行为仍需发布前 smoke。
- 后续事项：新增页面或修改 provider/route/sidebar 时必须同步 `pageRegistry`、App Status/domain docs 和 route/sidebar tests。
