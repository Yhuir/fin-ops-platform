# 影响分析与测试闸门

**用途:** 每次模块化 IO 重构、功能改动、bug fix、API/read model/worker/权限/数据流变更前必须使用。

## 改动前影响分析

每次动手前，必须回答以下问题：

### 1. 模块范围

- 目标模块:
- 模块类型: 页面模块 / 资源模块 / 共享边界
- 本次改动类型: bug fix / feature / refactor / API / read model / worker / permission / docs only
- 是否改变业务行为:
- 是否改变 API response shape:
- 是否改变 read model freshness 语义:
- 是否改变 read model partition/scope/incremental projection 策略:
- 是否改变权限或审计:
- 是否进入 Go / Fiber / Go Worker candidate:

### 2. 后端影响

| 层 | 是否影响 | 文件/符号 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| route / HTTP mapping |  |  |  |  |
| application service |  |  |  |  |
| domain service / policy |  |  |  |  |
| repository / SQL |  |  |  |  |
| transaction / UoW |  |  |  |  |
| audit |  |  |  |  |
| permission |  |  |  |  |

### 3. read model / worker 影响

| 项 | 是否影响 | 具体内容 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| read_model_key |  |  |  |  |
| scope_type/scope_key |  |  |  |  |
| source/schema version |  |  |  |  |
| readiness/freshness |  |  |  |  |
| partition key / scope key |  |  |  |  |
| scoped incremental projection |  |  |  |  |
| dirty scope |  |  |  |  |
| outbox event |  |  |  |  |
| worker registry |  |  |  |  |
| Go Worker / Python Worker ownership |  |  |  |  |
| App Status |  |  |  |  |
| Operation barrier |  |  |  |  |
| force refresh entry |  |  |  |  |
| Redis/RabbitMQ behavior |  |  |  |  |

### 4. 前端影响

| 层 | 是否影响 | 文件/组件 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| page |  |  |  |  |
| feature API |  |  |  |  |
| feature types |  |  |  |  |
| component |  |  |  |  |
| loading/empty/error |  |  |  |  |
| refreshing/stale/blocked |  |  |  |  |
| permission rendering |  |  |  |  |
| drawer/dialog/action |  |  |  |  |
| domain events |  |  |  |  |

### 5. 跨模块影响

- 上游模块:
- 下游模块:
- 共享 facts:
- 共享 read model:
- 共享 worker:
- 共享 frontend event:
- 共享 operation barrier:
- 旧功能可能受影响:
- 旧 route/service/repository/read model/frontend API 是否仍被调用:
- 新链路是否可能读取旧模块内部状态:

### 6. Legacy 退役与污染防护

每次模块迁移都必须列出旧链路状态：

| Legacy path | 当前调用者 | 目标状态 | 删除/隔离证据 | 防污染测试 |
| --- | --- | --- | --- | --- |
|  |  | removed / quarantined / compat-only / blocked-by-human-gate |  |  |

禁止：

- 只新增新模块，不处理旧 route/handler/service/frontend API。
- 新链路调用旧模块 internal-only surface。
- 旧链路继续写 canonical facts、dirty scopes、outbox、read model readiness、cache 或 App Status。
- 用 legacy fallback 吃掉新链路错误，让测试看似通过。
- 保留没有 owner、调用者清单、删除条件和测试覆盖的旧代码路径。

必须证明：

- 新 API/command/query 的调用图不会回到旧 handler。
- 新 read model refresh 不经过旧 dirty/outbox 写法。
- 前端页面不会绕过 feature API 调旧 endpoint。
- 保留的 `compat-only` 路径只做兼容映射或只读查询。
- 删除旧路径前后，旧 API response shape 和关键业务流有回归测试保护。

### 7. 环境与验证限制

- 本地是否有 `PGSQL_URL`:
- 是否有 staging 数据库:
- 是否需要真实 PostgreSQL:
- 是否需要真实 worker/outbox/readiness:
- 是否需要 Redis/RabbitMQ:
- 是否需要 OA Mongo/OA MySQL:
- 是否只读:
- 是否会写生产数据:
- 是否需要备份:
- 是否需要维护窗口:
- 是否需要人工审批:
- 本地替代验证方式:
- 生产验证 runbook:

当前默认约束：

- 没有本地 `PGSQL_URL`。
- 没有 staging 数据库。
- 当前 `finops-prod` 可 SSH 登录服务器，但用户是 `finops-deploy`，没有无密码 sudo。
- 当前 `finops-prod-root` 已可免密公钥登录，验证返回 `user=root uid=0 host=VM-0-6-opencloudos key_login=ok`。
- root 访问只允许用于特权只读验证；不得读取或输出 secret，不得执行生产写入、DB 写入、worker 消费/重放。
- 不允许把 SSH 密码或任何 secret 写入计划、命令、脚本、测试或日志。

## read model refresh 边界闸门

允许路径：

- `ReadModelRefreshGateway` 归一化、校验、去重后委托 queue repository。
- `RuntimeQueueRepository.enqueue_read_model_refresh(...)`。
- 事务内 writer 使用 `enqueue_read_model_refresh_in_transaction(...)` 或等价合同。
- read model scope contract repair 工具在明确 operator/repair 语义下清理历史违规 scope。
- 测试中 fake/stub queue。

禁止路径：

- 业务 service 直接 SQL 写 `job.outbox_events`。
- 业务 service 直接 SQL 写 `job.read_model_dirty_scopes`。
- 前端或页面 API 伪造 read model fresh。
- Redis 缓存未通过 fresh gate 的 payload。
- RabbitMQ 作为 read model 状态事实源。
- worker 依赖 HTTP/session/Application。

每次新增或修改 refresh 调用点必须有：

- scope_type/scope_key normalization 测试。
- dedupe/reason/source version 测试或说明不适用。
- stale/refreshing/fresh/failed API 行为测试。
- App Status/operation barrier 影响测试或说明不适用。

## Read Model 强制刷新闸门

强制刷新是生产级能力，不是页面级补丁。

允许：

- 写操作根据 canonical result 产出 affected scopes，再通过统一 gateway enqueue refresh。
- 运维/repair 工具在明确 actor、scope、reason、audit 和 dry-run 语义下触发 refresh。
- API 提供受权限控制的 force refresh entry，并返回 job/readiness/status。
- 前端只通过 operation barrier 或登记的 refresh endpoint 触发目标 scope，不能刷新未知范围。

禁止：

- 页面直接“刷新所有 read model”。
- service 绕过 gateway 直接写 dirty/outbox。
- 把强制刷新当作掩盖 scope 计算错误的 fallback。
- fresh/stale 状态缺失时继续展示为同步完成。
- 用 Redis/RabbitMQ 状态代替 PostgreSQL durable queue/readiness。

每个涉及跨页面同步的写操作必须有测试证明：

- 写入返回 affected scopes/months/version/job。
- refresh gateway 收到正确 scope、reason、dedupe key。
- stale -> refreshing -> fresh/failed 的 API 状态可被观察。
- 前端成功写入后等待或重读正确 read boundary。
- 另一个依赖同一 read model 的页面不会继续读旧数据并显示为 fresh。

## Partitioned Scoped Incremental Projection 闸门

所有页面 read model 默认目标是 `Partitioned Scoped Read Model + Scoped Incremental Projection`。

必须登记：

- read_model_key。
- scope_type。
- partition key，例如 month、account、object、domain、status 或 config version。
- affected scope 计算来源。
- full rebuild fallback 条件。
- parent/aggregate scope 规则。
- freshness proof。
- operation barrier target。
- builder owner: Python / Go Worker / mixed。

禁止：

- 普通写后同步默认走 full rebuild。
- `all` 父 scope 在 child shard 未 fresh 时写 fake fresh。
- 只按页面刷新，不按事实影响 scope 刷新。
- Redis cache 代替 SQL/readiness freshness proof。
- Workbench active generation 被机械改成普通 projection。

必须测试或记录替代证明：

- 写入只 dirty 受影响 scope。
- 非目标 scope 不被无意义刷新。
- full rebuild 只在 backfill、repair、cold start 或人工 runbook 下使用。
- parent/aggregate scope 等待 child shard fresh。
- 页面 A 写入后，页面 B 通过对应 scope fresh 后再显示同步结果。

## Go / Fiber / Go Worker Candidate 闸门

Go 化只能发生在 `11-GO-HOT-PATH-CARVE-OUT.md` 的 candidate list 内。

每个 Go candidate 必须先回答：

| 项 | 结果 | 证据 |
| --- | --- | --- |
| Candidate key 是否在列表内 |  |  |
| 性能证据 | API p95 / SQL p95 / worker lag / enqueue-to-fresh / CPU / import parse time |  |
| IO contract | complete / incomplete |  |
| Legacy isolation | removed / compat-only / blocked |  |
| Freshness proof | complete / not applicable |  |
| Shadow run | possible / impossible |  |
| Python-vs-Go equivalence tests | planned / present / impossible |  |
| Rollback | per worker / per route / per feature flag |  |
| PostgreSQL dual queue | `job.outbox_events` + `job.read_model_dirty_scopes` / not applicable |  |
| Fiber use | none / internal API / rejected |  |

禁止：

- 候选列表之外自动 Go 化。
- 未通过 admission gates 直接实现 Go。
- Fiber handler 承载长时间任务。
- Go 直接写未登记 canonical facts。
- Go 绕过 dirty/outbox/readiness。
- Python worker 和 Go worker authoritative 双写、双 ack 或双 publish。
- RabbitMQ 作为 job/read model/freshness 事实源。

必须测试：

- Python old output vs Go new output。
- shadow mode 不 ack、不 publish、不写 readiness、不写 cache。
- rollback 后 Python worker/service 可重新接管。
- Go 失败时 dirty scope/outbox/readiness/error shape 可观测。
- Go service/worker health/check/version/timeout/retry/resource limits。

## 七类测试闸门

### 1. Business core unit tests

适用条件：

- 业务规则、金额计算、状态转换、分类规则、tag 匹配、权限决策、去重、幂等、version conflict、非法输入。

必须覆盖：

- 成功路径。
- 边界输入。
- 空输入。
- 非法输入。
- 重复输入。
- 状态冲突。
- 失败分支。

### 2. Service-layer tests

适用条件：

- service、repository、state store、audit logging、background job、read model、cache、跨模块 orchestration。

必须覆盖：

- 持久化。
- read model invalidation/rebuild。
- audit record。
- 幂等副作用。
- partial failure。
- rollback。
- 防止半写入状态。

### 3. API contract tests

适用条件：

- 新增或改变 HTTP/API contract。

必须覆盖：

- success status 和 response shape。
- missing fields。
- wrong types。
- illegal states。
- insufficient permissions。
- version conflicts。
- idempotent repeats。
- stale/fresh/refreshing dependencies。
- external dependency failure。

禁止：

- 只断言 `status_code == 200`。

### 4. Read model/cache/background job tests

适用条件：

- list pages、summary、search、workbench、ledger、tax offset、pending invoice、bank details、import flows 或任何 read model。

必须覆盖：

- write 后 read model invalidation。
- refreshing/stale/fresh status。
- stale cache 行为。
- background job completion。
- bulk processing。
- concurrent writes。

禁止：

- 用 skipped tests 或 relaxed assertions 隐藏 cleanup/worker 问题。

### 5. Frontend component and interaction tests

适用条件：

- 前端页面、表格、drawer、dialog、button、filter、import flow、settings、permission rendering。

必须覆盖：

- initial loading。
- loading/empty/error。
- refreshing/stale。
- user clicks。
- form validation。
- permission hidden/disabled controls。
- API success 后刷新。
- API failure 后反馈。
- drawer/dialog open/close。
- filtering/sorting/pagination/search。

### 6. End-to-end business-flow integration tests

适用条件：

- 改动跨多个模块。

优先路径：

- import -> preview -> confirm -> background job -> workbench display。
- bank tagging -> ledger generation -> workbench sync。
- OA import -> invoice relation -> list refresh。
- settings change -> read model invalidation -> API/UI reads new configuration。
- confirm relation -> withdraw relation -> read model recovery。

### 7. Existing feature regression tests

永远需要评估。

问题：

- 哪些现有页面、API、read model、state、export、permission、workflow 会受影响？

必须保护：

- 旧 API response shape。
- 旧页面渲染。
- 旧 filter/sort/pagination。
- 旧 export fields。
- 旧 permissions。
- 旧 read model 不变空。
- 旧业务链不被新状态/tag/cache 破坏。

## 改动完成前验收

最终 summary 必须包含：

- 新增或修改了哪些测试。
- 覆盖七类测试中的哪些类别。
- 哪些类别不适用，以及原因。
- 运行了哪些验证命令。
- 哪些验证未运行，以及原因。
- 剩余未测试风险。
- docs impact 结果。
- 环境限制: 哪些验证因没有 `PGSQL_URL` 或 staging 数据库未运行。
- 生产验证计划: 如果需要真实数据库/worker/read model，列出只读或受控写入 runbook 状态。
- Legacy 退役结果: 删除了哪些旧路径，隔离了哪些旧路径，剩余旧路径为何不能删除。
- Read Model 强制刷新结果: affected scopes、force refresh 入口、freshness proof 和跨页面同步测试覆盖情况。
- Partitioned scoped incremental projection 结果: partition key、scope key、incremental trigger、full rebuild fallback 和 parent/aggregate 规则。
- Go candidate 结果: 是否适用、是否延期、性能证据、shadow run、Python-vs-Go equivalence、rollback、Go Worker/Fiber 运行形态。

## 最小验证命令集合

根据改动范围选择，不能机械全跑但必须足够覆盖风险：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
cd web && npm run build
```

对单模块改动，应优先运行相关模块测试和受影响共享边界测试。

## 无 staging 环境下的验证分层

| 层级 | 可做事项 | 禁止事项 | 完成状态含义 |
| --- | --- | --- | --- |
| Local static | 类型检查、lint、import check、纯函数单测、前端测试、fake API contract | 假装验证了真实 DB/worker | 只证明代码和合同局部成立 |
| Local fake/stub | repository fake、queue fake、read model gateway fake、API fake、frontend mock | 用 fake 结果声明生产 read model 已闭环 | 证明边界调用和 response shape |
| Production read-only | SSH 后执行只读 SQL、health、readiness、worker status、日志检查 | 写业务表、改 readiness、消费/重放 outbox | 证明生产当前状态和兼容性 |
| Production controlled-write | dry-run 后的受控写入、幂等 smoke、可回滚操作 | 无审批、无备份、无回滚的写入 | 证明生产链路闭环 |

没有 staging 时，任何涉及真实 PostgreSQL/read model/worker 的重构最多只能在 local 层证明设计正确。生产闭环必须另走 read-only 或 controlled-write runbook。

当前 SSH 状态下，`Production read-only` 可以覆盖 root 可见的 systemd、日志、部署文件和只读 health/readiness 检查；read model/worker/DB 级验证仍需要受控只读 wrapper，避免暴露 DSN 或 secret。

## Autonomous No-Block Policy

缺少 staging 数据库和本地 `PGSQL_URL` 不阻塞自动推进。

自动运行必须：

- 用 fake/stub/contract 测试替代真实 DB 验证。
- 对无法收集的生产 DB/worker 证据标记 `production-evidence-deferred`。
- 继续下一个安全模块。
- 只在生产写入、secret、特权操作、业务语义不明、主 repo 不干净或无法安全对齐 `dev` 时停止。
