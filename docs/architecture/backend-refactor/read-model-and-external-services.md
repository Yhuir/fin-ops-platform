# Read Model 与外部服务契约

## 外部服务是否需要模块化

需要。Redis、RabbitMQ、Read Model、PostgreSQL、OA Mongo、MinIO/S3、OA Auth 都必须模块化。

PF-P002 已将 Platform / Ops / Runtime 边界审计固化到 `platform-runtime-boundary-audit.md`。后续模块 prompt 判断外部服务是否可直接调用时，必须先读取该审计文档中的“允许的 platform adapter 调用”和“禁止或可疑的业务层直接调用”。

原因：

- 业务逻辑不应该知道具体 Redis/RabbitMQ/client driver。
- 单元测试必须能 mock 外部服务。
- 外部服务失败不能破坏业务事实正确性。
- 模块边界必须稳定，避免 Python 业务逻辑散落依赖具体外部服务实现。

## PostgreSQL

PostgreSQL 是业务事实源。

规则：

- 写操作必须使用明确 transaction boundary。
- 同一写 usecase 中，facts、audit、dirty scope、outbox 必须同事务提交。
- repository 封装 SQL，业务 usecase 不直接拼 driver 调用。
- 复杂查询必须有索引设计、测试数据和 `EXPLAIN ANALYZE` 记录。
- 旧 `ApplicationStateStore.load()`、full snapshot 和 pickle 不能进入 production API 主路径。

## Read Model

Read Model 不是事实源，而是可重建投影。它服务高频读路径。

适用场景：

- Workbench summary/groups/rows。
- Turnover Ledger rows/groups/export source payload。
- Batch Accounting submitted/unsubmitted projection and Workbench payload。
- Search index。
- Pending invoice rows。
- Bank detail rows。
- Tax offset。
- Cost statistics。
- Invoice usage/collection。

硬规则：

- 写请求只更新 facts 并标记 dirty scope，不在请求线程全量重建。
- Worker 刷新 read model。
- API 只读 active generation 或最后一次稳定投影。
- building/failed generation 不能进入用户读路径。
- stale/missing 时返回 `refreshing`、`stale`、`unavailable` 等明确状态，不伪装 fresh。

## Source Version 和幂等刷新

每个 dirty scope 必须有单调递增的 source version。

Worker 刷新时使用：

```text
(tenant_id, scope_type, scope_key, source_version)
```

判断规则：

- 如果 active generation 的 source version 大于等于当前 event，跳过。
- 如果 event 重复投递，刷新必须幂等。
- 如果旧 event 晚于新 event 到达，不得回滚 active generation。
- scope_type 和 scope_key 必须稳定，不能依赖语言内部对象或 pickle。

## Building / Active Generation

复杂 read model 必须采用 generation 发布。

流程：

1. Worker 创建 building generation。
2. 写入 summary、groups、group rows、rows、metadata。
3. 校验行数、source versions、summary/group/row 一致性。
4. 同一事务切换 building 为 active。
5. 旧 active 标记 superseded 或按保留策略清理。

API 读取规则：

- 只读 active。
- 如果没有 active，返回 refreshing/unavailable。
- 如果新 generation failed，继续读旧 active，并在 App Health 暴露 failed。

## Redis

Redis 只做可再生成数据：

- 短 TTL page cache。
- 热点 query cache。
- pub/sub wakeup。
- 辅助 lock。

规则：

- Redis 不保存最终业务事实。
- Redis 清空不影响正确性。
- cache key 必须包含 source version 或 active generation。
- 不做复杂跨 key 删除保证正确性；优先让旧 key 自然 TTL 过期。
- Redis 不可用时，API 应降级到 PostgreSQL read model。

## RabbitMQ

RabbitMQ 是 transport，不是事实源。

规则：

- 业务事件事实保存在 PostgreSQL outbox。
- RabbitMQ message 只携带 envelope 或可校验 JSON payload。
- 不传 Python 对象、pickle、内存引用或不稳定 repr。
- RabbitMQ 失败时，PostgreSQL outbox/polling worker 可恢复投递。
- DLQ、retry、backlog 必须进入 App Health。

## OA Mongo

OA Mongo 是只读外部源。

规则：

- API 请求路径不直接扫 OA Mongo。
- worker 或工具从 OA Mongo 同步到 PostgreSQL projection。
- app 不写 OA Mongo。
- OA Mongo 不可用时，已有 PostgreSQL projection 继续服务读请求。

## MinIO/S3

文件对象进入对象存储，PostgreSQL 保存 metadata：

- object key。
- checksum。
- size。
- content type。
- migration/verification status。

规则：

- API 读取文件前验证 PostgreSQL metadata。
- GridFS fallback 只允许 migration/shadow/audit/tooling 显式使用。
- 生产请求路径不自动探测 legacy GridFS。

## Auth / Session

Python 模块化后仍需统一鉴权上下文：

- 从 OA token/cookie 解析用户。
- 通过 OA userinfo 和 access control 判断权限。
- 每个写请求必须携带 actor 和 trace id。
- 模块 service 不直接读取 HTTP header；由 app 层注入 auth context。

所有 Python 模块必须复用同一 auth/session 语义，不能在模块内发明新的登录态或权限判断。

## Consistency Checker

生产必须有一致性巡检：

- active generation 是否唯一。
- summary/groups/rows 行数是否一致。
- source_versions 是否覆盖当前 facts。
- dirty scope 是否长时间 pending/processing。
- outbox backlog 是否异常。
- RabbitMQ DLQ 是否增长。
- Redis cache 是否使用过期 generation。

巡检结果进入 App Health 和运维日志。
