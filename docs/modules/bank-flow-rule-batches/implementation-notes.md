# 流水规则批量处理实施记录

## 2026-06-30 submitted 列表 read model mode 修复

目标：

- 修复流水规则批量处理提交后，关联台已有 `bank_flow_rule_batch` relation，但页面“已提交”列表不显示该批次的问题。

关键决策：

- 根因是过渡期复用 `no_oa_bank_batch` 底座时，写侧已经使用 `relation_mode=bank_flow_rule_batch`，但构建/read model 回灌仍依赖旧 no-OA 判定。具体旧污染点包括：列表查询没有显式 relation mode I/O；active relation 回灌只识别 no-OA；服务内由 submitted batch 反推 relation fact 时把所有已提交批次硬编码为 `no_oa_bank_batch`。
- 修复边界放在服务和 read repository：`NoOaBankBatchService.build_batches`、`submit_selected_rows` 接受目标 `relation_mode`；批次 payload/read model row 携带 `relation_mode`；列表 API 将 `relation_mode` 传给 read repository；SQL read repository 用 payload relation mode 分区，旧缺字段行默认只归 `no_oa_bank_batch`。
- 服务内部旧逻辑删除/隔离：submitted/withdrawn/stale/superseded 批次保留只保留当前 refresh mode；submitted batch relation fact 只为当前 refresh mode 生成并继承 batch mode；no-OA legacy repair/migration 只能在 no-OA refresh 链路内工作，不能改写 `bank_flow_rule_batch` relation。
- 新增 `read_model.no_oa_bank_batch_rows` relation-mode 过滤表达式索引，保障过渡 read model 的 submitted/unsubmitted 查询性能。

测试覆盖：

- `tests/test_no_oa_bank_batch_service.py` 覆盖 `bank_flow_rule_batch` active relation 能投影成 submitted 批次，并且不会污染 legacy no-OA submitted 列表。
- `tests/test_no_oa_bank_batch_application_service.py` 覆盖应用层列表把 `relation_mode` 传入 read repository。
- `tests/test_no_oa_bank_batch_routes.py` 覆盖 `/api/bank-flow-rule-batches` 列表路由传入 `bank_flow_rule_batch`。
- `tests/test_no_oa_bank_batch_api.py` 覆盖 `/api/bank-flow-rule-batches/submit-selection` 提交后能在 bank-flow submitted 列表读到，并且不会进入 legacy no-OA submitted 列表。
- `tests/test_no_oa_bank_batch_read_model_refresh.py` 和 `tests/test_postgres_migrations.py` 回归 worker 与迁移清单。

验证命令：

- `pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_routes.py tests/test_postgres_migrations.py`

未测风险：

- 未新增浏览器截图回归；发布后已触发 `no_oa_bank_batch/all` refresh，metadata 使用 `bank_flow_rule_batch_read_model_refresh`，生产 read model 已存在 `bank_flow_rule_batch/submitted` 行。

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
- `收支类型` 第一列压缩为固定窄列，并用方向底色/左侧色带强化 `支出`、`收入`、`全部` 分隔。

边界说明：

- 主要调整前端展示层 view model、table `rowSpan` 和样式。
- 标签 direction 读取兼容 `expense/outflow/debit/支出/支` 与 `income/inflow/credit/收入/收`；后端组装 active tag 时同 code 优先采用最新银行标签定义中的 direction。
- 不改变 `active_tags` 事实来源、`requirements_by_tag_code` 持久化、保存 payload、权限、read model、operation barrier 或 Workbench paired/open 判定。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_tag_selection_api.py -q`
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
