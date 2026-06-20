# 数据安全与重置 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 当前入口 | 必测原因 |
| --- | --- | --- |
| 管理员权限/OA 密码 | `server.py` data reset routes、`OAIdentityService` | 防止非管理员或失效密码触发危险删除；响应不能泄露密码 |
| 重置 service | `SettingsDataResetService` | 删除目标、保留目标、文件清理、状态写入必须稳定 |
| protected targets | `SettingsDataResetService.protected_targets()` | 防止误删 OA 源表、app settings、metadata、import metadata |
| 后台 job | `BackgroundJobService` + `/data-reset/jobs*` | 页面离开后可恢复进度；并发提交必须互斥；失败要可诊断 |
| 派生生命周期 | `_execute_derived_data_lifecycle_event("settings_reset_completed")` | 重置后旧 read model/cache 不能伪装 fresh |
| OA rebuild | `reset_oa_and_rebuild` 路径、OA adapter、workbench rebuild | OA 重建要受保留月份和配置表单限制，不能破坏纯银行+发票关系 |
| App Health/App Status | `tests/test_app_health_api.py`、App Status overview | running/failed/partial reset job 必须进入全局状态平面 |
| 设置页 UI | `SettingsPage`、`SettingsDataResetDialogs`、Workbench 内设置入口 | 影响确认、密码弹窗、progress reentry、错误反馈、权限隐藏 |
| 备份/导出 | `tests/test_export_app_mongo.py`、operations docs | 当前自动化覆盖导出只读和不可覆盖；真实 PostgreSQL/PITR/对象存储恢复仍需 staging |

## 场景覆盖清单

| 场景 | 覆盖入口 | 状态 |
| --- | --- | --- |
| 银行流水重置保留发票并保护 OA 源表 | `tests/test_settings_data_reset_service.py` | 已覆盖 |
| 发票重置清理税金认证记录并保护银行事实 | `tests/test_settings_data_reset_service.py` | 已覆盖 |
| OA 重置按保留月份重建、限制表单/状态、复用附件发票缓存 | `tests/test_settings_data_reset_service.py` | 已覆盖 |
| OA pair relation 删除但纯银行+发票 relation 保留 | `tests/test_settings_data_reset_service.py` | 已覆盖 |
| 缺失/错误 OA 密码不清数据、不重建、不泄露密码 | `tests/test_settings_data_reset_service.py` | 已覆盖 |
| 后台 reset job 可创建、查询、恢复 active progress，不保存密码 | `tests/test_settings_data_reset_service.py` | 已覆盖 |
| 并发 reset job 返回 `409 settings_data_reset_job_running` 且不泄露密码 | `tests/test_settings_data_reset_service.py` | 2026-06-11 新增 |
| failed/partial/interrupted background job 进入 App Health attention | `tests/test_app_health_api.py`、`tests/test_background_job_service.py` | 已覆盖 |
| legacy app Mongo export manifest、NDJSON counts、只读 store、不可覆盖目录 | `tests/test_export_app_mongo.py` | 已覆盖 |
| runtime state policy 对 active/attention/background jobs 的镜像写入约束 | `tests/test_runtime_state_policy.py` | 已覆盖 |
| Settings/Workbench UI 的 impact confirmation、OA password、progress reentry、权限隐藏、多页面 fresh contract | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/e2e/settings-data-reset-flow.spec.ts` | 已覆盖；Browser e2e 覆盖真实 Chromium 下设置页影响确认、OA 密码复核、job polling、完成后 reload 与全局反馈，并在 reset 完成后进入银行明细验证 fresh empty、进入待找发票验证 fresh rows。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 当前结论 | 缺口等级 | 维护要求 |
| --- | --- | --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_settings_data_reset_service.py` | 覆盖 action、protected targets、bank/invoice/OA relation 保留删除规则、unsupported action | 无 P0 | 新增 reset action 或删除规则时必须先补 service 规则测试 |
| 2. Service-layer tests | 适用 | `tests/test_settings_data_reset_service.py`、`tests/test_background_job_service.py`、`tests/test_export_app_mongo.py` | 覆盖 state store 清理、文件删除调用、job 进度、payload sanitize、只读导出 | P1 | PostgreSQL PITR/对象存储备份恢复未本地自动化 |
| 3. API contract tests | 适用 | `tests/test_settings_data_reset_service.py` | 覆盖 admin-only、密码失败、同步 reset、job create/query/active、并发 409、protected_targets、敏感字段不泄露 | 无 P0 | 修改 route/error/status/job shape 时同步补契约断言 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_settings_data_reset_service.py`、`tests/test_app_health_api.py`、`tests/test_background_job_service.py`、`tests/test_runtime_state_policy.py` | 覆盖 lifecycle fan-out、cost statistics clear、job attention/active、runtime state policy | P1 | 真 Redis cache、真实 Postgres dirty/outbox/worker drain 需要 staging/nightly smoke |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖确认、密码弹窗、cancel、错误、progress reentry、权限隐藏；Browser e2e 覆盖真实页面 job polling/reload 和 reset 后跨页读取银行明细/待找发票 fresh contract | P1 | 真实浏览器视觉、长任务 progress、网络断开恢复需 smoke |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_settings_data_reset_service.py` 间接集成；`web/e2e/settings-data-reset-flow.spec.ts` 覆盖 UI -> job -> reload -> downstream reads | 覆盖 reset -> lifecycle/rebuild -> API payload 的核心路径，以及设置页发起 job 到 reload，再进入银行明细 fresh empty 和待找发票 fresh rows 的浏览器路径 | P1 | 真实导入数据 -> reset -> worker drain -> 多页面最终 fresh 需 staging smoke |
| 7. Existing feature regression tests | 适用 | 各业务模块测试 + 本模块 reset 测试 | 覆盖银行/发票/OA/ETC/成本/App Health 关键旧行为 | 无 P0 | 每次改 reset action 必须列出旧页面/API/read model/export/权限影响面 |

## 历史 bug 回归库

| 日期 | 失败模式 | 回归测试 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 并发 data reset 可能重复创建危险后台任务，导致删除动作重入或 UI 进度错乱 | `test_reset_job_api_rejects_concurrent_job_without_echoing_password` | `PYTHONPATH=backend/src python3 -m unittest tests.test_settings_data_reset_service.SettingsDataResetServiceTests.test_reset_job_api_rejects_concurrent_job_without_echoing_password -v` |
| 2026-06-17 | data reset 缺少真实浏览器闭环，无法证明影响确认、OA 密码复核、job polling、settings reload 和全局反馈在 Chromium 下可连续完成 | `web/e2e/settings-data-reset-flow.spec.ts` | `cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts` |
| 2026-06-20 | data reset 完成后浏览器只停在 Settings 成功反馈，未证明受影响页面会重新读取 fresh read model 或避免旧银行流水残留 | `web/e2e/settings-data-reset-flow.spec.ts` | reset 后继续打开银行明细，断言 `read_model_status=fresh` 且旧流水为空；再打开待找发票，断言 `pending_invoice` fresh rows 可见 |
| 既有 | 错误/缺失 OA 密码后仍清数据或回显密码 | `test_reset_api_rejects_missing_oa_password_without_clearing_data`、`test_reset_api_rejects_wrong_oa_password_without_clearing_data_or_echoing_secret`、`test_reset_api_does_not_leak_oa_password_when_verification_service_fails` | 模块后端验证 |
| 既有 | OA reset 删除纯银行+发票关系或重复解析附件发票 | `test_reset_oa_and_rebuild_preserves_pure_bank_invoice_pair_relation`、`test_reset_oa_and_rebuild_reuses_cached_attachment_invoices_without_reparsing` | 模块后端验证 |
| 既有 | failed/partial reset job 不进入运维 attention | `test_app_health_reports_unacknowledged_failed_and_partial_success_jobs_as_attention`、`test_app_health_marks_interrupted_job_without_source_not_retryable_but_acknowledgeable` | 模块后端验证 |

## 关键 smoke flows

- 生产前 staging：备份 PostgreSQL / 对象存储 / runtime config -> 执行一种 reset -> worker drain -> App Health 绿灯 -> 多页面确认 fresh。
- 银行 reset：导入银行+发票 -> 建立匹配 -> reset bank -> 银行事实清空，发票事实和受保护目标保留，关联台/read model 刷新。
- 发票 reset：导入银行+发票+税金认证 -> reset invoices -> 税金和发票相关页面刷新，银行事实保留。
- OA reset：准备 OA 历史月份、附件发票、纯银行+发票关系 -> reset OA -> 只按保留月份重建，纯 relation 保留，OA relation 清理。
- UI 恢复：Settings 发起 job -> 离开页面 -> 回到 Settings -> active job progress 恢复；并发提交返回 409。
- Browser e2e：Settings 数据重置 -> 影响确认 -> OA 密码复核 -> job create/polling -> settings reload -> 全局成功反馈 -> 银行明细 fresh empty -> 待找发票 fresh rows。

## 模块验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_settings_data_reset_service \
  tests.test_app_health_api \
  tests.test_background_job_service \
  tests.test_export_app_mongo \
  tests.test_runtime_state_policy \
  tests.test_platform_runtime_boundary_guards \
  -v

cd web && npm test -- --run \
  src/test/SettingsPage.test.tsx \
  src/test/WorkbenchSelection.test.tsx \
  src/test/AppHealthOperationsPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx \
  src/test/AppHealthStatusContext.test.tsx \
  src/test/AppHealthBroadcast.test.tsx

cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

- `bash scripts/verify.sh all` 覆盖全量后端 unittest、前端测试/build、deterministic Playwright browser smoke 和 docs；其中 `web/e2e/settings-data-reset-flow.spec.ts` 覆盖设置页 data reset 浏览器闭环。
- 远端 nightly CI 能降低本地漏跑风险，但不能证明真实生产数据、真实 OA、真实 Redis/RabbitMQ/systemd worker、真实对象存储和 PITR 恢复。

## 未测风险

- 真实 PostgreSQL 备份/PITR/staging restore、对象存储快照、Nginx/systemd/runtime config 备份恢复不在本地 unittest 内。
- 真 Redis cache 和 RabbitMQ transport 只能通过 runtime/staging smoke 证明，不应靠 mock 测试宣称完全闭环。
- 大生产库 reset 后 worker drain、dirty/outbox 清理、App Health 收敛、页面最终 fresh 需要 staging 数据量验证。
- 真实 OA Mongo 字段漂移、OA 草稿/附件、目标申请人登录仍由 OA 集成模块和 staging smoke 覆盖。
