# 后端重构迁移路线

## 总原则

这次重构不是一次性替换全部代码，而是按数据和流量风险分阶段切换：

```text
expand -> backfill -> dual write / verify -> switch read -> contract
```

- `expand`：先增加新库、新表、新服务，不破坏旧系统。
- `backfill`：从 Mongo 导出并导入 PostgreSQL，形成可比对数据。
- `dual write / verify`：关键写入同时进入旧路径和新路径，持续比对。
- `switch read`：只切换已经通过校验的读路径。
- `contract`：确认稳定后移除旧路径和旧依赖。

## 阶段 0：冻结目标和基线

### 目标

- 明确 Axum/PostgreSQL 架构、数据边界、迁移策略和验收指标。
- 保留当前 Python 后端作为生产可回滚版本。
- 建立压测和业务数据规模基线。

### 交付物

- 本目录重构文档。
- PostgreSQL 初版 ERD 和 migration。
- Mongo 备份与恢复演练记录。
- 当前生产接口列表和主要页面 P95/P99 基线。

### 验收标准

- 能明确列出每个 Mongo collection 对应的新 PostgreSQL 表或废弃原因。
- 能在 staging 环境完成 Mongo 备份恢复。
- 能在 staging 环境启动 PostgreSQL、Redis、NATS、MinIO。

## 阶段 1：基础设施和骨架服务

### 范围

- 新建 Axum API 服务骨架。
- 接入 PostgreSQL、Redis、NATS、MinIO。
- 接入 tracing、OpenTelemetry、Prometheus。
- 实现健康检查、配置加载、错误模型、认证上下文。

### 验收标准

- `/healthz`、`/readyz` 可以区分进程存活和依赖可用。
- API 启动失败时能明确指出缺失配置。
- 所有请求日志包含 trace id、用户、路径、状态码、耗时。
- Prometheus 暴露 API latency、DB pool、队列发布失败数。

## 阶段 2：PostgreSQL schema 和迁移工具

### 范围

- 建立主 schema、分区策略、索引、审计表、outbox 表。
- 建立 `sqlx migrate` 目录和 CI 校验。
- 建立 Mongo 到 PostgreSQL 的导出、转换、导入工具。

### 验收标准

- migration 可在空库重复执行到最新版本。
- staging 数据迁移后，核心对象数量和金额汇总与 Mongo 一致。
- 关键查询有 `EXPLAIN ANALYZE` 记录，满足初始 P95 目标。

## 阶段 3：文件存储迁移

### 范围

- 新建 MinIO/S3 bucket、版本化、生命周期、访问账号。
- 从 GridFS 迁移原始导入文件和附件。
- PostgreSQL 建立 `file_objects`、`import_files`、`attachment_files`。

### 验收标准

- 每个文件都有 checksum、size、content_type、storage_key。
- 随机抽样文件可从 MinIO/S3 读取并与 GridFS 原始文件 checksum 一致。
- 旧 GridFS 在迁移完成后进入只读归档，不立即删除。

## 阶段 4：导入和解析链路

### 范围

- Axum API 接收导入请求、写入文件元数据、发布解析任务。
- Python Worker 解析 Excel/PDF/OCR，结果写入 PostgreSQL staging 表。
- 用户确认导入后写入正式事实表，并产生 outbox 事件。

### 验收标准

- 导入任务可查询进度、失败原因、重试次数。
- 同一个文件重复提交通过 checksum 和 idempotency key 控制。
- 导入确认、撤回、重放都有审计事件。

## 阶段 5：OA 同步链路

### 范围

- OA Mongo 读取从页面请求路径移出，改为后台同步。
- 同步结果写入 `oa_applications`、`oa_application_items`、`oa_attachments` 等表。
- 同步任务支持增量、水位、重试和人工补偿。

### 验收标准

- OA Mongo 短暂不可用不影响已缓存工作台页面。
- 同步滞后时间可监控。
- 同一 OA 单据多次同步不会产生重复业务事实。

## 阶段 6：核销工作台和 read model

### 范围

- 迁移核销关系、候选匹配、忽略、备注、异常处理。
- 建立按月份增量重建的工作台 read model。
- 建立 `search_index_rows` 支持全局搜索。

### 验收标准

- 单月工作台优先读 read model，不实时拼全量数据。
- 操作一条核销关系只重建受影响月份和相关汇总。
- all-time 视图不阻塞单月操作，必要时走后台聚合。
- 10 万和 100 万级流水/发票数据下的 P95 达到目标。

## 阶段 7：切换、回滚和收尾

### 切换顺序

1. 只读影子查询：Axum 查询 PostgreSQL，但用户仍看旧系统结果。
2. 小范围读切换：内部用户或单个菜单切到 Axum。
3. 写双写：关键写操作同时写旧 Mongo 路径和 PostgreSQL。
4. 全量读切换：前端 API 指向 Axum。
5. 停止旧写路径：旧 Python 后端只保留只读和回滚入口。
6. 归档旧数据：app Mongo 和 GridFS 冻结归档。

### 回滚原则

- 每次切换前必须有 Mongo 和 PostgreSQL 的时间点备份。
- 只要 dual-write 校验失败，不进入下一阶段。
- 切换读流量后发现口径差异，先回滚 API 路由，不手动修生产数据。
- PostgreSQL 写入已经成为事实源后，回滚必须走补偿脚本，不直接恢复旧 Mongo 覆盖新库。

## 压测目标

初始生产目标建议：

| 场景 | 数据规模 | 目标 |
| --- | --- | --- |
| 健康检查 | 不依赖业务数据 | P95 < 20ms |
| 设置读取 | 常规配置 | P95 < 80ms |
| 单月工作台 read model 命中 | 10 万流水/发票 | P95 < 300ms |
| 单月工作台 read model 命中 | 100 万流水/发票 | P95 < 800ms |
| 全局搜索 | 100 万搜索行 | P95 < 500ms |
| 导入确认 | 1 万行文件 | API 提交 < 500ms，后台异步完成 |
| read model 重建 | 单月 10 万行 | 目标 < 60s，后台执行 |

这些目标需要在 staging 压测后修订，不能只按框架 benchmark 判断。

