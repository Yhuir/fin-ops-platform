# Prompt 09：搭建 Workbench V2 前端工程骨架

目标：在 `web/` 下建立正式前端工程，为后续工作台和税金抵扣页提供可持续开发的基础。

要求：

- 使用 `Vite + React + TypeScript`
- 建立两个页面路由：
  - `OA & 银行流水 & 进销项发票关联台`
  - `销项票税金 - 进项票税金`
- 建立共享月份上下文
- 保留现有原型文件作为参考，不要删除：
  - `web/prototypes/reconciliation-workbench-v2.html`
- 先用本地 mock 数据渲染页面壳体，不接后端

建议文件：

- `web/package.json`
- `web/src/main.tsx`
- `web/src/app/App.tsx`
- `web/src/app/router.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/app/styles.css`

交付要求：

- 能本地启动页面
- 两个页面可切换
- 顶部月份选择控件存在
- `税金抵扣` 入口存在
- 加入基础测试

验证：

- 运行前端测试
- 启动开发服务器
- 截图或说明两个页面都已能打开
