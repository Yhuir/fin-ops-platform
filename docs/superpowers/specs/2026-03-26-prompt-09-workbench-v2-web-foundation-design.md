# Prompt 09 Workbench V2 Web Foundation Design

## Goal

在保留现有静态原型的前提下，为 `OA & 银行流水 & 进销项发票关联台` 和 `销项票税金 - 进项票税金` 建立正式前端工程骨架，让后续 `10-15` 可以在 React 工程内持续开发，而不是继续堆叠单文件原型。

## Scope

本次只覆盖以下内容：

- 在 `web/` 下建立 `Vite + React + TypeScript` 前端工程
- 建立两个页面路由：
  - 核销工作台
  - 税金抵扣页
- 建立共享月份上下文
- 用本地 mock 数据渲染页面壳体
- 增加最小前端测试

本次不做：

- 对接后端接口
- 真实导入流程
- 三栏拖拽和复杂动作联调
- 重新设计视觉风格

## Design

### 1. Migration Strategy

`09` 采用“迁移而不是重画”的策略：

- 保留现有 [reconciliation-workbench-v2.html](/Users/yu/Desktop/fin-ops-platform/web/prototypes/reconciliation-workbench-v2.html) 作为参考
- 把已经确认过的页面骨架迁移到 React 组件
- 先建立清晰的组件边界和状态容器
- 后续交互增强和真实接口接入放到后续 prompt

这样可以避免在搭前端工程时重新发散 UI。

### 2. App Structure

正式前端工程按以下边界组织：

- `src/app/`
  - 应用入口
  - 路由
  - 全局样式
- `src/contexts/`
  - 共享月份上下文
- `src/pages/`
  - `ReconciliationWorkbenchPage`
  - `TaxOffsetPage`
- `src/features/`
  - 与页面对应的 mock 数据和轻量 UI 组件

第一版不引入状态管理库，避免为“页面壳体迁移”过度设计。

### 3. Shared Month State

月份选择放到共享上下文中：

- 顶部导航持有月份控件
- 两个页面都消费同一月份值
- 路由切换后月份不丢

这能保证后续工作台和税金页用同一筛选口径。

### 4. Page Boundaries

#### ReconciliationWorkbenchPage

迁移当前原型的基础壳体：

- 顶部标题和页面切换入口
- 月份选择
- 已配对 / 未配对分区
- 三栏表格感布局
- 行内状态标签和基础按钮感

但这一步只做 mock 数据下的结构和视觉，不接真实动作。

#### TaxOffsetPage

迁移税金抵扣页的基础工作台：

- 顶部标题和返回入口
- 月份共享筛选
- 销项票税金 / 进项票税金汇总卡片
- 税金明细表格壳体

它的目标是先成为正式路由页，而不是一次做完税务业务逻辑。

### 5. Testing and Verification

至少覆盖：

- 应用默认能进入工作台页
- 顶部 `税金抵扣` 入口存在并可切页
- 月份选择可更新共享状态
- 工程可构建

## Impact

### New Files

- `web/package.json`
- `web/tsconfig.json`
- `web/tsconfig.node.json`
- `web/vite.config.ts`
- `web/index.html`
- `web/src/main.tsx`
- `web/src/app/App.tsx`
- `web/src/app/router.tsx`
- `web/src/app/styles.css`
- `web/src/contexts/MonthContext.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/test/App.test.tsx`
- `web/src/test/setup.ts`

### Existing Files

- 保留 `web/prototypes/reconciliation-workbench-v2.html`
- 更新 `web/README.md`

## Testing

验证命令目标：

- `npm install`
- `npm run test -- --run`
- `npm run build`
- `npm run dev -- --host 127.0.0.1 --port <port>`

## Follow-up

完成 `09` 之后：

- `10` 继续做三栏尺寸与布局基础
- `11` 补选中态和详情抽屉行为
- `12-15` 再逐步接动作、后端契约和集成测试
