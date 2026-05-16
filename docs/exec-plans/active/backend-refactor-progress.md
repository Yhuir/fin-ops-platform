# Axum + PostgreSQL 后端重构进度

## 当前决策

- PostgreSQL 不开放公网访问。
- 当前 PostgreSQL 只监听 `localhost:5432`。
- 如果未来 Axum API、Worker 和 PostgreSQL 分机部署，也只允许内网/VPC 访问，并通过防火墙白名单、最小权限账号和 TLS 加固。
- OA 源数据库不纳入备份、导出、恢复、迁移或压测范围。
- 只备份 app 关联 Mongo 数据库 `fin_ops_platform_app`。

## 已完成服务器操作

- 已在 `139.155.5.132` 创建 `/data/backups/fin_ops` 目录结构。
- 已安装 PostgreSQL 16.12。
- 已初始化并启动 `postgresql.service`。
- 已创建 `fin_ops` 数据库。
- 已创建账号：`fin_ops_migrator`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly`。
- 已创建 schema：`app`、`read_model`、`job`、`audit`、`staging`。
- 已启用扩展：`pgcrypto`、`pg_trgm`、`btree_gin`。
- 已将本机 TCP 认证设置为 `scram-sha-256`。
- 已验证四个业务账号可连接。
- 已验证 `fin_ops_readonly` 不能写 `app` schema。

## 已完成 app Mongo 备份

- 备份目录：`/data/backups/fin_ops/2026-05-16_012900`
- 备份文件：`app-mongo-fin_ops_platform_app.archive.gz`
- checksum：`1968e81888dd359ba7d9d8424cdef399744d81a6d5e7305db1f8222404b9422a`
- `mongorestore --dryRun` 已通过。
- 已恢复到测试库 `fin_ops_platform_app_restore_test_20260516`。
- collection count 比对：`total=50 diff=0`。
- GridFS 抽样：`integrity=OK`。

## 已完成子代理任务

- 子代理 A：仓库盘点与契约梳理，输出 `backend-refactor-inventory.md`。
- 子代理 D：PostgreSQL schema 详细设计，输出 `docs/architecture/backend-refactor/postgresql-schema-notes.md`。
- 子代理 G/H：outbox、任务队列、Worker 协议、读模型和搜索设计，输出 `outbox-and-jobs.md` 与 `read-models-and-search.md`。
- 子代理 H：生产就绪、观测、安全、切换和回滚 runbook，输出 `observability-and-alerting.md`、`production-readiness-checklist.md` 与 `cutover-and-rollback-runbook.md`。
- 子代理 E：Axum API 阶段 1 骨架，输出 `rust/fin-ops-api/` 与 `docs/dev/axum-backend.md`。
- 子代理 M1/M2/M3：按模块生成 PostgreSQL SQLx migrations，输出 `rust/fin-ops-api/migrations/0001_foundation.sql` 到 `0007_read_models_search.sql`。

## 已完成 migration 验证

- 已将 `0001` 到 `0007` 复制到服务器临时目录执行 PostgreSQL 16.12 空库验证。
- 验证数据库：临时库，执行完成后已删除。
- 验证结果：全部通过。
- 创建表数量：`38`。
- 验证扩展：`btree_gin`、`pg_trgm`、`pgcrypto`。
- 验证边界：只验证 schema 语法和依赖顺序，不导入生产数据，不访问 OA 源库。

## 下一步

1. 在本机或 CI 安装 Rust 工具链后，执行 `cargo fmt --all --check`、`cargo check --workspace`、`cargo test --workspace`。
2. 实现 migration runner 或接入 SQLx CLI，并在 staging/临时库中重复执行 schema 验证。
3. 实现迁移工具 dry-run：从 app Mongo 备份或恢复测试库导出，写入 PostgreSQL staging 表，并生成 count/hash 校验报告。
4. 在不替换现有 Python 后端的前提下，先迁移低风险只读 API，再迁移导入、工作台和核销写路径。
5. 进入切换前，必须通过 `production-readiness-checklist.md` 和 `cutover-and-rollback-runbook.md`。
