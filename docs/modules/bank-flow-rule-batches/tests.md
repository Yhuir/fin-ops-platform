# 流水规则批量处理测试矩阵

状态：partial-covered。本轮实现使用旧 no-OA 文件名承载新流水规则入口；后续独立模块化时应重命名测试文件并拆出专用 service/read model tests。

## 七类测试适用性

| 类别 | 是否适用 | 计划覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | 已覆盖 checkbox requirement metadata、paired/open 判定、`requires_oa`+`requires_invoice` 缺任一项 fail closed、折叠阈值、rebaseline 状态转换；未知/停用/重复标签仍需扩展。 |
| 2. Service-layer tests | 适用 | 已覆盖批次提交 relation command payload、reset submitted 批量撤回、rebaseline dry-run/apply manifest 校验和幂等；独立规则审计和 partial failure rollback 仍需扩展。 |
| 3. API contract tests | 适用 | 已覆盖 `GET/PUT /api/bank-flow-rule-batches/tag-rules`、`POST /submit-selection`、`POST /reset-submitted`、`POST /rebaseline-no-oa/dry-run`、`POST /rebaseline-no-oa/apply`、缺 manifest 和 stale manifest 错误；权限错误 shape 仍主要靠浏览器 role matrix。 |
| 4. Read model, cache, and background job tests | 适用 | 当前覆盖过渡期 `no_oa_bank_batch` stale/refreshing fail-closed、`bank_flow_rule_batch` operation barrier alias 和 no-OA worker/manifest guard；独立 `bank_flow_rule_batch` 投影表、source version、schema version、worker refresh 待 read model 拆分时补。 |
| 5. Frontend component and interaction tests | 适用 | xlsx/grid 抽屉、左侧只读、OA/发票 checkbox、保存失败、标签变化后 grid 同步、选择清空、批量提交 loading/error/empty/stale 状态。 |
| 6. End-to-end business-flow integration tests | 适用 | 已覆盖 bank tag rules -> submit bank rows -> reset submitted -> 未提交候选恢复、bank tag rules -> submit bank rows -> workbench open/paired、银行明细标签变更 -> 流水规则抽屉同步、`requires_invoice` open -> 选择补票候选发票 -> 确认后 paired、legacy no-OA rebaseline dry-run -> apply manifest -> barrier 刷新。 |
| 7. Existing feature regression tests | 适用 | no-OA legacy paths、Workbench paired/open、bank-details tag rules、pending invoices rules、turnover ledger、search、operation barrier、permissions/audit。 |

## 计划后端测试入口

- 当前实现：`tests/test_no_oa_bank_batch_tag_selection_api.py`
- 当前实现：`tests/test_operation_freshness_barrier.py`
- 当前实现：`tests/test_workbench_candidate_grouping.py`
- 当前实现：`tests/test_workbench_relation_command_service.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_requirement_service.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_application_service.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_api.py`
- 后续拆分：`tests/test_bank_flow_rule_batch_read_model_refresh.py`
- `tests/test_bank_flow_rule_batch_rebaseline_service.py`
- `tests/test_bank_flow_rule_batch_workbench_integration.py`
- 更新 `tests/test_workbench_candidate_grouping.py`
- 更新受影响 no-OA regression tests，证明旧入口被迁移或清理后不会误占用银行 rows。

## 计划前端测试入口

- 当前实现：`web/src/test/NoOaBankBatchApi.test.ts`
- 当前实现：`web/src/test/NoOaBankBatchPage.test.tsx`
- 当前实现：`web/src/test/CandidateGroupGrid.test.tsx`
- 后续拆分：`web/src/test/BankFlowRuleBatchApi.test.ts`
- 后续拆分：`web/src/test/BankFlowRuleBatchPage.test.tsx`
- `web/src/test/BankFlowRuleBatchRuleDrawer.test.tsx`
- `web/e2e/bank-flow-rule-batches-flow.spec.ts`

## 必测失败路径

- 规则保存 `expected_version` 冲突。
- 请求包含未知、停用或重复 tag code。
- 新银行标签未配置时默认需要 OA 和发票。
- 左侧标签列被尝试编辑时无 UI 入口，API 也拒绝写银行标签事实。
- 提交空选择、重复 row、跨月、跨账户、混合标签、row 已占用、规则版本过期。
- Relation command 写入失败时不保存半批次。
- Read model stale/missing 时页面不能把空列表当真实无候选。
- Rebaseline apply 缺 dry-run manifest 或 manifest 与当前候选不一致时拒绝 apply。
- Rebaseline apply 重放时幂等返回，不重复撤回 relation。

## 验证命令

实现 slice 后至少运行：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_candidate_grouping.py tests/test_workbench_relation_command_service.py -q
npm --prefix web test -- --run CandidateGroupGrid.test.tsx NoOaBankBatchPage.test.tsx NoOaBankBatchApi.test.ts App.test.tsx
npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium
npm --prefix web run e2e -- e2e/permissions-role-matrix.spec.ts --project=chromium
npm --prefix web run build
```

当前文档 slice 只要求：

```bash
git diff --check
bash scripts/verify.sh docs
rg -n "bank-flow-rule-batches|bank_flow_rule_batch|流水规则批量处理" docs/modules docs/architecture docs/dev
```
