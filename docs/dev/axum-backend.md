# Axum 后端骨架

本文档说明后端重构阶段 1 新增的 Rust API 骨架。该服务位于 `rust/fin-ops-api/`，是独立 Cargo workspace，不替换、不删除现有 Python 后端。

## 目录

```text
rust/fin-ops-api/
  Cargo.toml
  crates/fin-ops-api/
    Cargo.toml
    src/
      main.rs
      config/
      error.rs
      state.rs
      routes/
      middleware/
      infra/
      services/
      repositories/
      jobs/
      observability/
```

分层边界：

- `routes/`：HTTP 入参、状态码和响应映射。
- `services/`：用例编排和事务边界；当前只包含健康检查编排。
- `repositories/`：后续放 SQLx 查询和事务内读写。
- `jobs/`：后续放 outbox、NATS 发布和 worker 协议。
- `infra/`：PostgreSQL pool，以及 Redis、NATS、S3 client 占位。
- `observability/`：JSON tracing 日志和 Prometheus metrics。
- `config/`：环境变量读取和启动期校验。

## 环境变量

必需：

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 连接串。缺失时服务启动失败。 |

可选：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FIN_OPS_API_BIND_ADDR` | `127.0.0.1:8080` | HTTP 监听地址。 |
| `FIN_OPS_API_REQUEST_TIMEOUT_SECS` | `30` | 请求超时时间。 |
| `FIN_OPS_API_MAX_BODY_BYTES` | `26214400` | 请求体大小上限。 |
| `DATABASE_MAX_CONNECTIONS` | `5` | PostgreSQL pool 最大连接数。 |
| `REDIS_URL` | 空 | Redis client 占位配置。 |
| `NATS_URL` | 空 | NATS client 占位配置。 |
| `S3_ENDPOINT` | 空 | S3/MinIO endpoint 占位配置。 |
| `S3_BUCKET` | 空 | S3/MinIO bucket 占位配置。 |
| `S3_REGION` | 空 | S3 region 占位配置。 |
| `RUST_LOG` | `fin_ops_api=info,tower_http=info` | tracing 过滤器。 |

不要把真实数据库密码、S3 key、token 写入仓库。文档和本地示例只使用占位值。

## 本地检查

需要本机已安装 Rust 工具链：

```bash
cd rust/fin-ops-api
cargo fmt --all --check
cargo check --workspace
```

可选运行测试：

```bash
cd rust/fin-ops-api
cargo test --workspace
```

测试使用 mock readiness probe 或 lazy PostgreSQL pool，不需要连接生产数据库。

## Migration

SQLx migration 位于 `rust/fin-ops-api/migrations/`，按文件名顺序执行。当前 migration 覆盖 PostgreSQL foundation、导入/文件、银行流水、发票、OA 归一化、核销、outbox、staging、read model 和搜索索引。

本地或 CI 有 SQLx 工具后执行：

```bash
cd rust/fin-ops-api
export DATABASE_URL='postgres://fin_ops_migrator:***@127.0.0.1:5432/fin_ops'
sqlx migrate run
```

不要在仓库、日志或 shell history 中保存真实连接串。服务器 PostgreSQL 16.12 已用临时验证库执行过 `0001` 到 `0007`，空库 schema 验证通过；正式迁移仍必须先创建目标月份分区并跑数据 count/hash 校验。

## 本地启动

准备本地或开发 PostgreSQL 后再启动：

```bash
cd rust/fin-ops-api
export DATABASE_URL='postgres://fin_ops_api:***@127.0.0.1:5432/fin_ops'
cargo run -p fin-ops-api
```

将 `***` 替换为本地受控 secret；不要把真实连接串写入仓库。服务默认监听 `127.0.0.1:8080`。

## 健康检查

进程存活检查不依赖数据库：

```bash
curl -s http://127.0.0.1:8080/healthz
```

预期响应：

```json
{"status":"ok","service":"fin-ops-api"}
```

依赖就绪检查会执行 PostgreSQL pool 查询：

```bash
curl -s http://127.0.0.1:8080/readyz
```

PostgreSQL 不可用时返回 `503`，同时保留 Redis、NATS、S3 的分项占位状态。Redis、NATS、S3 当前不是必需依赖，不影响 ready 状态。

Prometheus metrics：

```bash
curl -s http://127.0.0.1:8080/metrics
```

当前暴露基础 HTTP request counter、HTTP duration histogram 和 readiness check counter。后续接入队列、DB pool 和业务指标时继续放在 `observability/metrics.rs`。
