# 关联月份元数据修复

适用问题：旧关联链从随机 ID 提取年月，导致非法日期报错或合法伪月份落库。修复代码必须先部署，不能以数据修正代替代码修复。

## 调查与计划

使用 `python -m fin_ops_platform.tools.workbench_scope_repair --case-id <case>` 只读取得 relation 和 committed responses。省略 case 时可调查全部关系；调查数据只保存到受限临时目录，不提交业务明细。比较 canonical typed members 的月份、历史事件、原始请求范围及原响应，不能把所有与当前来源不同的历史 scope 一律判错。

计划 JSON 包含：

- `relations: [{before: <read_state 返回的完整 relation>, after_scope: "all 或 YYYY-MM"}]`。
- `responses: [{before: <read_state 返回的 response 记录>, after_payload: <纠正后的完整响应>}]`。

只修改能证明的月份错误；response 仅允许改变已有 `affected_months`、`affected_scope_keys`、`changed_scopes`，保留请求、指纹、状态、金额、成员、case 和事件标识。不能给历史缺失来源猜日期；证据不足单独记录。

## 执行与恢复

```bash
python -m fin_ops_platform.tools.workbench_scope_repair \
  --plan /受限临时目录/scope-plan.json --execute \
  --actor <操作人> --reason <已验证的修复原因>
```

同事务按原值加锁比较，关系表与 normalized payload 同步修正，追加独立操作审计。第二次执行必须为零变更。不修改原始关联历史，不增加拓扑版本，不发下游支付事件，不删除幂等记录。

必要时对同一计划增加 `--rollback`；它只恢复仍符合本次修复后状态的记录，发现后续业务变化时拒绝覆盖。回滚保留审计。不得将回滚旧代码视作根因已经修复。

## 验证与清理

验证 SQL 当前范围、重新读取页面的成员/金额/状态、幂等重放字段、无新增 OA 事件，以及原始历史仍在。跨页面按现有 canonical API 验证，不调用已退役 projection/refresh。

验收完成后删除本次计划前值文件、临时调查副本、备份及回滚导出，记录删除结果；保留数据库内业务审计、修复审计和既有 release。主数据库、其他任务文件及既有备份不属于清理范围。
