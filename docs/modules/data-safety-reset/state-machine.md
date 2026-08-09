# 数据安全与重置 状态机

> 修改 `数据安全与重置` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。

## 业务状态

| 状态 | 事实源 | 说明 |
| --- | --- | --- |
| `impact_preview` | `GET /api/workbench/settings/data-reset/preview` | 服务端计算受影响行数与绑定行版本的 SHA-256 fingerprint；前端不能自报影响面 |
| `recovery_pending` | preview `recovery_ready=false` | 继续按钮禁用；运维必须先创建并验证同一 fingerprint 的 PostgreSQL restore point |
| `recovery_ready` | `job.settings_data_reset_recovery_receipts` | action/fingerprint 精确匹配、未过期、未撤销、未消费 |
| `password_pending` | Settings UI | 已确认影响和恢复点，等待操作原因与当前 OA 密码 |
| `password_failed` | API `403 oa_password_verification_failed` 或 `401/502/503` | 不允许执行任何删除、重建或 job 创建；响应不得回显密码 |
| `password_verified` | `_validate_settings_data_reset_request` | OA 登录接口返回 token，并解析为与当前 session 相同的 user id/username；仅表示当前请求可继续，不持久化密码 |
| `receipt_consumed` | reset request repository transaction | receipt、job、outbox、queued audit 原子提交；事务失败时 receipt 保持未消费 |
| `reset_queued` | `BackgroundJobService.create_job(type="settings_data_reset")` | 异步重置排队，`source/result_summary` 只能保存 action 等非敏感字段 |
| `reset_running` | background job `status=running` + progress | UI 可离开后恢复；同 owner 再提交必须返回 `409 settings_data_reset_job_running` |
| `file_cleanup_pending` | `app.import_files.status=deleting` | 数据库事实已事务性清理，文件/对象等待提交后删除；此状态必须可由同一 reset action 重试。 |
| `reset_succeeded` | job `succeeded` / serialized `completed` | 删除、durable 派生生命周期登记和 API runtime reload request 完成；仍需依赖 App Status/read model 验证最终 fresh |
| `rebuild_pending` | OA reset result `rebuild_status=pending` | 关联台重建已经可靠入队但尚未证明 fresh；不得同步查询全页 payload 后改成 completed |
| `reset_failed` | job `failed` 或同步 API structured error | 必须进入 App Health attention；保留错误但不泄露密码 |
| `reset_partial` | result `status=partial` 或 `rebuild_status=failed` | 按 failed job 处理；用户需要运维检查 affected scopes 和 rebuild status |
| `protected_target_skipped` | `protected_targets` payload + service 删除规则 | 受保护目标不应被删除；新增目标必须补测试 |

## 允许流转

- `impact_preview` -> `recovery_pending` -> 运维创建恢复点 -> `recovery_ready` -> `password_pending` -> `password_verified` -> `receipt_consumed` -> `reset_queued` -> `reset_running` -> `reset_succeeded`
- 银行/发票 reset 的文件子状态：active import file -> `deleting` -> `deleted`。文件缺失按幂等删除成功处理；删除异常保留 `deleting` 并使 job failed。
- OA reset 的下游状态独立流转：`rebuild_pending` -> read model `refreshing` -> `fresh`，或 -> `failed`。
- `impact_preview` -> `password_pending` -> `password_failed`
- `reset_running` -> `reset_failed`；worker 重启发现未知的 destructive `running` job 时必须 fail closed，禁止自动重放。
- `reset_running` -> `reset_partial`
- `reset_failed` / `reset_partial` -> 运维 acknowledge / repair / retry，不允许自动伪装成功

## 禁止流转

- `password_failed` -> 任何删除、state save、job create、rebuild 或 read model invalidation。
- fingerprint、receipt、原因或同身份 OA 登录复核任一缺失/变化 -> job/outbox/删除。
- worker 未在目标表锁内重算出相同 fingerprint，或 receipt 不属于当前 job -> 删除。
- `reset_running` 时同一 owner 创建第二个 data reset job。
- 删除 `protected_targets` 中任意目标。
- 重置后把旧 read model/cache 标成 `fresh`。
- reset 请求/job 线程调用 Workbench 全页 query、OA 行投影或 OCR，并据此把 `rebuild_status` 标成 `completed`。
- 在 `settings_reset_completed` lifecycle 已登记 matching dirty scopes 后再走一条重复 enqueue 路径。
- 在 job payload、error、audit summary、App Health payload、前端 state 中保存或回显 `oa_password`。
- settings maintenance worker 绕过 pidfile owner/命令行校验向任意进程发送 reload signal，或在 reload 失败时把 job 标成成功。
- OA reset 删除纯银行+发票 relation，或绕过 OA 保留月份策略全量扫描/重建。

## UI 状态

| UI 状态 | 触发 | 要求 |
| --- | --- | --- |
| loading | Settings payload、reset active job、App Status 并行加载 | 不误显示可执行成功状态 |
| empty | 无 active reset job | 仅表示当前没有运行中 data reset，不表示下游 read model fresh |
| password dialog | 用户确认 impact 与恢复点后 | 原因必填；密码只保留在当前交互，不落入 job/result payload |
| running/progress | job active 或同步请求进行中 | 展示 phase/current/total/percent/message；路由切换后可恢复 |
| error | 密码失败、job failed、active job query 失败 | 明确错误反馈；不显示成功 toast |
| stale/refreshing | 重置后下游 read model/worker 正在刷新 | 由 App Status 或下游页面展示，Settings 自身不能假定全部完成 |
| permission hidden/disabled | 非 admin、read-only、session missing/expired | 隐藏或禁用重置入口，后端仍必须拒绝 |

## Read Model / Worker 状态

| 状态 | 来源 | 要求 |
| --- | --- | --- |
| `fresh` | 下游 read model readiness/source version | 只有 worker/projection 证明 fresh 后页面才能显示 fresh |
| `missing` | reset 清理 projection 或 readiness 不存在 | API/query gateway 应 enqueue refresh 或返回 refreshing/unavailable |
| `refreshing` | dirty scope pending/processing、background job running | 页面显示刷新中；不能把空 rows 当真实无数据 |
| `stale` | source/schema mismatch、dirty scope 覆盖同一 scope | 必须继续 refresh；App Status yellow/busy |
| `failed` | rebuild/job/worker failed | App Health attention；需要 inspect/retry/repair |
| `unavailable` | PostgreSQL/worker/runtime monitoring 不可用 | route 映射不可用状态；不能吞掉错误 |

## refresh 触发来源

- `settings_reset_completed` lifecycle event，`include_all=True`。
- `reset_oa_and_rebuild` 复用 `settings_reset_completed` 的 Workbench read model refresh 与 matching dirty scope；不得额外重复 enqueue。
- 发票或 OA reset 后的 historical ETC repair。
- 后续 read model query miss/stale enqueue。
- Workbench stale scan 只由 matching worker 启动；API 进程初始化不得触发 scan、historical ETC reconcile 或 interrupted job recovery。reset 主链路仍由 `settings.data_reset.requested` worker、`settings_reset_completed` 和显式 read-model refresh 完成。

## 失败恢复

1. 先查 Settings data reset job payload，确认 action、phase、message、result。
2. 查 App Health/App Status，确认 background job、dirty scopes、worker readiness 和 dependency 状态。
3. 查 `protected_targets` 和 state store/import file 状态，确认是否出现半删除。
   - `deleting` 表示待重试清理，不得手工伪改 `deleted`；修复存储依赖后重跑同一 reset action。
4. 对 read model stale/missing 先 requeue/rebuild，不直接手改 fresh。
5. 涉及真实生产数据时先恢复到 staging 验证，再决定生产 repair 或 PITR。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-08-09 | 增加同身份 OA 登录复核、影响 fingerprint 与恢复凭证 gate | 未知 OA 结果 fail closed；恢复凭证/job/outbox/queued audit 原子提交；worker 锁表后重算范围并记录 started/terminal audit | `tests.test_oa_identity_service`、`tests.test_settings_data_reset_guard`、`tests.test_settings_data_reset_job`、`tests.test_runtime_infrastructure_postgres_integration` |
| 2026-08-01 | data reset 改为独立 durable `settings-maintenance` worker | API 只校验/建 job/入队；密码不持久化；中断 destructive job fail closed；成功后安全 reload API runtime 清除进程内状态 | `tests.test_settings_data_reset_job`、`tests.test_runtime_worker_registry`、`tests.test_platform_runtime_boundary_guards` |
| 2026-07-30 | 银行/发票 reset 增加 `deleting -> deleted` 文件清理意图 | 移除已删除 `import_batch_id` fallback；数据库提交与文件删除之间的失败可诊断、可幂等重试 | `tests.test_postgres_state_store`、`tests.test_postgres_state_store_integration` |
| 2026-07-16 | OA reset 改为 durable lifecycle 后返回 `rebuild_status=pending` | 删除同步 Workbench 全页 completion probe 与重复 matching enqueue，区分 reset job 完成和 read model fresh | `tests.test_settings_data_reset_service` |
| 2026-06-11 | 补齐 data-safety-reset 状态机 | 明确密码校验、job、protected target、read model/worker 和 UI 状态 | 待本轮模块验证 |
