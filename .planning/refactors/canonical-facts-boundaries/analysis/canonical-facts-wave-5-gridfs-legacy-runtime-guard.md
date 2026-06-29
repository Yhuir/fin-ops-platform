# Canonical Facts Wave 5: GridFS Legacy Runtime Guard

日期：2026-06-28

## Slice

验证并锁定 legacy GridFS 只能作为 file-object migration/rollback 工具路径，不能回到普通 API runtime source-of-truth。

## Evidence

- `PostgresStateStore` 默认不自动配置 `LegacyGridFSFileReader`；后续 wave 5 slice 已删除显式 cutover window、`legacy_file_reader` 注入和 `read_import_file("gridfs://...")` fallback。
- `app/server.py` 当前不引用 `LegacyGridFSFileReader`、`GridFSObjectMigrationService` 或 `file_object.gridfs_migration`。
- `app/worker.py` 只在 `--enable-file-object-migration` 分支构造 `LegacyGridFSFileReader` / `GridFSObjectMigrationService` 并注册 `file_object.gridfs_migration` handler。

## Change

- `tests/test_platform_runtime_boundary_guards.py`
  - 新增 `test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime`。
  - 禁止 API server 引用 legacy GridFS source path。
  - 要求 worker GridFS migration 显式受 `--enable-file-object-migration` gate 保护。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime -v
```

结果：通过。

## Closure Note

本 slice 当时未删除运行时代码，因为 `GridFSObjectMigrationService` 仍是允许保留的 migration/rollback path。后续 slice 已删除 PostgreSQL state store 的 GridFS read fallback；最终 closure 仍需要 GridFS migration worker/tool 的删除条件或明确 blocker。
