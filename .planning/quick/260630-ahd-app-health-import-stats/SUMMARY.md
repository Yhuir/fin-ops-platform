# App Health 导入统计 GSD 总结

日期：2026-06-30

## 完成内容

- 后端 dashboard inventory 改为从 canonical `app.invoices.source_links` 统计 `手工导入` 和 `OA 解析`。
- `OA 解析` 增加 `supplementary_count`，表示 OA 解析来源且不在手工导入中的发票数。
- 新增 `data_inventory.import_events`，输出流水、手工发票、OA 解析和 OA 单据同步历史。
- 前端 AppHealth 主页面新增最近 5 条导入历史，右侧抽屉展示全量历史。
- 更新 API 合同、模块边界、测试矩阵、运维监控说明和实施记录。

## 验证

- `PYTHONPATH=backend/src python3 -m pytest -q tests/test_operations_dashboard_service.py`
- `PYTHONPATH=backend/src python3 -m pytest -q tests/test_app_health_api.py`
- `cd web && npm test -- --run src/test/AppHealthOperationsPage.test.tsx`

## 风险

- 现有 durable facts 没有单独记录 OA 附件发票 promotion 的 worker-run 批次；历史 OA 解析事件按 canonical source link `created_at` 聚合。若未来需要严格 run-level 口径，应在 promotion 写入时新增专门事件事实。
