# Canonical Facts Wave 5 - Workbench retained-all Mongo fallback removal

日期：2026-06-28

## 目标

删除 `server.py` 中 Workbench retained-all 对 direct `MongoOAAdapter` 的生产分支依赖，避免旧 App Mongo adapter 在月份列表失败时继续按 cutoff 范围扫描源数据。

## 删除内容

- `_workbench_oa_payload_builder()` 不再通过 `isinstance(..., MongoOAAdapter)` 决定是否走 retained-all 分支；retained-all 由明确的 OA retention cutoff 设置触发。
- `_retained_oa_months_for_all_scope(...)` 在 adapter 无法提供 available months 时返回空列表，不再 fallback 到 cutoff month range。
- 删除 `_fallback_retained_oa_months_for_all_scope(...)` 和 `_fallback_retained_oa_end_month()`。

## Guard

- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 将 `backend/src/fin_ops_platform/app/server.py` 的 `MongoOAAdapter` baseline 从 4 降到 2。
- `test_workbench_oa_payload_builder_extraction_stays_local` 要求 retained-all 触发条件来自 OA retention cutoff，不允许恢复 Mongo type check。
- `test_get_api_workbench_all_does_not_fabricate_cutoff_month_range_when_month_listing_errors` 证明月份列表失败时不会虚构 cutoff month range，且错误状态会透出。

## 非闭环项

- `server.py` 仍保留 `MongoOAAdapter` import，用于当前 attachment invoice parser version helper。
- Worker OA sync 仍显式构造 `MongoOAAdapter`，需作为 worker source/admission 边界单独处理。
- 本 slice 没有修改 07-owned read model runtime 文件。
