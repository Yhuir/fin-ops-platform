# 销项发票收款情况 状态机

> 修改 `销项发票收款情况` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

- 当前状态：
  - 自动收款状态：由 `InvoiceLifecyclePolicy.evaluate_output_invoice_collection(...)` 和 `OutputInvoiceCollectionStatusRuleService` 根据销项发票、银行收入流水、红冲/退款、人工关系和 lifecycle facts 判定，输出到 row `collectionStatus`。
  - 手动状态覆盖：`OutputInvoiceCollectionLifecycleService.set_collection_status(...)` 写入 status override，可携带预计收款日期、备注和 `expectedVersion`。
  - 收款提醒：`upsert_collection_reminder(...)` 创建或更新 active reminder；`cancel_collection_reminder(...)` 取消提醒。
  - 红蓝票关系：`confirm_red_invoice_relation(...)` 写入 `red_invoice` 或 `blue_invoice` 人工关系；`delete_red_invoice_relation(...)` 撤销关系。
  - 正式收据：`preview -> issued -> voided -> reissued`。创建必须有 idempotency key；history 读取真实 receipt lifecycle facts。
- 状态事实源：
  - 销项发票和银行/关系事实来自 import/workbench/read model 上游。
  - OA、收入流水和关联销项发票项展示来自 `workbench_relation` 统一分发关系；只有 `relationStatus="linked"` 能计入已收款或 confirmed relation 判断。linked relation 下存在多张销项发票时，`output_invoice_collection` 投影为一条收款行，发票金额按全部成员净额汇总，负数/红字发票必须保留在 `invoiceRelations.summaries`。未正式化自动匹配 decision 或历史 `relationStatus="candidate"` 兼容值按未关联处理，不作为第三种收款关系状态。
  - 收款状态规则来自 `InvoiceLifecyclePolicy` 和 `OutputInvoiceCollectionStatusRuleService`。
  - 手动状态、提醒、红蓝票关系、收据 facts 来自 output invoice collection lifecycle repository。
  - 页面列表事实来自 SQL read model `output_invoice_collection`，fresh 时叠加 lifecycle facts。
- 允许流转：
  - 自动状态可被合法手动状态覆盖；清空手动状态后回到 policy 自动判定。
  - reminder 可 create/update/cancel，渠道只允许 `oa`、`email`、`manual`。
  - 红蓝票关系可 confirm/delete，确认时必须提供 related invoice identity 或 invoice id。
  - receipt preview 可在存在可用收入流水且非红冲/退款状态时创建正式收据。
  - issued receipt 可 void；voided receipt 可 reissue；reissue 后不能重复重开同一 receipt。
- 禁止流转：
  - 不支持的手动收款状态、非法提醒渠道、缺失 related invoice、非法 relation type 必须失败。
  - stale read model 不能被当作 fresh rows 返回。
  - 缺少 idempotency key 不能创建正式收据。
  - 非 issued receipt 不能 void；非 voided receipt 不能 reissue；已重开 receipt 不能重复 reissue。
  - service 不得绕过 queue gateway/transaction-bound writer 直接写 dirty/outbox。

## UI 状态

- loading：页面初次挂载时并行加载 rows、filter-options 和 status-rules；loading 期间展示标准页面状态，不保留旧 route snapshot。
- empty：无业务 rows 时展示标准 empty state；refreshing 技术细节不直接暴露给用户。
- error：rows/filter-options/detail/drawer 请求失败时展示页面或 drawer 级错误；不静默吞掉提交失败。
- stale/refreshing：后端返回 `readModelStatus=refreshing` 时页面设置 refreshing 状态并在 active route 下自动重试；route unmount 后必须清理 retry timer。
- combined freshness：rows 与 filter-options 并行读取时，页面级 fresh 必须取两者合并结果；任一响应为 stale/missing/schema_mismatch/refreshing/unavailable 时，禁止进入普通 empty state、禁止启用导出，并沿用刷新诊断与重试语义。
- permission disabled/hidden：
  - 读详情需要 output collection read session 权限。
  - 收款状态、提醒、红蓝票和 receipt mutation 需要 mutation 权限。
  - receipt settings 入口 admin-only。
  - 权限不足时 API 返回 403，前端隐藏或禁用对应入口。
- relation list：当 OA、收入流水或关联销项发票项为多项时，对应栏显示 `+N` 入口，`N=relationCount-1` 表示额外项数；点击后打开详情 drawer，按 `kind=oa|bank|invoice` 展示全部 summaries。销项发票栏多项时必须保留当前行发票主信息和多张发票价税合计，再显示 `+N`，不得只留下展开入口。

## Read Model / Worker 状态

- fresh：`read_model.app_status_readiness` 或等价 repository 状态证明 `output_invoice_collection` scope fresh；rows route 返回 `200` 并可叠加 lifecycle overlay。
- missing/stale/source version mismatch：rows route 返回 `202`、`read_model_status=refreshing`，enqueue `output_invoice_collection` refresh；不得同步 live rebuild。
- schema stale：SQL payload 缺少 `oa` 或 `invoiceRelations` 等统一关系字段时，视为 schema stale 并 enqueue refresh；旧 read model 不得作为 fresh rows 返回。
- relation-group projection：linked relation 下多张销项发票是 row ownership 事实，必须先按 relation 归并为单条收款行，再回退到单发票 identity 行；归并行的 `invoiceRelations.totalWithTax`、`invoiceTotal` 和收款状态基于成员净额与 linked 收入流水计算，不能把同一 relation 拆成重复的 364800 行，也不能漏掉负数发票。
- relation detail unavailable：生产 PostgreSQL runtime 下缺少 SQL read repository 或 row detail lookup 时，`/rows/{row_id}/relation-details` 返回 `202`、`read_model_status=refreshing` 并 enqueue `output_invoice_collection:all`；不得 live rebuild detail 并伪装 fresh。
- refreshing：dirty/outbox 或 readiness 显示 scope 正在刷新；页面保持 busy/auto retry。
- failed/unavailable：App Status domain 进入 blocked 或 unavailable；页面不能伪装数据 ready。
- refresh 触发来源：
  - 页面 rows/detail/export 访问先比较 source/schema/rule version；只有当前 exact month scope missing/stale/mismatch 时才经 gateway 去重入队。
  - 发票导入、关系变化、pending invoice rules、手动状态、提醒、红蓝票关系、收据 create/void/reissue 只提交 canonical fact/version，普通写响应的 `freshness_targets` / `operation_barrier_targets` 为空；当前页写成功后重跑 normal GET，其它页面访问或重新激活时独立收敛。
  - `all` scope 只允许显式维护/修复使用，并由 `InvoiceUsageCollectionReadModelRefreshService` 扩展为月份 shard；普通写不得 fallback `all`。
- 失败恢复：
  - 按 `docs/operations/runtime-worker-governance.md` 先确认 `workbench_relation` 和 `invoice_lifecycle` fresh，再重放 `output_invoice_collection`。
  - outbox/dirty scope 失败必须保留审计，不允许直接 SQL 抹平。
  - 重放后以 API fresh 和 App Status readiness 为准。

## 变更记录

> 2026-07-22 Phase 27 已用“普通写零页面 fan-out、页面访问 exact-scope 收敛”取代此前的写后 freshness target / operation barrier 方案。下方 2026-06/07 记录只用于历史回归溯源，不是当前 writer 合同。

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
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
