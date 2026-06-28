# Canonical Facts 状态机

本模块是资源治理模块，不提供独立页面状态机。状态机只描述业务事实从外部输入进入 PostgreSQL canonical facts，再通过 direct API、affected diagnostics 和真实后台任务影响页面。

## 通用事实生命周期

| 状态 | 含义 | 允许进入方式 | 允许离开方式 |
| --- | --- | --- | --- |
| `external_source` | 外部系统、Excel、PDF、ZIP、银行导出或 OA Mongo 中的原始事实 | 外部系统或上传文件提供 | 由 owner import/sync/repair service normalize |
| `candidate` | 已解析但尚未确认写入 canonical facts 的候选事实 | import preview、sync staging、repair dry-run | confirm 写入、reject、expire、repair abort |
| `canonical_committed` | 已由 owner 模块写入 PostgreSQL `app.*` canonical facts | owner command/service/UoW 原子提交 | owner 状态机更新、撤回、作废、修复、迁移 |
| `affected_declared` | 写入已返回 affected ids/months/scopes、domain event、job/result 诊断或明确说明不适用 | owner writer 或同事务等价 writer 输出 | 页面 direct refetch、真实后台任务处理或 runtime 诊断 |
| `background_processing` | 真实异步任务正在处理导入、OA sync、文件迁移、matching、cache warmup 或受控修复 | runtime worker claim job/outbox | done、failed、retry |
| `direct_visible` | 页面 direct API 已能从 canonical facts / OA projection / import facts 读取当前业务结果 | 页面 GET、smoke、owner query service 验证 | 后续 canonical write 再次改变事实 |

## 非法状态

- 非 owner 模块直接写 `app.*` canonical fact 表，但没有 owner command/service/UoW 记录。
- `read_model.*`、Redis、RabbitMQ、frontend domain event 反向成为业务事实源。
- canonical write 成功但未声明应有的 affected ids/months/scopes、domain event、job/result diagnostics，且 owner 文档没有说明不适用。
- production API/worker 通过 full snapshot、local pickle、`state:*` JSON、Mongo app snapshot 或 GridFS fallback 补业务事实。
- runtime repair 修改 facts 但没有 dry-run、审计、回滚 manifest 或 owner 认可。

## Owner 模块状态机

各 fact family 的具体状态机不在本文件重复维护。修改以下事实时必须读取对应 owner 模块状态文档：

- `workbench_pair_relations`：`docs/modules/workbench-relations/state-machine.md`
- 导入、发票、银行流水、ETC、OA、税金、往来款、待付款、销项收款等事实：对应 `docs/modules/<owner>/state-machine.md`
- legacy read model 下线清单：`docs/modules/read-models/state-machine.md`
- worker/queue：`docs/modules/runtime-workers/state-machine.md`
