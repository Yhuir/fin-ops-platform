# Workbench Pane Search / Filter / Sort Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 为关联台 `已配对 / 未配对` 两个区域的三栏引入栏级搜索、列级多选筛选和按组时间排序，同时裁剪不需要的列。

**Architecture:** 不新增后端接口，第一阶段直接基于已加载的 grouped payload 在前端派生 `displayGroups`。每个 zone 独立维护搜索、筛选、排序状态，并按“当前栏驱动、整组联动”规则生成三栏显示。

**Tech Stack:** React、TypeScript、现有 `WorkbenchZone / ResizableTriPane / CandidateGroupGrid` 组件树、前端测试基于 Vitest + Testing Library。

---

## File Map

### Frontend

- Modify: `web/src/features/workbench/tableConfig.ts`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/components/workbench/WorkbenchZone.tsx`
- Modify: `web/src/components/workbench/ResizableTriPane.tsx`
- Modify: `web/src/components/workbench/CandidateGroupGrid.tsx`
- Create or modify: `web/src/components/workbench/WorkbenchPaneSearch.tsx`
- Create or modify: `web/src/components/workbench/WorkbenchColumnFilterMenu.tsx`
- Create or modify: `web/src/features/workbench/groupDisplayModel.ts`
- Modify: `web/src/app/styles.css`

### Tests

- Modify: `web/src/test/WorkbenchColumns.test.tsx`
- Modify: `web/src/test/CandidateGroupGrid.test.tsx`
- Modify: `web/src/test/WorkbenchSelection.test.tsx`
- Create or modify: `web/src/test/WorkbenchPaneFilter.test.tsx`

### Docs

- Modify: `docs/product/银企核销需求.md`
- Create: `docs/superpowers/specs/2026-04-08-workbench-pane-search-filter-sort-design.md`
- Create: `docs/superpowers/plans/2026-04-08-workbench-pane-search-filter-sort.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`

---

## Task 1: 建立三栏派生状态与列裁剪底座

- [ ] 写失败测试：OA、银行流水、发票栏按新要求移除列
- [ ] 新增前端 `displayGroups` helper，支持按当前栏命中 group ids 派生三栏显示
- [ ] 在页面层新增 `paired/open` 两套搜索、筛选、排序状态
- [ ] 跑相关前端测试

## Task 2: 完成栏级实时搜索与列级多选筛选

- [ ] 写失败测试：点击搜索 icon 后输入关键词，当前栏只显示命中项，其他栏显示相关整组
- [ ] 写失败测试：列筛选支持多选、全选、清空
- [ ] 每个 zone 一次只开一个搜索框
- [ ] 跑相关前端测试

## Task 3: 完成按组时间排序与 QA 收口

- [ ] 写失败测试：银行流水按时间升降序切换并按组生效
- [ ] 写失败测试：发票按开票日期升降序切换并按组生效
- [ ] 收口 `已配对 / 未配对` 双区行为一致性
- [ ] 跑前端全量 tests
- [ ] 跑前端 build
