# 银行明细 SQL Read Model 运维手册

## 目标

银行明细页面生产热路径使用两类 SQL read model：

- `read_model.bank_detail_rows` + `read_model.bank_detail_scopes(scope_type='bank_detail')`：流水列表、自动标签、关系标签、分类统计和交易数量。
- `read_model.bank_account_balances` + `read_model.bank_detail_scopes(scope_type='bank_account_balance')`：账户最新余额和总余额。

API 在 PostgreSQL production/lightweight runtime 下只读 SQL read model；缺失、过期或 schema 不匹配时写对应 dirty scope/outbox 并返回刷新态，不在请求线程里全量扫描银行流水或重建 workbench payload。

账户余额口径独立于自动标签：每个账户余额来自 `app.bank_transactions` 中该账户按交易时间排序的最新一笔非空 `balance`，总余额等于各账户最新余额之和。日期、关键字、分类筛选、自动标签规则保存和关系标签刷新只允许影响流水列表、交易数量和标签统计，不得改变账户余额或总余额。

## 上线步骤

1. 应用 migration `0030_bank_detail_read_model.sql`、后续银行明细索引/版本 migration，以及 `0039_bank_account_balance_read_model.sql`。
2. 在灰度环境检查 RabbitMQ topology，确认包含 `bank_detail.read_model.refresh` 和 `bank_account_balance.read_model.refresh`。
3. 先 dry-run backfill：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.bank_detail_backfill --dry-run --enqueue-missing

PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.bank_account_balance_backfill --dry-run --enqueue
```

4. 入队历史月份、生成账户余额并 drain：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.bank_detail_backfill --enqueue-missing --worker-drain --max-iterations 500

PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.bank_account_balance_backfill --rebuild-now
```

5. 启动常驻 worker：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-bank-detail-read-model-refresh \
  --enable-bank-account-balance-read-model-refresh \
  --worker-kind bank-detail-read-model \
  --event-type bank_detail.read_model.refresh \
  --event-type bank_account_balance.read_model.refresh \
  --max-events-per-iteration 24 \
  --poll-interval-seconds 0.5
```

## 回滚

- 停止 bank detail/account balance worker 和 RabbitMQ dispatcher 中相关 event type 的发布。
- 将 API runtime 回到 legacy/local bootstrap 或恢复上一版本应用。
- 保留 `read_model.bank_detail_*` 和 `read_model.bank_account_balances` 表；它们是可重建投影，不参与写模型事实。
- Redis 可直接清空；银行流水列表缓存 key 包含 read model scope signature，账户余额接口不使用银行明细 scope cache。

## 验证 SQL

```sql
select scope_key, status, row_count, generated_at, last_error
from read_model.bank_detail_scopes
order by scope_key desc;

select account_identity, bank_name, account_last4, latest_balance, latest_balance_at,
       latest_balance_transaction_id, currency, transaction_total_count
from read_model.bank_account_balances
order by bank_name, account_last4, account_identity;

select currency, sum(latest_balance) as total_balance
from read_model.bank_account_balances
where latest_balance is not null
group by currency;

select scope_month, count(*) as rows
from read_model.bank_detail_rows
group by scope_month
order by scope_month desc;

select scope_type, status, count(*)
from job.read_model_dirty_scopes
where scope_type in ('bank_detail', 'bank_account_balance')
group by scope_type, status;

select event_type, status, count(*)
from job.outbox_events
where event_type in ('bank_detail.read_model.refresh', 'bank_account_balance.read_model.refresh')
group by event_type, status;

select worker_id, worker_kind, event_types, heartbeat_at
from job.runtime_worker_heartbeats
where worker_kind in ('bank-detail-read-model', 'bank-account-balance-read-model')
order by heartbeat_at desc;
```

## 余额异常排查

当页面总余额变化但没有新增、删除、重导银行流水时，按以下顺序排查：

```sql
select account_identity, bank_name, account_last4, latest_balance,
       latest_balance_at, latest_balance_transaction_id, source_versions
from read_model.bank_account_balances
order by bank_name, account_last4;

select coalesce(legacy_mongo_id, id::text) as transaction_id,
       account_no, account_name, balance, currency,
       txn_date, trade_time, bank_serial_no, status
from app.bank_transactions
where coalesce(legacy_mongo_id, id::text) = '<latest_balance_transaction_id>';

select scope_key, status, row_count, schema_version, generated_at, last_error
from read_model.bank_detail_scopes
where scope_type = 'bank_account_balance';
```

如果只保存了自动标签规则或关系标签，`read_model.bank_account_balances` 的 `generated_at` 和 `latest_balance_transaction_id` 不应变化；变化说明有银行流水导入/重导/删除、原始余额字段变化，或错误地触发了 `bank_account_balance.read_model.refresh`。

```sql
select event_type, status, count(*)
from job.outbox_events
where event_type = 'bank_account_balance.read_model.refresh'
group by event_type, status;
```

## 监控边界

- `job.outbox_events` 和 `job.read_model_dirty_scopes` 是 durable 状态源。
- RabbitMQ 只投递 envelope，不携带业务 payload。
- Redis 只做短 TTL page cache；Redis miss/error 必须回 SQL read model。
- 分类保存、pair relation/candidate/exception、标签字典变更只刷新 `bank_detail` 受影响月份或 `all`，不刷新 `bank_account_balance`。
- 银行导入、删除、重导或原始余额字段变化必须刷新 `bank_account_balance` 的 `all` scope。
- 银行明细 API 在 `read_model_status=refreshing`、`stale` 或 `schema_mismatch` 时应继续返回最后一版 SQL 投影供页面展示，同时入队刷新；持续超过一个 worker 轮询周期仍不视为正常完成态，必须检查 `bank_detail.read_model.refresh` 是否有 pending/failed 事件、`worker-bank-detail` 是否有心跳、以及 `read_model.bank_detail_scopes.last_error`。
- 年度视图会同时依赖 12 个 `bank_detail` 月度 scope。生产 `worker-bank-detail` 必须使用批量 drain 参数，例如 `--max-events-per-iteration 24 --poll-interval-seconds 0.5`，避免每 5 秒只处理一个月导致刷新体验退化。
