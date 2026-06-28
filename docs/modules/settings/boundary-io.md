# 设置模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：设置页面只通过 settings API/service 修改配置、OA 凭证、数据重置等控制面能力。
- 当前缺口：`server.py` 仍保留部分设置 endpoint，数据重置和 OA 凭证横跨多个模块。
- 旧代码删除条件：设置相关 endpoint 全部有 route/service owner，前端不再调用 legacy path。

## 职责边界

### 负责

- 平台设置页面、工作台设置、OA 凭证设置、数据重置入口。
- 调用 app settings、credential provider、data reset service。
- 设置变更后触发必要 lifecycle/direct API refetch signal。

### 不负责

- 不直接执行业务导入或页面投影。
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
| Lifecycle/outbox | runtime queue | 设置影响下游页面时必须显式触发 |
| OA manual import result | frontend refresh | OA 手工导入、附件刷新、删除导入标记返回业务结果和 `affected_scope_keys`；设置页直接重读列表，不等待 operation barrier |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 影响页面：设置重置可能影响全部 direct API 页面。
- OA 手工导入设置入口会影响 `workbench`、`workbench_relation`、`invoice_lifecycle`、`tax_offset`、`search`、`cost_statistics`，不拥有这些页面读取路径。
- Services：`AppSettingsService`、`SettingsDataResetService`、OA applicant credentials。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/SettingsPage.tsx` |
| Frontend components | `web/src/components/settings/*`、`web/src/components/workbench/WorkbenchSettingsModal.tsx` |
| Frontend API | `web/src/features/workbench/api.ts` |
| Backend route | settings endpoints in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `app_settings_service.py`、`settings_data_reset_service.py`、`oa_applicant_credentials.py`、`target_oa_applicant_token_provider.py` |
| Repository | `postgres_repositories/oa_applicant_credentials.py` |
| Lifecycle/runtime | `derived_data_lifecycle_service.py`、`app_status_domain_registry.py`、`app_status_job_registry.py`、runtime worker registry |
| Tests | `tests/test_app_settings_service.py`、`tests/test_settings_data_reset_service.py`、`web/src/test/Settings*.test.*` |

## 依赖方向

- 允许依赖：settings/data reset service, credential repository, background job service。
- 必须通过：settings service and explicit reset job API。
- 禁止绕过：前端直接保存 secret；settings API 直接清库或直接写页面投影。

## 测试与验证

- `tests/test_app_settings_service.py`
- `tests/test_settings_data_reset_service.py`
- `web/e2e/settings-data-reset-flow.spec.ts`
- `web/src/test/SettingsOaManualSearchImportTable.test.tsx`

## 当前缺口和删除条件

- 拆分 route owner 后同步本文件和 README。
- 重置行为变更必须先读 data-safety-reset boundary。
