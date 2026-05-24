# 销项发票收款情况实现计划

日期：2026-05-25

## 目标

实现 `销项发票收款情况` 页面第一阶段：真实只读查询、Sheet6 状态规则抽屉、Sheet7 收据预览抽屉、已出收据空历史契约，并把后续规则落库和正式收据生命周期预留为清晰服务边界。

## 约束

- 一行代表一张正式销项发票。
- 不新增持久化 read model 表，API 返回 read-model-shaped DTO。
- 不保存状态规则，不创建正式收据，不伪造收据历史。
- 页面沿用 `进项发票使用情况` 的 MUI Table 大列/小列模式，不引入新表格库。
- 保留现有未提交改动，只做必要增量合并。

## 实施步骤

1. 后端 TDD
   - 新增 `tests/test_output_invoice_collection_service.py`，覆盖状态优先级、分页筛选排序、收据预览候选选择、无收入流水/红冲退款阻断。
   - 新增 `tests/test_output_invoice_collection_api.py`，覆盖 `/api/output-invoice-collections/*` 路由契约。
   - 实现 `OutputInvoiceCollectionQueryService`、`OutputInvoiceCollectionStatusRuleService`、`OutputInvoiceReceiptPreviewService`。
   - 在 `server.py` 做薄路由接线。

2. 前端 TDD
   - 新增页面测试，覆盖菜单路由、表头筛选/排序、三类工作流抽屉、详情懒加载、无伪历史状态。
   - 新增 `outputInvoiceCollections` API/types 和组件模块。
   - 在 `router.tsx`、`sidebarItems.ts`、测试 mock 中做增量接线。

3. 集成与验证
   - 复查 DTO 命名和前后端字段一致性。
   - 运行聚焦后端测试、聚焦前端测试、前端构建。
   - 如本地服务可用，打开页面检查无横向滚动、抽屉交互和主要空/错误态。

## 完成标准

- 所有新增后端 API 有测试覆盖，并且不依赖 Excel 运行时文件。
- 页面能通过左侧菜单进入并完成查询、筛选、排序、分页和抽屉工作流。
- 收据预览只基于真实收入流水候选，不生成正式收据事实。
- 未实现的二期/三期能力以明确空状态或接口边界表达，不出现假按钮或假数据。
