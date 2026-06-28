# 销项发票收款情况 状态机

> 修改 `销项发票收款情况` 相关业务状态、UI 状态、direct API 合同或 legacy read model/worker 下线状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

- 当前状态：
  - 自动收款状态：由 `InvoiceLifecyclePolicy.evaluate_output_invoice_collection(...)` 和 `OutputInvoiceCollectionStatusRuleService` 根据销项发票、银行收入流水、红冲/退款、人工关系和 lifecycle facts 判定，输出到 row `collectionStatus`。
  - 手动状态覆盖：`OutputInvoiceCollectionLifecycleService.set_collection_status(...)` 写入 status override，可携带预计收款日期、备注和 `expectedVersion`。
  - 收款提醒：`upsert_collection_reminder(...)` 创建或更新 active reminder；`cancel_collection_reminder(...)` 取消提醒。
  - 红蓝票关系：`confirm_red_invoice_relation(...)` 写入 `red_invoice` 或 `blue_invoice` 人工关系；`delete_red_invoice_relation(...)` 撤销关系。
  - 正式收据：`preview -> issued -> voided -> reissued`。创建必须有 idempotency key；history 读取真实 receipt lifecycle facts。
- 状态事实源：
  - 销项发票和银行/关系事实来自 import facts、Workbench canonical relation facts 和 direct query service。
  - OA、收入流水和关联销项发票项展示来自 `workbench_relation` 统一分发关系；`relationStatus="candidate"` 只能作为候选证据展示，不能计入已收款或 confirmed relation 判断。
  - 收款状态规则来自 `InvoiceLifecyclePolicy` 和 `OutputInvoiceCollectionStatusRuleService`。
  - 手动状态、提醒、红蓝票关系、收据 facts 来自 output invoice collection lifecycle repository。
  - 页面列表事实来自 direct API rows payload；后端可在过渡期继续使用 `output_invoice_collection` legacy projection 并叠加 lifecycle facts，但页面不消费 projection freshness/status。
- 允许流转：
  - 自动状态可被合法手动状态覆盖；清空手动状态后回到 policy 自动判定。
  - reminder 可 create/update/cancel，渠道只允许 `oa`、`email`、`manual`。
  - 红蓝票关系可 confirm/delete，确认时必须提供 related invoice identity 或 invoice id。
  - receipt preview 可在存在可用收入流水且非红冲/退款状态时创建正式收据。
  - issued receipt 可 void；voided receipt 可 reissue；reissue 后不能重复重开同一 receipt。
- 禁止流转：
  - 不支持的手动收款状态、非法提醒渠道、缺失 related invoice、非法 relation type 必须失败。
  - stale legacy read model 不能重新作为页面 ready 证明。
  - 缺少 idempotency key 不能创建正式收据。
  - 非 issued receipt 不能 void；非 voided receipt 不能 reissue；已重开 receipt 不能重复 reissue。
  - service 不得绕过 transaction-bound writer、canonical facts、audit 或真实 outbox。

## UI 状态

- loading：页面初次挂载时并行加载 rows、filter-options 和 status-rules；loading 期间展示标准页面状态，不保留旧 route snapshot。
- empty：无业务 rows 时展示标准 empty state；旧同步技术细节不直接暴露给用户。
- error：rows/filter-options/detail/drawer 请求失败时展示页面或 drawer 级错误；不静默吞掉提交失败。
- direct page payload：rows、filter-options、export-preview 和 export 不返回 `readModelStatus`、`read_model_status`、`readModelScopeKey`、`read_model_scope_key` 等 legacy 字段；页面不自动重试、不隐藏普通 empty/table，也不因为 legacy status 禁用导出。
- permission disabled/hidden：
  - 读详情需要 output collection read session 权限。
  - 收款状态、提醒、红蓝票和 receipt mutation 需要 mutation 权限。
  - receipt settings 入口 admin-only。
  - 权限不足时 API 返回 403，前端隐藏或禁用对应入口。
- relation list：当 OA、收入流水或关联销项发票项为多项时，对应栏显示 `+N` 入口，`N=relationCount-1` 表示额外项数；点击后打开详情 drawer，按 `kind=oa|bank|invoice` 展示全部 summaries。销项发票栏多项时必须保留当前行发票主信息和多张发票价税合计，再显示 `+N`，不得只留下展开入口。

## Legacy Projection / Worker 历史状态

- 适用范围：以下内容只描述已下线后端 projection/worker 的迁移记录；页面级 rows/filter/export-preview/detail 当前均走 direct query/export service，不消费 `refresh_status`、scope、source-version、dirty-scope 或 worker queue 状态。
- legacy missing/stale/source-version/schema mismatch：只作为旧 projection 删除前诊断；页面保持 direct loading/error/empty/detailAvailable 语义，不返回 `202 refreshing` 或 freshness 字段。
- relation detail unavailable：`/rows/{row_id}/relation-details` 只返回 direct query service 的 detail payload 或业务不可用诊断，不透传 read-model freshness 字段。
- all scope / month shard / refresh 来源：发票导入、关系变化、生命周期变化和收款写入过去曾触发 `output_invoice_collection` projection；当前页面写成功后直接 refetch rows/history/detail，下游通过 canonical facts、真实 outbox 和 direct payload 收敛。
- 失败恢复：当前页面恢复依赖 direct API 重新请求和真实业务依赖恢复；旧 projection 重放、dirty-scope 清理或 readiness 只作为迁移/删除排障线索，不能作为页面 ready 证明。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-27 | 页面 route 删除 freshness 字段兜底剥离 helper | relation-details mapper 直接返回 direct query service payload；测试必须证明 service 不产生页面级 `read_model_status`、scope 或 refresh 字段，而不是靠 route 静默删除 | `tests/test_output_invoice_collection_api.py` |
| 2026-06-26 | 前端写后 direct refetch rows | 不改变收款/红蓝票/收据业务状态或后端响应 shape；`OutputInvoiceCollectionsPage` 不再等待 operation barrier，写成功后直接 refetch rows | `web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`bash scripts/verify.sh docs` |
| 2026-06-27 | 页面 API 移除 freshness 字段 | rows/filter-options/export-preview/export 不返回 `readModelStatus`、`read_model_status` 或 scope refresh 字段；route 不再注入 SQL read-model provider | `tests/test_output_invoice_collection_api.py`、`tests/test_output_invoice_collection_service.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx` |
| 2026-06-24 | 历史 relation detail fail-closed | 历史上曾用 SQL detail row 构造详情；direct API 迁移后页面 detail 走 query service，legacy detail service 只作内部兼容 | `tests.test_output_invoice_collection_api`、`tests.test_invoice_usage_collection_sql_runtime`、`tests.test_read_model_manifest` |
| 2026-06-26 | 页面 direct API 忽略 legacy freshness | 删除页面级 rows/filter-options combined freshness、自动重试和导出禁用合同；legacy read model 状态仅保留为后端过渡记录 | `web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`bash scripts/verify.sh docs` |
| 2026-06-24 | T8 module IO contract reconciliation | 历史记录：当时曾要求 rows 与 filter-options 合并 fresh 后才允许普通空态和导出；已被 2026-06-26 direct API 迁移取代 | `web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`bash scripts/verify.sh docs` |
| 2026-06-24 | 补齐写后 freshness target 合同并删除 app-level output projection helper | 历史记录：当时曾让 mutation response 增加 `read_model_scope_keys` 和 `freshness_targets`，前端写后等待具体月份 operation barrier；已被 2026-06-27 direct API mutation scope cleanup 取代 | `tests.test_output_invoice_collection_lifecycle`、`tests.test_output_invoice_collection_api`、`tests.test_read_model_architecture_guards`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx` |
| 2026-06-23 | 补 legacy manifest 合同守卫 | 历史迁移记录：当时锁定 `output_invoice_collection` projection owner、permission owner 和 repository port 不与 `invoice_lifecycle` / `input_invoice_usage` 混用；当前页面读取已迁到 direct API | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_invoice_lifecycle_and_usage_manifest_preserve_scoped_contracts` |
| 2026-06-23 | 统一关系 OA/流水/发票项 `+N` 展示 | 不新增收款业务状态；销项发票多项显示合计和额外项 `+N` | `python -m pytest tests/test_output_invoice_collection_service.py tests/test_invoice_usage_collection_sql_runtime.py -q`、`npm --prefix web test -- OutputInvoiceCollectionsPage.test.tsx --run` |
| 2026-06-18 | 补充红蓝票 Browser fan-out | 不改变状态机；新增真实 Chromium 覆盖红蓝票关系确认后 rows direct refetch 和人工依据展示 | `cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts` |
| 2026-06-17 | 补充 Browser e2e 主流程 | 不改变状态机；新增真实 Chromium 覆盖手动状态/提醒保存、rows direct refetch、正式收据创建和 history 展示 | `cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts` |
| 2026-06-11 | 首轮测试闭环文档化 | 历史记录：当时明确业务/UI/read model/worker 状态和禁止流转；当前页面状态以 direct API 合同为准 | `tests/test_output_invoice_collection_*`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`bash scripts/verify.sh docs` |
