# Phase 13: Settings T0 权限提权闭环 - Context

**Gathered:** 2026-08-02
**Status:** Ready for planning
**Source:** 用户确认的 T0-01 安全设计审查

<domain>
## Phase Boundary

本 phase 只规划并在后续执行中修复 T0-01：普通 `full_access` 用户可以通过普通 settings 保存接口写入 `admin_usernames`，把自己提升为管理员。

本 phase 必须形成从后端授权、Settings API、持久化、审计、OA 角色同步、前端访问账户管理、旧数据清理、部署回滚到自动化验证的生产闭环。除修复该权限事实链所必需的改动外，不改变项目状态、银行账户映射、OA 导入、待找发票规则、数据重置、OA 凭据或其它业务页面行为。

</domain>

<decisions>
## Implementation Decisions

### 管理员模型
- **D-01（locked）** 第一阶段唯一 protected administrator 是 `YNSYLP005`。
- **D-02（locked）** 管理员身份不能通过 APP 的任何 GET/POST/PUT/PATCH/DELETE 请求新增、删除、提升或降级；管理员轮换只属于 root-owned 部署配置和受控运维，不属于 settings 业务数据。
- **D-03（locked）** `YNSYLP005` 只能管理其他 OA 账号的 `full_access`、`read_export_only`、`denied` 三种结果；API 不暴露可写 `admin` tier，删除账号表示 `denied`。

### HTTP 与模块边界
- **D-04（locked）** 普通 `GET/POST /api/workbench/settings` 不再读取、返回或写入 ACL，不接受 `allowed_usernames`、`readonly_export_usernames`、`admin_usernames` 或 `access_control`；出现旧字段必须明确失败，禁止静默忽略或兼容 fallback。
- **D-05（locked）** 新增 admin-only `GET/PUT /api/workbench/settings/access-control`。HTTP 授权复用现有 admin session resolver；普通 settings 继续使用 mutation session resolver，不能整体升级为 admin-only。
- **D-06（locked）** access-control DTO 使用单一 `accounts` 列表，每项只有 `username` 与 `access_tier=full_access|read_export_only`；响应只读返回 `administrator=YNSYLP005` 和版本。请求 actor 只取后端 session，不接受 body actor。
- **D-07（locked）** settings 模块拥有 ACL canonical setting 的保存命令；permissions-and-audit 模块只拥有身份解析、权限决策和 audit 合同；OA integration 只消费归一后的 ACL snapshot。不得让 route 写 SQL、service 解析 cookie/header、repository 决定业务权限。

### 持久化、并发与审计
- **D-08（locked）** 复用现有 `app.app_settings` 与 `audit.events`，不新增表、不新增通用框架。ACL 使用独立 `access_control_version` 和 `expected_version`，在 PostgreSQL 事务内锁定当前 settings row、比较版本、只合并 ACL keys、递增版本并写 durable audit；冲突返回 409。
- **D-09（locked）** 普通 settings writer 必须在事务内保留数据库中的最新 ACL，不能用 service 的旧 snapshot 覆盖并发 ACL 更新。ACL semantic no-op 不写数据库、不写 audit、不调用 OA。
- **D-10（locked）** 增加数据库 invariant，canonical 管理员只能是 `YNSYLP005`；该 invariant 同时作为回滚到旧应用代码时的安全兜底。应用层仍必须先拒绝非法请求，不能依赖数据库异常作为正常权限检查。
- **D-11（locked）** 权限变更成功 audit 必须与 canonical ACL 同事务提交，记录 session actor、前后 tier 摘要、ACL version、受影响账号与 trace/request id；失败不得留下成功 audit，metadata 不含 token、密码或完整敏感 payload。

### OA 同步与性能
- **D-12（locked）** 普通 settings 保存不得调用 OA role sync。只有 ACL 真实变化调用现有 `OARoleSyncService`；本 phase 保留同步调用和现有补偿语义，不新增 outbox worker、队列类型、systemd unit 或 read model。
- **D-13（locked）** 鉴权热路径把分散的动态 allowed/readonly/admin provider 收敛为一次 ACL snapshot 读取；删除动态管理员 provider。不得为此新增 Redis 或新的缓存框架。
- **D-14（locked）** ACL 是低频 control-plane 写入；性能目标是普通 settings 保存零 OA I/O、每次 session 权限判断最多一次动态 ACL snapshot 获取、ACL no-op 零外部 I/O。真实延迟以目标测试和生产 smoke 采样，不用未经测量的数字宣称通过。

### 前端与旧链路删除
- **D-15（locked）** 访问账户区使用独立 ACL load/save callback、独立 saving/error/conflict 状态；普通“保存设置”不再携带 ACL。现有页面结构和视觉风格不重做，不引入新状态库或表单框架。
- **D-16（locked）** 必须删除 generic settings route/service/API client、pending-invoice caller、server wiring、auth clone、deterministic mocks、E2E fixtures 和测试中的旧 ACL write path；禁止保留 legacy endpoint、双写、旧字段 fallback 或隐藏兼容分支。

### 发布与回归
- **D-17（locked）** 发布前只读盘点 PostgreSQL ACL、root-owned env admin 配置和 OA 三类角色成员。历史非 `YNSYLP005` admin 必须 fail closed 清理并记录迁移 audit，不能在没有明确事实时静默保留为管理员。
- **D-18（locked）** 发布后必须验证 `YNSYLP005` admin、代表性 full-access、read-export 和 denied session；验证 full-access 普通 settings 保存仍为 200，手工 ACL 提权请求为 403/明确拒绝，AppHealth/OA 凭据/data reset 仍保持 admin-only。
- **D-19（locked）** 本 phase 不改变其它页面 API response、read model scope、worker、dirty scope、cache key 或业务事实；如果计划发现必须改变这些边界，停止并把扩展范围提交用户确认。

### the agent's Discretion
- 在不改变上述合同的前提下，选择最小的现有 repository transaction helper、错误类、DTO type 和测试 helper。
- 选择 ACL JSON key 的内部排列方式，但不得新增第二事实源。
- 选择 migration 编号和精确 CHECK 表达式；必须支持现有 PostgreSQL migration runner 和旧版本回滚安全。

</decisions>

<canonical_refs>
## Canonical References

### 产品与安全口径
- `SECURITY.md` — `YNSYLP005` 固定管理员和高风险权限修改审计要求。
- `docs/references/source-yinqi-reconciliation.md` — OA 可见、APP 访问、full/read 两层权限及唯一管理账号事实。
- `docs/product-specs/platform-settings-health.md` — settings、权限与审计 command/service 边界。
- `deploy/oa/README.md` — OA 三类角色、allowed/readonly/admin/full_access 同步和生产配置合同。

### 模块边界
- `docs/architecture/module-boundaries/inventory.md` — settings、permissions-and-audit、oa-integration 模块登记。
- `docs/modules/settings/boundary-io.md` — settings HTTP/service/repository I/O 和旧代码删除条件。
- `docs/modules/permissions-and-audit/boundary-io.md` — session/access-control/audit 责任边界。
- `docs/modules/oa-integration/boundary-io.md` — OA role sync 依赖方向。
- `docs/modules/settings/state-machine.md` — settings 与 access-control 当前状态机。
- `docs/modules/permissions-and-audit/state-machine.md` — access tier、session、audit 原子性合同。

### 当前代码与测试
- `backend/src/fin_ops_platform/app/routes_settings.py` — generic settings HTTP owner 和现有 mutation/admin resolver。
- `backend/src/fin_ops_platform/services/app_settings_service.py` — settings normalize/save、ACL provider、OA sync 旧耦合。
- `backend/src/fin_ops_platform/services/access_control_service.py` — tier 决策、固定/env/dynamic admin 来源。
- `backend/src/fin_ops_platform/services/oa_role_sync_service.py` — OA assignments 与同步/补偿边界。
- `backend/src/fin_ops_platform/services/postgres_state_store.py` — app settings state-store port。
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py` — app settings PostgreSQL writer 和现有 row-lock/version pattern。
- `backend/src/fin_ops_platform/services/audit.py` — 当前仅内存 audit，不满足 ACL durable audit。
- `web/src/pages/SettingsPage.tsx` — settings page 权限和 save callbacks。
- `web/src/components/settings/SettingsPageContent.tsx` — global save 与访问账户 local state。
- `web/src/components/settings/SettingsAccessAccountsSection.tsx` — 现有 full/read-only 管理 UI。
- `web/src/features/workbench/api.ts` — generic settings GET/POST DTO 与旧 ACL fields。
- `tests/test_workbench_settings_sync_api.py`、`tests/test_session_api.py`、`tests/test_auth_guard.py` — backend API/session regression。
- `web/src/test/SettingsPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts` — frontend/component/Browser role matrix。

</canonical_refs>

<specifics>
## Specific Ideas

- 目标修复必须位于后端可信边界；前端隐藏仅用于 UX。
- 优先删除 `admin_usernames` runtime persistence/provider/write I/O，而不是在每个 caller 上叠加条件判断。
- 优先复用现有 `SELECT ... FOR UPDATE`、per-setting version、`audit.events`、admin session resolver 和 OA role sync service。
- 普通 settings 与 ACL 分开保存，避免跨命令部分成功和普通保存被 OA 网络拖慢。
- 不为低频 ACL command 增加 worker；只有发现同步崩溃窗口必须达到自动恢复这一新需求时，才另开 worker phase。

</specifics>

<deferred>
## Deferred Ideas

- 多管理员、管理员委派、双人审批、临时管理员和 UI 内管理员轮换。
- 把同步 OA role sync 改造成 durable outbox worker。
- 全面重定义 OA `required_permission` / allowed roles 与本地 allowlist 的授权优先级；本 phase 只保证这些来源不能产生非 `YNSYLP005` admin，并用 characterization/regression 防止意外访问面变化。
- 重构整个巨型 `AppSettingsService` 或拆分所有 setting family。
- 与 T0-01 无关的普通 settings 缺省值、项目范围、标签、OA import、凭据和 data reset 改造。

</deferred>

<scope_fence>
## Scope Fence

- 只允许写 `.planning/phases/13-settings-improvements/` 规划产物；本轮不修改实现、测试、migration、部署脚本或长期文档。
- 后续执行可以修改 CONTEXT 中列出的直接模块与必要上下游，但不得改业务页面 response/read-model/worker I/O。
- 发现生产 admin 事实不止 `YNSYLP005`、现有 env 与产品合同冲突、或 OA 同步必须改为 worker 才能上线时，执行阶段必须 checkpoint，不得猜测。

</scope_fence>

---

*Phase: 13-settings-improvements*
*Context gathered: 2026-08-02 via confirmed T0-01 design review*
