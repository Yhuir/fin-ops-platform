---
status: complete
date: 2026-06-30
---

# Quick Task 260630-rc5 Summary

## 完成内容

- `PendingInvoiceDetailDrawer` 固定三类标题：`流水详情`、`OA 详情`、`发票详情`。
- 移除详情标题栏副标题，避免人名、发票号或 `txn_imported_*` 这类内部 ID 进入标题栏。
- OA 详情改为复用右侧 `PendingInvoiceDrawerFrame`，打印下载按钮保留在抽屉 footer。
- 详情字段渲染前过滤 `id`、`*_id`、relation case、raw JSON、未映射英文内部字段，并映射常见英文字段到中文。
- 收紧待找发票详情抽屉标题栏、详情卡片标题和字段网格间距。
- 新增 PendingInvoices 页面回归测试，覆盖流水、发票、OA 三类详情标题、字段中文化和内部 ID 隐藏。

## 验证

```bash
cd web && npm test -- --run src/test/PendingInvoicesPage.test.tsx
cd web && npm run build
git diff --check -- web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx web/src/app/styles.css web/src/test/PendingInvoicesPage.test.tsx .planning/quick/260630-rc5-ui-id-oa/260630-rc5-PLAN.md
```

## 验证结果

- Vitest：`src/test/PendingInvoicesPage.test.tsx` 23 tests passed。
- Build：通过；保留现有 CSS minify warning 和 chunk size warning。
- Diff whitespace：通过。

## Docs Impact

仅前端展示和布局变更，不改变 API shape、read model、worker、权限、模块边界或业务状态机；模块长期文档不需要更新。

## 未覆盖风险

- 未跑真实浏览器截图/Playwright；布局压缩由组件测试和 build 覆盖，视觉细节仍建议人工看一眼页面。
- 字段映射是本地最小白名单；后端新增未登记英文业务字段时会被隐藏，后续需要按字段补充中文映射。
