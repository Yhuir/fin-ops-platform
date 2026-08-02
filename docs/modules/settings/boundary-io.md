# 设置模块边界与 I/O

日期：2026-07-22

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：设置页面只通过 settings API/route owner/service 修改配置、专用 ACL、OA 凭证、数据重置等控制面能力。
- 当前缺口：页面/API 与 App 内部 control-plane Audit 已闭环；真实生产 reset、真实 OA/provider、credential 登录、worker drain 和多页面 smoke 仍属于外部运维 gate。
- 旧代码删除状态：`server.py` 中 `/api/workbench/settings*` 旧 handler、settings data reset job handler、OA 手工导入 settings handler 与 `_refresh_local_app_settings_snapshot(...)` 已删除；`AppSettingsService` 不再用内存 `_snapshot` 补齐持久化 settings 缺失字段，外部模块也不得直接读取或替换其 `_snapshot`。

## 职责边界

### 负责

- 平台设置页面、工作台设置、OA 凭证设置、数据重置入口。
- 调用 app settings、credential provider、data reset service。
- 拥有 `/settings` 唯一人工 ACL I/O、专用 admin-only GET/PUT command、ACL normalization、独立 version/CAS、OA target/补偿编排，以及 canonical ACL 与 durable audit 的原子提交。
- 设置变更只提交 setting facts、version 与审计；普通保存不触发跨页面
  read-model fan-out，canonical 页面在下次 normal GET 读取最新设置。
- app settings 中跨模块只读/写控制面事实，例如成本统计标签规则。

### 不负责

- 不直接执行业务导入或 read model projection。
- 不在前端保存敏感凭证。
- 不绕过数据安全 reset service。
- 不判定 APP tier；permissions-and-audit 拥有 evaluator，OA integration 只消费完整 normalized ACL snapshot。历史 menu binding cleanup 已完成并退休，稳态部署只断言严格拓扑，不再提供 cleanup/rollback 写路径。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 设置表单 | `SettingsPage.tsx`、`components/settings/*` | API 负责校验和权限 |
| 普通 settings GET/POST | Settings page、Workbench 列布局等既有 caller | 不读取、返回或写 ACL；任一历史 ACL key 明确 `400 access_control_write_forbidden` |
| ACL GET/PUT | 仅 `YNSYLP005` 的后端 admin session | GET 返回完整 snapshot；PUT 只接受正整数 `expected_version` 与完整 `accounts[]`，tier 仅 `full_access\|read_export_only`，列表缺席表示 denied |
| OA canonical username | normalized ACL snapshot / OA `sys_user.user_name` | 共享 casefold key 负责比较与去重并保留 canonical spelling；collision、跨 tier overlap、控制字符和 protected admin 输入在 OA I/O 前失败 |
| OA credentials | settings/OA credential API | secret 不进入日志 |
| 数据重置请求 | settings data reset dialogs | 必须走 job/control service |
| 页面 Audit | `GET /api/operations/app-health/page-audit?page=settings` | 管理员只读；同一 repeatable-read snapshot，禁止 secret/provider/reset mutation I/O |

数据重置 create/detail/active 都必须重新取得 admin session；job owner 直接取该 session username。旧的“身份解析失败时回退 `web_finance_user`” resolver 已删除，禁止恢复匿名/共享 owner。

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 设置 payload/result | 前端页面 | 不泄露 secret |
| ACL result | Settings ACL UI、permissions evaluator | `{administrator, version, accounts}`；no-op 为 `changed=false`，stale 为 `409 current_version`，不提供兼容 payload |
| Durable ACL audit | `audit.events` | 与 canonical ACL/version 同一 PostgreSQL transaction；记录 session actor、server request id、mutation/version 与 changed username hashes，不记录 token 或完整 ACL payload |
| OA target / compensation | `OARoleSyncService` | 只替换三个专用角色 members；目标失败 502 且零 app write，PG 失败最多一次恢复旧 snapshot，无法确认则 503 inconsistent |
| Reset job | process-owned `BackgroundJobService` / app health | 可查询、可恢复；OA reset 的 runtime service reload 必须复用同一 background-job owner，禁止在任务执行中替换实例、双写同一 job store 或把当前任务误标为进程重启中断。只有应用进程首次启动/真正重启才创建 owner 并执行 interrupted-job recovery。job `completed` 只证明清理和 durable lifecycle 登记完成；OA `rebuild_status` 在下游 fresh 前必须是 `pending`。 |
| Affected scope/version | 调用页面 | 普通保存只返回业务 version 和信息性 affected scopes；不写页面 refresh queue |
| OA manual import result envelope | 设置页 | 返回精确 affected scopes，`freshness_targets` 与 `operation_barrier_targets` 为空；后续业务页面 normal GET 读取 canonical facts |
| 银行账户映射只读 payload | cost statistics canonical query | `AppSettingsService.get_cost_statistics_source_settings_payload()` 一次输出 `bank_account_mappings` 与 `bank_transaction_tags`；下游不得直接读取设置页前端状态 |
| 成本统计标签规则 payload | cost_statistics query/filter route | `AppSettingsService.get_cost_statistics_tag_selection_payload()` 输出归一后的收入/支出主子标签、虚拟 `__uncategorized__` 未分类标签、selection schema version 和 selected leaf codes；schema v2 默认全选当前有效收支标签，legacy 显式选择保留原支出选择并一次性加入当前有效收入标签。`update_cost_statistics_tag_selection(...)` 只持久化 `app.app_settings.cost_statistics_tag_selection` 并记录 audit，不写成本统计 read model、不入队 dirty scope |
| 外部往来标签选择事务端口 | turnover ledger local write UoW | 只允许调用 `get_turnover_ledger_tag_selection_state()`、`commit_turnover_ledger_tag_selection_update(...)`、`restore_turnover_ledger_tag_selection_state(...)`；rollback 只恢复该 setting family，禁止读取/保存整份私有 `_snapshot` |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 页面 Audit：direct canonical，registry `read_model_keys=()` 且 relation proof 不适用；只证明 persisted singleton、非敏感 credential registration 与 reset job state。下游 read model 不属于本页 consumer。
- 影响 read model：仅在 `workbench` 或 `workbench_relation` 明确登记的 maintenance/reset 合同中产生精确
  scope；设置模块不广播“全部 read model”。
- OA 手工导入只提交 canonical OA facts、audit 和信息性 affected scopes；OA 待付款、
  税金抵扣、成本统计等 direct 页面在下一次 normal GET 读取最新事实。关联台按 `workbench`
  freshness/refresh 合同收敛；`workbench_relation` 是否刷新由其 owner 的显式合同决定。
- Services：`AppSettingsService`、`SettingsDataResetService`、OA applicant credentials。`AppSettingsService.get_cost_statistics_source_settings_payload()` 是成本统计读取银行账户映射与自动标签规则版本的受控 read port；`get_cost_statistics_tag_selection_payload()` / `update_cost_statistics_tag_selection(...)` 是 selection schema v2 收支标签规则的受控 read/write port，由成本统计 route 暴露给页面抽屉；Turnover Ledger 本地 UoW 只能通过领域化 tag-selection state/commit/restore 端口进入 Settings owner。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/SettingsPage.tsx` |
| Frontend components | `web/src/components/settings/*`、`web/src/components/workbench/WorkbenchSettingsModal.tsx` |
| Frontend API | `web/src/features/workbench/api.ts`；普通 mapper/serializer 与专用 ACL client 分离 |
| Backend route | `backend/src/fin_ops_platform/app/routes_settings.py`；`server.py` 只负责 route owner 与 session/runtime ports 组装 |
| Backend service | `app_settings_service.py`、`oa_role_sync_service.py`、`settings_data_reset_service.py`、`oa_applicant_credentials.py`、`target_oa_applicant_token_provider.py` |
| Repository | `postgres_repositories/oa_applicant_credentials.py`、`postgres_repositories/ops_tax_etc.py`；`0118_bank_flow_rule_batch_settings_raw_alignment.sql` 只修复 `bank_flow_rule_batch_tag_rules` 的 formal/raw 镜像一致性，不改变 canonical rule value |
| Audit proof owner | `postgres_repositories/settings_page_audit.py`、`page_audit_registry.py`、`postgres_repositories/operations_audit.py` |
| Lifecycle | `derived_data_lifecycle_service.py`、`app_status_domain_registry.py`、`app_status_read_model_registry.py` |
| Tests | `tests/test_app_settings_service.py`、`tests/test_workbench_settings_sync_api.py`、`tests/test_oa_role_sync_service.py`、`tests/test_permissions_write_entry_inventory.py`、`tests/test_settings_data_reset_service.py`、`web/src/test/Settings*.test.*`、`web/e2e/permissions-role-matrix.spec.ts` |

## 依赖方向

- 允许依赖：settings/data reset service、credential repository、background job service 和 normalized ACL 的 OA role-sync port。
- 必须通过：普通 settings service、专用 ACL command/CAS critical section 和 explicit reset job API；permissions evaluator 只通过 Settings snapshot provider 读取 ACL。
- 禁止绕过：generic settings/Workbench modal/OA 管理后台新增 ACL 写入口；OA role/permission/env 反向授予 APP tier；前端直接保存 secret；settings API 直接清库、直接写/同步查询 read model、调用 Workbench 全页 builder 或重复入队 matching dirty scope。

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
- Downstream outputs: 按 setting family 更新 canonical setting/version、返回精确 affected
  scopes 或标记 explicit not-applicable；普通设置写不产生页面 dirty scopes。银行账户映射
  与成本统计标签规则在下一次 canonical query/export 中直接生效，不触发成本统计 rebuild。
- Forbidden paths: `state:*` JSON、`state:full_state` 或旧 snapshot 不得作为 production 业务事实 fallback；其它模块不得直接写 settings store，也不得通过 `getattr/setattr` 访问 `AppSettingsService._snapshot`。
- Old code deletion: legacy settings snapshot、state JSON fallback、route-inline settings writes、server local snapshot refresh helper、跨模块整份 snapshot rollback 和内存 `_snapshot` 持久化补字段 fallback 已删除；migration/audit/rollback 工具保留不算 closure。

## 生产 normalization I/O（2026-07-12）

## Access control canonical I/O

- Input：generic settings 只接受普通设置 DTO；历史 ACL keys 一律 `400`。专用 ACL command 只接受 admin session、`expected_version` 和其他账户的 full/read 列表。
- Output：generic settings 不返回 ACL。专用 GET/PUT 返回固定 `administrator=YNSYLP005`、`version`、`accounts`，冲突返回 `409 current_version`。
- Persistence：`app.app_settings` 是 canonical singleton；repository 在 shared advisory lock 和同一 PostgreSQL transaction 内只合并 ACL family、递增 `access_control_version` 并写 `audit.events`。migration `0133` 把 `allowed_usernames` 固定为 protected admin → full-access → readonly 的精确顺序，并以 validated CHECK 和 raw mirror 作为回滚安全底线。
- Dependency direction：route 只做 HTTP/auth 映射；`AppSettingsService` 拥有 normalize/OA target/compensation 编排；repository 拥有 row lock/SQL/audit；permissions 只解析 identity/判定 tier；OA integration 只消费完整 normalized snapshot。
- Old code deletion：generic route/service/client/modal/column save/pending replay 不得携带 ACL；`dynamic_admin_usernames_provider`、`get_admin_usernames`、运行时 `FIN_OPS_ADMIN_USERNAMES` 和可写 admin tier 保持删除。不得新增兼容 fallback 或第二写入口。
- 本变更不新增 read model、worker、dirty scope、outbox、cache 或其他页面 response 字段。

- `settings_normalization_ops` dry-run 只输出 changed top-level keys 与前后 hash，不输出完整设置或秘密。
- execute 调用 `AppSettingsService.normalize_settings_payload(...)`，并在单事务内通过 `PostgresOpsTaxEtcRepository.save_app_settings_in_transaction(...)` 保存；tool 不复制 normalization 规则，也不直接拼 settings SQL。
- 生产入口固定为 `finops-deploy-control settings-normalize <release> --dry-run|--execute`。

## 流水规则 formal/raw 一致性（2026-07-21）

- `app.app_settings.settings_payload.bank_flow_rule_batch_tag_rules` 是 canonical value；`raw_payload.normalized_payload` 只是同值审计镜像，不是第二事实源。
- 历史迁移 `0111` 只规范了 formal payload，导致设置页只读 Audit 报 `settings_formal_raw_payload_mismatch`。`0118` 仅把该 setting family 的 canonical value 同步到 raw 镜像并记录 migration marker，禁止修改规则版本、OA/发票开关或其它 setting family。
- 后续正常写入继续统一走 repository settings writer，由同一事务同时写 formal 与 raw；禁止再增加只改 `settings_payload` 的旁路 SQL。
