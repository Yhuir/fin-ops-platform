# Axum + PostgreSQL 目标架构

## 目标

后端重构的目标是把当前 Python HTTP 服务和 Mongo app 状态库，演进为可扩展、可审计、可恢复的生产级财务后端：

- API 层具备高并发、明确超时、结构化日志和统一鉴权。
- 财务核心事实进入 PostgreSQL，支持事务、约束、索引、分区和审计。
- 工作台、搜索、成本统计、税金抵扣等重查询页面使用物化读模型。
- 导入、OA 同步、文件解析、OCR、read model 重建等重任务异步化。
- MongoDB 只作为 OA 原始数据只读源和迁移期数据源。
- 文件从 GridFS 迁入 MinIO/S3，数据库只保存文件元数据。

## 目标拓扑

```text
React 前端
  |
Nginx / TLS / 上传限制 / 静态文件
  |
Axum API
  |
  +-- PostgreSQL 主业务库
  |     +-- 核心事实表
  |     +-- 审计表
  |     +-- outbox_events
  |     +-- read model 表
  |     +-- 搜索表
  |
  +-- Redis
  |     +-- 缓存
  |     +-- 限流
  |     +-- 短期任务进度
  |
  +-- NATS JetStream
  |     +-- 文件解析任务
  |     +-- OA 同步任务
  |     +-- read model 重建任务
  |
  +-- MinIO / S3
  |     +-- 原始导入文件
  |     +-- 附件
  |     +-- 导出文件
  |
  +-- OA Mongo 只读源
        +-- 由同步任务读取，不在页面请求中实时扫描

Python Worker
  |
  +-- 订阅 NATS 任务
  +-- 读取 MinIO/S3 文件
  +-- 处理 Excel/PDF/OCR/OA 附件
  +-- 写回 PostgreSQL
```

## 技术定版

| 层 | 选择 | 说明 |
| --- | --- | --- |
| API | Axum + Tokio | Axum 负责路由、extractor、响应，Tokio 负责异步运行时。 |
| Middleware | Tower | 统一超时、trace id、限流、鉴权、CORS、body limit、压缩。 |
| 数据访问 | SQLx | 手写 SQL 优先，保留编译期或 CI 期查询校验能力。 |
| 迁移 | `sqlx migrate` | 一期用 SQL migration；动态 SQL 生成不是主路径。 |
| 动态查询 | sea-query，可选 | 只用于复杂搜索筛选构造，不作为主 ORM。 |
| 主库 | PostgreSQL 16/17 | 财务事实源、事务、一致性、索引、分区、PITR。 |
| 缓存 | Redis | 只存可再生成数据，不存最终业务事实。 |
| 队列 | NATS JetStream | 跨 Rust/Python Worker，支持持久化、ack、重放。 |
| 可靠投递 | PostgreSQL outbox | 业务事务和事件发布解耦，避免写库成功但任务丢失。 |
| 文件 | MinIO/S3 | 替代 GridFS，支持版本化、生命周期和独立备份。 |
| 日志 | tracing + JSON | 所有请求、任务、DB 慢查询和外部调用带 trace id。 |
| 指标 | OpenTelemetry + Prometheus | API latency、DB pool、任务队列、read model、业务指标。 |

## Axum API 边界

Axum 服务按模块拆分，但先保持一个部署单元：

```text
crates/fin-ops-api/
  src/
    main.rs
    app_state.rs
    config.rs
    error.rs
    middleware/
    routes/
      health.rs
      auth.rs
      imports.rs
      workbench.rs
      reconciliation.rs
      exceptions.rs
      settings.rs
      files.rs
    services/
    repositories/
    jobs/
    observability/
```

核心规则：

- `routes/` 只做 HTTP 入参、鉴权上下文、响应映射。
- `services/` 承载业务用例和事务边界。
- `repositories/` 只封装 SQLx 查询和事务内读写。
- `jobs/` 只负责发布任务和消费内部事件，不直接放业务规则。
- 所有写操作必须携带操作者、trace id、幂等键和审计上下文。

## PostgreSQL 事实源

PostgreSQL 负责以下最终状态：

- 银行流水、发票、OA 单据归一化结果。
- 导入批次、导入文件、解析结果、撤回状态。
- 核销关系、免 OA 批次、异常处理、备注和忽略状态。
- 成本统计、税金抵扣、ETC、往来款等业务事实。
- 文件元数据、对象存储 key、checksum、大小、内容类型。
- 审计日志、任务状态、outbox 事件、read model 版本。

Mongo 迁移后只保留两类用途：

- OA Mongo：只读原始数据源。
- 迁移期 app Mongo：回滚和对账参考，迁移完成后冻结为归档。

## Read Model 与查询路径

页面查询不能实时从所有来源拼全量数据。目标路径：

```text
用户写操作
  -> PostgreSQL 事实表事务提交
  -> outbox_events 写入同一事务
  -> outbox publisher 发布 NATS 消息
  -> worker 重建受影响月份 read model
  -> API 读取 read model
```

关键 read model：

- `workbench_read_models`：工作台月份视图和全局汇总。
- `workbench_rows`：可筛选、可分页、可定位的行级投影。
- `workbench_candidate_matches`：自动匹配候选。
- `search_index_rows`：跨银行流水、发票、OA、项目的统一搜索表。
- `cost_statistics_read_models`：成本统计口径。
- `tax_offset_read_models`：税金抵扣口径。

## Python Worker 边界

Python Worker 保留现有解析能力，但不再承载 HTTP 主入口：

- 读取 MinIO/S3 原始文件。
- 解析 Excel、PDF、OCR、ETC 附件和 OA 附件。
- 输出结构化结果到 PostgreSQL staging 表或结果表。
- 失败时写任务状态、错误码、可重试标记和错误摘要。

Python Worker 不直接修改核销关系等核心业务状态，除非通过明确的服务命令或数据库存储过程边界。

## 生产安全底线

- 所有外部输入都必须验证：文件大小、MIME、扩展名、行数、金额精度、日期范围。
- 金额使用 PostgreSQL `numeric` 和 Rust decimal 类型，不使用 float。
- 数据库账号最小权限：API、migrator、worker、read-only 分开。
- MinIO/S3 bucket 开启版本化和生命周期策略。
- 所有删除采用软删除或可审计删除，除非是明确的临时文件清理。
- 后台任务必须支持 retry、dead-letter、人工重放。
- 生产必须具备 PostgreSQL PITR、MinIO 版本恢复、Mongo 迁移前冷备份。

