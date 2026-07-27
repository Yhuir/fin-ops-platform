# 银行账户余额测试矩阵

> 账户余额不再是独立 read model。它是银行明细页面 canonical accounts query 的聚合结果。

## 当前合同

- 直接从 canonical 银行流水按账户聚合最新余额、最新交易日期和范围笔数。
- 不读取 `read_model.bank_account_balances`，不等待 `bank_account_balance:all`，不 enqueue。
- 账户结果不受 transactions 当前页分页限制；筛选和权限由银行明细 route/query 合同负责。
- 历史 projection migration/表只供上一版本回滚，当前没有 reader/writer。

## 测试责任

| 类别 | 入口 |
| --- | --- |
| 业务/service/repository | `tests/test_bank_details_canonical_query.py` |
| API contract | `tests/test_bank_details_routes.py`、`web/src/test/BankDetailsApi.test.ts` |
| 前端 loading/empty/error/账户选择 | `web/src/test/BankDetailsPage.test.tsx` |
| 旧 worker/runtime 负向回归 | `tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py` |
| E2E | `web/e2e/bank-details-initial-state.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts` |

本模块没有独立 cache/background job 测试，因为对应 runtime 已删除；该类别只保留负向
合同。真实 PostgreSQL 聚合性能在部署前生产只读 smoke 验证。
