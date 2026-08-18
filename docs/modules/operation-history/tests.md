# 操作历史测试

- 业务核心：权限与游标/日期输入校验；已知写入 route 使用稳定 action code/用户动作/对象文案；未知与旧 HTTP action 使用受限的用户可读兼容投影，不泄露 route。
- Service/Repository：durable append、嵌套领域事件继承 HTTP request id、同 request 生命周期聚合、操作人快照/选项、固化证据优先且不额外查询关系历史、旧关联记录按类型去标识化兼容、敏感字段和内部 ID 移除、覆盖点后查询、append-only trigger。
- API：005 可读，非管理员拒绝，非法 operation key/cursor 拒绝；mutation 形成同 request id 的 requested/completed 且 actor name/account 一致；OA 补充凭证成功/失败/删除固化目标与文件证据，手工录入固化发票字段；requested 写失败时业务写 fail closed。
- 前端：管理员逻辑操作列表、操作人下拉、固定 `detail` 详情模板、目标关系/文件状态/发票字段/失败原因、携带认证的图片和 PDF blob 预览、预览错误与详情加载错误、内部标识不可见、详情 Drawer 与非管理员直达重定向；同一请求不得显示两行。
- E2E：管理员侧栏/页面可见，普通账号侧栏隐藏且直达重定向；真实写入记录由发布后 production smoke 验证。
- 回归：现有权限页 registry、App Health system audit、流水/发票导入和数据重置。
