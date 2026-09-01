# 页面访问权限 E2E 覆盖

| Spec ID | 状态 | 自动化证据 |
| --- | --- | --- |
| `PERM-E2E-001` | covered | `tests/test_auth_guard.py`、`tests/test_session_api.py`、`web/e2e/permissions-role-matrix.spec.ts` |
| `PERM-E2E-002` | covered | `tests/test_route_access_policy.py`、`web/src/test/PageRouteHost.test.tsx`、`web/src/test/AppSidebar.test.tsx`、Browser matrix |
| `PERM-E2E-003` | covered | 现有各页面 API/component/E2E 写入主链路；权限层不再重复维护页面内 write-control inventory |
| `PERM-E2E-004` | covered | `tests/test_app_settings_service.py`、admin API tests、`web/src/test/SettingsPage.test.tsx`、Browser matrix |
| `PERM-E2E-005` | covered | `tests/test_oa_role_sync_service.py`、settings service/API tests、Settings component test、Browser matrix |
| `PERM-E2E-006` | covered | access-control service/session/settings CAS tests与 Browser 保存后切换 session |
| `PERM-E2E-007` | covered | `tests/test_permissions_write_entry_inventory.py` 校验前端 registry、后端 page set 和 route policy 一致 |

生产发布后额外运行 access-control preflight、session/API latency 和浏览器视觉 smoke；本地 mock 不替代 OA/MySQL/PostgreSQL 真实结果。
