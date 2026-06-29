# GSD Debug: 进项发票使用情况漏显跨月关联关系

日期：2026-06-29

## 样本

- 页面症状：`进项发票使用情况` 查询 `南京联升仪表有限公司`，发票 `26322000003919774666` 显示支付状态 `待处理`，OA/流水为空。
- 关联台事实：同一关系组包含 OA `杨丽萍`、银行流水 `南京联升仪表有限公司` 金额 `584.5`、进项发票 `南京联升仪表有限公司` 金额 `584.5`。
- 关键形态：OA/银行流水发生在 `2026-04`，进项发票在 `2026-05`，属于跨月 relation。

## 真实根因

根因在 `workbench_relation` read model 的 scope 行索引合同，不在进项发票使用页面渲染层。

旧实现有两个叠加问题：

1. `WorkbenchRelationSqlProjectionBuilder` 只为当前月份原生对象写 `workbench_relation_rows`。跨月 relation 的 group 虽然能包含 2026-05 发票，但 2026-04 scope 内不一定有该发票 row 索引。
2. `read_model.workbench_relation_rows` 旧 schema 使用 `(tenant_id, row_id)` 全局唯一。一个业务 row 只能属于最后一次重建的 scope，跨月 relation 无法稳定同时服务关联台月份和发票月份。

因此关联台可以看到 group，但进项发票使用情况按发票 row id 读取 relation context 时，可能拿不到该跨月 group，导致该发票仍按未匹配状态展示。

## 修复

- `workbench_relation` 投影改为：每个 scope 保存该 scope 内 relation group 涉及的所有成员 row 索引，而不仅是当前月份原生对象。
- PostgreSQL 迁移 `0077_workbench_relation_rows_scope_unique.sql` 删除旧 `(tenant_id, row_id)` 覆盖约束，新增 `(tenant_id, scope_key, row_id)` scope 内唯一约束。
- 生产 deploy 发现 `0077` 已有早期 checksum；已登记 accepted drift，并新增 `0078_workbench_relation_rows_scope_unique_repair.sql` 作为幂等 forward repair。
- read model upsert 改为 `on conflict (tenant_id, scope_key, row_id)`，避免不同 scope 互相覆盖。
- 文档同步更新 `workbench_relation` 边界、read model 合同和运维回填顺序。

## 验证

- 新增回归：`tests/test_workbench_relation_sql_projection.py::test_rebuild_indexes_cross_month_relation_members_in_current_scope`
- 迁移保护：`tests/test_postgres_migrations.py::test_workbench_relation_rows_are_scope_unique`
- 已运行：
  - `pytest tests/test_workbench_relation_sql_projection.py tests/test_workbench_relation_read_facade.py tests/test_postgres_migrations.py -q`
  - `pytest tests/test_invoice_usage_collection_sql_runtime.py tests/test_input_invoice_usage_api.py tests/test_input_invoice_usage_service.py -q`
  - `pytest tests/test_postgres_repositories_boundaries.py tests/test_read_model_manifest.py tests/test_read_model_architecture_guards.py -q`

## 发布回填要求

迁移只改变约束，不会自动补齐旧 read model 行。生产发布后必须按顺序回填：

1. 重建目标历史月份或 `all` fan-out 的 `workbench_relation` shards。
2. 等 `workbench_relation` fresh 后重建 `invoice_lifecycle`。
3. 再重建 `input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`pending_invoice` 等下游页面 read model。

验证必须以 API/read model fresh 状态和目标样本行展示为准，不能手工改 `read_model.*` 表。
