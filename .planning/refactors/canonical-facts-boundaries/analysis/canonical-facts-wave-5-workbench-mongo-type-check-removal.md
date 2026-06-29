# Canonical Facts Wave 5 - Workbench Mongo type-check removal

日期：2026-06-28

## 目标

减少 `server.py` 对 direct `MongoOAAdapter` 的 production type coupling，防止旧 App Mongo adapter 条件分支继续污染 Workbench canonical facts 链路。

## 删除内容

- `Application._workbench_cache_read_payload_helper()` 不再通过 `isinstance(..., MongoOAAdapter)` 启用旧 Mongo cache gating；生产 app 现在固定使用 non-Mongo cache contract。
- `Application._derived_lifecycle_oa_adapter_cache_executor(...)` 不再要求 adapter 是 `MongoOAAdapter`；只在 adapter 显式暴露 `invalidate_records_cache(...)` 时调用。

## Guard

- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 将 `backend/src/fin_ops_platform/app/server.py` 的 `MongoOAAdapter` baseline 从 6 降到 4。
- `test_workbench_cache_read_payload_helper_extraction_stays_local` 要求 app wiring 使用 `is_mongo_oa_adapter=lambda: False`，禁止恢复 Mongo 类型判断。

## 非闭环项

- `server.py` 仍保留 retained-all OA payload 和 fallback month 的 `MongoOAAdapter` type checks；这些分支与旧 Workbench all-scope Mongo behavior 绑定，需要单独迁移/删除。
- Worker OA sync 仍显式构造 `MongoOAAdapter`，需作为 worker source/admission 边界单独处理。
- 本 slice 没有修改 07-owned read model runtime 文件。
