# Cost Statistics Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans before implementation. Follow this plan in order.

**Goal:** Add a new `成本统计` page to the React app, driven by bank transactions that have linked OA cost fields, with month-level summary, project drill-down, transaction-level detail, and export.

**Architecture:** Build a read-only backend statistics service on top of existing bank transaction, OA mapping, and project-costing data. Expose dedicated `/api/cost-statistics*` endpoints, then add a new React page and route with breadcrumb-style drill-down and current-view export.

**Tech Stack:** Python backend services, existing Mongo persistence, React 18, TypeScript, Vite, Testing Library.

---

## File Map

### Backend

- Create: `backend/src/fin_ops_platform/services/cost_statistics_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py` only if extra indexed read helpers are needed
- Create: `tests/test_cost_statistics_service.py`
- Create: `tests/test_cost_statistics_api.py`

### Frontend

- Create: `web/src/pages/CostStatisticsPage.tsx`
- Create: `web/src/features/cost-statistics/types.ts`
- Create: `web/src/features/cost-statistics/api.ts`
- Create: `web/src/components/cost-statistics/CostStatisticsToolbar.tsx`
- Create: `web/src/components/cost-statistics/CostStatisticsTable.tsx`
- Create: `web/src/components/cost-statistics/CostStatisticsBreadcrumb.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/app/styles.css`
- Create: `web/src/test/CostStatisticsPage.test.tsx`

### Docs

- Modify: `docs/product/银企核销需求.md`
- Modify: `docs/dev/README.md`
- Modify: `docs/dev/project-costing-foundation.md`
- Create: `docs/dev/cost-statistics-workbench.md`
- Modify: `docs/README.md`
- Modify: `README.md`
- Modify: `prompts/README.md`

---

## Task 1: Lock product and data boundary

- [ ] 明确成本统计只以**支出流水**为主数据源
- [ ] 明确只有能取得 `项目名称 / 费用类型 / 费用内容` 的流水才能入统
- [ ] 明确页面是独立路由，不是弹窗
- [ ] 明确下钻链路：月份汇总 -> 项目明细 -> 具体流水

## Task 2: Build backend read model and contracts

- [ ] 为月份汇总写失败测试
- [ ] 为项目明细写失败测试
- [ ] 为具体流水详情写失败测试
- [ ] 实现 `CostStatisticsService`
- [ ] 提供：
  - `GET /api/cost-statistics?month=YYYY-MM`
  - `GET /api/cost-statistics/projects/{project_name}?month=YYYY-MM`
  - `GET /api/cost-statistics/transactions/{transaction_id}`

## Task 3: Add cost statistics page and drill-down

- [ ] 在顶部导航新增 `成本统计`
- [ ] 新增 `/cost-statistics` 页面
- [ ] 复用全局年月上下文
- [ ] 实现月份汇总视图
- [ ] 实现项目明细视图
- [ ] 实现面包屑和返回路径
- [ ] 实现流水详情层

## Task 4: Export and polish

- [ ] 为当前层级增加 `导出`
- [ ] 导出文件名带 `年月 / 层级 / 项目`
- [ ] 补 loading / empty / error
- [ ] 补前后端回归测试

## Task 5: Verify end-to-end

- [ ] 后端单测通过
- [ ] 前端单测通过
- [ ] 前端构建通过
- [ ] 本地手动验证：
  - 能进入页面
  - 能切月份
  - 能下钻
  - 能导出
