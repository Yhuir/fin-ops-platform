---
status: complete
quick_id: 260630-r4a
date: 2026-06-30
commit: "—"
---

# Quick Task 260630-r4a Summary

## Result

- 重新设计了销项发票收款情况右侧详情抽屉的标题和正文排版。
- 详情标题现在直接显示 `销项发票详情`、`流水详情` 或 `OA详情`，关闭按钮保持在同一行。
- 关联详情只展示中文业务字段；不再渲染 row id、内部 key、英文字段名、关联台证据 JSON 或对象 stringify 结果。

## Files Changed

- `web/src/features/outputInvoiceCollections/api.ts`
- `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx`
- `web/src/app/styles.css`
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx`

## Verification

- `cd web && npm test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx`
- `cd web && npm run build`

Build completed with existing Vite CSS minify/chunk-size warnings; no blocking errors.

## Docs Impact

No long-term docs update needed. This changed frontend presentation only, without changing module boundary, API contract, read model scope, worker, permissions, or business rules.
