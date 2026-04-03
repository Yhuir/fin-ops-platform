# 关联工作台 V2 前端实现

## 1. 当前实现形态

Workbench V2 已经从单文件原型迁入正式 React 工程：

- `web/src/app/App.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/pages/TaxOffsetPage.tsx`

页面仍保留用户确认过的 Excel 风格工作台，但数据源已经不是 mock，而是统一走前端 API 适配层。

## 2. 前端数据分层

当前前端分成两层：

- 页面 / 组件层：只消费 camelCase 的前端 view-model
- API 适配层：负责请求 `/api/*` 并把后端 snake_case DTO 映射成前端模型

对应文件：

- `web/src/features/workbench/types.ts`
- `web/src/features/workbench/api.ts`
- `web/src/features/tax/types.ts`
- `web/src/features/tax/api.ts`

这样做的目的很直接：

- 不把后端字段格式散落到表格组件
- 不破坏 Prompt 10-13 已经确认的交互组件
- 后续如果后端 DTO 继续演进，只需要收口在 adapter 层

## 3. 工作台页

### 3.1 数据来源

`ReconciliationWorkbenchPage` 当前真实请求：

- `GET /api/workbench?month=YYYY-MM`
- `GET /api/workbench/rows/{row_id}`
- `POST /api/workbench/actions/confirm-link`
- `POST /api/workbench/actions/mark-exception`
- `POST /api/workbench/actions/cancel-link`
- `POST /api/workbench/actions/update-bank-exception`

### 3.2 保留的交互口径

- 点击行只做选中，不自动打开详情
- 同 `caseId` 在整个页面内联动高亮
- `详情` 按钮单独打开右侧抽屉
- splitter 继续按 Prompt 10 的逻辑独立拖拽

### 3.3 详情加载方式

详情抽屉现在是“先开抽屉，再补详情”：

- 点击 `详情`
- 先把当前行设为选中 + 抽屉打开
- 再请求 `GET /api/workbench/rows/{row_id}`
- 请求成功后替换抽屉内容

这样既满足“详情按行加载真实详情”，也避免抽屉打开延迟过重。

### 3.4 行内动作

当前行内动作映射：

- `确认关联` -> `confirm-link`
- `标记异常` -> `mark-exception`
- `取消关联` -> `cancel-link`
- `异常处理` -> `update-bank-exception`
- `关联情况` -> 当前仍是前端状态提示，不单独发接口

`确认关联` 会按当前行的 `caseId` 自动收集同案相关行，一次把 OA / 流水 / 发票一起提交给后端。

## 4. 税金抵扣页

### 4.1 数据来源

`TaxOffsetPage` 当前真实请求：

- `GET /api/tax-offset?month=YYYY-MM`
- `POST /api/tax-offset/calculate`

### 4.2 页面行为

- 进入页面先拉取当月默认数据和默认勾选
- 勾选销项 / 进项票时调用真实计算接口
- 月份切换时重新拉取当月清单并重置为后端默认勾选
- 返回关联台后继续复用全局月份上下文

### 4.3 前端映射策略

后端税金接口的输出 / 输入项字段不完全同构，因此前端统一映射成：

- `invoiceNo`
- `invoiceType`
- `counterparty`
- `issueDate`
- `taxRate`
- `amount`
- `taxAmount`

其中 `amount` 由 `total_with_tax - tax_amount` 推导，保证表格列维持统一展示结构。

## 5. 页面状态

本轮已补三类状态：

- `loading`
- `empty`
- `error`

覆盖范围：

- 工作台页面
- 税金抵扣页面
- 详情抽屉加载状态
- 表格空行

## 6. 本地联调

Vite 开发服务已配置 `/api` 代理：

- 默认目标：`http://127.0.0.1:8001`
- 可通过 `VITE_API_PROXY_TARGET` 覆盖

推荐本地联调顺序：

1. 启动后端：`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --host 127.0.0.1 --port 8001`
2. 启动前端：`cd web && npm run dev -- --host 127.0.0.1 --port 4174`
3. 打开：
   - `/`
   - `/tax-offset`
