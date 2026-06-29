# Canonical Facts Wave 5 - GridFS Production Worker Deletion Blocker

日期：2026-06-29

## 目标

评估是否可以删除剩余 `file_object.gridfs_migration` production worker path。

## 发现

GridFS legacy migration path 仍存在于：

- `backend/src/fin_ops_platform/app/worker.py`
  - `--enable-file-object-migration`
  - `LegacyGridFSFileReader.from_data_dir(...)`
  - `GridFSObjectMigrationService(...)`
  - `handlers["file_object.gridfs_migration"]`
- `deploy/oa/env/fin-ops.worker.file-migration.env.example`
- `deploy/oa/env/fin-ops.worker.file-migration-rabbitmq.env.example`
- `deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example`
- `docs/operations/deployment.md`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
  - `file-migration` worker registration
  - `--enable-file-object-migration`
  - `file_object.gridfs_migration`

## Blocker

`runtime_worker_registry.py` 属于 07 read-model closure 当前只读文件。删除 worker flag、deploy env 和 dispatcher event 时，必须同步删除 registry registration，否则 worker inventory、env examples 和 deployment docs 会不一致。

因此本 slice 标记为：

- `blocked-by-read-model-controller`

## 决策

本线程不半删 GridFS worker path。等 07 controller 停止或用户显式把 `runtime_worker_registry.py` 分配给 08 后，再一次性删除：

- worker parser flag；
- worker handler registration block；
- registry `file-migration` registration；
- file-migration deploy env examples；
- dispatcher default `file_object.gridfs_migration` event；
- deployment/backend docs 的 optional file-migration worker 描述；
- RabbitMQ staging preflight expectation；
- platform runtime boundary guard 从“只允许 gated”改成“生产 worker 不得引用 GridFS migration”。

`verify_file_object_migration.py` 和 `rollback_file_object_migration.py` 已在后续 slice 删除。保留的 `GridFSObjectMigrationService` 仍由 production worker path 引用，不计入 final closure。
