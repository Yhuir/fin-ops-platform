# 数据安全与重置 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 2026-08-01 - Data reset durable execution 与 runtime reload 闭环

- 重置 API 不再执行或启动任何清理线程，只持久化非敏感 job/event；worker 从 PostgreSQL durable queue 领取并显式更新 lifecycle。
- destructive job 的未知中断状态禁止自动重放；queue 失败会同步把新 job 标为 failed，密码验证失败时零 job/零 queue write。
- worker 完成清理和 refresh 登记后，只向 systemd RuntimeDirectory 内、owner/cmdline 均校验通过的 Gunicorn pidfile 发送 reload；reload 失败使 job partial/failed，不能伪装成功。

## 当前决策

- data reset 是跨模块危险操作，不归入单一 Settings 页面测试；每次改动都必须按数据事实、文件/object storage、read model/worker、App Health、权限和旧页面影响面审计。
- `protected_targets` 是可执行契约，不只是文档说明；新增或改变目标必须补 service/API 回归。
- data reset 必须先通过管理员 session 和当前 OA 密码校验；密码不得进入 job payload、result、error、App Health 或前端持久 state。
- 并发 data reset job 必须互斥。同一 owner 有 active job 时，新的 job create 返回 `409 settings_data_reset_job_running` 并返回当前 job，前端用于恢复进度。
- data reset job 只能使用 `BackgroundJobService`；旧内存 `DataResetJob` / `_data_reset_jobs` path 已删除，不能回归。
- 本地自动化覆盖 reset 规则、API/job contract、UI 交互和 App Health attention。旧 App Mongo export 工具已删除；真实 PostgreSQL PITR、对象存储恢复、Redis/RabbitMQ/systemd worker drain 和大生产库收敛归入 `documented-risk`，由 staging/nightly/smoke 补。

## 历史记录

## 2026-07-30 - PostgreSQL reset 文件清理可重试闭环

- 根因：正式 migration 已删除 `app.import_files.import_batch_id`，但 reset repository 仍把它作为 batch type fallback 和 update 目标；同时数据库事务提交后才删除文件，删除异常会留下数据库已清理但文件状态不可恢复的半完成结果。
- 决策：只复用现有 `app.import_files.status` 和 background job，不新增队列或表。reset 事务按 `raw_payload.normalized_payload.batch_type/override_batch_type` 识别文件并标记 `deleting`；提交后现有 state store 幂等删除文件/对象并标记 `deleted`。
- 旧链路删除：移除全部 `app.import_files.import_batch_id` fallback/detach SQL；文件已经不存在时仍完成 metadata `deleted`，避免重试永久卡住。
- 失败语义：物理存储删除异常继续使 reset job failed，目标行保留 `deleting`；修复存储依赖后重跑相同 action 即可继续清理。
- 生产约束：本轮生产验证不得触发 data reset，只验证 schema、合同审计、部署和只读链路；真实 reset 仍需 staging 备份/恢复 smoke。

## 2026-07-16 - OA reset completion 与关联台 fresh 解耦

- 目标：移除 OA reset 请求/job 线程中的 Workbench 全页 completion probe，避免重置接口同步执行昂贵查询并误报重建完成。
- 影响范围：`Application._execute_settings_data_reset(...)`、Settings data reset API/job contract、关联台 lifecycle dirty scope、模块测试与状态机。
- 关键决策：复用现有 `settings_reset_completed` durable lifecycle；成功登记后返回 `rebuild_status=pending`，登记 Workbench refresh/matching dirty scope 失败则返回 `status=partial`、`rebuild_status=failed`。不新增 projection、queue、poller 或兼容 fallback。
- 旧链路删除：删除 reset 内 `_build_api_workbench_payload("all")` 同步全页读取和第二次 `_schedule_or_run_workbench_auto_matching_for_scopes(...)`；Settings 测试不再调用旧 full builder 证明重建结果。
- 测试覆盖：reset service/API 覆盖 pending、lifecycle enqueue 失败、只登记一次 matching dirty scope、不同步构建 OA/Workbench rows、附件缓存保留且不在 reset 中 OCR；OA 过滤和缓存投影本身继续由 `tests/test_mongo_oa_adapter.py` 负责。
- 未测风险：真实 durable queue、worker drain、最终 active generation fresh 和大生产库耗时必须等所有 thread 合并并统一部署后验证；本轮不部署、不操作生产队列。

## 2026-07-05 - 模块边界 close 与旧 reset job path 删除

- 目标：完成 data-safety-reset 模块边界 close，确认危险重置入口只有 `SettingsDataResetService` + `BackgroundJobService`，并删除旧模块代码对新链路的污染。
- 发现：`server.py` 中仍保留不可达的旧内存 `DataResetJob` / `_data_reset_jobs` / `_run_settings_data_reset_job(...)` 路径；`SettingsDataResetService` 的银行/发票 reset 仍通过 broad `state_store.save({...})` 清理 Workbench relation/read-model state。
- 变更：删除旧内存 data reset job 实现；银行/发票 reset 继续用 `state_store.save(...)` 保存 imports/file_imports/matching 兼容聚合，但 Workbench overrides、pair relations、read models、candidate matches 和 matching dirty scopes 改走已有显式 save/port。
- Guard：`test_settings_data_reset_uses_background_job_service_only` 禁止旧内存 job path 回归；`test_settings_data_reset_pair_snapshot_uses_explicit_port` 收紧为禁止通过 broad state payload 清理 Workbench reset state。
- 结果：模块状态更新为 closed；真实 PostgreSQL/PITR、对象存储恢复、Redis/RabbitMQ/systemd worker drain 和大库最终 fresh 仍按 operations/staging smoke 跟踪，不作为本地模块边界 blocker。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/settings_data_reset_service.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_settings_data_reset_pair_snapshot_uses_explicit_port tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_settings_data_reset_uses_background_job_service_only -v
PYTHONPATH=backend/src python3 -m unittest tests.test_settings_data_reset_service -v
bash scripts/verify.sh docs
```

## 2026-06-20 - reset 后多页面 fresh Browser contract

- 目标：补齐 data reset Browser 主流程只停留在 Settings 成功反馈的缺口，让同一真实 Chromium flow 继续验证受影响页面会重新读取 fresh read model。
- 影响范围：`web/e2e/settings-data-reset-flow.spec.ts`、deterministic API mock、`e2e-coverage.md`、`tests.md`、全局 testing/inventory/closure state。
- 关键决策：只加固测试和 mock，不改产品逻辑；mock 在 reset job 完成后记录 completed action，`reset_bank_transactions` 使银行明细交易列表返回 fresh empty，用来表达“旧银行流水不能继续显示为 fresh”。
- 测试覆盖：Browser flow 在 job 202、polling、settings reload 后进入银行明细，断言 `bank_detail` rows `read_model_status=fresh` 且旧流水为空；再进入待找发票，断言 `pending_invoice` rows `fresh` 且业务行可见。
- 验证命令：`cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium` 通过 2 tests。
- 未测风险：真实 PostgreSQL PITR、对象存储恢复、Redis/RabbitMQ/systemd worker drain、大库 reset 后全页面最终 fresh 和真实 OA Mongo/附件仍需 staging/production gate。

## 2026-06-11 - 首轮 data-safety-reset 测试闭环

- 目标：审计数据重置、备份/导出、protected targets、state store 清理、read model dirty/worker/App Health、OA 密码校验和前端交互测试闭环。
- 影响范围：`SettingsDataResetService`、`server.py` data reset routes、`BackgroundJobService`、Settings/Workbench UI、App Health/App Status、read model/worker runtime 状态。
- 关键决策：补并发 job API 回归，防止 active reset 期间重复创建危险后台任务；真实基础设施和备份恢复风险记录为 documented-risk。
- 文档影响：补齐 `README.md`、`tests.md`、`state-machine.md`，并更新全局依赖地图和测试闭环状态。
- 测试覆盖：新增 `test_reset_job_api_rejects_concurrent_job_without_echoing_password`，覆盖 API contract、background job 并发互斥、旧功能回归和敏感字段不泄露。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_settings_data_reset_service.SettingsDataResetServiceTests.test_reset_job_api_rejects_concurrent_job_without_echoing_password -v`
  - 本轮模块验证命令见 `docs/modules/data-safety-reset/tests.md` 和 `docs/dev/testing-closure-state.md`。
- 未测风险：真实 PostgreSQL/PITR/staging restore、对象存储备份恢复、真实 Redis/RabbitMQ/systemd worker drain、真实大库 reset 后多页面最终 fresh、真实 OA Mongo/草稿/附件。
- 后续事项：发布前执行 staging data reset smoke；deploy 模块继续审计 nightly/deploy smoke 与生产入口。
