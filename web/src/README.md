# Web Source

前端源码在 `web/src/`。

## 目录

- `app/`：应用入口、路由和全局样式。
- `contexts/`：全局状态，例如 app health 和跨页面广播。
- `pages/`：页面入口。
- `features/`：领域 API client、类型和页面相关模块。
- `components/`：可复用 UI 组件。
- `test/`：前端测试。

## 约定

- 页面 API 调用优先封装到 `features/*/api.ts`。
- 工作台、银行明细、税金、成本统计等页面不把业务事实只存在本地状态。
- 只读权限和写权限的 UI 控制必须和后端权限校验同时存在。

更多说明见 `../../docs/dev/frontend.md`。
