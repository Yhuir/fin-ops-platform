# 银行明细 模块维护入口


- Module key: `bank-details`
- 类型: 页面模块
- Route: `/bank-details`
- Page key: `bank-details`

## 修改前必读

- `docs/product-specs/bank-turnover-and-no-oa.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`

## 代码入口

- `web/src/pages/BankDetailsPage.tsx`
- `web/src/features/bankDetails/*`
- `backend/src/fin_ops_platform/app/routes_bank_details.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
- `backend/src/fin_ops_platform/services/bank_detail_available_month_scope_provider.py`
- `backend/src/fin_ops_platform/services/bank_detail_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/bank_detail_read_model_refresh_producer.py`
- `backend/src/fin_ops_platform/services/bank_detail_derived_lifecycle_executor.py`

## 当前边界

关注银行流水、标签、no-OA 状态、业务对象关系和跨页刷新。

银行明细 read model 的 `bank_detail:all` 是 refresh fan-out 控制 scope，用于枚举月份 shard；页面无界查询不能等待 `bank_detail:all` parent proof。无日期筛选的交易列表和账户列表必须解析为当前已存在的月份 scope 集合，并用这些 month shards 的 freshness/source versions 证明页面数据 fresh；只有没有任何月份 shard 时才保留 `all` 作为 empty/missing 判断入口。

`bank_detail:<YYYY-MM>` 投影以月份为 partition。每次 refresh 必须先计算稳定 source signature：银行流水规范化行、自动分类上下文行、人工分类/确认，以及 workbench relation read model source versions。若 row count 与除 `source_version` 外的 source versions 完全一致，projection 只推进 scope source version 并跳过重写 `read_model.bank_detail_rows` 与自动分类重算；若任一输入变化，必须完整重投影该月份并重新发布 fresh scope。该跳过路径只允许在已有 scope signature 可证明一致时使用，不能把 missing/schema mismatch/stale 伪装成 fresh。

2026-07-05 起，本模块页面读链路已 close：`BankDetailsApplicationService.accounts_payload(...)` / `transactions_payload(...)` 只读取 read model/query port，不再回退 `BankDetailsService.list_accounts(...)` / `list_transactions(...)` 或导入服务扫描；缺失 repository、missing、stale、schema mismatch 均通过 freshness/status payload fail-closed。分类候选推断和标签字典只通过显式 provider 注入，应用服务不持有宽 `import_service` / `BankDetailsService`。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `e2e-spec.md`：维护银行明细 Browser e2e 业务验收合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/Vitest/API/integration 的覆盖映射和缺口。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
