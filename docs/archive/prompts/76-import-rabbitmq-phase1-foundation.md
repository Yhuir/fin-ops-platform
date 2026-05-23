# 76. 导入功能 RabbitMQ 化第一阶段执行 Prompt

## /goal

把导入功能生产级接入 RabbitMQ 的第一阶段落地：PostgreSQL 固定为导入任务事实源，RabbitMQ 只作为唤醒和投递通道；新增统一 import job 事实表、统一事件 envelope、RabbitMQ topology 路由、worker 处理框架和可验证测试。不要把所有导入接口一次性改成异步执行；任何导入业务处理器必须逐个迁移、逐个验收、保留 PostgreSQL fallback 和回滚边界。

## 背景约束

- 现有 RabbitMQ 已覆盖 read model、OA sync、file object migration 等 runtime events。
- 导入功能包含银行流水/普通导入、文件导入、ETC、税务认证、手工 OA 等不同业务链路。
- 生产级原则：RabbitMQ 不是业务事实源；业务状态、任务状态、失败状态、幂等键、trace 均落 PostgreSQL。
- RabbitMQ 消息里只允许 event_id、event_type、scope_type、scope_key、source_version、priority、trace_id 等 envelope 字段；禁止放大 JSON、快照或业务事实。

## 并行任务

1. **Schema / 数据事实源**
   - 新增 `job.import_jobs`。
   - 字段覆盖 job id、tenant、import_type、idempotency_key、status、stage、priority、attempt_count、max_attempts、last_error、payload/result/raw payload、trace、available/started/finished/locked timestamps。
   - 增加幂等唯一索引、claim 查询索引、trace/import_type 查询索引。
   - 增加 `job.import_job_status_v1` 只读视图。
   - 补齐 `fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly`、`fin_ops_migrator` grant。

2. **Queue / Envelope**
   - 定义 `import.process.requested` 事件类型。
   - 将它加入 `DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES` 和 RabbitMQ supported routes。
   - 事件 outbox payload 只保存 PostgreSQL 内部读取所需的 `import_job_id` 等小字段；RabbitMQ envelope 继续不携带 payload。

3. **Service / Worker**
   - 新增 `ImportJobRepository`，提供 create/get/processing/succeeded/failed/enqueue_process_requested。
   - 新增 `ImportJobWorker`，通过显式 processor registry 执行 import_type。
   - 未注册 processor 时，必须把 import job 标记为 failed，并让 outbox event 正常 ack，避免无限重试和隐性丢任务。
   - 新增 worker CLI flag `--enable-import-job-processing`，但不默认启用，不改变现有导入接口行为。

4. **测试 / 验证**
   - 新增 import job repository/worker 单元测试。
   - 更新 runtime queue / RabbitMQ topology 测试。
   - 更新 migration pinned list。
   - 运行针对性测试和 `git diff --check`。

## 串行执行顺序

1. 读现有 `runtime_queue.py`、`rabbitmq_runtime.py`、`worker.py`、migration/test patterns。
2. 写归档 prompt，记录本阶段目标和非目标。
3. 新增 `0019_import_jobs.sql`。
4. 新增 import job service/worker 模块。
5. 更新 RabbitMQ event type 和 worker CLI。
6. 更新测试。
7. 运行验证。
8. 输出变更、验证结果、剩余生产迁移步骤。

## 验收标准

- 默认配置仍是 PostgreSQL 模式，现有导入 API 行为不变。
- RabbitMQ topology plan 出现 `import.process.requested` 和对应 DLQ。
- Dispatcher 默认发布范围包含 `import.process.requested`，但生产可通过 `RABBITMQ_DISPATCH_EVENT_TYPES` 灰度控制。
- Worker check 启用 `--enable-import-job-processing` 时能显示 handler、event route 和 event type。
- 重复创建同一个 idempotency_key 的 import job 不会生成两个活动任务。
- 未注册 import processor 时任务进入 failed，outbox event 被正常 ack，不出现无限 RabbitMQ 重投。
- 测试通过或明确说明未通过原因。

## 非目标

- 不在本阶段把所有导入端点切成异步。
- 不把文件内容、导入明细、大 JSON payload 投递到 RabbitMQ。
- 不让 RabbitMQ 成为导入任务状态、失败事实或业务事实源。
- 不移除 PostgreSQL fallback。
