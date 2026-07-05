# Bank Account Balance 模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：completed
- 当前边界可信度：high
- 目标边界：银行账户余额作为 all-only read model，由银行明细应用服务读取，由 worker 通过账户级 SQL 投影重建快照。
- 当前缺口：当前 partition 是 global all scope only；生产性能依赖账户级 SQL 聚合、批量写入和 hot-path index，不允许恢复为 Python 全量流水聚合。
- 旧代码删除条件：旧账户余额即时计算路径无人引用，且账户余额 API/read model 测试覆盖。

## 职责边界

### 负责

- 银行账户余额快照投影。
- 为银行明细页面和账户 API 提供余额读取。
- 维护 `bank_account_balance:all` fresh 状态。

### 不负责

- 不拥有银行流水源事实。
- 不处理银行流水导入、分类、标签业务。
- 不扩展成任意账户流水查询。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Refresh scope | `bank_account_balance` manifest | 仅支持 `all` |
| 查询请求 | `BankDetailsApplicationService` | 读取快照，不现场扫描全量流水 |
| 银行流水导入确认 | import processing service/job result | 通过银行导入的 write target envelope 暴露 `bank_account_balance:all` operation barrier target |
| Backfill 请求 | `bank_account_balance_backfill.py` | 显式运维入口 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 账户余额 snapshot | bank details API | fresh gate 后返回 |
| Dirty scope/status | runtime queue/app status | all-only scope |
| Write target visibility | 导入页面/后台 job | 银行流水导入完成后必须让调用方可等待 `read_model_key=bank_account_balance`、`scope_key=all` |

## 持久化与投影

- Read model：`bank_account_balance`
- Projection：`partitioned_scoped_incremental`；当前 all scope 使用 SQL 直接按账户聚合，只返回账户级 rows，禁止 worker 把全量 `app.bank_transactions` 搬回 Python 再计算余额。
- Partition：global all scope only
- Worker：`bank-account-balance`
- Repository owner：`BankAccountBalanceReadModelRepositoryPort`
- Performance I/O：`save_bank_account_balances(...)` 必须批量写入；stale source-version event 必须跳过重建；PostgreSQL hot path index 位于 `0089_read_model_performance_hot_paths.sql`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Projection | `backend/src/fin_ops_platform/services/bank_account_balance_projection.py` |
| Repository | `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py` |
| Refresh | `bank_account_balance_read_model_refresh.py`、`bank_account_balance_read_model_refresh_producer.py` |
| Query owner | `backend/src/fin_ops_platform/services/bank_details_application_service.py` |
| Route/tool | `backend/src/fin_ops_platform/app/bank_account_balance_backfill.py` |
| Manifest/worker | `read_model_manifest.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_bank_account_balance_read_model.py`、`tests/test_bank_account_balance_derived_lifecycle_executor.py` |

## 依赖方向

- 允许依赖：bank detail read model repository、runtime queue。
- 必须通过：all-only scope policy。
- 禁止绕过：用 arbitrary scope 调用此 read model；在页面里现场累计余额。

## 测试与验证

- `tests/test_bank_account_balance_read_model.py`
- `tests/test_bank_account_balance_derived_lifecycle_executor.py`
- `tests/test_import_processing_service.py`
- `tests/test_read_model_manifest.py`

## 当前缺口和删除条件

- 若未来账户余额变为按账号/月分区，必须先更新 manifest、scope policy、worker 和本文档。
- 禁止恢复旧账户余额即时计算或 worker 端 Python 全量流水扫描；若 SQL 投影无法满足新字段，先扩展 SQL projection 和测试。
- 删除旧账户余额即时计算路径前，必须保留银行流水导入确认/job result 的 `bank_account_balance:all` operation barrier 回归。
