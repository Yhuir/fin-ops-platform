# 操作历史状态

- HTTP mutation：`requested -> completed(success|failed)`；同一 `request_id` 关联。
- 领域事件：业务事务成功后追加 `operation.action` 或更具体事件类型。
- 财务事实修正：必须携带 reason，数据库在同一事务追加 correction 与 audit event；缺失 reason 时拒绝修改。
- 审计事实一经写入不可更新或删除。
