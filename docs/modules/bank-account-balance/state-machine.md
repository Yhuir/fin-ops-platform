# Bank Account Balance 状态机

日期：2026-07-27

## Bank Details 页面状态

`GET /api/bank-details/accounts` 已迁移为 direct canonical query，不再消费 read-model/worker 状态。

| 状态 | 判定 | 页面行为 |
| --- | --- | --- |
| loading | direct GET 未完成 | 显示加载态，不渲染假账户。 |
| ready | direct GET 200 | 显示账户、最新余额、范围笔数与汇总。 |
| empty | direct GET 200 且 `accounts=[]` | 显示真实空账户语义。 |
| error | 参数非法或 query 失败 | 显示错误；不轮询、不回退旧 projection。 |

禁止页面状态：

- `fresh` / `refreshing` / `stale` / `schema_mismatch` / `missing`
- `balance_read_model_status`、refresh job、operation barrier
- 用 `bank_detail` rows、旧 balance projection、Python 或浏览器全量聚合替代 canonical SQL

## 共享旧 Read Model 状态

旧 `bank_account_balance:all` manifest/worker/repository/backfill 暂时保留给范围外 consumer 与主控清理。其 `fresh/refreshing/stale/failed/unavailable` 状态只描述旧共享 projection，不再决定 Bank Details 页面响应。主控删除前必须完成 whole-repo consumer scan，并同步全局 read-model/worker/deploy/App Status 合同。

## 变更记录

| 日期 | 变更 | 验证 |
| --- | --- | --- |
| 2026-07-27 | Bank Details accounts 改为 direct canonical SQL；页面退出 balance RM freshness/polling | `tests/test_bank_details_canonical_query.py`、`tests/test_bank_details_routes.py`、Bank Details frontend/E2E tests |
