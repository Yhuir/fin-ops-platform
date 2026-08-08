# 数据安全与重置模块边界与 I/O

日期：2026-07-16

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：所有数据重置通过 `SettingsDataResetService`、durable event 和独立 `settings-maintenance` worker 执行，必须可审计、可阻断误用、可验证。
- 当前缺口：无 final closure blocker；真实 PostgreSQL/PITR、对象存储恢复、Redis/RabbitMQ/systemd worker drain 和大库收敛仍是 staging/operations smoke 风险，不阻塞模块边界 close。
- 旧代码删除条件：旧 reset script/API 不再绕过 service；旧内存 data reset job path 不得回归；Workbench reset 清理不得通过 broad state payload 写跨域 state。

## 职责边界

### 负责

- 设置页数据重置、durable reset job、进度查询和安全防护。
- API 只校验 admin/当前 OA 密码并写 job + durable outbox；独立 worker 执行清理、read model/matching enqueue 和 API graceful reload。
- 重置后只触发 derived lifecycle/read model rebuild 队列；不在 API 请求线程中执行重置、查询、投影或组装下游页面 payload。
- 运维脚本和生产安全约束。

### 不负责

- 不承载普通业务写操作。
- 不直接绕过 service 清理生产数据。
- 不在前端保存 reset secret 或跳过权限。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Reset request | Settings page/API | 必须由真实 OA admin session 授权并用当前 OA 密码复核；不存在本地固定 token/默认密码；一次用户意图生成稳定 `idempotency_key`，缺失时 API fail closed。 |
| Reset job poll | frontend/app health | 只读 job 状态 |
| Script invocation | `scripts/reset_demo_db.sh` | 仅符合运维边界 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Reset job | `BackgroundJobService` + `settings.data_reset.requested` | PostgreSQL 生产路径在一个事务中同时写 background job 与 outbox；任一写入失败整体回滚。相同 key/action 重放同一 job，不重复入队；相同 key/不同 action 冲突。密码不得进入 job/outbox；未知的 interrupted destructive reset 不自动重放。 |
| Lifecycle event | derived data lifecycle | `settings_reset_completed` 等显式事件 |
| Read model invalidation | runtime queue/app status | 不留下伪 fresh |
| OA rebuild status | reset API/job caller | durable lifecycle 成功登记后返回 `pending`；只有下游 worker/read model 自己能证明 fresh，reset 不得返回同步 `completed`。 |
| Import file cleanup intent | `app.import_files.status` | PostgreSQL 事务内从 active 状态转为 `deleting`；物理文件/对象删除成功后转为 `deleted`，失败保留 `deleting` 供原 reset job 重试。 |

## 持久化与投影

- Own read model：无。
- 影响 read model：全部或大部分 read model。
- Service owner：`SettingsDataResetService`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend service | `backend/src/fin_ops_platform/services/settings_data_reset_service.py`、`settings_data_reset_job.py`、`settings_data_reset_request.py`、`postgres_repositories/settings_data_reset.py`、`postgres_repositories/settings_data_reset_request.py` |
| File cleanup | `backend/src/fin_ops_platform/services/postgres_state_store.py` |
| Backend route | `routes_settings.py` 的 data reset job endpoints；旧同步 `POST /api/workbench/settings/data-reset` 已删除 |
| Job/worker | `BackgroundJobService`、`settings_data_reset`、`settings-maintenance` registration；旧 executor/thread 与 `DataResetJob` / `_data_reset_jobs` 内存路径已删除 |
| Lifecycle | `derived_data_lifecycle_service.py` |
| Frontend | `web/src/pages/SettingsPage.tsx`、`web/src/components/workbench/SettingsDataResetDialogs.tsx` |
| Operations | `scripts/reset_demo_db.sh`、`docs/operations/data-safety.md` |
| Tests | `tests/test_settings_data_reset_service.py`、`web/e2e/settings-data-reset-flow.spec.ts` |

## 依赖方向

- 允许依赖：`BackgroundJobService`、`RuntimeQueueRepository`、`ReadModelRefreshGateway`、state store 的显式 save/load ports。
- 必须通过：`SettingsDataResetService`、durable queue 和 `settings-maintenance` worker。
- 禁止绕过：直接数据库清理；绕过真实 OA admin session/当前 OA 密码/审计执行 reset；恢复本地固定 token、默认密码或旧内存 job；通过 broad state payload 清理 Workbench relation/read-model state；调用 Workbench 全页 builder、同步读取页面 projection 或重复登记 matching dirty scope 来伪造重建完成。

## 测试与验证

- `tests/test_settings_data_reset_service.py`
- `tests/test_settings_data_reset_job.py`
- `tests/test_runtime_infrastructure_postgres_integration.py`
- `web/e2e/settings-data-reset-flow.spec.ts`

## 当前缺口和删除条件

- 生产数据操作必须同步 operations 文档和回滚/备份策略。
- PostgreSQL reset 只按 `raw_payload.normalized_payload.batch_type/override_batch_type` 识别导入文件；已删除的 `app.import_files.import_batch_id` 不得作为 fallback 回归。
- 本地可执行边界已 close；真实基础设施恢复、worker drain 和大库最终 fresh 只能由 staging/production smoke 证明，作为运维风险跟踪。
- OA reset job 的 `completed` 只证明清理与 durable lifecycle 登记完成；`rebuild_status=pending` 到最终 fresh 的收敛由关联台 worker/read model 状态负责。
