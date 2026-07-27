# 银行明细模块维护入口

- Module key: `bank-details`
- 类型：页面模块
- Route：`/bank-details`
- Page key：`bank-details`

## 修改前必读

- `docs/product-specs/bank-turnover-and-no-oa.md`
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/dev/api-contracts.md`
- `docs/modules/bank-account-balance/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`

## 代码入口

- `web/src/pages/BankDetailsPage.tsx`
- `web/src/features/bankDetails/*`
- `backend/src/fin_ops_platform/app/routes_bank_details.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `backend/src/fin_ops_platform/services/bank_details_canonical_query.py`
- `backend/src/fin_ops_platform/services/bank_details_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_category_mutation_writer.py`

## 当前边界

银行明细页面已经迁移为 PostgreSQL canonical direct read：

- 浏览器只调用 `/api/bank-details/accounts`、`/api/bank-details/transactions`、导出和本模块写 API。
- route 只负责鉴权、参数解析与 HTTP 映射；查询组合由 `BankDetailsCanonicalQueryService` 负责，SQL 由 `PostgresBankDetailsCanonicalQueryRepository` 负责。
- rows、statistics、category counts 与当前页关系标签在同一个 `REPEATABLE READ READ ONLY` snapshot 中读取。
- 正式关系只读取 `app.workbench_pair_relations` 中 `status=active` 的事实；关系 overlap 查询只接收当前可见或导出目标流水 IDs，不读取 Workbench 页面 payload、`workbench_relation` projection 或其它页面 read model。
- 账户列表和余额直接以有界 SQL 聚合 canonical `app.bank_transactions`，保留账户 identity、最新余额、最新流水、币种和空余额账户语义，不在 Python 或浏览器全量聚合。
- 页面响应不再携带 `read_model_status`、`source_versions`、refresh scope/job/barrier；前端不轮询。loading、empty、error 与用户重试仍是可观察状态。
- 分类、候选确认、人工补分类和自动标签规则写入继续走 canonical fact、CAS、审计和定向写入；成功后当前页面只重新 GET 一次。

旧 `bank_detail` / `bank_account_balance` read model、worker、下游 tagged-row ports、backfill 和部署单元已在跨页面清理中删除。历史 migration/表暂留作回滚证据，不存在页面或 worker 运行时调用方。

## 维护触发器

- 页面筛选、排序、分页、导出、drawer/dialog、权限或可观察状态变化。
- API 参数、响应 shape、错误码、CAS/审计或写后重读变化。
- canonical 表、账户 identity、分类规则、active relation membership 或 snapshot 一致性变化。
- 查询次数、最大页大小、导出上限或性能 guard 变化。
- 共享旧 read model 消费者完成迁移，满足删除条件。

## 本目录文件

- `boundary-io.md`：当前 direct-read I/O、文件范围和旧链删除状态。
- `state-machine.md`：业务写状态与页面 loading/empty/error 状态。
- `tests.md`：七类测试、验证命令和剩余风险。
- `e2e-spec.md` / `e2e-coverage.md`：Browser 业务合同与覆盖映射。
- `implementation-notes.md`：提炼后的实施决策和验收记录。
