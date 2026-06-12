# 数据安全与重置 状态机

> 修改 `数据安全与重置` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。

## 业务状态

| 状态 | 事实源 | 说明 |
| --- | --- | --- |
| `impact_preview` | 前端固定文案 + API `supported_actions` / `protected_targets` | 用户确认影响面；不能绕过管理员权限和 OA 密码校验 |
| `password_pending` | Settings/Workbench UI | 已选择重置动作，等待当前 OA 密码 |
| `password_failed` | API `403 oa_password_verification_failed` 或 `401/502/503` | 不允许执行任何删除、重建或 job 创建；响应不得回显密码 |
| `password_verified` | `_validate_settings_data_reset_request` | 仅表示当前请求可继续，不持久化密码 |
| `reset_queued` | `BackgroundJobService.create_job(type="settings_data_reset")` | 异步重置排队，`source/result_summary` 只能保存 action 等非敏感字段 |
| `reset_running` | background job `status=running` + progress | UI 可离开后恢复；同 owner 再提交必须返回 `409 settings_data_reset_job_running` |
| `reset_succeeded` | job `succeeded` / serialized `completed` | 删除和派生生命周期执行完成；仍需依赖 App Status/read model 验证最终 fresh |
| `reset_failed` | job `failed` 或同步 API structured error | 必须进入 App Health attention；保留错误但不泄露密码 |
| `reset_partial` | result `status=partial` 或 `rebuild_status=failed` | 按 failed job 处理；用户需要运维检查 affected scopes 和 rebuild status |
| `protected_target_skipped` | `protected_targets` payload + service 删除规则 | 受保护目标不应被删除；新增目标必须补测试 |

## 允许流转

- `impact_preview` -> `password_pending` -> `password_verified` -> `reset_queued` -> `reset_running` -> `reset_succeeded`
- `impact_preview` -> `password_pending` -> `password_failed`
- `reset_running` -> `reset_failed`
- `reset_running` -> `reset_partial`
- `reset_failed` / `reset_partial` -> 运维 acknowledge / repair / retry，不允许自动伪装成功

## 禁止流转

- `password_failed` -> 任何删除、state save、job create、rebuild 或 read model invalidation。
- `reset_running` 时同一 owner 创建第二个 data reset job。
- 删除 `protected_targets` 中任意目标。
- 重置后把旧 read model/cache 标成 `fresh`。
- 在 job payload、error、audit summary、App Health payload、前端 state 中保存或回显 `oa_password`。
- OA reset 删除纯银行+发票 relation，或绕过 OA 保留月份策略全量扫描/重建。

## UI 状态

| UI 状态 | 触发 | 要求 |
| --- | --- | --- |
| loading | Settings payload、reset active job、App Status 并行加载 | 不误显示可执行成功状态 |
| empty | 无 active reset job | 仅表示当前没有运行中 data reset，不表示下游 read model fresh |
| password dialog | 用户确认 impact 后 | 密码只保留在当前交互，不落入 job/result payload |
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
- `reset_oa_and_rebuild` 后的 Workbench matching dirty scope reset/rebuild。
- 发票或 OA reset 后的 historical ETC repair。
- 后续 read model query miss/stale enqueue。
- `startup_stale_scan` 默认关闭；启用时只标记 stale workbench matching dirty scopes；reset 主链路仍由 `settings_reset_completed` 和 reset job 显式清理/重建 read model。

## 失败恢复

1. 先查 Settings data reset job payload，确认 action、phase、message、result。
2. 查 App Health/App Status，确认 background job、dirty scopes、worker readiness 和 dependency 状态。
3. 查 `protected_targets` 和 state store/import file 状态，确认是否出现半删除。
4. 对 read model stale/missing 先 requeue/rebuild，不直接手改 fresh。
5. 涉及真实生产数据时先恢复到 staging 验证，再决定生产 repair 或 PITR。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐 data-safety-reset 状态机 | 明确密码校验、job、protected target、read model/worker 和 UI 状态 | 待本轮模块验证 |
