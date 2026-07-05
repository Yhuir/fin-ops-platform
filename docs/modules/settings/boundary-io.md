# 设置模块边界与 I/O

日期：2026-07-05

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：设置页面只通过 settings API/route owner/service 修改配置、OA 凭证、数据重置等控制面能力。
- 当前缺口：无已知阻断项；真实生产 reset、真实 OA、worker drain 和多页面 smoke 仍属于运维验证风险。
- 旧代码删除状态：`server.py` 中 `/api/workbench/settings*` 旧 handler、settings data reset job handler、OA 手工导入 settings handler 已删除；`AppSettingsService` 不再用内存 `_snapshot` 补齐持久化 settings 缺失字段。

## 职责边界

### 负责

- 平台设置页面、工作台设置、OA 凭证设置、数据重置入口。
- 调用 app settings、credential provider、data reset service。
- 设置变更后触发必要 lifecycle/read model invalidation。

### 不负责

- 不直接执行业务导入或 read model projection。
- 不在前端保存敏感凭证。
- 不绕过数据安全 reset service。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 设置表单 | `SettingsPage.tsx`、`components/settings/*` | API 负责校验和权限 |
| OA credentials | settings/OA credential API | secret 不进入日志 |
| 数据重置请求 | settings data reset dialogs | 必须走 job/control service |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 设置 payload/result | 前端页面 | 不泄露 secret |
| Reset job | background job/app health | 可查询、可恢复 |
| Dirty scope/lifecycle | runtime queue | 设置影响 read model 时必须显式触发 |
| OA manual import target envelope | operation barrier/frontend refresh | OA 手工导入、附件刷新、删除导入标记返回的 `operation_barrier_targets` 必须被设置页等待后再展示最终 fresh 状态 |
| 银行账户映射只读 payload | cost_statistics projection/query source version | `AppSettingsService.get_cost_statistics_source_settings_payload()` 可一次性输出 `bank_account_mappings` 与 `bank_transaction_tags`，供成本统计计算 `bank_accounts` 和 source version；下游不得直接读取设置页前端状态 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 影响 read model：设置重置可能影响全部 read model。
- OA 手工导入设置入口会影响 `workbench`、`workbench_relation`、`invoice_lifecycle`、`tax_offset`、`search`、`cost_statistics`，不拥有这些 read model。
- Services：`AppSettingsService`、`SettingsDataResetService`、OA applicant credentials。`AppSettingsService.get_cost_statistics_source_settings_payload()` 是成本统计读取银行账户映射与自动标签规则版本的受控 read port，避免成本统计页面直接调用 settings API。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/SettingsPage.tsx` |
| Frontend components | `web/src/components/settings/*`、`web/src/components/workbench/WorkbenchSettingsModal.tsx` |
| Frontend API | `web/src/features/workbench/api.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_settings.py`；`server.py` 只负责 route owner 组装和 runtime side-effect ports |
| Backend service | `app_settings_service.py`、`settings_data_reset_service.py`、`oa_applicant_credentials.py`、`target_oa_applicant_token_provider.py` |
| Repository | `postgres_repositories/oa_applicant_credentials.py` |
| Lifecycle | `derived_data_lifecycle_service.py`、`app_status_domain_registry.py`、`app_status_read_model_registry.py` |
| Tests | `tests/test_app_settings_service.py`、`tests/test_settings_data_reset_service.py`、`web/src/test/Settings*.test.*` |

## 依赖方向

- 允许依赖：settings/data reset service, credential repository, background job service。
- 必须通过：settings service and explicit reset job API。
- 禁止绕过：前端直接保存 secret；settings API 直接清库或直接写 read model。

## 测试与验证

- `tests/test_app_settings_service.py`
- `tests/test_settings_data_reset_service.py`
- `web/e2e/settings-data-reset-flow.spec.ts`
- `web/src/test/SettingsOaManualSearchImportTable.test.tsx`

## 当前缺口和删除条件

- Route owner 已拆分为 `SettingsApiRoutes`；`server.py` 不再拥有 settings HTTP I/O 解析、body 校验或 settings response shape。
- 重置行为变更必须先读 data-safety-reset boundary。

## Canonical facts ownership

- Owned facts: `app.app_settings` 中的业务设置 facts。
- Shared facts: `app.oa_applicant_credentials` 由 `oa-integration` credential owner 管理。
- Allowed writes: settings service、明确 settings application boundary。
- Allowed reads: settings APIs、owner read ports。
- Downstream outputs: 按 setting family 产生 affected read model dirty scopes、domain events 或 explicit not-applicable；银行账户映射变化会通过成本统计 source version 的 `bank_account_mappings_fingerprint` 使旧 read model payload 失配并刷新。
- Forbidden paths: `state:*` JSON、`state:full_state` 或旧 snapshot 不得作为 production 业务事实 fallback；其它模块不得直接写 settings store。
- Old code deletion: legacy settings snapshot、state JSON fallback、route-inline settings writes 和内存 `_snapshot` 持久化补字段 fallback 已删除；migration/audit/rollback 工具保留不算 closure。
