---
phase: 13
slug: settings-improvements
status: complete
researched: 2026-08-02
research_mode: codebase-and-production-evidence
head_examined: 0bf3c6d0a
---

# Phase 13 — Settings ACL 唯一授权事实源与 OA 菜单投影研究

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 管理员模型
- **D-01（locked）** 第一阶段唯一 protected administrator 是 `YNSYLP005`。
- **D-02（locked）** 管理员身份不能通过 APP 的任何 GET/POST/PUT/PATCH/DELETE 请求新增、删除、提升或降级；管理员轮换只属于 root-owned 部署配置和受控运维，不属于 settings 业务数据。
- **D-03（locked）** `YNSYLP005` 只能管理其他 OA 账号的 `full_access`、`read_export_only`、`denied` 三种结果；API 不暴露可写 `admin` tier，删除账号表示 `denied`。

#### HTTP 与模块边界
- **D-04（locked）** 普通 `GET/POST /api/workbench/settings` 不再读取、返回或写入 ACL，不接受 `allowed_usernames`、`readonly_export_usernames`、`admin_usernames` 或 `access_control`；出现旧字段必须明确失败，禁止静默忽略或兼容 fallback。
- **D-05（locked）** 新增 admin-only `GET/PUT /api/workbench/settings/access-control`。HTTP 授权复用现有 admin session resolver；普通 settings 继续使用 mutation session resolver，不能整体升级为 admin-only。
- **D-06（locked）** access-control DTO 使用单一 `accounts` 列表，每项只有 `username` 与 `access_tier=full_access|read_export_only`；响应只读返回 `administrator=YNSYLP005` 和版本。请求 actor 只取后端 session，不接受 body actor。
- **D-07（locked）** settings 模块拥有 ACL canonical setting 的保存命令；permissions-and-audit 模块只拥有身份解析、权限决策和 audit 合同；OA integration 只消费归一后的 ACL snapshot。不得让 route 写 SQL、service 解析 cookie/header、repository 决定业务权限。

#### 持久化、并发与审计
- **D-08（locked）** 复用现有 `app.app_settings` 与 `audit.events`，不新增表、不新增通用框架。ACL 使用独立 `access_control_version` 和 `expected_version`，在 PostgreSQL 事务内锁定当前 settings row、比较版本、只合并 ACL keys、递增版本并写 durable audit；冲突返回 409。
- **D-09（locked）** 普通 settings writer 必须在事务内保留数据库中的最新 ACL，不能用 service 的旧 snapshot 覆盖并发 ACL 更新。ACL semantic no-op 不写数据库、不写 audit、不调用 OA。
- **D-10（locked）** 增加数据库 invariant，canonical 管理员只能是 `YNSYLP005`；该 invariant 同时作为回滚到旧应用代码时的安全兜底。应用层仍必须先拒绝非法请求，不能依赖数据库异常作为正常权限检查。
- **D-11（locked）** 权限变更成功 audit 必须与 canonical ACL 同事务提交，记录 session actor、前后 tier 摘要、ACL version、受影响账号与 trace/request id；失败不得留下成功 audit，metadata 不含 token、密码或完整敏感 payload。

#### OA 同步与性能
- **D-12（locked）** 普通 settings 保存不得调用 OA role sync。只有 ACL 真实变化调用现有 `OARoleSyncService`；本 phase 保留同步调用和现有补偿语义，不新增 outbox worker、队列类型、systemd unit 或 read model。
- **D-13（locked）** 鉴权热路径把分散的动态 allowed/readonly/admin provider 收敛为一次 ACL snapshot 读取；删除动态管理员 provider。不得为此新增 Redis 或新的缓存框架。
- **D-14（locked）** ACL 是低频 control-plane 写入；性能目标是普通 settings 保存零 OA I/O、每次 session 权限判断最多一次动态 ACL snapshot 获取、ACL no-op 零外部 I/O。真实延迟以目标测试和生产 smoke 采样，不用未经测量的数字宣称通过。

#### 前端与旧链路删除
- **D-15（locked）** 访问账户区使用独立 ACL load/save callback、独立 saving/error/conflict 状态；普通“保存设置”不再携带 ACL。现有页面结构和视觉风格不重做，不引入新状态库或表单框架。
- **D-16（locked）** 必须删除 generic settings route/service/API client、pending-invoice caller、server wiring、auth clone、deterministic mocks、E2E fixtures 和测试中的旧 ACL write path；禁止保留 legacy endpoint、双写、旧字段 fallback 或隐藏兼容分支。

#### 发布与回归
- **D-17（locked）** 发布前只读盘点 PostgreSQL ACL、root-owned env admin 配置和 OA 三类角色成员。历史非 `YNSYLP005` admin 必须 fail closed 清理并记录迁移 audit，不能在没有明确事实时静默保留为管理员。
- **D-18（locked）** 发布后必须验证 `YNSYLP005` admin、代表性 full-access、read-export 和 denied session；验证 full-access 普通 settings 保存仍为 200，手工 ACL 提权请求为 403/明确拒绝，AppHealth/OA 凭据/data reset 仍保持 admin-only。
- **D-19（locked）** 本 phase 不改变其它页面 API response、read model scope、worker、dirty scope、cache key 或业务事实；如果计划发现必须改变这些边界，停止并把扩展范围提交用户确认。

#### 唯一授权事实源与 OA 菜单投影
- **D-20（locked）** 对除 `YNSYLP005` 外的所有账号，Settings 专用 ACL 中的 `accounts` 是 APP 访问等级的唯一业务事实源；账号不在列表中即为 `denied`。OA identity 只证明“这个 token 属于谁”，OA `finops:app:view`、OA roles、`FIN_OPS_ALLOWED_USERNAMES`、`FIN_OPS_ALLOWED_ROLES` 和 `FIN_OPS_READONLY_EXPORT_USERNAMES` 都不能再独立授予 APP 权限。
- **D-21（locked）** APP 内只有两个可分配等级：`full_access`（所有操作均可）与 `read_export_only`（只可看和只可导出）。`admin` 只属于固定 `YNSYLP005`；`denied` 由账号不在列表中派生，不作为第三个可分配角色。
- **D-22（locked）** `/settings` 的“访问账户权限”是唯一人工管理入口；只有 `YNSYLP005` 看得见并可调用专用 ACL API。不得恢复 Workbench modal、generic settings、环境变量名单、OA 当前角色或其它页面的第二写入口。
- **D-23（locked）** OA 菜单由 OA 壳体在 APP 加载前渲染，因此 Settings owner 必须通过既有 OA integration adapter 把 canonical ACL 投影为专用 `finops_read_export`、`finops_full_access`、`finops_admin` 角色成员；用户不需要进入 OA 管理后台手工维护。OA 投影只控制菜单可见性，不能反向成为 APP 授权事实源。
- **D-24（locked）** 生产菜单只允许绑定上述三类专用 fin-ops 角色。发布前必须盘点并清除 `finops:app:view` 对非专用 OA 角色的历史绑定；否则像 `YNSYLP006` 这类业务角色成员会继续看见入口。清理必须是受控、可审计、可回滚的 exact-target 操作，不能改动其它 OA 菜单或业务角色成员关系。
- **D-25（locked）** 真实 ACL 变化只有在 canonical ACL、durable audit 与目标 OA 角色投影达到既有一致性/补偿合同后才返回成功；生产若未启用 OA role sync、缺少专用角色/菜单、网络超时或发现非专用角色漂移，必须明确失败或进入 `access_control_sync_inconsistent`，禁止返回“保存成功”但菜单未同步。
- **D-26（locked）** 删除账号后的后端访问撤销不依赖 OA identity cache：下一次 APP session/API 权限判断必须直接得到 `denied`；直接输入 `/fin-ops/` 或 `/fin-ops-api/*` 也必须被拒绝。OA 菜单可见性以角色投影后的新 OA router/session 读取为验收边界，不承诺在不刷新 OA 壳体的既有浏览器 DOM 中瞬时消失。
- **D-27（locked）** 本 follow-up 不新增权限框架、数据库表、Redis、read model、worker、outbox 或第二套缓存；复用现有 ACL snapshot、Settings admin API、OA role sync、route policy、SessionGate 与审计边界。必须删除被替代的 permission/role/env 授权分支、部署兜底和测试假设，并用全量角色矩阵、菜单角色独占性、直接 URL/API、其它页面回归与生产双账号证据闭环。

### the agent's Discretion
- 在不改变上述合同的前提下，选择最小的现有 repository transaction helper、错误类、DTO type 和测试 helper。
- 选择 ACL JSON key 的内部排列方式，但不得新增第二事实源。
- 选择 migration 编号和精确 CHECK 表达式；必须支持现有 PostgreSQL migration runner 和旧版本回滚安全。

### Deferred Ideas (OUT OF SCOPE)
- 多管理员、管理员委派、双人审批、临时管理员和 UI 内管理员轮换。
- 把同步 OA role sync 改造成 durable outbox worker。
- 多租户、组织/部门级 ACL、临时授权、按页面/字段的细粒度权限。
- 重构整个巨型 `AppSettingsService` 或拆分所有 setting family。
- 与 T0-01 无关的普通 settings 缺省值、项目范围、标签、OA import、凭据和 data reset 改造。
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
| --- | --- | --- |
| PAGE-05 | 页面 phase 在实现前记录模块文档、入口、风险与验证策略 | 本研究给出两条端到端链、模块边界、删除 sentinel、失败语义与验证架构。 `[VERIFIED: .planning/REQUIREMENTS.md]` |
| PAGE-15 | Settings page analysis 存放在独立 phase artifacts | 本文件是 Phase 13 的 canonical research artifact，并限定只影响 settings/permissions/OA/app-shell 边界。 `[VERIFIED: .planning/REQUIREMENTS.md]` |
</phase_requirements>

## 执行摘要

当前 HEAD 已经完成 T0-01 首轮闭环：普通 settings 与 ACL DTO 分离、admin-only `GET/PUT .../access-control`、PostgreSQL ACL CAS、同事务 durable audit、固定 `YNSYLP005`、独立 Settings UI 保存、generic writer 保留 ACL family，以及 migration `0132` 的管理员 invariant 均已存在。因此 planner 不应重做这些能力。 `[VERIFIED: codebase]`

本 follow-up 的代码证明根因只剩两个相互独立的授权面：APP 后端仍把 OA permission、OA roles 和三组 env 名单与 canonical ACL 做并集；OA 菜单 bootstrap 只插入三类专用角色绑定，却不删除/拒绝历史非专用角色绑定。结果是从 Settings 删除的账号既可能在 `/api/session/me` 被重新评为 `full_access`，也可能继续由 OA 壳体在 APP 加载前显示菜单。 `[VERIFIED: codebase]`

2026-08-02 的生产证据精确复现了第一条链：`YNSYLP006` 已不在 Settings accounts，但其有效 OA session 带 `finops:app:view` 和业务 roles，`/api/session/me` 仍返回 `full_access`、`allowed=true`、`can_access_app=true`、`can_mutate_data=true`。这不是前端缓存或 SessionGate 缺陷，而是 `AccessControlService.evaluate()` 的 server-side admission 规则直接放行。 `[VERIFIED: authorized production evidence supplied 2026-08-02]`

**Primary recommendation:** 保留现有 ACL command/CAS/UI，只把 `AccessControlService` 收敛为“固定 admin，否则只查一次 canonical ACL snapshot”；同时把既有 OA adapter 加固为“sync 必须启用、三类 role/menu 必须存在且菜单绑定必须独占、角色成员按 ACL 精确投影”，并扩展现有 preflight/post-deploy 工具证明该合同。 `[VERIFIED: codebase + 13-CONTEXT.md]`

## Project Constraints (from AGENTS.md)

- 文档与计划默认中文；先按 inventory 和四个受影响模块的 `boundary-io.md` 核对边界。 `[VERIFIED: AGENTS.md]`
- 改权限前必须做 docs impact assessment；实现后同步 settings、permissions-and-audit、oa-integration、app-shell-navigation 及安全/部署长期事实源。 `[VERIFIED: AGENTS.md]`
- 后端 route 只做 HTTP/auth 映射，业务规则在 service，SQL 在 repository；service 不读取 cookie/header。 `[VERIFIED: AGENTS.md]`
- 生产级需求必须覆盖权限、审计、回滚、数据一致性和验证；token 不进入聊天、仓库或日志。 `[VERIFIED: AGENTS.md]`
- 优先复用/删除，禁止隐藏 fallback、并行旧路径和无需求的新抽象；跨模块删除必须 whole-repo symbol/text scan。 `[VERIFIED: AGENTS.md]`
- 行为变化必须按七类测试判断适用性；本 phase 七类均有适用或负向适用项。 `[VERIFIED: AGENTS.md]`

## 代码证明的根因链

### 链 1：Token → OA identity → APP admission → SessionGate

```text
Authorization Bearer / Admin-Token cookie
  -> auth.extract_oa_token
  -> OAIdentityService.resolve_identity(token)
       -> /system/user/getInfo
       -> identity {username, roles, permissions}
       -> token-keyed identity cache（仅缓存身份）
  -> AccessControlService.evaluate(identity)
       -> YNSYLP005 ? admin
       -> 读取一次 Settings ACL snapshot
       -> [当前错误分支] permission 命中 OR env username OR env role OR ACL username
       -> access_tier/can_access_app/can_mutate_data
  -> /api/session/me 返回 200 + allowed/tier
  -> SessionContext: allowed ? authenticated : forbidden
  -> SessionGate: forbidden 时阻止业务 React tree

Direct /fin-ops-api/*
  -> Application._enforce_route_access（body/route business dispatch 前）
  -> denied => 403
  -> unsafe method 且 !can_mutate_data => 403

OA pending payments exception
  -> global policy 有意跳过
  -> module-owned _resolve_oa_pending_payment_read_session
  -> 同一 resolve_oa_request_session / AccessControlService
```

以上调用链由 `auth.py`、`oa_identity_service.py`、`access_control_service.py`、`server.py`、`route_access_policy.py`、`SessionContext.tsx` 与 `SessionGate.tsx` 共同实现。 `/api/session/me` 有意不被全局 route guard 拦截，以便返回 `allowed=false` 让前端显示 forbidden；其它受保护 API 在 route dispatch 前拒绝 denied。OA pending payments 是唯一显式 module-owned guard 例外，但仍复用同一 session evaluator。 `[VERIFIED: codebase]`

`AccessControlService.evaluate()` 当前按以下优先级放行非管理员：OA identity 包含 `required_permission`；或 username 命中 env/canonical allowed 并集；或 OA roles 命中 `FIN_OPS_ALLOWED_ROLES`。只读 tier 也由 env/canonical readonly 并集决定。任何一个分支都能绕过 Settings accounts。 `[VERIFIED: codebase]`

`_load_access_control_snapshot()` 当前捕获 provider 异常并返回默认 ACL；但随后 permission/role/env 仍能放行。`test_get_session_me_does_not_fail_when_dynamic_settings_provider_is_unavailable_for_permitted_user` 明确把这一 fail-open 行为锁成测试预期。 `[VERIFIED: codebase]`

OA identity cache 只缓存 `{username, roles, permissions}`，不缓存 APP `AccessDecision`；因此删除账号后只要 evaluator 不再接受 permission/role/env，每次新的 `/api/session/me` 或受保护 API 判断都会重新读取 ACL 并立即 denied，无需清 identity cache。 `[VERIFIED: codebase]`

### 链 2：Settings UI → canonical ACL → OA role/menu projection

```text
/settings（仅 canAdminAccess 显示访问账户区）
  -> fetchWorkbenchAccessControl / updateWorkbenchAccessControl
  -> SettingsApiRoutes.access_control / update_access_control
  -> existing admin session resolver
  -> AppSettingsService.update_access_control
       -> normalize accounts -> full/read snapshot + fixed admin
       -> begin_settings_acl_critical_section(expected_version)
       -> semantic no-op: return, no write/audit/OA
       -> OARoleSyncService.sync_access_control(target)
            -> OA MySQL transaction
            -> sys_user_role exact target for 3 dedicated roles
       -> PostgreSQL commit
            -> app.app_settings ACL family/version
            -> audit.events in same transaction
       -> PG failure => OA compensate to previous snapshot
  -> 200 / 409 / 502 / access_control_sync_inconsistent
```

现有 Settings UI 已有独立 ACL load/save、saving/error 状态；route 已有 strict DTO/admin resolver；repository 已有 advisory lock、`FOR UPDATE`、CAS、ACL-family merge、formal/raw save 和 durable audit；这些是 follow-up 应复用的 owner。 `[VERIFIED: codebase]`

现有 `MySQLOARoleSyncExecutor.apply()` 只加载三类 role、加载目标 user、删除/插入 `sys_user_role`。它不读取 `sys_menu` 或 `sys_role_menu`，所以既不能发现菜单缺失，也不能发现业务角色仍绑定 `finops:app:view` 菜单。 `[VERIFIED: codebase]`

现有 `OARoleSyncService.from_environment()` 在 `FIN_OPS_OA_ROLE_SYNC_ENABLED` 非 truthy 时返回无 executor 的 service，而 `sync_access_control()` 直接 return；因此真实 ACL 变化仍可能在零 OA I/O 下提交 PG 并返回成功。现有 preflight 也把 `enabled=false` 视为可接受，并把 `oa_matches_target` 定义成 `not enabled OR members match`。这与 D-25 冲突。 `[VERIFIED: codebase]`

## 全量入口与授权事实源清单

| 入口/事实 | 当前作用 | 目标处置 | Sentinel |
| --- | --- | --- | --- |
| `YNSYLP005` protected constant | 唯一 admin，snapshot 读取前判定 | 保留；不可由 HTTP/DB/env/OA role 推导 | admin matrix + migration CHECK `[VERIFIED: codebase]` |
| Settings dedicated `accounts` | canonical full/read list | 保留为非 admin 唯一 authority；absence=`denied` | `test_session_api` matrix `[VERIFIED: codebase]` |
| OA `finops:app:view` permission | 当前直接授予 full access | 从 evaluator 删除，仅作为 OA menu metadata/identity payload | permission-only identity 必须 denied `[VERIFIED: codebase]` |
| OA business/dedicated roles | `FIN_OPS_ALLOWED_ROLES` 命中可直接授予 full access | 从 evaluator 删除；三类 dedicated roles 只做菜单投影 | role-only identity 必须 denied `[VERIFIED: codebase]` |
| `FIN_OPS_ALLOWED_USERNAMES` | env allowlist 与 ACL 并集 | 删除运行时读取、env example、deploy required-key 和文档；不得保留 YNSYLP005 启动兜底 | whole-repo zero runtime refs `[VERIFIED: codebase]` |
| `FIN_OPS_READONLY_EXPORT_USERNAMES` | env readonly 与 ACL 并集 | 删除运行时读取和 deploy/docs；只读只由 ACL snapshot 决定 | whole-repo zero runtime refs `[VERIFIED: codebase]` |
| `FIN_OPS_ALLOWED_ROLES` | env OA role allowlist | 删除运行时读取和 deploy/docs | whole-repo zero refs except rejection/history `[VERIFIED: codebase]` |
| `FIN_OPS_OA_REQUIRED_PERMISSION` / `required_permission` | 同一标记混合了OA menu selector与APP permission fallback | 从`AccessControlService`/auth/evaluator删除`required_permission`和APP admission；在OA integration/deploy边界保留并锁定`FIN_OPS_OA_REQUIRED_PERMISSION=finops:app:view`作为唯一menu selector，绝不进入APP tier evaluator | evaluator signature sentinel + OA menu selector contract `[VERIFIED: codebase]` |
| default unittest auth | 构造 `test_finops_user` + permission/role，当前靠 fallback 放行 | 测试必须显式 seed canonical ACL 或使用明确 protected-admin identity；不得给 evaluator 加 test bypass | test helper/harness inventory `[VERIFIED: codebase]` |
| local dev auth | 构造 `FIN_OPS_DEV_USERNAME` + permission/role | 身份模拟可保留，但仍须命中 canonical ACL（或明确使用 YNSYLP005）；不得凭 dev flag 自动授权 | local auth negative test `[VERIFIED: codebase]` |
| frontend mocks/E2E fixtures | 多处把 `permissions=[finops:app:view]` 与 allowed/full 绑定 | mock tier/allowed 由 fixture ACL/session mode 明示；新增 permission-present-but-denied fixture | mock sentinel `[VERIFIED: codebase]` |
| global route policy | 所有 `/api/*`、`/imports*` 等统一 guard | 复用；验证 direct API denied | inventory + route policy tests `[VERIFIED: codebase]` |
| OA pending module guard | global exception 后自行 resolve session | 复用；必须与全局 evaluator 同结果；缺失 platform ports 不得在 production fail-open | module-owned guard tests `[VERIFIED: codebase]` |
| `SessionGate` | 仅消费 `/api/session/me.allowed` | 不加业务规则；保持 UX gate，后端仍是安全边界 | component test `[VERIFIED: codebase]` |
| `fin_ops_menu.mysql.sql` | 以 `perms=finops:app:view` 创建/更新菜单 | 保留 exact menu identity，但必须拒绝同 perms 多菜单/歧义 | preflight `[VERIFIED: codebase]` |
| `fin_ops_role_binding.mysql.sql` | 只 INSERT 三类专用 role-menu | 加 exact inventory/cleanup；不能只插不删 | SQL/deploy test `[VERIFIED: codebase]` |
| `sys_user_role` dedicated roles | OA 菜单可见性投影 | 由 ACL target 精确替换；不得反向授权 APP | adapter/integration test `[VERIFIED: codebase]` |
| `sys_role_menu` non-dedicated binding | 让业务角色成员继续看到菜单 | 发布前 exact-target 清除；runtime sync 发现漂移须失败 | menu exclusivity evidence `[VERIFIED: codebase]` |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
| --- | --- | --- | --- |
| OA token -> username | API / Backend | External OA | OA 只证明身份；`OAIdentityService` 是 adapter。 `[VERIFIED: codebase]` |
| APP tier decision | API / Backend | Database / Storage | permissions owner 读取 Settings canonical ACL，不接受 OA role/permission authority。 `[VERIFIED: 13-CONTEXT.md]` |
| ACL command/CAS/audit | API / Backend | Database / Storage | Settings service 编排，PG repository 原子持久化。 `[VERIFIED: codebase]` |
| OA role/menu projection | External OA adapter | API / Backend | OA integration 写 `sys_user_role`、验证 `sys_role_menu`，不反向决定 tier。 `[VERIFIED: 13-CONTEXT.md]` |
| forbidden shell UX | Browser / Client | API / Backend | `SessionGate` 展示 API 决策，不自行授权。 `[VERIFIED: codebase]` |
| release inventory/cleanup | Deployment / Operations | PostgreSQL + OA MySQL | root-owned exact-target、审计、回滚与双身份证据。 `[VERIFIED: AGENTS.md]` |

## 目标模块边界与 I/O

| 模块 | 输入 | 输出 | 必须复用 | 禁止 |
| --- | --- | --- | --- | --- |
| `settings` | admin session、expected_version、accounts | normalized ACL command、public ACL DTO | 现有 route/service/CAS/audit/UI | 第二写入口、generic ACL 字段、route SQL `[VERIFIED: codebase]` |
| `permissions-and-audit` | OA identity username、一次 ACL snapshot | `AccessDecision`、403/tiers、audit contract | `resolve_oa_request_session`、route policy | OA permission/role/env fallback、frontend-only auth `[VERIFIED: codebase]` |
| `oa-integration` | 完整 normalized ACL snapshot | 三类 `sys_user_role` target；menu exclusivity proof | `OARoleSyncService`/MySQL executor | 读取 HTTP、决定 APP tier、disabled no-op `[VERIFIED: codebase]` |
| `app-shell-navigation` | `/api/session/me` normalized state | forbidden/authenticated shell | SessionContext/SessionGate | 复制 ACL、按 roles/permissions 再判断 `[VERIFIED: codebase]` |
| repository | ACL/current settings、audit metadata | CAS commit/recovery | existing advisory lock + row lock | 业务权限判断、跨库假原子性 `[VERIFIED: codebase]` |
| deploy/preflight | DB ACL、OA roles/menu bindings、双 token | secret-safe exact release artifact | existing deploy-control/preflight | 手工 OA UI、宽泛 delete、token 输出 `[VERIFIED: codebase]` |

## Standard Stack

不安装新依赖。继续使用 Python service/repository、现有 `psycopg` PostgreSQL transaction、现有 `PyMySQL` OA adapter、React SessionContext/SessionGate、unittest/Vitest/Playwright 与 deploy-control。`backend/requirements.txt` 已固定 `psycopg[binary,pool]==3.3.3`、`PyMySQL==1.1.1`。 `[VERIFIED: codebase/registry environment]`

## 最小目标设计

### 1. 收敛 evaluator，而非增加新 permission layer

```python
def evaluate(identity):
    username = normalize_username(identity.username)
    if username == PROTECTED_ADMIN_USERNAME:
        return ADMIN
    acl = load_one_canonical_acl_snapshot()  # error => non-admin denied
    if username in acl.readonly:
        return READ_EXPORT_ONLY
    if username in acl.full_access:
        return FULL_ACCESS
    return DENIED
```

删除 `required_permission`、`allowed_usernames`、`allowed_roles`、`readonly_export_usernames` env-backed fields、CSV parser 和 corresponding auth clone；OA identity 的 roles/permissions 仍可在 `/api/session/me` 作为信息返回，但不得参与 tier。protected admin 继续在 snapshot provider 前判定，保证 PG provider 故障时存在唯一恢复入口。 `[VERIFIED: 13-CONTEXT.md]`

用户名归一必须在 ACL DTO、snapshot、evaluator 和 OA adapter 共用一个现有/最小 helper；至少 trim、拒绝空值和控制字符、以同一比较键检测大小写重复。当前代码只做大小写敏感 trim/dedupe，planner 必须在实现前确认 OA `user_name` 的大小写合同；不能让 `ynsylp006` 与 `YNSYLP006` 形成双成员。 `[VERIFIED: codebase]`

### 2. OA sync 必须是可验证的 projection

在现有 `MySQLOARoleSyncExecutor.apply()` 的同一 OA MySQL transaction 内增加最窄验证：按 `perms=finops:app:view` 唯一解析 menu；加载三类 dedicated role id；确认三类 role 都绑定该 menu；查询该 menu 的全部 role binding，并要求 role-key 集合精确等于三类 dedicated roles。缺 menu、重复/歧义 menu、缺 role、缺 dedicated binding、存在 non-dedicated binding均抛现有 `OARoleSyncError` 子类，不写 PG。 `[VERIFIED: codebase + 13-CONTEXT.md]`

`OARoleSyncService.sync_access_control()` 不得在 disabled 时 return success。真实 ACL mutation 遇到 disabled/missing config 必须明确 `OARoleSyncConfigurationError`；本地单测通过注入现有 protocol fake executor，而不是恢复 production no-op。ACL semantic no-op 继续不调用 OA，因此 disabled 环境只能读取/保存普通 settings，不能伪成功修改 ACL。 `[VERIFIED: codebase + 13-CONTEXT.md]`

### 3. 发布清理与 runtime drift 分工

- 发布 preflight 只读列出目标 menu、三类 dedicated role、所有 `sys_role_menu` bindings 和三类 `sys_user_role` members；artifact 只含 role key/count/hash，不含 token/secret。 `[VERIFIED: existing preflight pattern]`
- 对 non-dedicated menu bindings 生成 exact `(role_id, menu_id)` before image 与 rollback INSERT；经 checkpoint 后仅删除这些 exact rows，不修改业务角色成员、不修改其它 menu。 `[VERIFIED: 13-CONTEXT.md]`
- runtime ACL PUT 只验证 exclusivity 并同步 dedicated user-role，不自动清理未知业务 role-menu；发现漂移返回失败，交给受控 deploy operation。 `[VERIFIED: 13-CONTEXT.md]`
- post-deploy 重新读取 `GET /system/menu/getRouters`（新 OA session/router 读取）或等价 OA 壳体验证；不以已打开浏览器 DOM 是否即时消失作为 gate。 `[VERIFIED: docs/architecture/oa-integration.md + 13-CONTEXT.md]`

### 4. 保留现有 PG/OA 补偿，不伪造跨库原子性

真变化仍按 OA target transaction -> PG ACL+audit transaction；PG 明确失败时 OA 补偿到 previous；补偿失败返回 `access_control_sync_inconsistent`。PG commit outcome unknown 继续用 mutation id + audit recovery。 `[VERIFIED: codebase]`

进程在 OA commit 后、PG commit 前崩溃仍存在跨库窗口；D-27 禁止为此新增 outbox。后端授权仍以未改变的 PG ACL fail-safe，菜单可能暂时漂移；现有 preflight/post-deploy、下一次受控 ACL mutation 前的 menu/role validation 和 `access_control_sync_inconsistent` runbook 必须负责发现，而不能宣称两库原子提交。 `[VERIFIED: codebase + 13-CONTEXT.md]`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
| --- | --- | --- | --- |
| APP RBAC | 新角色/策略框架 | existing `AccessDecision` + ACL snapshot | 只有 admin/full/read/denied 四结果。 `[VERIFIED: 13-CONTEXT.md]` |
| ACL persistence | 新表/通用 settings store | existing `app.app_settings` ACL family/CAS | 已有 version/lock/audit/invariant。 `[VERIFIED: codebase]` |
| 跨库 async consistency | outbox/worker | existing sync+compensation+preflight | locked out of scope。 `[VERIFIED: 13-CONTEXT.md]` |
| permission cache | Redis/identity decision cache | 每次最多一次 ACL snapshot | 撤权必须下一次判断生效。 `[VERIFIED: 13-CONTEXT.md]` |
| OA 管理 UI | APP/OA 新前端 | Settings single UI + adapter projection | 避免第二人工事实源。 `[VERIFIED: 13-CONTEXT.md]` |
| route decorators/guards | 新 auth framework | global route policy + one module guard | 已覆盖当前 API，改 evaluator 即全局生效。 `[VERIFIED: codebase]` |

## 精确旧代码删除清单

### Runtime backend

- `access_control_service.py`: 删除 `_parse_csv_environment`、四个 non-canonical dataclass fields、`FIN_OPS_*` 读取、permission branch、role branch、env readonly union；provider error 非 admin 直接 denied。 `[VERIFIED: codebase]`
- `auth.py`: local/default test synthetic identity 不再复制 `allowed_roles`/`required_permission`；身份模拟与授权 seed 分离。 `[VERIFIED: codebase]`
- `server.py`: `AccessControlService.from_environment(...)` 改成只注入 snapshot provider；不恢复其它 provider。 `[VERIFIED: codebase]`
- `oa_role_sync_service.py`: 删除 disabled silent return；增加 exact menu/dedicated-role binding validation；保留 bounded timeout、one OA transaction、exact user-role replacement。 `[VERIFIED: codebase]`
- `runtime_worker_handlers.py`: 它也构造 `OARoleSyncService.from_environment()`；必须确认仅用于 Settings service dependency wiring，不让 worker/new queue 成为 ACL owner。 `[VERIFIED: codebase]`

### Deploy/config/SQL/tools

- `deploy/oa/env/fin-ops.common.env.example`: 删除 `FIN_OPS_ALLOWED_USERNAMES`、`FIN_OPS_READONLY_EXPORT_USERNAMES`、`FIN_OPS_ALLOWED_ROLES` 的 APP admission 配置；保留并固定 `FIN_OPS_OA_REQUIRED_PERMISSION=finops:app:view` 仅供OA menu lookup/preflight/router验证，禁止接入APP evaluator。 `[VERIFIED: codebase]`
- `finops-deploy-control.sh::assert_runtime_env_contract`: 不再要求 `FIN_OPS_ALLOWED_USERNAMES`；反而 production ACL mutation/release gate 必须要求 role sync enabled/configured。 `[VERIFIED: codebase]`
- `fin-ops.secrets.env.example`: 默认 `FIN_OPS_OA_ROLE_SYNC_ENABLED=0` 与生产合同冲突；示例/validation 必须避免把 disabled 当可发布状态。 `[VERIFIED: codebase]`
- `fin_ops_role_binding.mysql.sql`: 现有 insert-only 行为不足；增加 exact non-dedicated inventory/controlled cleanup/rollback artifact，不得宽泛删除 `sys_role_menu`。 `[VERIFIED: codebase]`
- `settings_access_control_preflight.py`: 删除 env allow/readonly authority报告；`enabled=false` 必须 ineligible；OA facts加入 menu uniqueness、dedicated binding completeness、non-dedicated count/hash；post-deploy 加 denied direct API/router evidence。 `[VERIFIED: codebase]`
- `deploy/oa/README.md`、`docs/architecture/oa-integration.md` 与故障排查中“required permission/env allowlist 是 admission 条件”的旧描述必须删除。 `[VERIFIED: codebase]`

### Tests/frontend fixtures

- 把 `test_session_api` 中 permission-only=`full_access` 改为 permission-only=`denied`；provider failure + permission 也必须 denied；新增 role-only/env-only/readonly-env-only denied。 `[VERIFIED: codebase]`
- `tests/app_test_support.py::configure_access_control` 给 ACL service test 注入 OA executor fake，避免 disabled production no-op；default auth tests 显式 seed canonical `test_finops_user` 或使用明确 identity，禁止 evaluator test bypass。 `[VERIFIED: codebase]`
- 移除 backend tests 通过 `app._access_control_service.required_permission` 构造授权身份的假设。 `[VERIFIED: codebase]`
- `web/src/test/apiMock.ts`、`web/e2e/fixtures/apiMocks.ts` 不再用 permission 是否存在推导 allowed；增加 `permissions` 仍含 `finops:app:view` 但 tier/allowed denied 的 fixture。 `[VERIFIED: codebase]`
- 保留 SessionGate、Settings admin UI、full/read business UI 现有 tests；这些消费 normalized session，不需要改业务页面组件。 `[VERIFIED: codebase]`

### Whole-repo sentinel

实现完成后机械扫描必须证明：运行时代码无 `FIN_OPS_ALLOWED_USERNAMES|FIN_OPS_ALLOWED_ROLES|FIN_OPS_READONLY_EXPORT_USERNAMES` admission 引用；无`AccessControlService.required_permission`/`self.required_permission`/`self.allowed_roles`，permission/roles不参与`AccessControlService.evaluate`；`FIN_OPS_OA_REQUIRED_PERMISSION`只允许出现在OA menu asset/config/preflight/deploy/docs/test的固定`finops:app:view` selector合同，任何其它值或APP auth引用失败；非dedicated `sys_role_menu` binding为零；其它遗留字面量只允许migration/rejection/history docs中的防回归证据。 `[VERIFIED: codebase scan]`

## 风险与失败语义

| 风险 | 必须行为 | HTTP/ops evidence |
| --- | --- | --- |
| ACL provider/PG read error | YNSYLP005 仍 admin；其他账号 denied，不可用 permission/role fallback | `/api/session/me` 200 denied 或受保护 API 403；错误日志无 ACL payload `[VERIFIED: 13-CONTEXT.md]` |
| OA identity error/expired token | 不信任客户端 username；401/502/503 保持现有 mapping | auth tests `[VERIFIED: codebase]` |
| role sync disabled/missing config | 真 ACL change 不提交 PG，不返回成功 | 502 `oa_role_sync_failed`/明确 config code `[VERIFIED: 13-CONTEXT.md]` |
| menu/role missing或 menu 歧义 | OA transaction/PG 都不变 | 502 + preflight blocker `[VERIFIED: 13-CONTEXT.md]` |
| non-dedicated role-menu drift | runtime 不自动宽删；ACL PUT fail；deploy exact cleanup | drift count/hash + rollback SQL `[VERIFIED: 13-CONTEXT.md]` |
| OA network timeout | OA rollback；PG 不写 | bounded timeout + 502 `[VERIFIED: codebase]` |
| PG CAS conflict after OA target | OA compensate previous；返回 409/失败，不覆盖 current | service/repository test `[VERIFIED: codebase]` |
| PG failure + OA compensation failure | `access_control_sync_inconsistent`，人工核对两库 | 503 + critical secret-safe log `[VERIFIED: codebase]` |
| OA commit 后进程崩溃 | PG 仍是 APP authority；preflight/next command发现菜单漂移 | no false atomic claim `[VERIFIED: codebase]` |
| 大小写/重复/空用户名 | 统一比较键；空/控制字符/大小写重复 fail before OA | 400 validation matrix `[VERIFIED: codebase]` |
| identity/router cache | APP tier不依赖 roles/permissions cache；menu以新 router/session验收 | direct API immediate denied + refreshed OA shell `[VERIFIED: codebase]` |
| 已打开 OA DOM | 不承诺瞬时移除；不能影响后端撤权 | D-26 acceptance `[VERIFIED: 13-CONTEXT.md]` |

## Common Pitfalls

1. **只删 permission branch，保留 env/role union：** 任一旧 source 仍会恢复 full access。whole-repo sentinel 必须同时覆盖四组 env 与 constructor fields。 `[VERIFIED: codebase]`
2. **只同步 user-role，不查 role-menu：** 用户离开 dedicated role 仍可能因业务角色看到 menu。preflight/runtime 必须证明 menu binding exact set。 `[VERIFIED: codebase]`
3. **把 disabled sync 当“OA 不适用”：** 这会重现 PG success/OA stale。生产 gate 必须 fail closed。 `[VERIFIED: codebase]`
4. **在 SessionGate 叠加 roles 判断：** 直接 API 仍可绕过且形成双规则；修复只能在 evaluator。 `[VERIFIED: codebase]`
5. **复用 identity cache 保存 tier：** 会破坏下一次判断立即撤权；tier 必须每次从 ACL 派生。 `[VERIFIED: codebase]`
6. **普通 ACL PUT 自动删除未知 OA bindings：** 缺少审阅/rollback，可能伤及业务角色；cleanup 属于 root-owned exact operation。 `[VERIFIED: 13-CONTEXT.md]`
7. **隐式 test auth 继续靠 permission：** 全量测试会保护生产旁路；fixture 必须显式表达 ACL membership。 `[VERIFIED: codebase]`

## Validation Architecture

### Test Framework

| Property | Value |
| --- | --- |
| Backend | Python `unittest`; quick slice below `[VERIFIED: codebase]` |
| Frontend | Vitest; Settings/SessionGate/session API `[VERIFIED: codebase]` |
| Browser | Playwright `permissions-role-matrix.spec.ts` `[VERIFIED: codebase]` |
| Full gate | `bash scripts/verify.sh all` `[VERIFIED: AGENTS.md]` |

### 七类测试

| Category | Coverage required |
| --- | --- |
| 1. Business core unit | admin/full/read/denied；permission-only、role-only、env-only、provider-error 全 denied；trim/case/duplicate/empty；单 snapshot read。 `[VERIFIED: AGENTS.md]` |
| 2. Service/repository | ACL no-op；OA disabled/missing role/menu/non-dedicated drift；exact role replacement；PG CAS/audit；OA target/PG fail compensation；compensation fail inconsistent。 `[VERIFIED: AGENTS.md]` |
| 3. API contract | `/api/session/me` 保留 roles/permissions 但 denied；direct GET/unsafe API 403；dedicated ACL admin-only；409/502/503 shapes；generic settings 200 for full。 `[VERIFIED: AGENTS.md]` |
| 4. Read model/cache/worker | 负向：无 manifest/registry/outbox/dirty/cache 变化；identity cache hit 不改变 ACL immediate revoke；普通 settings 零 OA。 `[VERIFIED: AGENTS.md]` |
| 5. Frontend component | permission-present-but-denied -> SessionGate forbidden；admin ACL area唯一可见；full/read其它 UI保持；错误/conflict独立。 `[VERIFIED: AGENTS.md]` |
| 6. E2E integration | admin 把账号 full -> read -> removed；每步 session/API 与 OA dedicated role匹配；removed 即使带 permission/business role仍 forbidden；新 OA router无 menu。 `[VERIFIED: AGENTS.md]` |
| 7. Existing regression | 17 page routes至少 smoke；OA pending module guard；Settings、AppHealth、OA credentials、data reset、exports/writes、imports；其它 API DTO/read model/worker零变化。 `[VERIFIED: AGENTS.md]` |

### 推荐自动化命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_session_api \
  tests.test_auth_guard \
  tests.test_route_access_policy \
  tests.test_workbench_settings_sync_api \
  tests.test_app_settings_service \
  tests.test_oa_role_sync_service \
  tests.test_settings_access_control_preflight \
  tests.test_deploy_oa_script \
  tests.test_permissions_write_entry_inventory -v

cd web && npm test -- --run \
  src/test/SessionApi.test.ts \
  src/test/SessionGate.test.tsx \
  src/test/SettingsPage.test.tsx \
  src/test/App.test.tsx \
  src/test/PageRouteHost.test.tsx

cd web && npx playwright test e2e/permissions-role-matrix.spec.ts
bash scripts/verify.sh lint
bash scripts/verify.sh docs
bash scripts/verify.sh all
```

### Wave 0 gaps

- 扩展现有 `test_session_api.py` 与 `test_auth_guard.py`，不建新 auth suite。 `[VERIFIED: codebase]`
- 扩展 `test_oa_role_sync_service.py` 的 fake cursor/transaction 证据，覆盖 menu exclusivity 与 disabled。 `[VERIFIED: codebase]`
- 扩展 `test_settings_access_control_preflight.py`，使 disabled/non-dedicated binding ineligible，并加入 direct-route/restore 证据。 `[VERIFIED: codebase]`
- 更新 shared local application helper，使默认测试身份经 canonical ACL seed 授权；禁止 production evaluator bypass。 `[VERIFIED: codebase]`

## 性能与 I/O 目标

| Chain | Mechanical budget |
| --- | --- |
| session/access decision | 每次 evaluator 最多一次 ACL snapshot provider；permission/role/env 零读取；无 Redis。 `[VERIFIED: 13-CONTEXT.md]` |
| denied immediate revoke | 同一 OA token 下一次 `/api/session/me` 与 direct API 即读取最新 ACL；不等 OA identity TTL。 `[VERIFIED: codebase]` |
| generic settings save | 零 OA I/O；现有 one family-preserving PG transaction；无 queue/read model/cache I/O。 `[VERIFIED: codebase]` |
| ACL semantic no-op | 一次 locked read；零 PG write、零 audit、零 OA/menu I/O。 `[VERIFIED: codebase]` |
| ACL true mutation | 一次 OA validation+role transaction；一次 PG settings+audit transaction；失败补偿最多再一次 OA transaction。 `[VERIFIED: codebase]` |
| post-deploy sampling | 保留现有 ACL GET p95≤1000ms、ACL PUT max≤5000ms release gate；新增 session/direct-route latency只记录实测，不虚构更严数字。 `[VERIFIED: codebase]` |

## 生产验证闭环

### Preflight（只读，任何失败不发布）

1. 绑定 exact candidate/release/head 与安全 capability；读取 PG ACL/version/migration `0132`/validated CHECK。 `[VERIFIED: existing deploy gate]`
2. root env 中四个旧 admission env 必须不存在或为空；`FIN_OPS_OA_ROLE_SYNC_ENABLED=1` 且连接/timeout/role keys完整。 `[VERIFIED: 13-CONTEXT.md]`
3. OA menu `perms=finops:app:view` 必须唯一；三类 dedicated role存在且都绑定 menu；所有 menu bindings 的 role-key 集合精确为三类；三类 members 与 PG ACL target精确一致。 `[VERIFIED: 13-CONTEXT.md]`
4. 双 token 身份必须不同：`YNSYLP005` 为 admin；专用 denied identity建议使用问题账号 `YNSYLP006`，即使 OA payload仍有 `finops:app:view`/业务 roles也必须 denied。证据只存 salted hashes/counts。 `[VERIFIED: production evidence + existing preflight pattern]`
5. 若发现 non-dedicated binding，输出 exact-target before/after/rollback artifact并 checkpoint；未经批准不执行。 `[VERIFIED: 13-CONTEXT.md]`

### Post-deploy

1. `YNSYLP005`: `/api/session/me` admin；ACL GET/PUT可用；AppHealth/OA credentials/data reset仍 admin-only。 `[VERIFIED: 13-CONTEXT.md]`
2. 专用账号按 full -> read -> denied 运行现有 reversible matrix，finally 恢复原 accounts，并证明 OA三类 members同步。 `[VERIFIED: existing post-deploy tool]`
3. denied/YNSYLP006 证据：`/api/session/me` 200 + `allowed=false/access_tier=denied`；`GET /api/workbench`、`GET /api/oa-pending-payments/rows`（module guard）、代表性其余页面 API 和 unsafe POST 均403；直接打开 `/fin-ops/` 得到 SessionGate forbidden。 `[VERIFIED: codebase]`
4. 用该账号新 OA router/session 调 `/system/menu/getRouters` 或新登录 OA shell，确认无财务运营平台 menu；同时 SQL只读证明无 dedicated user-role、无 non-dedicated menu binding。旧浏览器 DOM不作为失败。 `[VERIFIED: docs/architecture/oa-integration.md + 13-CONTEXT.md]`
5. durable audit request-id 数量、ACL/role restore、menu exclusivity、完整全量 tests、17-page smoke 与无新增 runtime registry/read model diff 全部通过后才关闭 phase。 `[VERIFIED: AGENTS.md]`

## Security Domain

| Security category | Applies | Control |
| --- | --- | --- |
| Authentication / identity | yes | OA backend identity resolver；不信任 body username。 `[VERIFIED: SECURITY.md]` |
| Session management | yes | token只用于解析 username；cached roles/permissions不得决定 APP tier。 `[VERIFIED: codebase]` |
| Access control | yes | fixed admin + canonical ACL-only evaluator + global/module guards。 `[VERIFIED: 13-CONTEXT.md]` |
| Input validation | yes | strict ACL DTO、version、tier、username、duplicate/case checks。 `[VERIFIED: codebase]` |
| Cryptography | no new control | 使用现有 token transport与 hash/redaction；不自研密码学。 `[VERIFIED: SECURITY.md]` |

### Threat patterns

| Threat | STRIDE | Mitigation |
| --- | --- | --- |
| permission/role/env privilege bypass | Elevation of Privilege | delete all alternate admission branches + negative matrix `[VERIFIED: codebase]` |
| stale OA menu after revoke | Information Disclosure / Spoofing UX | exact role projection + menu exclusivity + new router evidence `[VERIFIED: 13-CONTEXT.md]` |
| body actor/admin injection | Spoofing / Elevation | server session actor + strict DTO + fixed admin `[VERIFIED: codebase]` |
| cross-DB partial failure | Tampering | existing compensation, inconsistent state error, preflight/recovery evidence `[VERIFIED: codebase]` |
| secret leakage | Information Disclosure | hashed usernames in artifacts; no token/password/full ACL logs `[VERIFIED: SECURITY.md]` |

## Environment Availability

| Dependency | Required By | Available locally | Version | Fallback |
| --- | --- | --- | --- | --- |
| Python | backend/tests | yes | 3.11.5 | none `[VERIFIED: local environment]` |
| Node/npm | frontend/tests | yes | Node 26.3.0 / npm 11.16.0 | project CI runtime remains authoritative `[VERIFIED: local environment]` |
| PostgreSQL CLI/psycopg | integration/migration | yes | psql 17.10 / psycopg 3.3.3 | disposable test DB if configured `[VERIFIED: local environment]` |
| MySQL CLI/PyMySQL | OA adapter tests/ops | yes | mysql 8.0.45 / PyMySQL 1.1.1 | fake cursor for unit; real staging required for release `[VERIFIED: local environment]` |
| Docker | disposable infra | yes | 28.5.1 | existing local test mechanisms `[VERIFIED: local environment]` |
| Production OA/PG | release evidence | not touched in research | — | authorized preflight only `[VERIFIED: task scope]` |

## Assumptions Log

| # | Claim | Risk if wrong |
| --- | --- | --- |
| A1 | OA usernames should compare case-insensitively while preserving canonical OA spelling. `[ASSUMED]` | Wrong collation/identity rules could deny a legitimate mixed-case account or create duplicate projection; planner must verify OA `sys_user.user_name` and `/getInfo` contract before locking normalization. |
| A2 | `/system/menu/getRouters` can be called with the dedicated bearer in production evidence. `[ASSUMED]` | If operational access prevents automation, planner must require a fresh OA shell/manual evidence checkpoint plus read-only SQL, not silently omit menu verification. |

## 计划者必须回答的问题

1. **用户名比较键是什么？** 必须用 OA `sys_user.user_name` collation与 `/system/user/getInfo.userName` 实测决定 uppercase/casefold 规则，并让 DTO/evaluator/OA adapter共用；不得各自处理。 `[VERIFIED: codebase gap]`
2. **non-dedicated menu binding 的 exact cleanup owner/rollback artifact 放在哪里？** 推荐扩展现有 deploy-control/preflight 与 `fin_ops_role_binding.mysql.sql`，不新增通用迁移框架。 `[VERIFIED: codebase]`
3. **default unittest auth 如何显式进入 canonical ACL？** 推荐在 `tests/app_test_support.py`/API contract harness seed `test_finops_user`，并更新少量 direct builders；禁止把 test bypass 留在 production evaluator。 `[VERIFIED: codebase gap]`
4. **production denied bearer 是否固定 YNSYLP006？** 若是，preflight/post-deploy必须绑定其 salted identity hash且确认不在 ACL；若不是，仍需额外保留 YNSYLP006 的只读 session/menu证据。 `[VERIFIED: production evidence]`
5. **OA router evidence 自动还是人工？** 两者都必须绑定 exact release、新 session、账号 hash与菜单 absence；旧 DOM截图不算。 `[VERIFIED: 13-CONTEXT.md]`
6. **失败 HTTP code 是否保持现有 route mapping？** 推荐 disabled/missing menu/role/network用现有 `oa_role_sync_failed` 502；补偿/未知漂移用 `access_control_sync_inconsistent` 503，避免新错误体系。 `[VERIFIED: codebase]`

## Sources

### Primary (HIGH confidence)

- `13-CONTEXT.md` D-01..D-27 — locked scope and decisions.
- `AGENTS.md`, `SECURITY.md` — module/testing/security/deploy constraints.
- `access_control_service.py`, `auth.py`, `oa_identity_service.py`, `server.py`, `route_access_policy.py` — authorization runtime.
- `routes_settings.py`, `app_settings_service.py`, `state_store_protocol.py`, `state_store.py`, `postgres_state_store.py`, `postgres_repositories/ops_tax_etc.py`, migration `0132` — canonical ACL/CAS/audit.
- `oa_role_sync_service.py`, `fin_ops_menu.mysql.sql`, `fin_ops_role_binding.mysql.sql`, `fin_ops_user_role_sync.mysql.sql`, `settings_access_control_preflight.py`, deploy-control/env assets — OA projection and release gate.
- `SessionContext.tsx`, `SessionGate.tsx`, `SettingsPage.tsx`, workbench API, component/E2E mocks — frontend consumption and fixtures.
- Required four module `boundary-io.md` files — current ownership contracts.
- Authorized production session evidence supplied for YNSYLP006 on 2026-08-02 — reproduced impact.

## Metadata

**Confidence:** HIGH for root cause, call chains, current code and minimal design; MEDIUM for OA router automation and username case normalization until target OA behavior is verified.

**Research date:** 2026-08-02

**Valid until:** 2026-08-09 (security-sensitive, active codebase)

**Packages installed:** none

**Runtime state inventory:** not applicable; this is authorization convergence, not rename/refactor/migration of stored identifiers.

**Graph context:** GSD graphify was disabled; CodeGraph index was healthy at 964 files / 34,966 nodes / 85,608 edges during the code scan. `[VERIFIED: local tooling]`
