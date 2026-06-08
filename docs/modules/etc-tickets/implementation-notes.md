# ETC票据管理 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 待补充。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-09 - 业务批次筛选计数口径修复

- 目标：修复 ETC 页面筛选后出现“已提交显示 1，但列表为空”的不一致状态。
- 影响范围：`GET /api/etc/business-batches`、`EtcBusinessBatchApplicationService` 列表筛选、ETC 页面 tab 计数、测试 API mock。
- 关键决策：修复后端筛选契约，让 `counts` 和 `items` 共享同一组 scope、月份、车牌和关键词筛选；ETC 月份筛选按开票日期、通行开始日期和通行结束日期共同匹配。前端不做临时覆盖计数，继续消费后端事实。
- 文档影响：更新产品口径、API 契约和测试矩阵。
- 测试覆盖：新增 API 契约测试验证已提交批次按通行月份可见且不匹配月份 counts/items 同为 0；新增前端交互测试验证 tab 计数与当前筛选下列表一致。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_business_batch_application_service.py backend/src/fin_ops_platform/app/server.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm run build`；`git diff --check`。
- 未测风险：未执行真实浏览器联调；自动化已覆盖接口契约和 ETC 页面筛选交互。

## 2026-06-09 - 已提交批次本地删除与发票释放闭环

- 目标：允许用户删除已提交 ETC 业务批次用于重新走流程，同时确保删除只影响本地 ETC 批次合并关系，不撤销真实 OA 或重开已闭环对账任务。
- 影响范围：`EtcService.delete_business_batch`、`DELETE /api/etc/business-batches/{id}`、ETC 页面 submitted bucket 删除入口、Workbench open 区 ETC summary/散票投影。
- 关键决策：后端对象不合并为单实体；`etc_business_batches` 继续作为用户可见业务批次事实源，`etc_reconciliation_tasks` 继续作为 workflow 状态。已提交批次删除写入 `submitted_business_batch_reset` 审计，业务批次进入 `deleted`，提交批次本地退出 submitted 状态，ETC 发票恢复 `unsubmitted/current_batch_id=null`，旧 OA 和 closed task 保留。
- 文档影响：更新产品口径、API 契约、状态机、测试矩阵和运维检查，明确这是本地 reset，不是 OA 撤销。
- 测试覆盖：新增 service 级已提交删除释放发票测试、API + Workbench 闭环测试、前端已提交批次删除确认与 local reset 调用测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_service.py backend/src/fin_ops_platform/app/server.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未执行真实浏览器联调；自动化已覆盖本地 reset、Workbench summary 消失和散票恢复合同。

## 2026-06-09 - 历史已提交批次数据修复与金额搜索闭环

- 目标：将历史批次 `etc_business_batch_0004` 从人工已提交但任务未闭环的中间状态修复为已提交闭环，并让关联台可按 `1673` 命中汇总 ETC 发票。
- 影响范围：`app.etc_business_batches`、`app.etc_reconciliation_tasks`、Workbench SQL read model 的 `workbench_rows`、`workbench_group_rows` 和 `workbench_groups`。
- 关键决策：对账任务按正式 `oa_submitted_confirmed -> closed` 语义补齐，不在前端隐藏未提交任务；`etc_invoice_summary` 保留展示金额 `amount=1,673.30`，同时提供结构化 `amount_value=1673.30` 给 read model numeric 列和搜索文本。
- 文档影响：更新 `tests.md` 与 `state-machine.md` 的 read model 金额字段说明；长期业务口径未变化。
- 测试覆盖：加强 `tests.test_workbench_sql_runtime`，覆盖 ETC summary `amount_value` 和 repository 写入 `workbench_rows.amount`、`workbench_group_rows.searchable_text`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/workbench_sql_projection.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`。
- 未测风险：未重新跑前端构建；本次没有改 ETC 页面 UI 代码。
- 后续事项：如果 all 聚合同步重建继续耗时，应由 worker 异步刷新并配合 generation retention 清理旧生成版本。

## 2026-06-09 - ETC人工已提交闭环与关联台summary修复

- 目标：修复人工点击“已提交”后批次仍留在未提交区、关联台未配对区找不到上报金额 ETC 汇总发票的问题。
- 影响范围：ETC 业务批次人工确认、`app.etc_business_batches` 持久化、Workbench SQL projection、ETC 页面人工确认交互。
- 关键决策：`etc_invoice_summary` 不再只依赖旧 `app.invoices + etc_submission_batches` 隐藏发票路径；已提交业务批次本身也是 summary 来源，并按业务批次 scope 生成一条汇总行，金额优先取 submission/business batch 上报金额，散票只作为展开明细和兜底金额来源。
- 文档影响：更新 `state-machine.md` 和 `tests.md`；长期业务口径未变化。
- 测试覆盖：新增 SQL projection 业务批次来源测试、repository 业务批次金额/数量落库测试，并加强前端人工确认后刷新任务和 submitted bucket 的交互测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime ...`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_closes_the_linked_reconciliation_task tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_creates_open_workbench_summary_with_reported_amount -v`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx -t "manually confirms a draft-created business batch as submitted without refresh entry"`。
- 未测风险：尚需在最终验证阶段运行完整 ETC 页面测试、完整 SQL runtime 测试和前端 build。
