/goal 生产级整合修复关联台银行流水计数口径：银行明细非删除流水数必须与关联台主 zone 真实银行流水数加 ignored 银行流水数一致；免 OA 批次摘要展示行不得污染真实银行流水计数；summary、groups page、group detail、前端区域标题和银行流水栏标题必须使用统一事实口径。

# Codex 最终执行 Prompt：关联台银行流水计数一致性

## 事实源

- 设计文档：`docs/superpowers/specs/2026-05-25-workbench-bank-counts-design.md`
- 实施计划：`docs/superpowers/plans/2026-05-25-workbench-bank-counts.md`
- 产品口径：`docs/product-specs/workbench.md`
- 当前生产现象：银行明细 `431`；关联台真实银行流水应为已配对 `237` + 未配对 `194` + 已忽略 `0`。

## 约束

- 必须使用 TDD：先写失败测试，再写实现。
- 不做前端临时补数，不用 group 数或摘要展示行数冒充流水数。
- 不改变免 OA 批次折叠展示，不取消 group 分页。
- 不回滚或覆盖同一仓库中他人的未提交改动。
- 生产级必须覆盖权限边界、审计可解释性、回填/缓存清理、数据一致性和验证方式。

## 串行 / 并行执行拓扑

### Gate 0：准备与基线，串行

1. 确认在隔离分支或 worktree 中执行。
2. 读取设计文档、产品规格、相关测试和 SQL read model 仓库代码。
3. 安装依赖并记录基线测试状态。
4. 不进入实现，直到确认待改文件和测试入口。

### Wave 1：后端事实计数，串行优先

Worker A 负责后端读模型计数，写范围：

- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_no_oa_bank_batch_workbench_integration.py` 或现有同类后端测试

任务：

1. 新增真实行计数 helper：普通 bank 行允许 `source_kind` 缺失/null/空；只排除显式 `no_oa_bank_batch_summary` 摘要展示行。
2. 每个 group 输出 `row_counts` 事实计数和 `display_row_counts` 展示计数。
3. `read_model.workbench_groups.row_count` 保存事实 `rows`。
4. `GET /api/workbench/summary` fallback 与 materialized summary 统一使用事实计数。
5. `GET /api/workbench/groups` endpoint 级 `row_counts` 使用分页前匹配 group 的真实行计数，不再用 `jsonb_array_length(payload->'bank_rows')`。
6. 保留 `read_model.workbench_group_rows.row_role=normal|summary|collapsed`，或使用等价字段明确区分摘要展示行、折叠原始行和普通行；摘要展示行不得参与真实银行流水事实计数。
7. 输出 diagnostics：`bank_detail_count`、`ignored_bank_count`、`bank_detail_reconciliation_status`。

### Wave 2：前端 API 与展示，可与后端测试准备并行

Worker B 负责前端契约和 UI，写范围：

- `web/src/features/workbench/types.ts`
- `web/src/features/workbench/api.ts`
- `web/src/features/workbench/groupDisplayModel.ts`
- `web/src/components/workbench/CandidateGroupGrid.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/test/WorkbenchApi.test.ts`
- `web/src/test/CandidateGroupGrid.test.tsx`
- `web/src/test/WorkbenchZone.test.tsx`

任务：

1. 映射 `display_row_counts`，但区域标题和银行流水栏标题只使用后端 `row_counts` / `zone_counts` 事实计数。
2. 保持 `collapsed_row_counts` 兼容；新增字段不得破坏旧 payload。
3. 免 OA 折叠组展示“当前显示 1 条摘要 / 实际 N 条流水”语义；展开详情继续走 group detail。
4. 初始页和分页页标题不得从当前已加载 preview rows 推断总数。

### Gate 1：集成，串行

1. 合并后端和前端改动。
2. 运行后端相关测试：
   - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
   - `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_workbench_integration -v`
3. 运行前端相关测试：
   - `cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/CandidateGroupGrid.test.tsx src/test/WorkbenchZone.test.tsx`
4. 如测试失败，先分析根因，不改断言掩盖口径问题。

### Wave 3：运行时数据核验，可在代码测试后串行执行

Worker C 负责本地 PostgreSQL 运行时核验，写范围优先为空；如需要脚本，先说明再新增。

任务：

1. 使用 `.runtime/fin_ops_platform/local-postgres.env` 连接本地运行库。
2. 验证 `app.bank_transactions(status <> deleted)`、`read_model.bank_detail_rows`、`read_model.workbench_groups + collapsed_rows.bank` 的真实银行流水集合。
3. 验证 `bank_detail_count = open_bank_count + paired_bank_count + ignored_bank_count`。
4. 记录当前生产数据期望：`431 = 194 + 237 + 0`，缺失 `0`，多余 `0`。

### Gate 2：最终验证与提交，串行

1. 运行必要 build/check：
   - `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
   - `cd web && npm run build`
2. 检查 git diff，只包含本目标相关文件。
3. 提交，提交信息使用 `Fix workbench bank count contract`。
4. 最终汇报必须说明：
   - 变更文件。
   - 通过的验证命令。
   - 未执行或失败的验证。
   - 生产回填步骤：标记 workbench scope dirty、重建月 scope 和 all scope、清 Redis groups cache、运行一致性检查。
