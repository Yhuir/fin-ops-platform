# 免OA流水批量处理 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 免 OA 流水批量处理首轮测试闭环状态为 `documented-risk`：已有测试覆盖 business core、application/service、API contract、read model/worker、前端交互、Workbench integration 和旧功能回归。
- 本模块是 Bankdetail 高风险子域。后续不要把 no-OA 机械拆成脱离 Bankdetail 的独立事实源。
- `GET /api/no-oa-bank-batches` 和 detail 读路径不得在 missing/stale 时同步重建全量批次；必须返回 read model status 并 enqueue refresh。
- Workbench confirm-link 的 internal transfer 特例必须最终写 no-OA submitted batch 和 `relation_mode=no_oa_bank_batch`，不得绕过批次写普通 `manual_confirmed`。
- no-OA submit/withdraw 的长期目标是 facts/audit/dirty/outbox 同事务；当前目标契约由 `tests/test_bankdetail_write_uow_contract.py` 保护，真实收敛前保持 `documented-risk`。
- 前端 stale polling、route unmount cleanup、category/rules events 刷新 list/detail/tag drawer 都是页面行为契约。

## 2026-06-11 - 首轮测试闭环审计

- 目标：把 `no-oa-bank-batches` 从测试闭环 `pending` 推进到可维护的 `documented-risk` 状态。
- 影响范围：免 OA 页面、tag-selection、list/detail、submit-selection、batch submit、bulk submit、withdraw、internal transfer from Workbench、no-OA read model、no-oa-bank-batch worker、App Status、Bankdetail tag/rule events。
- CodeGraph 审计：
  - `NoOaBankBatchPage` 调用 `fetchNoOaBankBatches`、`fetchNoOaBankBatchDetail`、`fetchNoOaBankBatchTagSelection`、`saveNoOaBankBatchTagSelection`、`submitNoOaBankBatchSelection`、`submitNoOaBankBatch`、`withdrawNoOaBankBatch`，并在 read model 非 fresh 时后台轮询。
  - `NoOaBankBatchApiRoutes` 是 HTTP route facade，负责 payload/session 映射和 error status；业务落在 `NoOaBankBatchApplicationService`。
  - `NoOaBankBatchApplicationService` 覆盖 list read model fallback、tag selection、submit/withdraw、after_mutation、durable queue enqueue 和 Workbench 影响。
  - `NoOaBankBatchService` 覆盖 draft/submitted/withdrawn/stale/conflict、internal transfer、legacy relation migration、pair relation metadata 和 snapshot/audit。
  - `NoOaBankBatchReadModelRefreshService` 只处理 `no_oa_bank_batch.read_model.refresh`，stale source version event 会 skip。
  - worker registry 和 App Status registry 已登记 `no-oa-bank-batch` worker、`no_oa_bank_batch` read model 和 `no_oa_bank_batch.read_model.refresh` event。
- 关键测试覆盖：
  - Business core：`tests/test_no_oa_bank_batch_service.py`。
  - Application/service：`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_bankdetail_write_uow_contract.py`。
  - API/route：`tests/test_no_oa_bank_batch_api.py`、`tests/test_no_oa_bank_batch_routes.py`、`tests/test_no_oa_bank_batch_tag_selection_api.py`。
  - Read model/worker：`tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`。
  - Frontend：`web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、domain event tests。
  - Integration/regression：`tests/test_no_oa_bank_batch_workbench_integration.py` 覆盖 Workbench internal transfer、manual relation 分流、mixed conflict、submitted/withdraw/open 恢复。
- 文档影响：
  - 补齐 `README.md` 模块边界和代码入口。
  - 将 `tests.md` 迁入测试闭环标准结构。
  - 补齐 `state-machine.md`。
- 未测风险：
  - 真实 PostgreSQL 历史 no-OA 批次、legacy relation、半迁移状态和重复 relation 的全量回放。
  - 真实 RabbitMQ/Redis/systemd worker drain 和网络抖动恢复。
  - 大数据月份、长标签树、长银行流水列表的浏览器性能和视觉遮挡。
  - Bankdetail/no-OA 写 UoW 真实事务内收敛尚未完全由本地 fixture 证明。
- 后续事项：
  - 修改 submit/withdraw 前，优先补 service/UoW/API characterization test。
  - 修改 read model freshness 前，必须运行 no-OA read model integration 和 worker refresh tests。
  - 修改前端 stale polling、route activation 或 domain event 时，必须运行 no-OA page tests 和 `useActiveFinanceDomainEvent` tests。

## 2026-06-11 - 内部往来双入口闭环

- 目标：修复同一组内部往来在免 OA 页面和关联台两个入口之间可能出现重复 active relation、旧未提交/冲突批次残留、历史 `manual_confirmed` 占用后不进入免 OA 已提交区域的问题。
- 决策：
  - 关联台仍允许作为内部往来提交入口，但成功事实必须委托并收敛到 no-OA submitted batch。
  - 如果免 OA 页面已经提交同一组 `row_ids`，关联台再次 confirm-link 复用 existing submitted batch 和同一个 `case_id`，保持幂等。
  - 存量两行、全银行流水、同金额、不同账户、收支成对且有效分类均为 `internal_transfer` 的 `manual_confirmed` active relation，刷新时迁移为 submitted no-OA internal transfer batch。
  - Workbench pair relation service 增加 active row 独占保护，不同 active case 不能共享同一 row。
  - PostgreSQL no-OA snapshot 保存必须删除新 snapshot 中缺席的旧 batch row，防止 SQL read model 继续返回旧 unsubmitted/conflict。
- 验收测试：
  - `test_manual_confirmed_internal_transfer_relation_migrates_to_submitted_no_oa_batch`
  - `test_workbench_confirm_after_no_oa_submit_reuses_existing_internal_transfer_fact`
  - `test_create_active_relation_rejects_active_row_reuse_by_different_case_id`
  - `test_save_no_oa_bank_batches_replaces_absent_read_model_rows`
