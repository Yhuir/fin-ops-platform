---
quick_id: 260621-ssv
slug: oa-ui
status: in_progress
date: 2026-06-21
---

# 免 OA 流水栏行级银行明细标签

## Objective

修复免 OA 流水批量处理页面右侧流水表缺少银行明细行级标签的问题。用户在展开批次明细时，应能直接看到每条流水来自银行明细的有效标签。

## UI Contract

- 标签显示在右侧流水表的“摘要/用途/备注”单元格内，位于摘要和用途/备注之后。
- 使用现有紧凑 chip 视觉语言，不新增表格列，不改变批次三栏布局。
- 优先展示 `category_label_path`，为空时回退到 `category_primary_label/category_sub_label/category_label/category_code`。
- 多段标签以多个 chip 展示，允许换行，不挤压金额、时间和对方户名单元格。
- 无标签时不渲染标签行，避免用占位文案制造噪音。

## Implementation

1. 在 `NoOaBankBatchPage` 增加行级银行明细标签显示 helper 和渲染。
2. 在 no-OA API client 测试中锁定 detail row 的分类路径映射。
3. 在页面测试中覆盖右侧流水栏展示标签 chip。
4. 更新 no-OA 模块测试矩阵和实施记录。

## Verification

- `cd web && npm test -- --run src/test/NoOaBankBatchApi.test.ts src/test/NoOaBankBatchPage.test.tsx`

## Seven Test Categories

- Business core unit tests: 不适用，本轮不改批次生成、状态流转、金额或提交规则。
- Service-layer tests: 不适用，本轮不改 service orchestration、repository、audit 或 worker。
- API contract tests: 适用，前端 API mapper 测试覆盖 detail row 的银行明细标签字段。
- Read model/cache/background job tests: 不适用，本轮不改 freshness、cache、dirty scope 或 worker。
- Frontend component and interaction tests: 适用，页面测试覆盖流水表行级标签显示。
- End-to-end business-flow integration tests: 不适用，本轮不改跨模块写流程。
- Existing feature regression tests: 适用，通过 no-OA API/page 现有回归保护标签管理、分页、提交/撤回和只读门禁。
