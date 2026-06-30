# App Health 导入统计 GSD 计划

日期：2026-06-30

## 目标

- AppHealth 运维状态主页面展示流水、手工发票、OA 解析、OA 单据同步的每次导入数量。
- 主页面默认只展示最新 5 条导入记录。
- 点击展开后，在右侧抽屉展示所有历史导入记录。
- 发票统计来源只保留 `手工导入` 和 `OA 解析`；`OA 解析` 总数后括号显示不在手工导入中的 OA 解析发票数量。

## 设计边界

- 后端 owner：`OperationsDashboardService`，只读聚合，不新增写操作、worker 或 read model。
- 前端 owner：`AppHealthOperationsPage`，只负责展示后端事实、截取最新 5 条和打开抽屉。
- API owner：`/api/operations/app-health-dashboard`，admin-only，只输出 dashboard 聚合 payload。
- 事实源：
  - 流水/手工发票导入历史：`app.import_batches.success_count`。
  - 发票来源总数：`app.invoices.source_links`。
  - OA 解析导入历史：canonical invoice OA source link created time 聚合。
  - OA 单据同步历史：`app.oa_sync_runs(sync_type='oa_projection').upserted_count`。

## I/O 合同

- 输入：PostgreSQL canonical facts 和 runtime metrics。
- 输出：
  - `data_inventory.invoice.sources = [manual, oa_attachment]`。
  - `oa_attachment.supplementary_count = count(oa_attachment_invoice and not manual_invoice_import)`。
  - `data_inventory.import_events[]` 全量历史记录，每条包含 `source_key`、`label`、`source_name`、`count`、`supplementary_count`、`imported_at`、`status`。
- 降级：发票 inventory 查询失败时保留 `manual` / `oa_attachment` 两个来源但数量为 `null`；导入历史查询失败只返回空历史并加入 `import_events_unknown` warning，不阻断其他总览。

## 验收

- 主页面发票来源不出现 `普通导入` 和 `ETC`。
- `OA 解析` 显示为 `总数（不在手工导入中的数量）`。
- 主页面只展示最新 5 条导入历史；抽屉展示全量历史。
- 后端/API/前端测试覆盖新统计口径、fallback 和交互。
