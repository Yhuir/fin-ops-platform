# 销项发票收款情况 状态机

> 修改 `销项发票收款情况` 相关业务状态、UI 状态或 canonical query/command 状态前必须读取本文件。页面已于 2026-07-27 退出 read model 运行时；历史记录中的 read-model 描述不覆盖当前合同。

## 业务状态

- 当前状态：
  - 自动收款状态：由 `InvoiceLifecyclePolicy.evaluate_output_invoice_collection(...)` 和 `OutputInvoiceCollectionStatusRuleService` 根据销项发票、银行收入流水、红冲/退款、人工关系和 lifecycle facts 判定，输出到 row `collectionStatus`。
  - 手动状态覆盖：`OutputInvoiceCollectionLifecycleService.set_collection_status(...)` 写入 status override，可携带预计收款日期、备注和 `expectedVersion`。
  - 收款提醒：`upsert_collection_reminder(...)` 创建或更新 active reminder；`cancel_collection_reminder(...)` 取消提醒。
  - 红蓝票关系：`confirm_red_invoice_relation(...)` 写入 `red_invoice` 或 `blue_invoice` 人工关系；`delete_red_invoice_relation(...)` 撤销关系。
  - 正式收据：`preview -> issued -> voided -> reissued`。创建必须有 idempotency key；history 读取真实 receipt lifecycle facts。
- 状态事实源：
  - 销项发票、OA 和银行事实来自 `app.invoices`、`app.oa_applications`、`app.bank_transactions` canonical PostgreSQL snapshot。
  - 正式关系只来自 `app.workbench_pair_relations status='active'`；active relation 连通 component 下存在多张销项发票时归并为一条净额收款行，负数/红字成员必须保留在 `invoiceRelations.summaries`。未正式化 candidate 不进入页面事实。
  - 收款状态规则来自 `InvoiceLifecyclePolicy` 和 `OutputInvoiceCollectionStatusRuleService`。
  - 手动状态、提醒、红蓝票关系、收据 facts 来自 output invoice collection lifecycle repository。
  - 页面列表、summary、facets 与 lifecycle overlay 在同一个 `REPEATABLE READ READ ONLY` transaction 中读取。
- 允许流转：
  - 自动状态可被合法手动状态覆盖；清空手动状态后回到 policy 自动判定。
  - reminder 可 create/update/cancel，渠道只允许 `oa`、`email`、`manual`。
  - 红蓝票关系可 confirm/delete，确认时必须提供 related invoice identity 或 invoice id。
  - receipt preview 可在存在可用收入流水且非红冲/退款状态时创建正式收据。
  - issued receipt 可 void；voided receipt 可 reissue；reissue 后不能重复重开同一 receipt。
- 禁止流转：
  - 不支持的手动收款状态、非法提醒渠道、缺失 related invoice、非法 relation type 必须失败。
  - 页面不得读取 output collection、Workbench relation 或 invoice lifecycle read model，也不得使用双读/fallback。
  - 缺少 idempotency key 不能创建正式收据。
  - 非 issued receipt 不能 void；非 voided receipt 不能 reissue；已重开 receipt 不能重复 reissue。
  - service 不得绕过 queue gateway/transaction-bound writer 直接写 dirty/outbox。

## UI 状态

- loading：页面初次挂载时加载 rows；filter options 随 rows 同响应返回，drawer 所需规则按现有入口加载。
- empty：rows API `200` 且 `pagination.total=0` 时展示标准 empty state。
- error：rows/detail/drawer 请求失败时展示页面或 drawer 级错误；不静默吞掉提交失败。
- stale/refreshing/polling：不适用。页面 API 不返回 `readModelStatus`、source version 或 `202 refreshing`，前端不自动轮询；用户刷新只发起一次正常 GET。
- permission disabled/hidden：
  - 读详情需要 output collection read session 权限。
  - 收款状态、提醒、红蓝票和 receipt mutation 需要 mutation 权限。
  - receipt settings 入口 admin-only。
  - 权限不足时 API 返回 403，前端隐藏或禁用对应入口。
- relation list：当 OA、收入流水或关联销项发票项为多项时，对应栏显示 `+N` 入口，`N=relationCount-1` 表示额外项数；点击后打开详情 drawer，按 `kind=oa|bank|invoice` 展示全部 summaries。销项发票栏多项时必须保留当前行发票主信息和多张发票价税合计，再显示 `+N`，不得只留下展开入口。

## Read Model / Worker 状态

- 页面运行时：不适用。rows、summary、statistics、facets、详情、导出和 lifecycle overlay 不读取页面/Workbench/invoice-lifecycle read model，不 enqueue refresh，也不等待 worker。
- relation component：多销项发票按 active relation 连通 component 归并；金额按成员净额计算，红字/负数发票不得丢失，OA/流水按事实 id 去重。
- 写后收敛：手动状态、提醒、红蓝票关系和收据命令只写 canonical lifecycle/audit/idempotency facts；成功后当前页面重跑正常 GET。
- 失败：canonical PostgreSQL 查询或 DTO 组装失败时返回结构化错误；不回退旧 projection。
- 共享遗留：`output_invoice_collection` projection、worker、manifest、scope policy 与 App Status 注册仍可能被全局代码引用，最终删除由主控合并后统一完成。

## 变更记录

> 2026-07-27 页面已改为 canonical PostgreSQL 直读；下方 2026-06/07 read-model 记录只用于历史回归溯源，不是当前读写合同。

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-07-27 | 页面迁移为 canonical PostgreSQL 直读 | 删除页面 read-model read application/gate/detail/polling/202 合同；多发票 relation 直接按 active component 净额归并，写后正常 GET | `tests/test_invoice_usage_collection_canonical_query.py`、`tests/test_output_invoice_collection_api.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` |
| 2026-07-07 | 读侧应用服务边界闭环 | 不改变业务/UI/read model/worker 状态；rows/filter-options/export-preview/export/relation detail 的 SQL read model 编排从 route owner 移入 `OutputInvoiceCollectionReadApplicationService`，route 只做 HTTP/session/权限/响应映射 | `tests.test_output_invoice_collection_read_application_service`、`tests.test_output_invoice_collection_api`、`tests.test_read_model_manifest`、`tests.test_read_model_architecture_guards` |
| 2026-07-01 | linked 多销项发票 relation 归并为单条净额收款行 | 改变 output collection read model row ownership；负数/红字发票进入 `invoiceRelations.summaries`，source version bump 到 `v4-relation-group-rows` | `tests.test_output_invoice_collection_service`、`tests.test_output_invoice_collection_api`、`tests.test_invoice_usage_collection_sql_runtime`、`tests.test_output_invoice_collection_read_model_fresh_gate_service` |
| 2026-06-24 | 补齐 relation detail 生产 fail-closed | 不改变 relation detail payload shape；生产 SQL runtime 缺 detail repository 时返回 refreshing/enqueue，fresh SQL detail row 直接构造详情，不回退 live query | `tests.test_output_invoice_collection_api`、`tests.test_invoice_usage_collection_sql_runtime`、`tests.test_read_model_manifest` |
| 2026-06-24 | T8 module IO contract reconciliation | 不改变收款业务状态；明确 rows 与 filter-options 合并 fresh 后才允许普通空态和导出 | `web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`bash scripts/verify.sh docs` |
| 2026-06-24 | 补齐写后 freshness target 合同并删除 app-level output projection helper | 不改变收款/红蓝票/收据业务状态；mutation response 增加 `read_model_scope_keys` 和 `freshness_targets`，前端写后等待具体月份 operation barrier；`Application.list_output_invoice_collection_scope_shards`、`mark_output_invoice_collection_scope_empty`、`rebuild_output_invoice_collection_read_model_scope` 被删除，worker projection owner 保持在 `InvoiceUsageCollectionSqlProjectionBuilder` | `tests.test_output_invoice_collection_lifecycle`、`tests.test_output_invoice_collection_api`、`tests.test_read_model_architecture_guards`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx` |
| 2026-06-23 | 补 read model manifest 合同守卫 | 不改变销项发票收款业务/UI/read model/worker 状态；锁定 `output_invoice_collection` 为 scoped incremental、fan-out `all`、自管 freshness，并保持 query owner、permission owner 和 repository ports 不与 `invoice_lifecycle` / `input_invoice_usage` 混用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_invoice_lifecycle_and_usage_manifest_preserve_scoped_contracts` |
| 2026-06-23 | 统一关系 OA/流水/发票项 `+N` 展示 | 不新增收款业务状态；新增 relation list UI 状态和 SQL payload schema stale 条件；销项发票多项显示合计和额外项 `+N` | `python -m pytest tests/test_output_invoice_collection_service.py tests/test_invoice_usage_collection_sql_runtime.py -q`、`npm --prefix web test -- OutputInvoiceCollectionsPage.test.tsx --run` |
| 2026-06-18 | 补充红蓝票 Browser fan-out | 不改变状态机；新增真实 Chromium 覆盖红蓝票关系确认后 rows refresh 和人工依据展示 | `cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts` |
| 2026-06-17 | 补充 Browser e2e 主流程 | 不改变状态机；新增真实 Chromium 覆盖手动状态/提醒保存、rows refresh、正式收据创建和 history 展示 | `cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts` |
| 2026-06-11 | 首轮测试闭环文档化 | 明确业务/UI/read model/worker 状态和禁止流转 | `tests/test_output_invoice_collection_*`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`bash scripts/verify.sh docs` |
