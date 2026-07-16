# 设置模块边界与 I/O

日期：2026-07-16

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：设置页面只通过 settings API/route owner/service 修改配置、OA 凭证、数据重置等控制面能力。
- 当前缺口：页面/API 与 App 内部 control-plane Audit 已闭环；真实生产 reset、真实 OA/provider、credential 登录、worker drain 和多页面 smoke 仍属于外部运维 gate。
- 旧代码删除状态：`server.py` 中 `/api/workbench/settings*` 旧 handler、settings data reset job handler、OA 手工导入 settings handler 与 `_refresh_local_app_settings_snapshot(...)` 已删除；`AppSettingsService` 不再用内存 `_snapshot` 补齐持久化 settings 缺失字段，外部模块也不得直接读取或替换其 `_snapshot`。

## 职责边界

### 负责

- 平台设置页面、工作台设置、OA 凭证设置、数据重置入口。
- 调用 app settings、credential provider、data reset service。
- 设置变更后触发必要 lifecycle/read model invalidation。
- app settings 中跨模块只读/写控制面事实，例如成本统计标签规则。

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
| 页面 Audit | `GET /api/operations/app-health/page-audit?page=settings` | 管理员只读；同一 repeatable-read snapshot，禁止 secret/provider/reset mutation I/O |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 设置 payload/result | 前端页面 | 不泄露 secret |
| Reset job | process-owned `BackgroundJobService` / app health | 可查询、可恢复；OA reset 的 runtime service reload 必须复用同一 background-job owner，禁止在任务执行中替换实例、双写同一 job store 或把当前任务误标为进程重启中断。只有应用进程首次启动/真正重启才创建 owner 并执行 interrupted-job recovery。job `completed` 只证明清理和 durable lifecycle 登记完成；OA `rebuild_status` 在下游 fresh 前必须是 `pending`。 |
| Dirty scope/lifecycle | runtime queue | 设置影响 read model 时必须显式触发 |
| OA manual import target envelope | operation barrier/frontend refresh | OA 手工导入、附件刷新、删除导入标记返回的 `operation_barrier_targets` 必须被设置页等待后再展示最终 fresh 状态 |
| 银行账户映射只读 payload | cost_statistics projection/query source version | `AppSettingsService.get_cost_statistics_source_settings_payload()` 可一次性输出 `bank_account_mappings` 与 `bank_transaction_tags`，供成本统计计算 `bank_accounts` 和 source version；下游不得直接读取设置页前端状态 |
| 成本统计标签规则 payload | cost_statistics query/filter route | `AppSettingsService.get_cost_statistics_tag_selection_payload()` 输出归一后的收入/支出主子标签、虚拟 `__uncategorized__` 未分类标签、selection schema version 和 selected leaf codes；schema v2 默认全选当前有效收支标签，legacy 显式选择保留原支出选择并一次性加入当前有效收入标签。`update_cost_statistics_tag_selection(...)` 只持久化 `app.app_settings.cost_statistics_tag_selection` 并记录 audit，不写成本统计 read model、不入队 dirty scope |
| 外部往来标签选择事务端口 | turnover ledger local write UoW | 只允许调用 `get_turnover_ledger_tag_selection_state()`、`commit_turnover_ledger_tag_selection_update(...)`、`restore_turnover_ledger_tag_selection_state(...)`；rollback 只恢复该 setting family，禁止读取/保存整份私有 `_snapshot` |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 页面 Audit：direct canonical，registry `read_model_keys=()` 且 relation proof 不适用；只证明 persisted singleton、非敏感 credential registration 与 reset job state。下游 read model 不属于本页 consumer。
- 影响 read model：设置重置可能影响全部 read model。
- OA 手工导入设置入口会影响 `workbench`、`workbench_relation`、`invoice_lifecycle`、`tax_offset`、`search`、`cost_statistics`，不拥有这些 read model。
- Services：`AppSettingsService`、`SettingsDataResetService`、OA applicant credentials。`AppSettingsService.get_cost_statistics_source_settings_payload()` 是成本统计读取银行账户映射与自动标签规则版本的受控 read port；`get_cost_statistics_tag_selection_payload()` / `update_cost_statistics_tag_selection(...)` 是 selection schema v2 收支标签规则的受控 read/write port，由成本统计 route 暴露给页面抽屉；Turnover Ledger 本地 UoW 只能通过领域化 tag-selection state/commit/restore 端口进入 Settings owner。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/SettingsPage.tsx` |
| Frontend components | `web/src/components/settings/*`、`web/src/components/workbench/WorkbenchSettingsModal.tsx` |
| Frontend API | `web/src/features/workbench/api.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_settings.py`；`server.py` 只负责 route owner 组装和 runtime side-effect ports |
| Backend service | `app_settings_service.py`、`settings_data_reset_service.py`、`oa_applicant_credentials.py`、`target_oa_applicant_token_provider.py` |
| Repository | `postgres_repositories/oa_applicant_credentials.py` |
| Audit proof owner | `postgres_repositories/settings_page_audit.py`、`page_audit_registry.py`、`postgres_repositories/operations_audit.py` |
| Lifecycle | `derived_data_lifecycle_service.py`、`app_status_domain_registry.py`、`app_status_read_model_registry.py` |
| Tests | `tests/test_app_settings_service.py`、`tests/test_settings_data_reset_service.py`、`web/src/test/Settings*.test.*` |

## 依赖方向

- 允许依赖：settings/data reset service, credential repository, background job service。
- 必须通过：settings service and explicit reset job API。
- 禁止绕过：前端直接保存 secret；settings API 直接清库、直接写/同步查询 read model、调用 Workbench 全页 builder 或重复入队 matching dirty scope。

## 测试与验证

- `tests/test_app_settings_service.py`
- `tests/test_settings_data_reset_service.py`
- `tests/test_audit_settings_page.py`
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
- Downstream outputs: 按 setting family 产生 affected read model dirty scopes、domain events 或 explicit not-applicable；银行账户映射变化会通过成本统计 source version 的 `bank_account_mappings_fingerprint` 使旧 read model payload 失配并刷新；成本统计标签规则是 explicit not-applicable refresh，保存后仅影响 query/export 层过滤和 cache key，不触发成本统计 read model rebuild。
- Forbidden paths: `state:*` JSON、`state:full_state` 或旧 snapshot 不得作为 production 业务事实 fallback；其它模块不得直接写 settings store，也不得通过 `getattr/setattr` 访问 `AppSettingsService._snapshot`。
- Old code deletion: legacy settings snapshot、state JSON fallback、route-inline settings writes、server local snapshot refresh helper、跨模块整份 snapshot rollback 和内存 `_snapshot` 持久化补字段 fallback 已删除；migration/audit/rollback 工具保留不算 closure。

## 生产 normalization I/O（2026-07-12）

- `settings_normalization_ops` dry-run 只输出 changed top-level keys 与前后 hash，不输出完整设置或秘密。
- execute 调用 `AppSettingsService.normalize_settings_payload(...)`，并在单事务内通过 `PostgresOpsTaxEtcRepository.save_app_settings_in_transaction(...)` 保存；tool 不复制 normalization 规则，也不直接拼 settings SQL。
- 生产入口固定为 `finops-deploy-control settings-normalize <release> --dry-run|--execute`。
