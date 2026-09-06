# 权限与审计模块边界与 I/O

日期：2026-09-07

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：权限与审计模块负责 session/access-control/audit，不承载业务判断；所有写 API 必须通过权限边界。现金写操作由明确私密路由策略排除全局操作历史，不能伪装只读请求绕过权限。
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
| Canonical ACL snapshot | Settings snapshot provider | 非管理员每次判断最多读取一次同一 `access_control_version`；`page_access_accounts[].page_keys` 决定页面集合，账号缺席、空集合、非法 payload 或 provider failure 一律 denied |
| Permission check | `server.py` + `route_access_policy.py` + module-owned guard | 每个 protected route 必须映射到一个或多个页面 key；命中任一授权页面才可进入，admin-only route 额外校验固定管理员；未知受保护路由 fail closed |
| ACL audit event | Settings repository critical section | actor 来自后端 admin session，request id 来自受信 HTTP adapter；与 canonical version 同事务，no-op/失败无 success audit |
| Audit event | business service/route | unsafe HTTP route 先经 operation history 语义注册表归一为稳定 action code/用户动作/对象文案，再记录服务端 session 的 actor id/name/account 快照和结果；需要在业务页面展示操作者的领域记录（包括 Workbench 异常审阅）必须在写入时固化同一身份快照，只向页面发布 account/name，不发布内部 actor id，也不在读取时反查或兜底；同一 HTTP mutation 中 service 级审计继承受信 request id，避免拆成重复逻辑操作；有界业务证据随 completion 固化；不信任 body actor |
| OA facts export audit | OA pending read route | 页面授权账号或管理员成功下载后记录 `oa_pending_payment_source_export_downloaded`；只接收 session actor、来源、数量和文件名，不接收 OA 行内容。 |
| Workbench exception compatibility command | `POST /api/workbench/exception/apply` | 兼容 API 继续保留自动异常/行级异常能力，但 route 的 actor 只来自已认证 session；body `actor` / `confirmed_by` 不能覆盖业务或审计身份。删除未配对工具栏人工“异常处理”不等于删除该后端兼容能力。 |
| Workbench receipt draft / print | `POST /api/workbench/actions/receipt-draft` + `POST /api/workbench/actions/print-receipt` | draft 是无持久化的 read-only POST，因此不产生通用 mutation audit，但 handler 仍要求 Workbench 写权限并通过全局/OA 安全 gate；print 是受保护写动作，actor/account/name 和 request id 只来自已认证 session，service 记录生成与打印请求审计。客户端提交的付款单位、日期和明细不是 actor 来源。 |
| Data reset audit | Settings request repository / settings-maintenance worker | queued 与 receipt 消费/job/outbox 同事务；started/success/partial/failed 由 worker durable audit 记录。actor 来自 admin session，reason 必填，记录 request/job/action/fingerprint/receipt，不记录 OA 密码。 |
| Page proof dispatch | System Audit + registered page key | `PAGE_AUDIT_REGISTRY` 全覆盖校验；18 页只允许有限 executor；未实现 proof fail closed，不动态选择函数。业务页面没有 Audit 控件或通用前端调用；`operation-history` proof 只检查覆盖点与 append-only 数据库保护，不触发业务写。 |
| App Health System Audit request | admin session + `page=app-health-operations` | 唯一前端 Audit 入口，只读；由 system owner 在一个 caller-owned PostgreSQL snapshot 内编排其余 17 页 proof。权限边界只授权读取，不授予 refresh、repair 或生产修复能力 |
| Operation history request | 005 管理员 session + filter/cursor/operation key | 只读取最近 `audit.coverage_started` 之后的 `audit.events`；列表按 request 聚合，详情只输出业务投影；非管理员 403；不输出 secret/raw payload/内部 ID，不触发 read model。 |
| External evidence registration/revocation | 运维 CLI + manifest/artifact + `--apply --actor --reason` | 无 HTTP/UI 入口；API/worker/readonly DB role 只有 select，apply 使用受控 migrator/operator role。service 校验完整 manifest 和 artifact，repository 原子 append/revoke 并写 `audit.events`。dry-run 不连接数据库；生产 apply 需要独立发布/运维授权。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Session payload | frontend context | normalized `allowed/can_access_app/can_admin_access/allowed_page_keys` 只来自 fixed 005 或 canonical snapshot；OA roles/permissions 仅信息性返回 |
| Access decision | global policy / module-owned guard | 同一 evaluator 的 admin/page-set/denied 结果，ACL 删除后下一次请求立即生效，provider failure fail closed |
| ACL audit record | `audit.events` | 记录 mutation id、actor、server request id、before/after version/outcome 与 changed username hashes；不泄露 secret/完整 ACL |
| Audit record | `audit.events` | 所有受保护写 API 先写 requested 事件；失败则业务写不执行。完成事件记录 HTTP 结果；业务服务事件继续记录领域前后值且不泄露 secret。 |
| System Audit report | App Health admin UI / release gate | 必须保留 proof availability、contract revision、snapshot、integrity/freshness/queue 和 external evidence 边界；权限通过不等于数据证明通过 |
| External evidence audit record | audit store/operator | 记录 evidence id/domain/fingerprint、actor、reason 与 register/revoke 动作；不得记录 manifest item 原文、credential 或 secret。 |

## 持久化与投影

### 现金私密页面

- 新页面 key 为 `cash`，仅“可用/不可用”。既有 fixed 005 管理员规则不变；普通账号只有明确保存该 key 才能访问现金 API，不新增 reader/editor/admin/delete 档位。
- `is_cash_request` 只匹配 `/api/cash` 或 `/api/cash/` 路径段，不匹配 cash-back 等近似前缀。现金 POST/PUT/DELETE 仍是状态变更，不能加入 read-only POST allowlist。
- 全局 requested/completed 操作历史两处均按同一现金路由策略排除，不保存业务参数、流水、任务或配置；平台专用 ACL 管理仍走原安全审计，不因 cash key 取消。
- `/api/background-jobs` 的 ordinary 页面 owner 集合明确排除 cash，防止扩充 ASSIGNABLE_PAGE_KEYS 后现金专用账号获得普通任务读取权限。现金不登记全局 PAGE_AUDIT_REGISTRY，不通过 System Audit 暴露现金事实或统计。
- 后端先行期间不新增前端导航/现金勾选，不自动授予非005账号现金权限。既有 Settings API GET/PUT 和 state normalization 原样保留 cash key；旧 UI 单项勾选也保留未知项，但“全选”按旧页面清单重建集合，因此在 F 阶段 UI 接入前不进行非005现金授权。该发布范围不新增 feature flag 或兼容授权逻辑。

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
| System Audit frontend | `web/src/pages/AppHealthOperationsPage.tsx`、`web/src/features/appHealth/api.ts`；业务页不得重新引入通用 Page Audit 组件或 page-key 调用 |
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

- 新增写 API 必须更新 permissions inventory tests 和模块 boundary docs；后端先行阶段 inventory 精确声明仅 cash 暂无前端页面，其余页面集合保持完全匹配。
- 动态管理员 provider、`get_admin_usernames`、运行时 `FIN_OPS_ADMIN_USERNAMES` 和本地 auth clone 已删除；不得以兼容路径恢复。
- dev/test auth 环境变量及其 runtime 分支已删除；遗留值必须保持无效，测试身份只能由 `tests/app_test_support.py` 显式注入，不能进入 runtime package。
- permission/role/三项退役 env admission branch 已删除；`finops:app:view` 只允许出现在 OA selector、部署/测试/文档的明确路径中，唯一 whole-repo inventory owner 负责机械阻止恢复。
- Settings 专用 ACL route 复用 admin session resolver；generic mutation resolver 仍服务拥有 settings 页面权限的普通账号，不能整体升级为 admin-only。
- Audit owner 接收 settings transaction 提交的 session actor、版本摘要、changed username hashes、mutation id 和 server request id；不接收 token、密码或完整 ACL payload。
- route access policy 的只读 POST allowlist 只能登记无 canonical 写入、无 durable job 创建、无状态持久化的查询/preview/calculate；导入 preview、ETC preview 和后台 job acknowledge/retry 均属于写入。
- 后端 route 从已解析 session 传递 actor/owner；客户端 actor 字段不得重新成为业务或审计身份源。
