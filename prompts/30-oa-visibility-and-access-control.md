# Prompt 30：实现“仅少数账户可见”的权限控制

目标：让 `fin-ops-platform` 只对少数 OA 账户可见；未授权用户不仅看不到菜单，而且直接访问 URL 和 API 也会被拒绝。

前提：

- `28-oa-shell-auth-foundation.md` 已完成
- `29-oa-menu-iframe-integration.md` 已完成
- OA 前后端源码路径：
  - `/Users/yu/Desktop/sy/smart-oa-ui`
  - `/Users/yu/Desktop/sy/smart_oa`

要求：

- 在 OA 侧新增权限码：
  - `finops:app:view`
- OA 菜单入口受该权限控制
- `fin-ops-platform` 后端也要求当前用户具备该权限
- 未授权用户访问：
  - 页面返回 `403`
  - API 返回 `403`
- 不允许只做前端隐藏

建议文件：

- `/Users/yu/Desktop/sy/smart_oa/smart-oa-modules/smart-oa-system/...`
- `/Users/yu/Desktop/sy/smart-oa-ui/src/store/modules/permission.js`
- `backend/src/fin_ops_platform/services/access_control_service.py`
- `backend/src/fin_ops_platform/app/auth.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_auth_guard.py`
- `web/src/components/auth/ForbiddenPage.tsx`

交付要求：

- 菜单不可见和后端拒绝访问同时成立
- `finops:app:view` 成为统一判定口径

验证：

- 有权限用户可访问
- 无权限用户看不到菜单
- 无权限用户直接访问 URL / API 都返回拒绝

