---
status: resolved
trigger: "日常报销批量账务管理已提交为 0，需要核对关联台是否仍有配对关系"
created: 2026-06-17
updated: 2026-06-17
---

# GSD Debug Session: daily-reimb-submitted-zero

## Symptoms

- expected_behavior: "日常报销批量账务管理应显示此前已提交的日常报销批量账务记录。"
- actual_behavior: "页面显示已提交为 0。"
- error_messages: "用户未报告页面错误；当前重点是核对数据事实源。"
- timeline: "用户此前提交过，当前观察到已提交数量为 0。"
- reproduction: "打开日常报销批量账务管理，查看已提交数量；同时核对关联台是否已有配对关系。"

## Current Focus

- hypothesis: "已提交为 0 是 read model repository group payload 映射丢失 relation special_metadata，导致 BatchAccountingService 无法识别 batch_accounting relation。"
- test: "修复 group payload 映射后运行只读服务脚本和后端回归测试。"
- expecting: "2026 年 batch-accounting submitted_count 从 0 恢复为 canonical/read model 中的 9 条 active batch relation。"
- next_action: "如需进一步清理，单独设计 CASE-AUTO-0001 metadata/row_ids 不一致的只读审计与 repair plan。"

## Evidence

- 2026-06-17: `app.workbench_pair_relations` 中存在 9 条 active relation，`special_metadata.source='batch_accounting'`，说明此前提交关系未从 canonical fact 丢失。
- 2026-06-17: `read_model.workbench_relation_rows/groups` 中 2026-01 至 2026-04 均为 fresh，并分发出对应 linked rows/groups。
- 2026-06-17: 修复前只读 `BatchAccountingService.build_payload(bank_year='2026', oa_year='2026', bucket='submitted')` 返回 `submitted_count=0`。
- 2026-06-17: 根因定位到 `PostgresReadModelRepository._workbench_relation_group_payload()`：DB group 的 `payload` 已经是 relation payload，但公开 DTO 只取 `base.get('payload')`，结果变成 `{}`，mapper 读不到 `special_metadata.source`。
- 2026-06-17: 修复后同一只读服务脚本返回 `submitted_count=9`、`read_model_status='fresh'`。
- 2026-06-17: 另发现历史数据异常：`CASE-AUTO-0001` 的 row_ids 实际银行流水为 `txn_imported_1240`，但 `special_metadata.bank_row_id='txn_imported_1453'`；这不是已提交为 0 的根因，但会造成明细错绑/重复风险。

## Eliminated

- hypothesis: "此前提交关系已从 canonical relation fact 删除。"
  evidence: "active batch_accounting metadata relation 仍有 9 条。"
- hypothesis: "workbench_relation read model 整体 missing/stale 导致空结果。"
  evidence: "2026 相关月份 read model scopes 为 fresh，linked groups 存在。"

## Resolution

- root_cause: "`_workbench_relation_group_payload()` 丢弃了 relation group 的 payload，导致 downstream mapper 无法识别 `special_metadata.source='batch_accounting'`。"
- fix: "当 group payload 已是 relation payload 时保留整个 base；仅在历史兼容数据存在嵌套 `payload` 时取内层。"
- verification: "`tests.test_workbench_relation_read_facade`、`tests.test_batch_accounting_api`、`tests.test_workbench_relation_sql_projection` 通过；只读服务脚本确认 submitted_count=9。"
- files_changed: "backend/src/fin_ops_platform/services/postgres_repositories/read_models.py; tests/test_workbench_relation_read_facade.py"
