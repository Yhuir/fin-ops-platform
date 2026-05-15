# 安全与权限基线

`fin-ops-platform` 作为 OA 内嵌财务子系统，不单独暴露登录体系，默认复用 OA 登录态和账户权限。

## 登录与会话

- 前端从 OA 同域 cookie 读取 `Admin-Token`。
- 请求后端时携带 `Authorization: Bearer <token>`。
- 后端通过 OA 会话接口识别当前用户，不信任前端菜单可见性。
- 未登录或 token 失效返回 `401`；已登录但无权限返回 `403`。

## 权限分层

当前长期口径：

- 不可见：OA 菜单不可见，API 不可访问。
- 只可看和只可导出：允许查询和导出，不允许写操作。
- 所有操作均可：允许业务处理操作。
- 管理员：`YNSYLP005` 固定拥有管理能力，包括访问账户管理和数据重置。

## 数据保护

- 不在日志中输出 OA token、数据库密码、导入文件敏感内容或完整附件正文。
- 导入文件和附件应存储在受控存储中，生产环境优先使用独立对象存储或受控 GridFS。
- 数据重置、权限修改、批量撤回等高风险操作必须记录操作者、时间、参数摘要和结果。

## 相关文档

- `docs/architecture/oa-integration.md`
- `docs/product-specs/settings-and-access-control.md`
- `deploy/oa/README.md`
