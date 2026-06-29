# Canonical Facts Wave 5 - Parser version Mongo dependency removal

日期：2026-06-28

## 目标

删除 app/server 和 SQL projection 中 parser-version-only 的 `MongoOAAdapter` 依赖，让 attachment invoice parser version 由独立 cache module 提供，而不是通过 direct OA Mongo adapter class 暴露。

## 删除内容

- `server.py` 不再 import `MongoOAAdapter`；`_current_oa_attachment_invoice_parser_version()` 直接调用 `attachment_invoice_cache_parser_version()`.
- `workbench_sql_projection.py`、`workbench_relation_sql_projection.py`、`search_pending_sql_projection.py`、`cost_tax_sql_projection.py` 不再 import `MongoOAAdapter` 读取 parser version。
- `test_oa_mongo_adapter_direct_use_is_allowlisted` 收紧 allowlist：移除 `server.py`、Workbench/Search/Cost/Tax SQL projection 的 parser-version-only 旧依赖。

## Guard

- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 将 `backend/src/fin_ops_platform/app/server.py` 的 `MongoOAAdapter` baseline 从 2 降到 0。
- `test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter` 改为断言 `server_module` 不再暴露 `MongoOAAdapter`。

## 非闭环项

- `app/worker.py` 仍显式构造 `MongoOAAdapter` 作为 OA sync external source，需要作为 worker source/admission 边界单独处理。
- 本 slice 没有修改 07-owned read model runtime 文件。
