# Canonical Facts 状态机

本模块是资源治理模块，不提供独立页面状态机。状态机只描述业务事实从外部输入进入 PostgreSQL canonical facts，再驱动派生 read model 的通用生命周期。

## 通用事实生命周期

| 状态 | 含义 | 允许进入方式 | 允许离开方式 |
| --- | --- | --- | --- |
| `external_source` | 外部系统、Excel、PDF、ZIP、银行导出或 OA Mongo 中的原始事实 | 外部系统或上传文件提供 | 由 owner import/sync/repair service normalize |
| `candidate` | 已解析但尚未确认写入 canonical facts 的候选事实 | import preview、sync staging、repair dry-run | confirm 写入、reject、expire、repair abort |
| `canonical_committed` | 已由 owner 模块写入 PostgreSQL `app.*` canonical facts | owner command/service/UoW 原子提交 | owner 状态机更新、撤回、作废、修复、迁移 |
| `dirty_declared` | 写入已声明受影响 read model scope、domain event 或 outbox | owner writer 或同事务等价 writer 输出 | worker claim 或 runtime 诊断 |
| `projection_refreshing` | 派生 read model 正在基于 canonical facts 收敛 | runtime worker claim dirty/outbox | fresh、failed、retry |
| `projection_fresh` | 对应 read model 已有 freshness proof | worker 成功发布 readiness/source proof | 后续 canonical write 再次进入 dirty |

## 非法状态

- 非 owner 模块直接写 `app.*` canonical fact 表，但没有 owner command/service/UoW 记录。
- `read_model.*`、Redis、RabbitMQ、frontend domain event 反向成为业务事实源。
- canonical write 成功但未声明应有的 dirty scope、domain event、operation barrier target，且 owner 文档没有说明不适用。
- production API/worker 通过 full snapshot、local pickle、`state:*` JSON、Mongo app snapshot 或 GridFS fallback 补业务事实。
- runtime repair 修改 facts 但没有 dry-run、审计、回滚 manifest 或 owner 认可。

## Owner 模块状态机

各 fact family 的具体状态机不在本文件重复维护。修改事实时必须读取对应 owner 模块状态文档。
