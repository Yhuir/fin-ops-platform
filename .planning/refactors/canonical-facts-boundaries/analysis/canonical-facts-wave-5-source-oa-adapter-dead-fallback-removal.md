# Canonical Facts Wave 5 - Direct OA source adapter dead fallback removal

日期：2026-06-28

## 目标

删除 direct OA Mongo legacy bootstrap builder 移除后留下的 `source_oa_adapter` / `_source_oa_adapter` 兼容状态，避免旧 App Mongo adapter 通过字段复用或 provider 注入回到 production app bootstrap。

## 删除内容

- `Application._initialize_runtime_services(...)` 不再定义 `source_oa_adapter`。
- `Application._initialize_runtime_services(...)` 不再写入 `self._source_oa_adapter`。
- `IntegrationHubService(...)` 不再接收 legacy source adapter 占位。
- `AppSettingsService(...)` 不再从 legacy source adapter 注入 OA import options provider。
- `Application._oa_pending_payment_source_adapter()` 不再读取 `_source_oa_adapter`。

## Guard

- `test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed` 禁止 `_source_oa_adapter` 和 `source_oa_adapter` 回归。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 将 `backend/src/fin_ops_platform/app/server.py` 的 `MongoOAAdapter` baseline 从 8 降到 7。

## 非闭环项

- `MongoOAAdapter` 仍保留在 OA pending payment source adapter 和 worker sync 等外部输入路径中；后续需要继续审计它们是否只通过 owner/admission 边界写入 PostgreSQL canonical facts。
- 本 slice 没有修改 07-owned read model runtime 文件。
