# 服务器 PostgreSQL 运行记录

本文记录 `139.155.5.132` 上 PostgreSQL 新建的实际状态。不要在本文写入任何密码、token、私钥或完整连接串。

## 服务器

- 主机：`139.155.5.132`
- Hostname：`VM-0-6-opencloudos`
- OS：OpenCloudOS 9.4
- 当前用途：现有 OA、MySQL、MongoDB、Redis、Nginx、fin-ops Python 后端同机运行。

## 已完成操作

### 备份目录

已创建：

```text
/data/backups/fin_ops
/data/backups/fin_ops/mongo
/data/backups/fin_ops/postgres
/data/backups/fin_ops/logs
/data/backups/fin_ops/checksums
/data/backups/fin_ops/restore-test
```

目录权限设置为 root-only。

### PostgreSQL 安装

已安装 OpenCloudOS EPOL 源中的 PostgreSQL 16：

```text
postgresql16-16.12-1.oc9.x86_64
postgresql16-contrib-16.12-1.oc9.x86_64
postgresql16-private-libs-16.12-1.oc9.x86_64
postgresql16-server-16.12-1.oc9.x86_64
```

版本：

```text
PostgreSQL 16.12
```

### PostgreSQL 集群

已初始化并启动：

```text
service: postgresql.service
data_directory: /var/lib/pgsql/data
config_file: /var/lib/pgsql/data/postgresql.conf
hba_file: /var/lib/pgsql/data/pg_hba.conf
listen_addresses: localhost
port: 5432
```

监听状态：

```text
127.0.0.1:5432
[::1]:5432
```

当前未开放 PostgreSQL 公网访问。

## 数据库与账号

- 已创建 `fin_ops` 业务数据库，owner 为 `fin_ops_migrator`。
- 已创建 `fin_ops_migrator`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly` 业务账号。
- 已创建 schema：`app`、`read_model`、`job`、`audit`、`staging`。
- 已启用扩展：`pgcrypto`、`pg_trgm`、`btree_gin`。
- 已设置本机 TCP 连接认证为 `scram-sha-256`，`pg_hba.conf` 备份为 `/var/lib/pgsql/data/pg_hba.conf.bak_2026-05-16_014404`。
- 已验证四个业务账号可通过 `127.0.0.1:5432` 连接 `fin_ops`。
- 已验证 `fin_ops_readonly` 不能在 `app` schema 建表。
- 未配置 PostgreSQL PITR。
- 未执行 PostgreSQL 逻辑备份演练。
- 已执行 app Mongo 备份，记录见 `app-mongo-backup-runbook.md`。
- 已执行 app Mongo 恢复演练，恢复到测试库 `fin_ops_platform_app_restore_test_20260516`，collection count 比对 `diff=0`。

## 下一步

1. 建立 PostgreSQL 逻辑备份任务和恢复演练流程。
2. 配置 WAL 归档、PITR 目录和定期恢复演练。
3. 接入 PostgreSQL 监控指标、慢查询日志和磁盘容量告警。
4. 根据实际负载调整 PostgreSQL 参数，初期保持保守配置。
5. 在 Axum/Worker 切换前执行 `production-readiness-checklist.md`。

## 风险

- 该服务器已有多项生产服务，内存和 swap 压力偏高，PostgreSQL 参数应保守配置。
- 当前只有单个 120G 根分区，PostgreSQL data、Mongo 备份、WAL 和对象文件长期同盘存在容量风险。
- MongoDB 监听 `0.0.0.0:27017`，且防火墙开放 `27017/tcp`，需要结合云安全组和访问白名单复核。
