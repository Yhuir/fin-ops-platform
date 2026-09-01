# OA 集成 E2E 覆盖

| Spec ID | 状态 | 自动化/生产证据 |
| --- | --- | --- |
| `OA-E2E-001` | covered-local + production smoke | `tests/test_auth_guard.py`、`tests/test_session_api.py`、`web/e2e/permissions-role-matrix.spec.ts`；生产 `/api/session/me` 验证 canonical identity、页面集合与 005 管理标记 |
| `OA-E2E-002` | covered | OA projection、runtime worker、App Status 与 freshness 原有测试；本次 ACL 不新增 read model/cache/worker I/O |
| `OA-E2E-003` | covered | OA 待付款 API/component/Browser tests；页面访问由统一 route policy 额外保护 |
| `OA-E2E-004` | covered-local / external-risk | 进项 OA 反提 service/API/component tests；真实目标申请人登录与 OA 草稿仍由生产受控 smoke 证明 |
| `OA-E2E-005` | covered-local / external-risk | ETC service/API/Browser tests；本次改造不改变真实 OA 草稿生命周期 |
| `OA-E2E-006` | covered | credential service/repository/API/frontend tests；005-only 控制面和 password 不回显保持不变 |
| `OA-E2E-007` | covered-local + production smoke | role sync/preflight/deploy tests验证 `finops_app_user` / `finops_admin` exact topology；发布后验证 iframe/session/同域路径 |

补充合同：OA `sys_user` 账号与姓名搜索由 role-sync repository、settings service/API 和 `web/e2e/permissions-role-matrix.spec.ts` 覆盖；OA role/permission 不反向授予 APP 页面权限。

生产验证不得输出 token、密码、DSN、OA raw user id 或完整 ACL。
