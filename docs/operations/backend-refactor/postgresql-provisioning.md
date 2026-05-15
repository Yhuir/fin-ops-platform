# PostgreSQL 服务器新建与生产配置计划

## 目标

在服务器上建立 PostgreSQL 16/17 作为新后端主业务库，满足：

- 可迁移：支持 `sqlx migrate` 管理 schema。
- 可恢复：支持逻辑备份和 PITR。
- 可观测：慢查询、连接池、容量和备份状态可监控。
- 最小权限：API、worker、migrator、readonly 账号分离。
- 可回滚：迁移期不覆盖旧 Mongo，PostgreSQL 可独立重建。

## 环境规划

至少准备三套环境：

| 环境 | 用途 |
| --- | --- |
| dev | 本地和开发联调，可用 Docker Compose。 |
| staging | 迁移演练、压测、恢复演练。 |
| prod | 生产。只允许经过 migration 和变更流程修改。 |

生产服务器建议独立磁盘：

- PostgreSQL data：低延迟 SSD。
- WAL：可与 data 同盘起步，高写入量时拆盘。
- backup：独立磁盘或对象存储。
- logs：独立日志目录，接入集中采集。

## 安装方式

生产优先使用操作系统包或托管数据库。本项目起步可用 Docker Compose 做 staging 演练，但生产不要只依赖单机容器卷而没有 PITR。

Ubuntu 示例：

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib
psql --version
```

如果需要指定 PostgreSQL 16/17，使用官方 PostgreSQL APT 源或云厂商对应版本。安装完成后记录：

```bash
sudo -u postgres psql -c "select version();"
sudo -u postgres psql -c "show data_directory;"
sudo -u postgres psql -c "show config_file;"
sudo -u postgres psql -c "show hba_file;"
```

## 初始化数据库和账号

以下 SQL 在生产执行前必须替换密码，并存入密钥管理系统，不写入 git。

```sql
create role fin_ops_migrator login password 'REPLACE_WITH_SECRET';
create role fin_ops_api login password 'REPLACE_WITH_SECRET';
create role fin_ops_worker login password 'REPLACE_WITH_SECRET';
create role fin_ops_readonly login password 'REPLACE_WITH_SECRET';

create database fin_ops owner fin_ops_migrator encoding 'UTF8';
```

连接到 `fin_ops` 后：

```sql
create schema if not exists app authorization fin_ops_migrator;
create schema if not exists read_model authorization fin_ops_migrator;
create schema if not exists job authorization fin_ops_migrator;
create schema if not exists audit authorization fin_ops_migrator;
create schema if not exists staging authorization fin_ops_migrator;

create extension if not exists pgcrypto;
create extension if not exists pg_trgm;
create extension if not exists btree_gin;

grant usage on schema app, read_model, job, audit, staging to fin_ops_api, fin_ops_worker, fin_ops_readonly;
grant select, insert, update, delete on all tables in schema app, read_model, job, staging to fin_ops_api;
grant select, insert, update, delete on all tables in schema app, read_model, job, staging to fin_ops_worker;
grant insert on all tables in schema audit to fin_ops_api, fin_ops_worker;
grant select on all tables in schema app, read_model, job, audit, staging to fin_ops_readonly;
```

后续 migration 创建新表后，需要默认权限：

```sql
alter default privileges for role fin_ops_migrator in schema app
  grant select, insert, update, delete on tables to fin_ops_api, fin_ops_worker;

alter default privileges for role fin_ops_migrator in schema read_model
  grant select, insert, update, delete on tables to fin_ops_api, fin_ops_worker;

alter default privileges for role fin_ops_migrator in schema job
  grant select, insert, update, delete on tables to fin_ops_api, fin_ops_worker;

alter default privileges for role fin_ops_migrator in schema audit
  grant insert on tables to fin_ops_api, fin_ops_worker;

alter default privileges for role fin_ops_migrator in schema app, read_model, job, audit, staging
  grant select on tables to fin_ops_readonly;
```

## 连接配置

生产建议：

- 只监听内网地址。
- `pg_hba.conf` 只允许应用服务器和运维跳板机。
- 强制 SCRAM 或证书认证。
- 应用侧使用连接池，限制最大连接数。
- API 和 worker 使用不同账号，便于审计和限权。

Axum API 配置示例：

```text
DATABASE_URL=postgres://fin_ops_api:***@postgres.internal:5432/fin_ops
DATABASE_MAX_CONNECTIONS=30
DATABASE_CONNECT_TIMEOUT_SECONDS=5
DATABASE_STATEMENT_TIMEOUT_MS=30000
```

Worker 配置示例：

```text
DATABASE_URL=postgres://fin_ops_worker:***@postgres.internal:5432/fin_ops
```

## 备份和 PITR

生产不能只依赖 `pg_dump`。建议：

- 每日逻辑备份：`pg_dump`，用于表级恢复和迁移验证。
- 持续归档 WAL + base backup：用于 PITR。
- 优先评估 pgBackRest 或 WAL-G 管理备份和 WAL 归档。

逻辑备份示例：

```bash
export PGDATABASE=fin_ops
export PGHOST=postgres.internal
export PGUSER=fin_ops_readonly

pg_dump \
  --format=custom \
  --file="/data/backups/postgres/fin_ops_$(date +%F_%H%M%S).dump" \
  "$PGDATABASE"
```

基础备份示例：

```bash
pg_basebackup \
  --host=postgres.internal \
  --username=replicator \
  --pgdata="/data/backups/postgres/base_$(date +%F_%H%M%S)" \
  --format=tar \
  --gzip \
  --wal-method=stream \
  --progress
```

PITR 需要 WAL 归档。配置前必须先在 staging 演练恢复到指定时间点，再进入生产。

## Migration 执行

Rust 项目使用 `sqlx migrate`：

```bash
export DATABASE_URL='postgres://fin_ops_migrator:***@postgres.internal:5432/fin_ops'
sqlx migrate run
```

原则：

- migration 文件只前进，不修改已发布 migration。
- DDL 变更先在 staging 跑全量迁移。
- 大表变更加锁风险评估，避免生产长时间锁表。
- 数据回填脚本和 schema migration 分开。

## 监控指标

必须接入：

- PostgreSQL up/down。
- 连接数和连接池占用。
- 慢查询数量。
- deadlock 数量。
- replication/WAL archive 延迟。
- 表和索引大小。
- autovacuum 状态。
- backup 最近成功时间。
- API query latency。
- worker 写库失败次数。

## 上线检查表

- [ ] 生产 PostgreSQL 版本、配置文件、data directory 已记录。
- [ ] 数据库账号已分离，密码未提交到 git。
- [ ] `pg_hba.conf` 只允许必要来源。
- [ ] `sqlx migrate run` 在 staging 通过。
- [ ] `pg_dump` 和 PITR 恢复演练通过。
- [ ] Prometheus/Grafana 能看到 PostgreSQL 指标。
- [ ] 应用和 worker 能用各自账号连接。
- [ ] 慢查询日志已启用并可采集。

## 参考资料

- PostgreSQL 17 `pg_basebackup`：https://www.postgresql.org/docs/17/app-pgbasebackup.html
- PostgreSQL 17 PITR：https://www.postgresql.org/docs/17/continuous-archiving.html
- PostgreSQL 当前版本备份与恢复：https://www.postgresql.org/docs/current/backup.html

