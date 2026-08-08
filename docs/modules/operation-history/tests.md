# 操作历史测试

- 业务核心：权限与游标/日期输入校验。
- Service/Repository：durable append、敏感字段移除、覆盖点后查询、append-only trigger。
- API：005 可读，非管理员拒绝，非法 UUID/cursor 拒绝；mutation 形成同 request id 的 requested/completed，requested 写失败时业务写 fail closed。
- 前端：管理员列表/详情 Drawer 与非管理员直达重定向。
- E2E：管理员侧栏/页面可见，普通账号侧栏隐藏且直达重定向；真实写入记录由发布后 production smoke 验证。
- 回归：现有权限页 registry、App Health system audit、流水/发票导入和数据重置。
