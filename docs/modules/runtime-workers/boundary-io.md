# Runtime Worker 模块边界与 I/O

日期：2026-08-15

## 当前集合

`runtime_worker_registry.py` 是唯一 registry，生产必须且只能运行四个 instance：

| Instance | Worker kind | 输入 | 责任 |
| --- | --- | --- | --- |
| `oa-sync` | `oa-sync` | `oa.sync`、`oa.payment_status.reconcile` | OA integration 普通 month/all 同步、selected-row 精确附件重解析，以及正式 OA+流水关系变化后的支付状态自动收敛 |
| `workbench-matching` | `workbench-matching` | PostgreSQL matching dirty scopes | 正式关系候选计算 |
| `import` | `import-job` | `job.import_jobs` 单任务领取 | 流水/发票/ETC 的 prepare/commit，以及已认证发票与 OA 手动导入 |
| `settings-maintenance` | `settings-maintenance` | settings maintenance events | 数据重置与关系要求重算 |

不存在 read-model worker。未登记的 systemd worker 必须由 release helper stop/disable。

## 输入 I/O

- Event worker 只从 PostgreSQL durable queue claim；不经过第二套 broker/wakeup transport。
- Matching worker 只读写其领域 dirty-scope repository，不使用通用 projection scope；执行正式关系命令时以
  `fin_ops_worker` 对 `app.workbench_idempotency_records` 持有 `SELECT/INSERT/UPDATE`，不得授予 `DELETE`。
- Matching worker 的银行有效分类由 formal-relation fact repository 对计划 IDs 一次批量读取 canonical SQL 分类投影；worker 不装载 category snapshot，不组装 Python effective-category provider。
- 每个 job/event 必须有 bounded retry、lease、idempotency 和结构化失败证据。
- 导入事务在取得任务 owner fence 后，用同事务 settings 共享锁复核创建者当前页面权限；撤权先提交则禁止事实写入。四类入口共用此权限边界。
- API route 只 enqueue 已登记任务；worker 不读取 HTTP cookie/header，不构造 response，不依赖 `Application`。
- OA 精确附件刷新复用 `oa.sync`，不新增 event/worker；worker 独占 Mongo 下载、OCR、定向 owner commit、统一附件 promotion 与 matching reconciliation。completed 与 `in_progress + expense_claim` 复用同一个 promotion 边界；进行中支付申请仍不接纳附件解析。API 只读取受控 durable status/result，不得恢复同步 fallback。
- OA 支付状态复用同一个 `oa-sync` instance 的独立 `oa.payment_status.reconcile` handler。关系事件携带 typed OA IDs，handler 查询最新 active topology；金额不等不阻断、inflow 不触发、failed 不覆盖；有 active outflow 写 `已支付`，无 active outflow 写 `待支付`。完整 OA `all` snapshot 还可登记 `remove_missing_oa_statuses + exact flow IDs`：handler 必须先批量复查 completed projection 与 pending admission，再幂等删除仍缺失 flow 的 MySQL 状态；month/retention 不得触发该外部删除。Migration `0160` 删除旧 ownership 表，并为全部已完成 OA 与已准入进行中 OA 的并集登记一次规则重算事件。
- `oa.sync(operation=refresh_attachments)` 的 pending/processing/failed 状态由专用 event status 接口和通用队列指标观测，不得计入全量 `oa_projection` freshness、App Health 全局 OA 状态或发布 readiness；单条修复失败不能污染全量 OA 健康结论。

## 输出 I/O

- 业务结果通过明确 service/repository 写 canonical tables。OA 手动导入先精确读取已选 OA 来源并校验 completed，再把定向 projection、manual marker、操作审计和任务终态放在同一事务；不得全量替换其他 manual marker或宣告整月同步完成。已认证发票的批次、明细和任务终态同事务。
- Event worker 状态写 `job.outbox_events` 与 attempt；导入状态只写 `job.import_jobs`，heartbeat 复用现有表。导入不再生产/消费 `import.process.requested`，不更新第二套 background job 状态。
- Worker 不读写 Redis，不写页面 DTO、projection schema、page cache 或 freshness/readiness 状态。

## 依赖方向

```text
registry -> worker bootstrap -> handler -> domain service -> repository
API route -> application service -> durable queue/domain repository
```

禁止 handler 反向依赖 route/auth/server response；禁止 service 裸 SQL；禁止恢复旧 worker/event/env。

## 文件范围

- Registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- Runner：`backend/src/fin_ops_platform/services/runtime_worker.py`
- Handlers：`backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- Queue：`backend/src/fin_ops_platform/services/runtime_queue.py`
- Matching queue：`backend/src/fin_ops_platform/services/postgres_repositories/workbench_matching_queue.py`
- Deploy helper：`deploy/oa/bin/finops-ensure-runtime-workers.sh`

Deploy helper 会保留已有实例的吞吐、lease、timeout 与 poll 调优，但在 registration check 之前原子迁移
per-worker env：`FIN_OPS_QUEUE_BACKEND` 固定为 `postgres`，删除该实例遗留的 `FIN_OPS_RABBITMQ_*` 与
`FIN_OPS_REDIS_*` 覆盖。公共 API cache 环境不属于此迁移范围。

## 验证

- Registry/command/health：`tests/test_runtime_worker_registry.py`、`tests/test_runtime_worker.py`。
- Queue/retry/idempotency：`tests/test_runtime_queue.py` 与业务 service tests。
- Deploy exact set：`tests/test_deploy_runtime_examples.py`、`tests/test_read_model_runtime_removal.py`。
- Production：`/health/ready`、worker heartbeat、PostgreSQL queue backlog/dead-letter、runtime closure gate。

Migration `0151_workbench_matching_worker_idempotency_grant.sql` 修复历史只读授权，确保 dirty scope 重试可通过
正式关系命令的持久化幂等边界完成；禁止通过直写 relation 或删除失败 scope 绕过该合同。

## 2026-09-20 匹配 worker 的明细归属

同一 workbench-matching worker 现在同时补普通关系内缺失的 OA 明细归属；心跳/运行汇总增加 `assigned_invoice_count`。提交入口复用 relation UoW、source-link CAS 和 operation audit。自动写入不自我 enqueue；没有新增事件/worker/read model。保留当前实例 poll 设置（仓库实例模板为 0.25 秒），不以 Python 默认值覆盖生产调优。

## 2026-09-20 ETC 来源与进行中配对

- ETC manual submitted 通过 owner 的同事务 CAS writer 标记 `job.workbench_matching_dirty_scopes`；无变化重复提交不投递。OA sync/银行导入继续使用原 producer，现有 `workbench-matching` 完成来源初建及后到流水补入，自动 relation 写不重复投递自己。
- 无新增 worker/read model/cache/event type。队列失败、版本漂移与事务失败沿用明确失败/重试，不删除任务掩盖错误。

## 2026-09-20 付款匹配 scope 补齐

原 workbench-matching worker 与 durable queue 合同不变。关系/凭证/发票归属 writer 通过 `mark_relation_matching_dirty` 在同一事务通知全部实际成员月份，不再只通知发票月份；规则 v16 复用已完成 scope 的版本重扫。自动匹配自身不回投相同业务任务，页面 GET 仍零入队。

## 2026-09-21 凭证组保存通知

凭证文件集合和子项总金额在一次事务提交后，只通过原 matching repository 通知目标 OA scope 一次；逐文件独立投递已移除。既有 worker 以批量 OA hydration 读取金额，不增加实例、事件类型、缓存或 read model。

## 2026-09-21 导入单任务事务合同

- `ImportJobRepository.claim_next` 使用 `FOR UPDATE SKIP LOCKED` 直接领取，`claim_version` 每次递增；续租与失败写入必须匹配 job ID、owner、领取版本。
- prepare 与 commit 共用同一任务。预览结果和 session 同事务，确认 CAS 预览版本；重复上传请求只返回原任务，不能覆盖已确认的 payload。
- `ImportJobCompletion.lock(transaction)` 在正式写入前锁定任务并校验所有权；`succeed(transaction,result)` 与正式数据同事务。worker 不做独立成功补写。
- 取消也锁任务：取消先提交则旧 owner 无法写事实，业务事务先提交则取消返回已完成冲突。
- 进程退出释放同一领取；强制进程终止后依靠过期 lease 恢复。最大尝试耗尽明确失败，用户显式重试；不存在第二事件 ACK。
- 已认证发票和 OA 手动导入由 `SharedImportProcessor` 使用明确的事务 repository；OA 仅新增/重新接纳指定行，不把未选记录置 inactive。
- import 失败数量、排队年龄单独观测；用户文件失败保留在 `import_queue.failed`，不计入全局 `queue_backlog.failed` / `failed_jobs`，不使 API readiness 或发布 runtime closure 失败。pending/processing 导入仍参与发布排空，outbox 失败/死信仍阻断发布。旧导入 outbox 仅作为历史证据读取。
- Migration `0175` 增加版本/确认状态并退役能对应权威 job 的旧事件；不删除事实和历史任务。

## 2026-09-21 准备续跑与任务取消

事件 handler 可返回 `status=deferred` 与非空 `reason`，worker 释放同一事件并撤回本轮领取增加的 attempt，不 ACK、不登记失败；后续轮次继续。`RuntimeWorkerTaskTimeout` 是 worker 控制信号，继承 BaseException，避免被第三方 Exception 包装吞掉；worker 显式捕获并通过原失败/有限重试通道记录真实超时。

retry、release 和 manual requeue 保留 event UUID、payload、source version，改用 `runtime.retry:<event UUID>` 作为重试队列去重键。新周期任务仍使用原 enqueue key，两者均保留且可实际执行，禁止覆盖新任务或以成功代替失败处理。release 沿用现有 runtime_shutdown_release 证据字段和 released attempt outcome。无新 worker、schema 或 read model。
