# 操作历史测试

- 业务核心：权限与游标/日期输入校验；已知写入 route 使用稳定 action code/用户动作/对象文案；未知与旧 HTTP action 使用受限的用户可读兼容投影，不泄露 route。
- Service/Repository：durable append、同 request 生命周期聚合、操作人快照/选项、关联台对象按类型去重汇总、敏感字段和内部 ID 移除、覆盖点后查询、append-only trigger。
- API：005 可读，非管理员拒绝，非法 operation key/cursor 拒绝；mutation 形成同 request id 的 requested/completed 且 actor name/account 一致，requested 写失败时业务写 fail closed。
- 前端：管理员逻辑操作列表、操作人下拉、稳定详情模板、内部标识不可见、详情 Drawer 与非管理员直达重定向；同一请求不得显示两行。
- E2E：管理员侧栏/页面可见，普通账号侧栏隐藏且直达重定向；真实写入记录由发布后 production smoke 验证。
- 回归：现有权限页 registry、App Health system audit、流水/发票导入和数据重置。
