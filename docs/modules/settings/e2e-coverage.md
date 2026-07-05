# 设置 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的设置 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `SETTINGS-E2E-001` | `covered` | `web/e2e/settings-data-reset-flow.spec.ts`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`tests/test_app_settings_service.py` | Browser 覆盖 `/settings` ready、标题、分类树、数据重置和项目状态 section；组件/API 覆盖普通 settings shape、snake/camel mapper、settings payload 不包含 OA secret，且前端不回传银行自动标签写字段。 |
| `SETTINGS-E2E-002` | `covered` | `web/e2e/settings-data-reset-flow.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/src/test/SettingsPage.test.tsx`、`tests/test_app_settings_service.py`、`tests/test_derived_data_lifecycle_service.py`、成本统计 API/read model tests | Browser 覆盖项目标记完成、保存 settings、POST body `completed_project_ids`、进入成本统计后 active scope fresh 排除已完成项目、项目范围切换 UI 不出现，并检查成功后无可见错误残留；`project_scope=all` 已从当前页面 UI 删除，保留为成本统计 API/read model 合同覆盖。后端覆盖 project scope lifecycle/dirty fan-out。 |
| `SETTINGS-E2E-003` | `covered` | `web/e2e/settings-data-reset-flow.spec.ts`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`tests/test_settings_data_reset_service.py` | Browser 覆盖数据重置影响确认、OA 密码复核、POST job 202、job polling、settings reload、成功反馈、严格浏览器错误捕获和成功后无可见错误残留；组件/后端覆盖 progress/reentry 和错误 UI。 |
| `SETTINGS-E2E-004` | `covered` | `tests/test_settings_data_reset_service.py`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`tests/test_app_status_overview_service.py` | 后端覆盖 protected targets、active job、并发 409、密码校验失败、reset OA rebuild、失败不泄密、不清数据和 job 状态；组件覆盖 cancel、password failure、reentry 和 progress。真实生产 reset 仍归 `SETTINGS-E2E-010`。 |
| `SETTINGS-E2E-005` | `covered` | `tests/test_oa_applicant_credentials_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`、`tests/test_target_oa_applicant_token_provider.py`、`web/src/test/SettingsPage.test.tsx` | 覆盖 admin-only、密码必填、列表不回显、settings payload 不泄密、PG 加密存储、target OA token provider 通过 credential service 获取密码和外部失败语义。 |
| `SETTINGS-E2E-006` | `covered` | `tests/test_app_settings_service.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/SettingsPage.test.tsx`、`tests/test_derived_data_lifecycle_service.py`、`web/e2e/bank-details-auto-tag-rules-flow.spec.ts` | settings service/API 覆盖 pending invoice rules version/audit/fan-out，并拒绝 `bank_transaction_tags` 写入；银行自动标签规则保存/reapply 由 bank-details Browser E2E 作为所属页面覆盖。 |
| `SETTINGS-E2E-007` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`tests/test_workbench_settings_sync_api.py`、`tests/test_oa_manual_import_api.py`、`tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_api.py` | Role matrix 覆盖 settings 高风险入口和 forbidden/expired gate；组件/API 覆盖只读隐藏/禁用、直接 mutation 拒绝、body actor 伪造拒绝、下游写服务零调用。 |
| `SETTINGS-E2E-008` | `covered` | `tests/test_oa_manual_import_api.py`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | 覆盖 refresh attachments、manual import create/delete 的 mutation gate、session actor 优先和 read-only 403；真实 OA 外部系统归 staging 风险。 |
| `SETTINGS-E2E-009` | `covered` | `tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/settings-data-reset-flow.spec.ts` | 后端覆盖 lifecycle、App Status overview、worker/readiness registry；Browser 通过项目范围到成本统计 fresh read model 证明关键下游读取不使用旧数据；更多页面最终 UI 由各页面 Spec-first 覆盖。 |
| `SETTINGS-E2E-010` | `external-risk` | `bash scripts/verify.sh infra-smoke` staging gate、runtime worker/read model tests、data reset service tests、write-operation SLO audit profiles | 本地 contract 覆盖 job、dirty scope、worker registry、App Status 和 Browser 用户路径；真实 PostgreSQL/RabbitMQ/Redis/systemd/OA/对象存储、生产备份恢复和全页面 drain 必须在 staging/runtime smoke 验证。 |

## Operation latency baseline

`web/e2e/settings-data-reset-flow.spec.ts` 已接入 Playwright `operation-latency-*.json` 附件。本轮记录的设置页操作覆盖：设置页打开、数据重置 section 切换、清除银行流水影响确认、继续到 OA 密码复核、OA 密码填写、确认清理 POST 202 到首个 25% 进度反馈、data reset job polling 到完成、reset 后进入银行明细和待找发票验证 fresh read model、项目状态 section 打开、项目标记完成、保存设置、进入成本统计 active scope fresh 视图，以及切换按项目统计确认已完成项目不出现在 active scope。

## 下一轮补测建议

1. staging 运行真实 data reset smoke：备份、pause/drain、reset、worker 恢复、Redis/cache 清理、全页面 fresh。
2. staging 运行 settings project scope 和 pending invoice rules 的真实 write-operation SLO audit，确认 dirty scopes 到 worker fresh 的端到端时延。
3. staging 验证真实 OA applicant credential 登录、token、草稿和权限失败不泄密。
4. 若新增 settings section 或 mutation route，补 `read_export_only` 直接 API 拒绝和 Browser 零 durable mutation 回归。
