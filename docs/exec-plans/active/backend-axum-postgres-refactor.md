# Axum + PostgreSQL 后端重构执行计划

## 背景

当前后端是 Python HTTP 服务，生产状态主要在 app Mongo 和 GridFS，OA Mongo 作为只读源。目标是迁移到 Axum API、PostgreSQL 主业务库、Redis、NATS JetStream、Python Worker、MinIO/S3 的生产架构。

架构依据见：

- `../../architecture/backend-refactor/target-architecture.md`
- `../../architecture/backend-refactor/migration-roadmap.md`
- `../../architecture/backend-refactor/data-model-and-read-models.md`
- `../../operations/backend-refactor/mongo-backup.md`
- `../../operations/backend-refactor/postgresql-provisioning.md`
- `../../operations/backend-refactor/mongo-to-postgresql-migration.md`

## 成功标准

- PostgreSQL 成为财务核心事实源。
- MinIO/S3 成为导入文件和附件主存储。
- Axum API 承载主流量。
- Python Worker 只负责文件解析、OCR、OA 附件解析等异步任务。
- OA Mongo 不在页面请求路径中实时扫描。
- 旧 app Mongo 冻结归档，可用于迁移后审计和有限回滚。
- 核心页面在 10 万/100 万级数据下达到压测目标。

## 执行步骤

### 1. 迁移前盘点

- [ ] 导出现有 API 路由、请求体、响应体和前端调用点。
- [ ] 盘点 app Mongo collections、GridFS bucket、文档数量和数据大小。
- [ ] 盘点 OA Mongo 读取集合、字段映射和同步口径。
- [ ] 盘点当前后台任务、导入流程、ETC/OCR/PDF 解析入口。
- [ ] 记录当前生产 P95/P99、慢接口、最大数据规模和失败场景。

### 2. 基础设施

- [ ] 新建 staging PostgreSQL。
- [ ] 新建 staging Redis。
- [ ] 新建 staging NATS JetStream。
- [ ] 新建 staging MinIO/S3 bucket。
- [ ] 建立 PostgreSQL 备份和恢复演练。
- [ ] 建立 app Mongo 备份和 staging 恢复演练。

### 3. Axum 服务骨架

- [ ] 建立 Rust workspace 和 Axum API crate。
- [ ] 接入配置加载、结构化错误、trace id、JSON 响应规范。
- [ ] 接入 SQLx pool、Redis client、NATS client、S3 client。
- [ ] 实现 `/healthz`、`/readyz`、metrics endpoint。
- [ ] 接入 tracing、OpenTelemetry OTLP、Prometheus。

### 4. PostgreSQL schema

- [ ] 建立 `app`、`read_model`、`job`、`audit`、`staging` schema。
- [ ] 建立导入、文件、银行流水、发票、OA 归一化、核销、异常、任务、审计表。
- [ ] 对银行流水、发票、OA、搜索表和工作台行投影建立分区策略。
- [ ] 建立 `pg_trgm`、GIN、组合索引和慢查询验证流程。
- [ ] 在 CI 中执行 `sqlx migrate run` 和 SQLx 查询校验。

### 5. 数据导出和 backfill

- [ ] 在当前 Python 后端补充规范化导出命令，复用现有 `ApplicationStateStore`。
- [ ] 导出 Mongo 业务对象为 NDJSON/CSV 和 manifest。
- [ ] 导出 GridFS 文件 manifest，并上传到 MinIO/S3 staging。
- [ ] 导入 PostgreSQL staging 表。
- [ ] 从 staging 转换到正式事实表。
- [ ] 生成数量、金额、状态、月份、文件 checksum 对账报告。

### 6. 异步任务链路

- [ ] 建立 PostgreSQL outbox。
- [ ] 建立 outbox publisher。
- [ ] 建立 NATS JetStream stream、consumer、dead-letter 策略。
- [ ] 建立 Python Worker 任务协议。
- [ ] 将导入解析、OA 同步、read model 重建改为异步任务。
- [ ] 为任务添加 retry、idempotency、进度、失败摘要和人工重试入口。

### 7. 读模型和搜索

- [ ] 建立 `read_model.workbench_rows` 和 `read_model.workbench_snapshots`。
- [ ] 建立 `read_model.search_index_rows`。
- [ ] 实现单月工作台 read model 重建。
- [ ] 实现 all-time 汇总后台聚合。
- [ ] 实现成本统计、税金抵扣等专题 read model。
- [ ] 对 10 万/100 万数据压测并调整索引。

### 8. API 迁移

- [ ] 迁移健康、设置、权限上下文等低风险 API。
- [ ] 迁移导入历史和文件元数据 API。
- [ ] 迁移单月工作台读 API。
- [ ] 迁移搜索 API。
- [ ] 迁移核销确认、撤销、异常处理等写 API。
- [ ] 迁移数据重置和运维 API。

### 9. 双写、切读和回滚

- [ ] 开启影子读并记录差异。
- [ ] 开启关键写路径双写。
- [ ] 连续通过差异校验后，小流量切读。
- [ ] 全量切读到 Axum。
- [ ] 保留旧 Python 后端和 app Mongo 回滚窗口。
- [ ] 稳定后停止旧写路径，冻结 app Mongo。

### 10. 收尾

- [ ] 删除迁移期兼容开关。
- [ ] 更新生产部署文档、运维 runbook 和恢复流程。
- [ ] 更新开发文档和 API 契约。
- [ ] 归档旧 Python 主入口或保留为离线迁移工具。
- [ ] 完成最终压测报告和上线复盘。

## 阻断条件

- Mongo 备份不能恢复。
- PostgreSQL PITR 没有演练通过。
- 迁移对账存在无法解释的金额差异。
- GridFS 到 MinIO/S3 文件 checksum 校验失败。
- 双写差异没有自动报表。
- 工作台 read model 无法从事实表重建。
- 核销确认、撤销、异常处理没有审计日志。

