# Prompt 28：实现 OA 登录复用与 session 底座

目标：让 `fin-ops-platform` 不再是公开内部工具，而是基于 OA 登录态启动；新增 `GET /api/session/me`，并让前端在进入系统前确认当前 OA 会话和访问许可。

前提：

- 已阅读：`OA 集成当前 app 技术方案.md`
- 已阅读：`docs/superpowers/specs/2026-04-03-oa-shell-auth-visibility-design.md`

要求：

- 后端新增 OA 身份解析服务
- 通过 OA token 调用 OA `/system/user/getInfo`
- 提供 `GET /api/session/me`
- 返回：
  - 当前用户
  - 角色
  - 权限
  - `allowed`
- 前端增加 session gate
- 在 session 未完成前不渲染业务主页面
- token 无效或会话过期时，显示明确状态，不出现自己的登录页

建议文件：

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/auth.py`
- `backend/src/fin_ops_platform/services/oa_identity_service.py`
- `web/src/features/session/api.ts`
- `web/src/contexts/SessionContext.tsx`
- `web/src/components/auth/SessionGate.tsx`
- `web/src/components/auth/ForbiddenPage.tsx`
- `web/src/app/App.tsx`
- `web/src/test/SessionGate.test.tsx`
- `tests/test_session_api.py`

交付要求：

- `GET /api/session/me` 可用
- React app 启动先做 session bootstrap
- 无效 OA token 不允许进入业务页面

验证：

- 前端目标测试
- 后端目标测试
- 前端 build

