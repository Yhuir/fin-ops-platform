# OA 集成架构

日期：2026-08-02

本文记录当前 OA 身份、菜单投影和 APP 授权合同。历史上由 `finops:app:view`、OA role/permission 或环境名单直接授予 APP 访问的方案已经退役，不能作为实现、测试或运维依据。

## 系统边界

`fin-ops-platform` 以 OA 同域 iframe 子系统运行：

- OA 前端路径：`/fin-ops/`
- APP API 路径：`/fin-ops-api/`
- OA 登录态：`Admin-Token`，由前端作为 Bearer token 传给 APP API
- OA 身份接口：`/system/user/getInfo`
- OA 动态菜单接口：`/system/menu/getRouters`

OA identity adapter 只认证 token 对应的 canonical username，并保留 display name、department、roles 和 permissions 作为信息字段。APP 不自建登录页，也不信任前端自报 username；OA roles/permissions 不参与 APP tier 决策。

应用运行时不包含 synthetic dev/test session。本地开发与生产均必须提供真实 OA token；测试身份只由测试夹具显式注入。四项历史 dev/test auth 环境变量已退役，任一 key 存在即在 state-store I/O 前阻断 Application 启动，并由 deploy-control 再次阻断发布。

## 四个独立责任层

| 层 | Owner | 事实与责任 | 明确不负责 |
| --- | --- | --- | --- |
| OA identity | `OAIdentityService` / `auth.py` | 验证 token，取得 `sys_user.user_name` canonical spelling | 不授予 APP tier |
| APP authorization | `AccessControlService` + Settings canonical ACL | 固定 `YNSYLP005` admin；其他账号按 ACL `full_access` / `read_export_only`，缺席即 denied | 不读取 OA role/permission/env 作为 fallback |
| OA menu projection | `OARoleSyncService` | 把同一 canonical ACL 结果投影成一个固定菜单的三个专用角色成员 | 不写 APP ACL，不决定 API 权限 |
| Deployment verification | preflight collector + deploy control | 标准发布仅使用 005；双身份 preflight 可显式验证 fixed menu exact topology，但不是激活前置条件 | 不做 runtime member sync，不清理业务 role/member/menu |

菜单可见性、前端 `SessionGate` 和后端 direct API denial 是独立强制层，但必须投影同一 canonical ACL 结果。菜单可见不等于 APP 已授权；菜单暂时可见的 denied 用户仍必须被 APP session/API 拒绝。

## 唯一 APP 授权事实源

- `YNSYLP005` 是固定 protected administrator。
- `/settings` 的专用 ACL API 是唯一人工权限入口。
- 非管理员只允许 `full_access` 或 `read_export_only`；账号不在 ACL 中派生为 `denied`。
- username 等值与去重使用 casefold comparison key，对外及 OA assignment 保留 `sys_user.user_name` canonical spelling。
- 每次非管理员判断最多读取一次 canonical ACL snapshot；缺失、格式错误或 provider 失败全部 fail closed。
- OA identity cache 只缓存身份信息，不缓存 APP access decision；ACL 删除后下一次 session/API 判断立即 denied。
- 三项历史 APP admission 环境名单已退役，任一 key 存在即阻断 release，不能作为 fallback；精确 key 清单只由 canonical deploy runbook/preflight owner 维护。

`FIN_OPS_OA_REQUIRED_PERMISSION` 必须精确为 `finops:app:view`，但它只属于 OA integration：用于定位唯一 `财务运营平台` menu。它不能授予 APP access，也不能替代 Settings ACL。

## OA fixed-menu projection

OA 中只允许一个 `permission=finops:app:view` 的 menu，且该 menu 的 role binding key exact set 必须为：

- `finops_read_export`
- `finops_full_access`
- `finops_admin`

三个 role key、menu 和三条 dedicated binding 都必须唯一。任何缺失、重复或额外 non-dedicated binding 都是 drift。

真实 ACL 变化在一个 OA transaction 内先锁定并验证 fixed selector、唯一 menu、三个唯一专用 role、exact 三 binding 且无 non-dedicated binding。全部验证在任何 DML 前完成。通过后 runtime 只替换三个专用 role 的 `sys_user_role` members：

- `read_export_only` → `finops_read_export`
- `full_access` → `finops_full_access`
- 固定 `YNSYLP005` → `finops_admin`

runtime 不创建或删除 menu/role/binding，不修改业务 role、业务 role members、其他 menu 或其他 binding。disabled、missing、selector/role/binding drift、连接/读/写 timeout 都必须 rollback/fail closed，不能返回保存成功。

## Settings persistence and compensation

- generic settings save 与 ACL semantic no-op 都是零 OA I/O。
- 真实变化先应用目标 OA members，再以同一 Settings critical section 提交 PostgreSQL canonical ACL 与 durable audit。
- 目标 OA 失败返回 `502 oa_role_sync_failed`，PostgreSQL/audit 不写入。
- OA target 已应用但 PostgreSQL 失败时，最多使用 previous snapshot 补偿一次。
- 补偿成功返回持久化失败；补偿或 commit outcome 无法确认返回 `503 access_control_sync_inconsistent`，停止自动继续并要求人工核对。

该链路不新增 outbox、worker、read model、Redis 或 permission cache。

## Deployment-owned exact verification

Runtime 发现 non-dedicated fixed-menu binding 会拒绝变更，不会自行清理。一次性 cleanup 已完成并从稳态发布链删除；标准部署只读取 005，并验证 migration/CHECK、strict env 与数据库 ACL guard。release-bound、root-owned `0600` 双身份 artifact 仅由显式专项验收生成，用于复核 canonical ACL、唯一 menu、三专用 role/binding/member 与 fresh OA router，不阻断标准激活。禁止 broad delete、legacy self-update 或任意手工 SQL fallback。

## App shell and direct access enforcement

- 前端启动先请求 `/api/session/me`；`SessionGate` 在 loading/forbidden/expired/error 时不挂载业务 route。
- 前端只消费 normalized `allowed`、`access_tier` 和 capabilities；OA roles/permissions 只展示为信息。
- 后端 global route policy 与模块自有 guard 消费同一 ACL outcome。直接输入 `/fin-ops/` 或调用受保护 `/fin-ops-api/*` 不能绕过授权。
- `read_export_only` 只能查询和导出；业务 mutation 返回 `403 permission_denied`。
- `YNSYLP005` 才能调用 ACL、App Health、OA credentials、data reset 等 admin-only control plane。

OA 菜单撤销必须用角色投影后的新 `/system/menu/getRouters` 响应或新 OA shell session 验收；刷新前的旧浏览器 DOM 不是证据。APP denial 则以下一次 fresh APP session/direct API response 为边界，不等待 OA shell 刷新。

## Release preparation and evidence

当前仓库已经实现 release-prep 合同，但本文不声称生产已部署：

1. deploy-control 比较 exact candidate 与唯一 active release，自动判定 `frontend`、`runtime` 或 `acl`；普通发布只读取 005。
2. 需要专项复验时显式生成 candidate-bound 双身份 read-only preflight artifact 及 SHA-256；标准发布不生成也不消费。
3. current runtime checkpoint 通过后 quiesce API/workers，再执行 profile 对应的 activation；runtime/ACL 执行 migration/CHECK，frontend 只发布 dist 和重启已有 runtime。
4. frontend 完成 pre/T+0 exact dist、ready、005 session 与公开 shell/asset；runtime/ACL 完成 T+0/T+60/T+300、queue、audit 与 evidence/hash gate。
5. ACL profile 才使用 fresh admin/representative tokens，逐档证明 full → read → denied、direct API、fresh OA router、三专用 role exact set、non-target invariants、audit 和 finally restore/read-back。

任何 preflight、router/session restore 或 evidence hash 失败都 fail closed。ACL candidate 失败时保持 maintenance 并 forward repair，不能启动 vulnerable binary。

生产操作、secret 传递、helper bootstrap 和完整命令以 `../../deploy/oa/README.md` 为唯一 runbook。token 只能经 stdin/受控 loader 传递，不得进入 argv、日志、release 或 artifact。

## 当前证据与生产边界

已完成的本地自动化证据：

- backend identity/ACL/direct API/role projection/inventory：`tests/test_session_api.py`、`tests/test_auth_guard.py`、`tests/test_oa_role_sync_service.py`、`tests/test_permissions_write_entry_inventory.py`
- frontend SessionGate/17-route/restore：`web/src/test/SessionGate.test.tsx`、`web/src/test/PageRouteHost.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts`
- deploy ACL preflight/steady-state topology：`tests/test_settings_access_control_preflight.py`、`tests/test_deploy_oa_script.py`

本地证据不证明真实 OA schema、network、fresh router、同域 cookie 或 production restore。权限专项验收只有在 candidate-bound preflight、post-deploy artifact/hash 和人工验收全部通过后才可声明完成；普通功能发布不重复该专项链路。

## 代码与文档 owner

- Identity/session：`backend/src/fin_ops_platform/services/oa_identity_service.py`、`backend/src/fin_ops_platform/app/auth.py`、`web/src/features/session/api.ts`
- APP authorization：`backend/src/fin_ops_platform/services/access_control_service.py`
- Settings ACL command：`backend/src/fin_ops_platform/services/app_settings_service.py`
- OA menu projection：`backend/src/fin_ops_platform/services/oa_role_sync_service.py`
- Preflight/artifact：`backend/src/fin_ops_platform/tools/settings_access_control_preflight.py`
- Deployment verification：`backend/src/fin_ops_platform/tools/settings_access_control_preflight.py`、`deploy/oa/bin/finops-deploy-control.sh`
- Canonical deploy runbook：`../../deploy/oa/README.md`
- APP runtime ownership：`../app-architecture/runtime-and-ownership.md`
