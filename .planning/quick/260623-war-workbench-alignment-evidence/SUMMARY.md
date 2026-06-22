# 260623-war - Summary

## 完成内容

- 新增后端行级归属服务 `WorkbenchRelationAlignmentService`。
- Workbench SQL active generation 在 `_group_payload` 阶段为 active relation 生成 `special_metadata.row_alignment`。
- 对可确定归属的 bank/invoice row 投影 `source_oa_id` 与 `source_oa_row_id`。
- 将 Workbench SQL projection schema version 更新为 `2026-06-23-relation-row-alignment-v1`。
- 补 `WorkbenchRelationCommandService` 回归测试，确认显式 `row_alignment` metadata 不丢失。
- 扩展 `audit_workbench_relation_display`，多 OA relation 中 bank row 缺 source OA 时报告 blocking issue。
- 补前端 API mapper 回归，确保后端 `source_oa_id` 到 `WorkbenchRecord.sourceOaId` 的链路不断。
- 更新关联台模块文档和 API contract。

## 验证命令

```bash
python -m pytest tests/test_workbench_relation_alignment_service.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_emits_source_oa_for_deterministic_multi_oa_relation_alignment tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_confirm_relation_preserves_explicit_row_alignment_metadata tests/test_audit_workbench_relation_display_tool.py
cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/groupDisplayModel.test.ts src/test/CandidateGroupGrid.test.tsx
```

## 未测风险

- 未连接真实生产 PostgreSQL 回放截图 case；发布前需要用只读 `audit_workbench_relation_display` 跑目标环境，并触发 Workbench active generation rebuild。
- 歧义金额关系不会自动修复，审计暴露后需要人工或业务侧补充显式 `row_alignment`。

