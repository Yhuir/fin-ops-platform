# Python-first 后端目标架构

## 当前完成度

本文档已经整理出目标优化后的高层架构：Python-first、模块化、外部服务边界、Read Model consistency、Worker 异步化和可观测性。

但该目标架构仍需要下一步用代码事实校准：

- 真实 API path ownership。
- 真实 handler/service/repository 调用关系。
- 真实 Redis/RabbitMQ/read model 使用点。
- 当前同步全量构建、snapshot fallback 和跨模块耦合点。
- 首批性能热点和优化优先级。

这些事实由 `PF-P001 - Architecture Inventory / Dynamic Call Chain Discovery` 的 Macro-Inventory 产出后，再反向修订本文档。后续每个模块的详细目标设计必须走 Micro-JIT-Planning，不得在全局阶段一次性写完。

## 目标

后端重构目标不是替换语言，而是把现有 Python 后端重构成边界清晰、低耦合、可测试、可观测、可按热点优化的生产架构。

目标状态：

- Python 继续承载默认业务 API。
- 业务模块按领域拆分，每个模块有明确输入、输出、依赖和测试。
- PostgreSQL facts、audit、dirty scope、outbox 和 read model 形成一致的写读闭环。
- Redis、RabbitMQ、OA Mongo、MinIO/S3、PostgreSQL driver 都被平台边界封装。
- Worker、Read Model、SSE、App Health、监控和一致性巡检共同暴露异步系统状态。
- 性能优化在 Python、PostgreSQL、Read Model、Redis、RabbitMQ 和 worker 边界内完成。

## 非目标

- 不做全量 Python 到其他语言的重写。
- 不新建 `backend-go` 作为默认目标系统。
- 不为单个业务模块创建新语言后端。
- 不让前端感知两套业务 API。
- 不把 Redis 或 RabbitMQ 当业务事实源。
- 不在 API 请求热路径读取 app Mongo snapshot、local pickle、full state 或 OA Mongo fallback。
- 不把 Sidecar、服务网格或 Dapr 作为第一阶段默认方案。

## 目标拓扑

```text
React / Vite 前端
  |
  v
Nginx / OA 同域路径 / Trace Header
  |
  v
Python API
  |
  +-- platform/auth：OA token、cookie、权限上下文
  +-- platform/db：PostgreSQL connection、transaction、repository boundary
  +-- platform/cache：Redis cache、wakeup、lock
  +-- platform/queue：PostgreSQL outbox、durable queue、RabbitMQ envelope
  +-- platform/storage：MinIO/S3 object pointer
  +-- platform/observability：trace id、structured log、metrics
  |
  +-- workbench
  +-- turnover-ledger
  +-- batch-accounting
  +-- bankdetail
  +-- invoices
  +-- imports
  +-- tax-cost
  +-- search
  +-- ops

Python Worker
  |
  +-- claim durable queue / consume RabbitMQ envelope
  +-- refresh read model
  +-- sync OA Mongo read-only source into PostgreSQL projection
  +-- parse Excel / PDF / OCR / attachment
  +-- emit App Health and consistency status
```

## 分层边界

当前代码不需要一次性搬成新目录。重构时按模块逐步收敛到以下边界：

```text
backend/src/fin_ops_platform/
  app/
    routes_*        # HTTP request/response mapping
    server.py       # routing assembly only
  domain/
    models.py       # stable domain value objects and enums
  services/
    platform_*      # shared platform ports/adapters where appropriate
    workbench_*     # workbench module
    turnover_*      # turnover ledger module
    batch_accounting* # batch accounting module
    bank_*          # bank detail module
    invoice_*       # invoice module
    imports*        # import module
    tax_* / cost_*  # tax and cost module
    search_*        # search and pending invoice read module
    runtime_*       # queue/cache/runtime boundary
```

规则：

- `app/` 不承载业务计算。
- 模块 service/usecase 可以依赖 domain model 和 platform port。
- 模块之间不得直接 import 对方 usecase 来做写入。
- 跨模块影响通过 facts、outbox、dirty scope、read model 或明确 query service 协作。
- 生产路径不得依赖 legacy full snapshot。

## 外部服务边界

外部服务必须模块化，但模块化首先在 Python 中落地：

| 外部服务 | 当前角色 | 目标边界 |
| --- | --- | --- |
| PostgreSQL | app facts、audit、queue、read model、settings | repository + transaction manager |
| Redis | 短 TTL cache、wakeup、辅助锁 | cache port，Redis 不影响正确性 |
| RabbitMQ | outbox envelope transport | queue transport adapter，业务 payload 以 PostgreSQL outbox 为准 |
| OA Mongo | OA 原始只读源 | worker/tool adapter，只写 PostgreSQL projection |
| MinIO/S3 | 文件对象 | storage port，PostgreSQL 保存 verified pointer |
| OA Auth | token/cookie/userinfo/权限 | auth context service |

单元测试默认 mock 这些边界。集成测试才连接真实 PostgreSQL、Redis、RabbitMQ 或对象存储。

## 性能优化规则

本轮重构只在 Python 系统内优化，不引入新语言后端。

优化顺序：

1. SQL/index/read model 优化。
2. Python 模块边界和算法复杂度优化。
3. Worker 异步化和 cache key 版本化。
4. 批处理、并发控制、后台预热和 worker lag 限流。
5. 如果仍不达标，先回到架构评审重新评估业务口径、数据模型和缓存策略；不得直接创建新语言后端。

## Sidecar 取舍

第一阶段不引入 Sidecar。只有出现以下证据时才重新评估：

- 多语言服务数量明显增加，Nginx/path routing 难以治理。
- 需要统一 mTLS、服务发现、熔断、限流或灰度策略。
- 多服务东西向流量复杂到影响排障和可靠性。

否则，Sidecar 会增加运维复杂度和网络跳数，不应作为性能优化默认方案。

## 生产安全底线

- 金额使用 PostgreSQL `numeric` 和 Python decimal，不使用 float。
- 所有写操作携带 actor、trace id、幂等键和审计上下文。
- 所有外部输入校验文件大小、MIME、扩展名、行数、金额精度、日期范围。
- Redis 清空不影响业务正确性。
- RabbitMQ 停止时可以回退到 PostgreSQL polling worker。
- Read Model miss/stale 不允许同步全量重算阻塞用户请求。
- Consistency checker 和 App Health 必须暴露 stale scope、failed generation、worker lag 和 outbox backlog。
