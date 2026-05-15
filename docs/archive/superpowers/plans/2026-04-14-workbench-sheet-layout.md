# Workbench Sheet Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把关联台 `已配对 / 未配对` 两个区域下三栏候选项从 card 风格改成更接近 Excel / sheet 的分割线风格，同时保留现有列、tag、动作和数据语义不变。

**Architecture:** 延续现有 `CandidateGroupGrid -> CandidateGroupCell -> WorkbenchRecordCard` 组件树，不改后端 contract 和 grouped payload。实现重点放在 group 容器、pane slot、record row 三层样式重组，以及“单条撑满、多条分行”的视觉规则。

**Tech Stack:** React、TypeScript、现有 workbench grouped UI、CSS、Vitest + Testing Library。

---

## File Map

### Frontend

- Modify: `web/src/app/styles.css`
- Modify: `web/src/components/workbench/CandidateGroupGrid.tsx`
- Modify: `web/src/components/workbench/CandidateGroupCell.tsx`
- Modify: `web/src/components/workbench/WorkbenchRecordCard.tsx`

### Tests

- Modify: `web/src/test/CandidateGroupGrid.test.tsx`
- Modify: `web/src/test/WorkbenchSelection.test.tsx`
- Modify: `web/src/test/WorkbenchColumns.test.tsx`

### Docs

- Create: `docs/superpowers/specs/2026-04-14-workbench-sheet-layout-design.md`
- Create: `docs/superpowers/plans/2026-04-14-workbench-sheet-layout.md`
- Create: `prompts/53-workbench-sheet-layout-foundation.md`
- Create: `prompts/54-workbench-sheet-layout-states-and-qa.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`

---

## Task 1: 建立 group 级 sheet 容器与轻量分割线基座

- [ ] 写失败测试：候选组不再表现为多张独立 card，而是统一 group band + 轻量分隔
- [ ] 调整 `candidate-group-row / candidate-group-cell / candidate-group-stack / record-card` 的 class 语义
- [ ] 去掉 record 级厚边框、圆角卡片感和悬浮卡片感
- [ ] 建立 group 背景、列间竖线、行间横线的样式基座
- [ ] 跑相关前端测试

## Task 2: 完成“单条撑满 / 多条分行”的 sheet 对齐表达

- [ ] 写失败测试：`1 条 OA + 多条发票` 时单条项会撑满整组高度
- [ ] 保持多条记录继续垂直堆叠，但改成分割线列表视觉
- [ ] 保持空栏提示融入同一组背景，不再像单独空卡片
- [ ] 验证 action column、列宽、滚动轨道与表头继续对齐
- [ ] 跑相关前端测试

## Task 3: 状态兼容、视觉收口与 QA

- [ ] 写失败测试：hover、selected、related、search highlight 在新样式下仍可辨识
- [ ] 调整 action cell 与整行背景联动，不再出现“卡片尾块”视觉
- [ ] 验证 `已配对 / 未配对` 双区样式口径一致
- [ ] 跑前端相关 tests
- [ ] 跑前端 build
