# 流水规则批量处理实施记录

## 2026-06-29 文档/边界 slice

目标：

- 将需求从“免 OA 流水批量处理”重新定位为“流水规则批量处理”。
- 先沉淀模块边界、I/O、状态机、API 合同和 E2E 规格，不做实现代码。

确认决策：

- 页面不再只处理免 OA 流水，应覆盖所有需要按银行流水标签批量处理的流水。
- 标签规则抽屉左侧事实来自银行明细 active 标签，且左侧只读。
- 右侧只保留 `OA`、`发票` checkbox。
- 勾选表示进入关联台已配对区前必须具备对应 row type；空表示不需要该项。
- 新增/未配置标签默认 `OA` 和 `发票` 都勾选。
- 旧 `selected_tag_codes` 不作为新规则迁移来源；所有数据重新按新规则处理。
- 从本页面提交的批量银行流水进入关联台；超过 3 条银行流水默认折叠。
- 是否进入已配对区仍由 OA/发票 requirement 和实际 row type 是否满足决定。
- 历史已提交 no-OA 批次应通过受控 rebaseline 全部撤回到未处理状态，再按新规则重新处理。

本 slice 更新：

- 新增 `docs/modules/bank-flow-rule-batches/` 模块文档骨架。
- 计划同步模块索引、canonical facts、read model 合同、Workbench relation/reconciliation/bank details 边界和 API 契约。
- GSD 记录位于 `.planning/quick/260629-bank-flow-rule-batches-boundary/`。

风险：

- 当前代码和部分文档已经包含旧 no-OA 中间实现；implementation slice 必须先清理命名和边界，避免新旧规则同时生产写入。
- rebaseline 是数据变更，不应与 UI 重命名混做；需要独立 dry-run/apply、审计和回滚验证。
- 若实现阶段允许跨账户、跨月或跨标签批量提交，需要重新扩展状态机和 relation metadata；当前文档保守约束为同月、同账户、同标签。

后续事项：

- 新增实现计划前，先决定规则持久化使用独立表还是 settings family。
- 实现新 route/service/read model 后，再迁移导航和旧 no-OA route。
- 编写 Playwright E2E 前先把 `e2e-spec.md` 中的 Spec ID 映射到测试名。

## 2026-06-29 实现 slice

目标：

- 将用户入口改为“流水规则批量处理”，生产调用走 `/api/bank-flow-rule-batches`。
- 重做标签规则抽屉为紧凑 grid：左侧银行标签只读，右侧仅 `OA` / `发票` requirement checkbox。
- 新路径不接收 `selected_tag_codes`；保存只提交 `rules`。
- 提交选中流水写入 `relation_mode=bank_flow_rule_batch`，metadata 保留规则版本、tag code、OA/发票 requirement 和折叠提示。
- Workbench 根据 `requires_oa` / `requires_invoice` 判定 paired/open，大于 3 条银行流水折叠，并显示“流水规则批次明细”。
- 新增历史 no-OA submitted rebaseline dry-run/apply API 和浏览器管理入口，apply 必须提交 dry-run manifest 并校验 batch/version，通过 relation command 撤回旧 relation，将旧 batch 标记 withdrawn，重复 apply 同一 manifest 幂等。

当前实现说明：

- 后端复用 no-OA 批次 service/read model 的一部分作为过渡承载，但新 route、新 relation mode 和新规则合同已独立。
- 旧 no-OA route 仍保留兼容；新页面和 E2E 使用 bank-flow-rule-batches route。
- rebaseline 浏览器入口只提供 dry-run 清单和 apply；不会在普通查询、提交或刷新时自动撤回历史批次。
- 新功能 mutation 和前端等待使用 `read_model_key=bank_flow_rule_batch`；operation barrier 内部将该 key 映射到现有 no-OA readiness/outbox/worker，避免复制 worker。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_candidate_grouping.py tests/test_workbench_relation_command_service.py -q`
- `npm --prefix web test -- --run CandidateGroupGrid.test.tsx NoOaBankBatchPage.test.tsx NoOaBankBatchApi.test.ts App.test.tsx`
- `npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium`
- `npm --prefix web run e2e -- e2e/permissions-role-matrix.spec.ts --project=chromium`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_operation_freshness_barrier.py tests/test_read_model_manifest.py tests/test_runtime_worker_registry.py -q`
- `bash scripts/verify.sh docs`
- `npm --prefix web run build`
- `git diff --check`

剩余风险：

- 真实生产历史数据的全量 rebaseline 仍需先 dry-run 导出清单并人工确认后执行 apply。
- 独立 `bank_flow_rule_batch` 投影表/worker 尚未拆出，当前 readiness 仍复用 no-OA worker。
- “补齐 OA/发票后从 open 进入 paired”的完整跨页浏览器动作仍需后续接入真实补票/补 OA 流程测试。

## 2026-06-30 标签规则抽屉分组 UI slice

目标：

- 将“流水规则标签管理”右侧抽屉继续保持紧凑 xlsx/grid 形态。
- `收支类型` 按连续方向合并单元格，同一方向只显示一次。
- `流水主标签` 按主标签合并单元格，同一主标签只显示一次。
- 同一 `流水主标签` 下的不同子标签共享同一行组背景色；不同主标签使用不同背景色。

边界说明：

- 只调整前端展示层 view model、table `rowSpan` 和样式。
- 不改变 `active_tags` 事实来源、`requirements_by_tag_code` 持久化、保存 payload、权限、read model、operation barrier 或 Workbench paired/open 判定。

验证：

- `npm --prefix web test -- --run src/test/NoOaBankBatchPage.test.tsx`
- `npm --prefix web run build`
- `npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium`
- `git diff --check`

## 2026-06-29 已提交批次重置 slice

目标：

- 将流水规则批量处理页当前所有 `submitted` 批次恢复为可重新按规则处理的未提交候选。
- 整理迁移期数据库状态，但不手工 SQL 修改批次表或 relation 表。

关键决策：

- 新增 `POST /api/bank-flow-rule-batches/reset-submitted`，由页面“重置全部已提交”触发。
- 后端复用既有 `withdraw_batch`、`WorkbenchRelationCommandService.cancel_relation(...)`、`persist_mutation(...)` 和 operation barrier；旧批次进入 withdrawn/audit history。
- read model 后续 rebuild 后，释放的银行 rows 按当前银行标签和 OA/发票规则重新进入未提交候选；不会自动重新提交。

验证：

- `tests/test_no_oa_bank_batch_tag_selection_api.py` 覆盖提交后 reset、relation 取消、row 回到未提交候选。
- `web/src/test/NoOaBankBatchPage.test.tsx` 覆盖页面按钮、API payload、operation event。
- `web/e2e/bank-flow-rule-batches-flow.spec.ts` 覆盖浏览器提交后 reset 并回到未提交。
