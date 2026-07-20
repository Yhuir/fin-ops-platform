# 外部往来款管理性能全量分析

日期：2026-07-20

## 结论

外部往来款管理当前生产读取已经达到既定门槛：页面 shell p95 `117.557ms`、grouped API p95 `284.012ms`、标签选项 p95 `177.869ms`、Page Audit p95 `323.220ms`，20/20 样本均为 2xx、fresh、0 enqueue，Audit 为 pass/fresh/drained/ready。

当前不是 worker 堵塞、数据库连接或前端重复请求问题。生产仅 21 条 read-model 行，现有全量 SQL 执行约 `0.169ms`；当前约 284ms 主要是认证、应用、网关和网络固定成本。不能据此增加缓存、新表、新 worker 或第二 read model。

但链路存在三项会破坏增长后性能或写后可信度的问题，以及两条应删除的旧代码：

1. 列表查询把所有命中行及 `payload + raw_payload` 全量取回，在 Python 中完成方向筛选、汇总、family 汇总和分页，复杂度与历史数据量线性增长。
2. `scope_key=all` 只检查 `all` dirty scope；正常写入标记月份 scope，页面可能在月份刷新期间把旧行误判为 fresh。
3. turnover projection 将同一规范化 payload 同时写入 `payload` 和 `raw_payload.normalized_payload`，生产 21 行已重复存储约 84KB，并在每次读取时一并搬运。
4. `TurnoverLedgerQueryService` 仍保留可达的 live `legacy_payload_builder` 及 `postgres_required` 分叉；生产虽走 PostgreSQL，但可选配置仍能绕过 freshness gateway。
5. `clear_turnover_ledger_rows` 已无生产调用方，只残留于 port、wrapper、manifest、测试和历史文档，是无 owner 的旧清空链。

因此本轮只做 turnover-ledger owner 内的五项收敛：SQL 端固定查询数的过滤/汇总/分页、all-scope 子 scope freshness 聚合、删除 legacy live fallback、删除 dead clear port、停止 raw payload 双写并 bump schema v6。API shape、canonical relation、命令写入、页面 UI、共享 gateway、其他页面 read model、worker 数量和部署拓扑均不变。

## 页面边界与 I/O

输入 I/O：

- `GET /api/turnover-ledger?view=grouped&family=...&direction=...&status=...&page=...&page_size=...`
- `read_model.turnover_ledger_rows` 规范化 `payload`、结构化 family/status/scope/source_versions。
- `job.read_model_dirty_scopes` 中 `scope_type=turnover_ledger` 的 current-effective dirty 状态。
- `turnover_ledger_source_versions()` 提供的预期 canonical/schema 版本。

输出 I/O：

- 既有 `summary`、`family_summaries`、`rows`、`pagination`、`filters`、`read_model_status`、`source_versions` 和 refresh metadata。
- 既有 grouped API 映射与前端 loading/refreshing/audit 行为。

共享事实源但不改变其行为：

- canonical Workbench relations 与 bank tags 继续由 projection builder 只读。
- refresh 请求继续只经 `ReadModelQueryGateway` / `ReadModelRefreshGateway` 进入 PostgreSQL durable queue。
- 其他页面不调用 turnover query port；本轮不改共享 generic repository helper。

## 根因与证据

### 1. 当前耗时不是数据库慢查询

- 生产 20 样本 grouped API p95 `284.012ms`。
- 当前 21 行全量 SELECT 执行约 `0.169ms`。
- 生产 payload `83,161 bytes`、raw payload `83,890 bytes`、source versions `36,249 bytes`。

结论：当前固定耗时不能靠新索引或缓存显著消除；读取算法和重复 JSON 是增长风险，应在 owner 边界内收敛。

### 2. 当前 query 是无界 O(N)

`list_turnover_ledger_view` 先 SELECT 所有匹配行，再在 Python 中做方向筛选、五项金额汇总、四个 family 汇总和 list slice。页大小最多 200 并没有限制数据库传输和 JSON 解码。历史月份增长后，即使只看第一页，也会完整加载所有历史 payload。

### 3. all-scope freshness 证明不完整

正常 write invalidation 以月份为 partition scope；页面 query 固定读取 `all` 组合视图。当前 repository 只查询 dirty key `all`，没有聚合 `turnover_ledger:*month*`。因此写后月份刷新未完成时，混合版本行可能被 normalize 成当前 expected versions 并显示为 fresh。

### 4. 旧链仍可达

- query service 在 repository miss 且 `postgres_required=false` 时直接调用 live `TurnoverLedgerService.list_ledger`。
- 这条路径绕过 read-model freshness、queue 和 operation barrier，不应作为生产页面 I/O 保留。
- `clear_turnover_ledger_rows` whole-repo 生产扫描只有定义和转发，没有 caller；正式 all rebuild 已由 gateway fan-out/partition save 负责。

## Grill-me 三轮审阅

### 第一次审阅：正确性、事实源与写后可见性

- 方向规则、金额 fallback、family/status/scope 过滤、排序、分页和 response shape 必须完全等价。
- `all` 必须把任一月份 pending/processing 判为 refreshing，把任一 failed 判为 stale；不能在子 scope 活跃时把 mixed versions 规范成 expected/fresh。
- repository 真正为空时仍由 gateway enqueue miss；只是筛选结果为空时应返回 fresh 空结果，避免无意义 rebuild。
- schema bump 强制旧双写 projection 经正式 gateway/worker 重建，禁止直接更新 read-model 表。

结论：正确性闭环成立，但需要真实 PostgreSQL 等价测试和 fresh/refreshing/stale/missing 测试。

### 第二次审阅：简洁性、模块隔离与过度设计

拒绝以下设计：Redis 页面缓存、新 read-model 表、新 worker、前端轮询、跨模块 SQL、改共享 query gateway、重写 projection 事实源。这些都没有当前生产证据支持，并会扩大其他页面影响面。

保留的五项修改全部位于 turnover owner 或 shared repository 的 turnover 专属方法中；其他页面 API、port、SQL 和 DTO 不变。SQL 汇总和分页使用固定 CTE/两次读取，不增加通用抽象层。

结论：方案是最小的结构性修复，不是最小玩具实现，也不是过度设计。

### 第三次审阅：旧链删除、发布、回滚与验证

- whole-repo guard 必须证明 `legacy_payload_builder`、query service settings switch、`clear_turnover_ledger_rows` 生产定义/调用和 turnover raw payload fallback 不再存在。
- schema v6 由部署后的正式 force refresh/rebuild 产生新 projection；所有 shard fresh 后才做性能和写后验证。
- 回滚只部署上一精确 release；旧版本仍优先读取 `payload`，所以新行 `raw_payload={}` 不破坏代码回滚。无 canonical migration、无业务数据变更。
- 最终必须验证直接 Page Audit、共享事实消费者 Audit，以及一组可逆 confirm→fresh→withdraw→fresh；找不到安全样本时不得制造业务数据，必须明确延后到最终系统门。

结论：计划完整闭环；无需再增加层、基础设施或兼容分支。

## 发布后写入门失败与补充根因分析

首次发布后的 40 次只读探针全部通过，但可逆生产写入没有达到本阶段既定门槛，因此本阶段不能按只读结果提前结束：

- 第一组：confirm command `1513.044ms`、confirm response-to-fresh `5796.803ms`；withdraw command `2360.949ms`、withdraw response-to-fresh `5869.402ms`。
- 第二组：confirm command `1335.404ms`、confirm response-to-fresh `8869.179ms`；withdraw command `2772.193ms`、withdraw response-to-fresh `5803.559ms`。
- 第三组诊断期间确认了页面会在 canonical relation 已更新后反复进入 `refreshing`；测试最终通过正式 withdraw 恢复，两条 test-owned 流水均为 unlinked，未留下 active relation。

真实根因不是前端轮询，也不是列表 SQL：

1. PostgreSQL command path 仍使用旧的 `TurnoverLedgerRelationWritePort` 全快照链。confirm 会全量读取所有 turnover 银行流水并重建所有自动 relation，随后把整个 relation snapshot 和完整 audit log 逐条 upsert；stale precondition 又独立全量读取一次。withdraw 也会保存完整 relation snapshot。该旧链造成命令事务超过 1 秒，并把无关 relation I/O 污染到两条局部命令。
2. turnover projection 仍经 `WorkbenchRelationReadFacade(require_fresh=True)` 等待 `workbench_relation` read model。虽然同一事务已经写入 canonical `app.workbench_pair_relations`，turnover worker 仍必须等待另一个 worker 先发布 relation read model；事件先到时会 defer/retry，形成约 5–9 秒串行传播。
3. repository 已有按 row ids 读取 canonical active pair relation 和计算 source summary 的窄方法，其他 projection 也已使用这一模式；turnover 没有复用它，属于残留旧依赖，不需要新队列、新表、新 worker 或缓存。

### 补充三轮 Grill-me 审阅

第一轮（正确性）：局部 command 仍必须复用现有 `TurnoverRelationService` 校验、同一 PostgreSQL 事务、stale/idempotency、Workbench pair relation 原子写入和 durable outbox。只允许把“全量银行行重建 + 全快照保存”改成“按所选行刷新 domain 输入 + 单 relation/单 audit event 持久化”；不能绕开业务规则。

第二轮（隔离与简洁）：turnover projection 可以直接读取 canonical pair relation source，因为它是该 projection 的既有事实输入，且 repository 已有窄 I/O。拒绝同步写 read model、增加 delta cache、新 worker、调整共享队列调度或改其他页面 read model。其他页面继续消费自己的 read model；只删除 turnover 对 relation read model 的等待依赖。

第三轮（旧链、回滚与验证）：必须删除 production command 的全量 `_rebuild_relation_snapshot` / `save_turnover_relations` 路径、全量 stale-row lookup 和 turnover projection 的 `WorkbenchRelationReadFacade` dependency。保留全快照 repository API仅供其仍有 owner 的导入/恢复场景，不作为 turnover confirm/withdraw。新增真实 PostgreSQL 原子窄写测试、canonical-source projection 测试、整条 confirm/withdraw 回归，并重新部署后以至少两组可逆样本验证 command 与 committed-to-fresh 门槛。

补充结论：修复范围仍局限于 turnover owner 和已有 PostgreSQL repository 窄方法；这是消除已测得瓶颈所需的最小结构性修复，不是新增架构层。

## 验收门槛

- 页面 shell p95 `<=500ms`。
- grouped API p95 `<=500ms`，目标 `<=250ms`；40 次全部 2xx。
- 标签选项 p95 `<=500ms`。
- Page Audit p95 `<=1000ms`，pass/fresh/drained/ready、0 issue。
- 列表查询数据库读取固定为汇总 + page + freshness，不随总行数线性传输 payload。
- fresh 样本 `refresh_enqueued=false`；任一月份 dirty 时 all page 不得返回 fresh。
- 可逆 command p95 `<=1000ms`，committed-to-fresh p95 `<=2000ms`、hard max `3000ms`。
- 关联台、银行明细、成本统计、OA 待付款等显式共享消费者 Audit 无回归。
