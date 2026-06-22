# 数据安全与重置 模块维护入口

- Module key: `data-safety-reset`
- 类型: 跨模块安全边界
- Route: `/settings` 内的数据重置入口；后端 `/api/workbench/settings/data-reset*`
- Page key: `settings.data-reset`

## 修改前必读

- `docs/operations/data-safety.md`
- `docs/operations/postgresql-runtime.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/references/postgresql-migration-history.md`
- `docs/modules/settings/README.md`
- `docs/modules/settings/state-machine.md`
- `docs/modules/app-health-operations/README.md`
- `docs/modules/permissions-and-audit/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/runtime-workers/README.md`

## 代码入口

- 后端 service：`backend/src/fin_ops_platform/services/settings_data_reset_service.py`
- 后端 route/job：`backend/src/fin_ops_platform/app/server.py`
  - `POST /api/workbench/settings/data-reset`
  - `POST /api/workbench/settings/data-reset/jobs`
  - `GET /api/workbench/settings/data-reset/jobs/active`
  - `GET /api/workbench/settings/data-reset/jobs/{job_id}`
- 后台任务：`BackgroundJobService` 的 `settings_data_reset` job
- 派生数据：`Application._execute_derived_data_lifecycle_event("settings_reset_completed", include_all=True, ...)`
- 前端入口：`web/src/pages/SettingsPage.tsx`、`web/src/components/workbench/SettingsDataResetDialogs.tsx`
- 共享状态提示：`web/src/components/shell/AppStatusIndicator.tsx`、`web/src/pages/AppHealthOperationsPage.tsx`
- 备份/导出参考：`tests/test_export_app_mongo.py`、`scripts/reset_demo_db.sh`

## 当前边界

本模块维护“危险数据操作”的安全闭环，不替代各业务模块的业务口径。当前可执行数据重置动作包括：

| 动作 | 主要删除/清理 | 必须保留或保护 | 主要 fan-out |
| --- | --- | --- | --- |
| `reset_bank_transactions` | 银行流水导入、银行相关 workbench/matching/read model 状态、银行导入文件 | 发票事实、`form_data_db.form_data`、app settings、import metadata | 银行明细、关联台、往来款、成本、search、App Status |
| `reset_invoices` | 进/销项发票导入、税金认证记录、发票相关 workbench/matching/read model 状态、发票导入文件、指向被删除发票的 active ETC batch invoice links | 银行流水事实、OA 源数据、ETC 源 metadata/附件审计、app settings、import metadata | 待找发票、税金、进项/销项/OA 待付款、成本、关联台、ETC summary link backfill、App Status |
| `reset_oa_and_rebuild` | OA 衍生 workbench override/relation/read model，随后按保留策略重建 OA 投影和匹配 | 纯银行+发票关系、OA 附件发票解析缓存、受保护目标 | OA 待付款、进项使用、关联台、ETC、成本、search、App Status |

受保护目标由 `SettingsDataResetService.protected_targets()` 统一暴露，目前包括：

- `form_data_db.form_data`
- `fin_ops_platform_app.app_settings`
- `fin_ops_platform_app.*_meta`
- `fin_ops_platform_app.import_file_metadata`

## 影响面

每次改本模块都要先列出影响面，不能只看设置页：

- 权限和身份：必须是管理员；重置前必须校验当前 OA 密码；响应和 job payload 不得回显密码。
- 数据事实：PostgreSQL app facts 是主事实源；OA Mongo 只读；旧 app Mongo 只作迁移/审计参考，不能覆盖 PostgreSQL。
- 发票事实：`app.invoices` 是唯一 canonical 发票池；`app.etc_batch_invoice_links` 是 ETC 批次到 canonical invoice 的关系事实；`app.etc_invoices` 只保留 ETC ZIP/PDF/XML 源 metadata、附件和审计。`reset_invoices` 不能留下指向旧 invoice id 的 active link，重导后必须通过 dry-run/backfill 恢复有效 link 再刷新关联台。
- 文件/对象：导入文件删除必须和 state store 清理一致；失败要保留可诊断 job 状态。
- Read model/cache：重置后不能把旧 read model 或 Redis cache 显示为 fresh。
- Worker/job：后台 job 必须可恢复进度、可查询 active、失败进入 App Health attention。
- 派生生命周期：`settings_reset_completed` 必须 fan-out 到受影响 read model/worker。
- 旧页面：银行明细、关联台、待找发票、税金、进项使用、销项收款、OA 待付款、成本统计、往来款、ETC、导入中心和 App Health 都可能被影响。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 新增、删除或改变 data reset action。
- 修改 `protected_targets`、删除目标、文件清理、备份/导出策略。
- 修改管理员权限、OA 密码校验、错误码、job payload 或 active job 语义。
- 修改 `settings_reset_completed` lifecycle、read model dirty scope、cache/worker/App Health 行为。
- 修改 Settings 页重置确认、密码弹窗、进度恢复、错误提示或权限显示。
- 线上或手工发现任何数据重置、备份、恢复、缓存 stale、worker drain 相关 bug。

## 本目录文件

- `state-machine.md`：维护重置、密码校验、job、protected target、read model/worker 状态。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
