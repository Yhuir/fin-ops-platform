# 导入中心模块边界与 I/O

日期：2026-08-09

## 职责边界

- 负责：分页展示已登记导入文件和 canonical 导入批次摘要、刷新当前列表、下载当前预览批次的错误明细、导航到三个正式导入入口。
- 不负责：上传、解析、字段映射、确认、重试、worker 调度、canonical facts 写入或 read model 刷新。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 文件记录分页 | `GET /api/import-facts/files?page&page_size` | 只读摘要，不返回 `raw_payload`、`row_results` 或 `normalized_rows` |
| 批次记录分页 | `GET /api/import-facts/batches?page&page_size` | 只读 canonical 批次摘要 |
| 错误下载 | `GET /imports/batches/{batch_id}/errors.csv` | 仅错误/需复核行，下载名不暴露内部 ID |

## 输出 I/O

- HeroUI/FinanceTable 文件与批次列表、状态、行数、操作人和时间。
- 页面没有写操作、持久化、read model、worker、dirty scope 或 outbox I/O。
- Page Audit 以同一只读 snapshot 组合银行、发票和 ETC 三个既有导入 proof，不建立第二套审计事实。

## 依赖方向与旧代码删除条件

- 只能依赖既有 import facts 查询与三个正式导入 route。
- 禁止重新引入同步导入入口、独立 staging 表、前端拼装 canonical 状态或第二份导入任务状态机。
- 错误 CSV 只属于可读诊断；人工复核仍回到具体导入 session。

## 验证

- `web/src/test/ImportCenterPage.test.tsx`
- `web/src/test/App.test.tsx`
- `tests/test_import_file_api.py`
- `tests/test_page_audit_registry.py`
- `tests/test_operations_audit_report.py`
