# 操作历史 E2E 规格

- `AUDIT-E2E-001`：005 登录后侧栏显示“操作历史”，普通账号不显示且直达路由/API 均被拒绝。
- `AUDIT-E2E-002`：一次成功业务写形成同 request id 的 requested/completed 记录，可查看人员、时间、页面、稳定的具体动作、用户对象和结果；不能看到 HTTP route 或内部审计标识。
- `AUDIT-E2E-003`：一次失败业务写形成 failed 完成记录；审计不可用时写操作不执行。
- `AUDIT-E2E-004`：关键流水/发票字段无修正原因不能更新或删除；有原因时留下 before/after correction。
