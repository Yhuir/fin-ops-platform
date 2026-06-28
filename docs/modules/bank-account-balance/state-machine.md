# Bank Account Balance 状态机

## 当前状态

独立 `bank_account_balance` read model 状态机已下线。`/api/bank-details/accounts` 只有 direct API 读取状态：成功返回当前业务 payload，失败返回普通 API 错误；不再暴露 `fresh`、`refreshing`、`stale`、`failed`、`unavailable` 或等价 freshness 字段。

## 已删除状态

- `fresh` / `refreshing` / `stale` / `failed` / `unavailable`
- `bank_account_balance:all` scope
- `bank_account_balance.read_model.refresh`
- `bank-account-balance` worker
- `read_model.bank_account_balances` 当前运行读写路径

## 非法状态

- Bank Details accounts API 返回 read-model freshness 字段。
- 导入、settings reset、runtime lifecycle 或 backfill 重新 enqueue `bank_account_balance.read_model.refresh`。
- Worker registry、App Status、RabbitMQ dispatcher、deploy env 或 manifest 重新注册 `bank-account-balance`。
- 新增 `BankAccountBalance*ReadModel*` service/port/projection/backfill。

## 变更记录

| 日期 | 变更 | 状态机影响 | 测试/验证 |
| --- | --- | --- | --- |
| 2026-06-24 | 建立模块维护骨架，并选择为 Search 后的 read model pilot | 历史记录；当时定义了 all-only worker/storage contract | 历史验证见 implementation notes |
| 2026-06-27 | Bank Details accounts page read 改为 direct API | 页面不再消费账户余额 read-model freshness | `tests/test_bank_details_routes.py`、`tests/test_bank_details_sql_runtime.py` |
| 2026-06-28 | 删除账户余额 legacy read-model runtime | 删除 worker/projection/repository/backfill/producer/manifest/App Status/deploy env；状态机转为已下线负向守卫 | `tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` |
