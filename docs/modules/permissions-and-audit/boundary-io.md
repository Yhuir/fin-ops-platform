# 权限与审计模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：权限与审计模块负责 session/access-control/audit，不承载业务判断；所有写 API 必须通过权限和审计边界。
- 当前缺口：部分 route 仍在 `server.py`，权限矩阵和 route owner 拆分需持续同步。
- 旧代码删除条件：旧无权限校验写入口不存在，permissions inventory tests 覆盖。

## 职责边界

### 负责

- Session API、权限映射、访问控制、审计记录、前端权限 gate。
- 为业务模块提供统一 permission owner。

### 不负责

- 不决定业务状态是否合法。
- 不直接执行业务写操作。
- 不在前端隐藏权限失败作为唯一防护。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Session/auth request | `auth.py`、session API | 解析身份、角色、权限 |
| Permission check | route/service | 写入口必须显式校验 |
| Audit event | business service/route | 记录对象、动作、身份、结果 |
| Workbench read/write access | protected Workbench routes | canonical direct reads 仍要求有效 session；mutation 仍要求 `can_mutate_data`，actor/tenant 来自服务端 session。移除页面 read-model version/status 不改变 relation business CAS、idempotency 或 audit。 |
| Page Audit request | admin session + registered frontend page key | `PAGE_AUDIT_REGISTRY` 全覆盖校验；17 页只允许有限 executor；未实现 proof fail closed，不动态选择函数。`cost-statistics` 使用唯一 `cost_statistics` executor，直接进入成本专属只读 repository；通用 page-business repository 不保留成本 fallback。 |
| App Health system Audit request | admin session + `page=app-health-operations` | 只读；由 system owner 在一个 caller-owned PostgreSQL snapshot 内编排其余 16 页 proof。权限边界只授权读取，不授予 refresh、repair、写 read model 或生产修复能力 |
| External evidence registration/revocation | 运维 CLI + manifest/artifact + `--apply --actor --reason` | 无 HTTP/UI 入口；API/worker/readonly DB role 只有 select，apply 使用受控 migrator/operator role。service 校验完整 manifest 和 artifact，repository 原子 append/revoke 并写 `audit.events`。dry-run 不连接数据库；生产 apply 需要独立发布/运维授权。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Session payload | frontend context | 权限字段稳定 |
| Access decision | route/service | fail closed |
| Audit record | audit store/log | 不泄露 secret |
| Page/System Audit report | admin API consumer | 必须保留 proof availability、contract revision、snapshot、integrity/freshness/queue 和 external evidence 边界；权限通过不等于数据证明通过 |
| External evidence audit record | audit store/operator | 记录 evidence id/domain/fingerprint、actor、reason 与 register/revoke 动作；不得记录 manifest item 原文、credential 或 secret。 |

## 持久化与投影

- Own read model：无。
- Persistence：audit records、session/permission source。
- Related docs：`SECURITY.md`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend auth | `backend/src/fin_ops_platform/app/auth.py` |
| Backend services | `access_control_service.py`、`audit.py` |
| Page Audit registry | `backend/src/fin_ops_platform/services/page_audit_registry.py` |
| Routes | `backend/src/fin_ops_platform/app/server.py`、route owners with protected endpoints |
| Frontend session | `web/src/features/session/api.ts`、`web/src/contexts/SessionContext.tsx` |
| Frontend gates | `web/src/components/auth/SessionGate.tsx`、`useSessionPermissions()`、`useOptionalSessionPermissions()` |
| App health | `web/src/contexts/AppHealthStatusContext.tsx` |
| Tests | `tests/test_auth_guard.py`、`tests/test_permissions_write_entry_inventory.py`、`tests/test_audit*.py`、`web/e2e/permissions-role-matrix.spec.ts` |

## 依赖方向

- 允许依赖：auth/session source, access control service, audit service。
- 必须通过：explicit route/service permission check。
- 禁止绕过：write endpoint without permission owner；frontend-only authorization；logging secrets；Audit route 触发 refresh/repair；把 system Audit 的 admin access decision 当作 integrity 结论。

## 测试与验证

- `tests/test_auth_guard.py`
- `tests/test_permissions_write_entry_inventory.py`
- `tests/test_audit_service.py`
- `web/e2e/permissions-role-matrix.spec.ts`

## 当前缺口和删除条件

- 新增写 API 必须更新 permissions inventory tests 和模块 boundary docs。
