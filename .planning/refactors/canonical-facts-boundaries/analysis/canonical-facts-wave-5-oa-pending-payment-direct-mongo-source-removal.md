# Canonical Facts Wave 5 - OA pending payment direct Mongo source removal

日期：2026-06-28

## 目标

删除 `server.py` 中 OA pending payment in-progress projection 直接构造 `MongoOAAdapter` 的旧 source path，避免 API 进程绕过 PostgreSQL OA projection/admission 边界读取 OA Mongo。

## 删除内容

- 删除 `Application._oa_pending_payment_source_adapter()`。
- `server.py` 不再 import 或调用 `load_mongo_oa_settings`。
- `Application._oa_pending_payment_projection()` 默认使用 `self._postgres_oa_projection_repository()`，非 PostgreSQL测试/本地路径才沿用既有 workbench adapter fallback。

## Guard

- `test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed` 现在禁止 `_oa_pending_payment_source_adapter()` 和 `load_mongo_oa_settings` 回归。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 将 `backend/src/fin_ops_platform/app/server.py` 的 `MongoOAAdapter` baseline 从 7 降到 6。
- `test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter` 保留动态 no-construction 断言。
- `tests.test_oa_pending_payment_api` 覆盖 app wiring、auto reconcile、route 和 SQL read-model miss/stale 行为。

## 非闭环项

- `server.py` 仍有 workbench/OA cache 相关 `MongoOAAdapter` type checks；它们属于后续 App Mongo/workbench retained-all cleanup。
- Worker OA sync 仍显式构造 `MongoOAAdapter`，需作为 worker source/admission 边界单独处理。
- 本 slice 没有修改 07-owned read model runtime 文件。
