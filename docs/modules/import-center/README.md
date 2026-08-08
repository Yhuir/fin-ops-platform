# 导入中心 模块维护入口

- Module key: `import-center`
- 类型: 页面模块
- Route: `/imports`
- Page key: `imports.center`

## 代码入口

- `web/src/pages/ImportCenterPage.tsx`
- `web/src/features/imports/api.ts`
- `web/src/features/imports/types.ts`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/operations_audit.py`

## 当前职责

导入中心只读组合现有 `/api/import-facts/files` 与 `/api/import-facts/batches` 分页摘要，并导航到银行流水、普通发票和 ETC 发票三个既有导入工作流。它不解析文件、不确认导入、不持有第二份导入状态。

## 修改前必读

- `docs/product-specs/imports-and-etc.md`
- `docs/modules/imports-bank-transactions/boundary-io.md`
- `docs/modules/imports-invoices/boundary-io.md`
- `docs/modules/imports-etc-invoices/boundary-io.md`
- `docs/modules/app-shell-navigation/boundary-io.md`
