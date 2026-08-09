# 权限与审计模块边界与 I/O

日期：2026-08-09

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：权限与审计模块负责 session/access-control/audit，不承载业务判断；所有写 API 必须通过权限和审计边界。
- 当前缺口：部分 route 仍在 `server.py`，权限矩阵和 route owner 拆分需持续同步；生产 OA/proxy 行为仍需发布后 smoke。
- 旧代码删除状态：共享 `route_access_policy.py` 已在 body 解析前覆盖受保护 API；旧 fail-open background owner fallback、运行时 synthetic dev/test session、默认重置密码与 legacy OA/project/ledger/reminder/matching HTTP families 已删除并由回归测试保护。

## 职责边界

### 负责

- Session API、权限映射、访问控制、审计记录、前端权限 gate。
- 为业务模块提供统一 permission owner。
- 固定 005 + single-snapshot ACL evaluator、global/module route enforcement，以及 ACL actor/request-id/audit outcome 合同。

### 不负责

- 不决定业务状态是否合法。
- 不直接执行业务写操作。
- 不在前端隐藏权限失败作为唯一防护。
- 不保存或修改 Settings ACL，不同步 OA role members，不把 OA role/permission、`finops:app:view` 或退役 env 解释为 APP grant。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Session/auth request | `auth.py`、session API | 运行时必须提供真实 OA Bearer/cookie token；OA 只解析 identity；roles/permissions 保留为信息字段，不参与 APP tier。退役 dev/test auth 环境变量不再被运行时代码读取，不能生成 identity。 |
| Canonical ACL snapshot | Settings snapshot provider | 非管理员每次判断最多读取一次同一 `access_control_version`；完整 full/read memberships 决定 tier，缺席/非法/provider failure 一律 denied |
| Permission check | `server.py` + `route_access_policy.py` + module-owned guard | 受保护 unsafe method 默认要求 mutation；只有登记的只读 POST 可豁免；module-owned OA pending guard 保持独立且必须等价 fail closed |
| ACL audit event | Settings repository critical section | actor 来自后端 admin session，request id 来自受信 HTTP adapter；与 canonical version 同事务，no-op/失败无 success audit |
| Audit event | business service/route | 记录对象、动作、服务端 session 的 actor id/name/account 快照、结果，不信任 body actor |
| Data reset audit | Settings request repository / settings-maintenance worker | queued 与 receipt 消费/job/outbox 同事务；started/success/partial/failed 由 worker durable audit 记录。actor 来自 admin session，reason 必填，记录 request/job/action/fingerprint/receipt，不记录 OA 密码。 |
| Page Audit request | admin session + registered frontend page key | `PAGE_AUDIT_REGISTRY` 全覆盖校验；18 页只允许有限 executor；未实现 proof fail closed，不动态选择函数。`operation-history` 只检查覆盖点与 append-only 数据库保护，不触发业务写。 |
| App Health system Audit request | admin session + `page=app-health-operations` | 只读；由 system owner 在一个 caller-owned PostgreSQL snapshot 内编排其余 17 页 proof。权限边界只授权读取，不授予 refresh、repair、写 read model 或生产修复能力 |
| Operation history request | 005 管理员 session + filter/cursor/operation key | 只读取最近 `audit.coverage_started` 之后的 `audit.events`；列表按 request 聚合，详情只输出业务投影；非管理员 403；不输出 secret/raw payload/内部 ID，不触发 read model。 |
| External evidence registration/revocation | 运维 CLI + manifest/artifact + `--apply --actor --reason` | 无 HTTP/UI 入口；API/worker/readonly DB role 只有 select，apply 使用受控 migrator/operator role。service 校验完整 manifest 和 artifact，repository 原子 append/revoke 并写 `audit.events`。dry-run 不连接数据库；生产 apply 需要独立发布/运维授权。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Session payload | frontend context | normalized `allowed/access_tier/capabilities` 只来自 fixed 005 或 canonical snapshot；OA roles/permissions 仅信息性返回 |
| Access decision | global policy / module-owned guard | 同一 evaluator 的 admin/full/read/denied 结果，ACL 删除后下一次请求立即生效，provider failure fail closed |
| ACL audit record | `audit.events` | 记录 mutation id、actor、server request id、before/after version/outcome 与 changed username hashes；不泄露 secret/完整 ACL |
| Audit record | `audit.events` | 所有受保护写 API 先写 requested 事件；失败则业务写不执行。完成事件记录 HTTP 结果；业务服务事件继续记录领域前后值且不泄露 secret。 |
| Page/System Audit report | admin API consumer | 必须保留 proof availability、contract revision、snapshot、integrity/freshness/queue 和 external evidence 边界；权限通过不等于数据证明通过 |
| External evidence audit record | audit store/operator | 记录 evidence id/domain/fingerprint、actor、reason 与 register/revoke 动作；不得记录 manifest item 原文、credential 或 secret。 |

## 持久化与投影

- Own read model：无。
- Persistence：permissions 不持久化 ACL 或 access decision；ACL success audit 由 Settings repository 与 `app.app_settings` 同事务写 `audit.events`，其他业务 audit 由其 owner UoW 写入。
- Related docs：`SECURITY.md`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend auth | `backend/src/fin_ops_platform/app/auth.py`、`backend/src/fin_ops_platform/app/route_access_policy.py` |
| Backend services | `access_control_service.py`（fixed 005 + snapshot evaluator）、`audit.py` |
| Page Audit registry | `backend/src/fin_ops_platform/services/page_audit_registry.py` |
| Routes | `backend/src/fin_ops_platform/app/server.py`、`routes_settings.py`、route owners with protected endpoints |
| Frontend session | `web/src/features/session/api.ts`、`web/src/contexts/SessionContext.tsx` |
| Frontend gates | `web/src/components/auth/SessionGate.tsx`、`useSessionPermissions()`、`useOptionalSessionPermissions()` |
| App health | `web/src/contexts/AppHealthStatusContext.tsx` |
| Tests | `tests/test_auth_guard.py`、`tests/test_permissions_write_entry_inventory.py`、`tests/test_audit*.py`、`web/e2e/permissions-role-matrix.spec.ts` |

## 依赖方向

- 允许依赖：OA identity source、Settings ACL snapshot provider、access control service、audit service。
- 必须通过：一次 canonical evaluator + explicit global/module route permission check；ACL command/audit 必须回到 Settings owner。
- 禁止绕过：permission/role/env/fixed marker grant；运行时 synthetic dev/test identity；access-decision cache；write endpoint without permission owner；frontend-only authorization；logging secrets；Audit route 触发 refresh/repair；把 system Audit 的 admin access decision 当作 integrity 结论。

## 测试与验证

- `tests/test_auth_guard.py`
- `tests/test_permissions_write_entry_inventory.py`
- `tests/test_audit_service.py`
- `web/e2e/permissions-role-matrix.spec.ts`

## 当前缺口和删除条件

- 新增写 API 必须更新 permissions inventory tests 和模块 boundary docs。
- 动态管理员 provider、`get_admin_usernames`、运行时 `FIN_OPS_ADMIN_USERNAMES` 和本地 auth clone 已删除；不得以兼容路径恢复。
- dev/test auth 环境变量及其 runtime 分支已删除；遗留值必须保持无效，测试身份只能由 `tests/app_test_support.py` 显式注入，不能进入 runtime package。
- permission/role/三项退役 env admission branch 已删除；`finops:app:view` 只允许出现在 OA selector、部署/测试/文档的明确路径中，唯一 whole-repo inventory owner 负责机械阻止恢复。
- Settings 专用 ACL route 复用 admin session resolver；generic mutation resolver 仍服务 full-access 普通写，不能整体升级为 admin-only。
- Audit owner 接收 settings transaction 提交的 session actor、版本摘要、changed username hashes、mutation id 和 server request id；不接收 token、密码或完整 ACL payload。
- route access policy 的只读 POST allowlist 只能登记无 canonical 写入、无 durable job 创建、无状态持久化的查询/preview/calculate；导入 preview、ETC preview 和后台 job acknowledge/retry 均属于写入。
- 后端 route 从已解析 session 传递 actor/owner；客户端 actor 字段不得重新成为业务或审计身份源。
