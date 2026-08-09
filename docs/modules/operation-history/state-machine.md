# 操作历史状态

- HTTP mutation：`requested -> completed(success|failed)`；同一 `request_id` 关联，页面只显示一条逻辑操作。超过 5 分钟仍无 completed 的 requested 显示为“不完整”，不永久伪装“进行中”。
- 领域事件：业务事务成功后追加 `operation.action` 或更具体事件类型。
- 财务事实修正：必须携带 reason，数据库在同一事务追加 correction 与 audit event；缺失 reason 时拒绝修改。
- 审计事实一经写入不可更新或删除。
