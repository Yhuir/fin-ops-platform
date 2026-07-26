# 运行时调用链与模块归属

本文维护当前 app 的运行时序、read model/worker 边界和模块 owner。它回答“请求如何到达事实源”“页面访问如何收敛派生数据”“哪个模块负责维护某类事实”。

PostgreSQL 业务唯一真相的全局 owner matrix 见 `../architecture/module-boundaries/canonical-facts.md`。本文描述运行链路；具体 canonical fact family 的写入口、读入口和禁止路径以 canonical facts 合同和对应业务模块 `boundary-io.md` 为准。

## 总体调用链

```mermaid
flowchart LR
  UI["React pages"] --> API["Flask routes"]
  API --> Service["Application / domain services"]
  Service --> Repo["Repositories / SQL stores"]
  Repo --> PG["PostgreSQL"]
  Service -. "explicit integration/reset/repair only" .-> Lifecycle["DerivedDataLifecycleService"]
  Lifecycle --> Queue["RuntimeQueueRepository"]
  Queue --> Outbox["job.outbox_events / job.read_model_dirty_scopes"]
  Worker["Runtime workers"] --> Outbox
  Worker --> Projection["SQL read models"]
  UI --> Gateway["ReadModelQueryGateway"]
  Gateway --> Projection
  Gateway --> Queue
```

## 读请求

1. 页面调用 `web/src/features/*/api.ts`。
2. Flask route 完成 HTTP 参数解析、权限映射和响应 shape。
3. 查询型 service 或 `ReadModelQueryGateway` 带着 expected schema/source contract 判断 read model 是否 fresh。
4. fresh 必须同时满足 expected contract、actual projection metadata、dirty/readiness 状态；缺少 expected contract 或 actual schema/source proof 时不能标 fresh。
5. fresh 时读取 SQL projection 或 repository；stale/missing/schema/source mismatch 时返回状态并按需 enqueue refresh。
6. 页面根据 `read_model_status`、`refreshing`、`stale`、`job` 等字段展示加载、刷新或不可用状态。

页面不能自行假设 read model fresh，也不能为了“有数据”绕过 freshness gate。

### 批量账务读路径

`/api/batch-accounting` 不拥有或读取 read model。它的读边界是 `BatchAccountingApiRoutes -> BatchAccountingService -> PostgresBatchAccountingQueryRepository`：

1. `unsubmitted` 直接分页查询指定年份的 canonical 批量账务银行候选和不限年份的已完成日常报销 OA；OA 必须没有包含银行成员的 active relation，已有 invoice-only relation不排除。
2. 当前 OA page 的附件发票只按 OA IDs 批量读取；禁止全量附件扫描。
3. `submitted` 只读 `app.workbench_pair_relations` 中 active、`relation_mode=batch_accounting` 且包含指定年份 canonical 银行成员的关系，再按当前页 member IDs 一次批量补齐 OA/发票详情。
4. rows、summary、counts 和 pagination 在同一个显式 `REPEATABLE READ / READ ONLY` snapshot 中得到。银行/OA 服务端分页；禁止 Workbench full payload、12 月循环、逐 scope proof、N+1 或 Python/浏览器全量分页。
5. submit 的 `bank_row_id + oa_row_ids` 上下文也走页面专属窄 canonical snapshot；正式写入和 withdraw 继续交给 `WorkbenchRelationCommandService`。缺 query repository 或 command service 时 fail closed。
6. 响应不再包含 read-model status/source-version/refresh enqueue/polling/operation barrier 字段。

## OA 会话启动边界

React 启动时由 `SessionProvider` 调用 `fetchSessionMe()`，通过 `SessionGate` 决定是否渲染业务路由。该请求属于应用 bootstrap 边界，不是页面级 loading：

- 前端 `fetchSessionMe()` 必须使用 `apiRequestJson(..., { timeoutMs })` 设置明确 deadline；请求挂起时进入 `error` 状态并提供 `SessionProvider.refresh()` 重试入口，不能无限停留在“正在验证 OA 会话”。
- 后端 `/api/session/me` 只做 HTTP mapping、错误码映射和 `resolve_oa_request_session(...)` 调用；OA 身份查询仍由 `OAIdentityService` 按 `FIN_OPS_OA_REQUEST_TIMEOUT_MS` 控制外部服务超时。
- `/api/oa-pending-payments*` 已由模块 route 的显式 read-session/write-auth ports 完整执行权限门，因此 global dispatcher 不再对该路径树重复解析同一 session；所有其它受保护页面继续经过原 global guard。该例外只去重 I/O，不缓存 identity、不改变共享权限策略或错误语义。
- 会话失败不能伪装成 read model fresh，也不写 facts、audit、dirty scope、outbox 或 read model。全局 App Status 可以把 session 不可用展示为 blocked/red，但页面本地不能改写后端 runtime facts。
- retry 只重新执行 session bootstrap；不会清理轻量页面 session state，除非返回的新用户 scope 或 session generation 触发前端缓存隔离规则。

## 写请求

1. Route 只做 HTTP contract、auth/permission、依赖组装和错误映射。
2. Application/domain service 校验业务规则，调用 repository 做原子写入。
3. 普通写只提交 owner canonical facts、可比较 source version、审计/idempotency 与必要领域任务；返回精确 affected scopes 作为信息，不产生页面 dirty/outbox。
4. API 返回写入结果、受影响月份/对象和版本；普通写的 `freshness_targets`、`operation_barrier_targets` 为空，不等待任何未访问页面重建。
5. 当前页可以在成功后重新执行自己的普通 GET；其它已打开、未访问或 hidden 页面不执行 I/O。
6. route 进入/重进、页面查询变化、浏览器手动刷新或用户明确重试时，页面 query owner 比较 expected/actual source versions。只有 missing/stale 的当前精确 scope 经 `ReadModelRefreshGateway` 入 durable queue，worker 异步重建 projection，页面有界、可取消地轮询。

authoritative integration snapshot 默认同样只提交 canonical facts/source version；当前 OA sync 不主动入队页面 refresh。只有 data reset、repair/backfill/reapply 和人工 maintenance 可按已登记合同主动入队；它们必须被标记为 batch/full-history，经过 scope policy/gateway，并与普通用户写严格区分。`DerivedDataLifecycleService` 只服务管理员 settings reset 与历史 ETC repair，不是普通写后的默认分发器。

写模型、权限认证、冲突校验不做“分发 read model”；它们保留明确 command/service 边界。

任何写入 PostgreSQL canonical facts 的路径，都必须先落到 `../architecture/module-boundaries/canonical-facts.md` 登记的 owner 模块。非 owner 模块只能通过 owner service、facade、UoW 或明确 adapter 发起写入；不能把 `read_model.*`、Redis、RabbitMQ 或前端事件反向当作业务事实。

### 写操作后的页面闭环

用户触发确认关联、撤回、异常处理、规则保存、导入确认、批量账务或往来款闭环等普通写操作时：

1. 写 API 成功代表 canonical write、version、audit/idempotency 已提交，并返回 affected scopes/months。
2. 写操作立即结束，不轮询其它页面的 operation barrier，也不把无关后台工作显示为本次操作阻塞。
3. 当前可见页若需要立即展示结果，只重新调用自己的正常 GET。GET 的 freshness gate 负责 exact-scope enqueue、refreshing/failed 状态和有界轮询。
4. 其它已打开、未挂载或 document hidden 的页面不响应业务刷新事件、不缓冲重放、不执行 load。focus、hidden→visible 与 BFCache 恢复不触发业务页面 I/O；route 重新 mount、页面查询变化、浏览器手动刷新或明确重试才重新运行该页 load/freshness contract。
5. 排序、分页和筛选只改变当前查询参数，不是页面激活，也不能触发其它页面重建。

`/api/operation-barrier/status` 只保留给显式返回非空 targets 的 maintenance/integration 操作；普通 mutation 不再依赖它。权限/session、DB 可写性、canonical version/idempotency/owner 状态仍由 command service 和 UoW 决定。

### 待找发票规则写入

待找发票规则保存走独立规则集边界：

1. `PendingInvoiceRulesApplicationService.update_rules(...)` 只接收 HTTP route 映射后的 direction、payload 和 actor。
2. `AppSettingsService.update_pending_invoice_rule_groups(...)` 校验当前 direction 的规则 `version`、归一化分组、递增对应规则版本并写审计。
3. 保存结果返回 `direction`、`old_version`、`new_version`、`affected_groups`、`actor_id` 与精确 scope hints；普通 freshness/barrier targets 为空。
4. API finalizer 只清必要的 process-local cache，不调用 `DerivedDataLifecycleService`，不写 dirty/outbox。
5. 当前待找发票页重新执行 normal GET；其余逻辑消费者在各自被访问时比较规则 owner version 并精确收敛。expense/income 使用独立 expected version，避免无关方向被误判 stale。

OA 付款算法不读取待找发票规则，因此 OA 页面不因该规则保存而刷新。App Health 只展示真实 runtime scope 事件，不把规则版本变化推导成未实际入队的全局同步。

### 关联台 automatic decision 显示边界

关联台的“撤回关联”只出现在已配对区并且只撤销 active relation；未配对区不提供撤回动作，也不兼容自动候选拆分：

1. route / facade 通过 `WorkbenchRelationCommandService` 预览 canonical active relation 撤回；只有存在 active relation 时才返回 `withdraw_relation`。
2. 若没有 active relation，preview/submit 必须返回 relation not found 或 invalid operation，不能回退到任何 legacy candidate/decision 表、store 或 snapshot。
3. 自动匹配只允许在内存中生成可原子提交的 `FormalRelationPlan`；无法满足确定性安全规则的结果不持久化、不合并未配对事实，也不得驱动 pending invoice、input invoice usage、OA pending、cost statistics 等 linked-only 下游状态。
4. Workbench active generation、all-scope aggregate、groups page 和 `audit_workbench_relation_display` 必须共同保证旧 `case:decision:*`、`automatic_decision` / `automatic_match` payload 不会继续污染页面。Release A 仅为应用回滚暂留旧物理表，但运行时必须保持零访问；Release B 通过独立 migration 删除。

### 成本统计 direct canonical read boundary

成本统计不再消费任何页面 read model。explorer、详情和导出均由 `CostStatisticsQueryService` 调用 canonical repository，在一个 `REPEATABLE READ READ ONLY` 数据库快照内读取银行流水、OA、正式配对关系、标签与设置，再由无 I/O policy 生成五种视图。

页面访问或浏览器刷新只发起本页面 API；不读取 Workbench/Bank Detail 页面 payload，不经过 freshness/version/dirty/outbox/worker，不产生跨页面 fan-out。页面打开期间不自动订阅变化；用户再次刷新读取最新已提交事实。旧 Cost projection、parent/shard、Redis、worker 和 scope 状态由 migration `0126` 退出并删除。
