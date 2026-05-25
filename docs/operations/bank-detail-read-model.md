# 银行明细 SQL Read Model 运维手册

## 目标

银行明细页面生产热路径使用 `read_model.bank_detail_rows` 和 `read_model.bank_detail_scopes`。API 在 PostgreSQL production/lightweight runtime 下只读 SQL read model；缺失、过期或 schema 不匹配时写 `bank_detail.read_model.refresh` dirty scope/outbox 并返回 202，不在请求线程里全量扫描银行流水或重建 workbench payload。

## 上线步骤

1. 应用 migration `0030_bank_detail_read_model.sql`。
2. 在灰度环境检查 RabbitMQ topology，确认包含 `bank_detail.read_model.refresh`。
3. 先 dry-run backfill：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.bank_detail_backfill --dry-run --enqueue-missing
```

4. 入队历史月份并 drain：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.bank_detail_backfill --enqueue-missing --worker-drain --max-iterations 500
```

5. 启动常驻 worker：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-bank-detail-read-model-refresh \
  --worker-kind bank-detail-read-model \
  --event-type bank_detail.read_model.refresh
```

## 回滚

- 停止 bank detail worker 和 RabbitMQ dispatcher 中该 event type 的发布。
- 将 API runtime 回到 legacy/local bootstrap 或恢复上一版本应用。
- 保留 `read_model.bank_detail_*` 表；它们是可重建投影，不参与写模型事实。
- Redis 可直接清空；缓存 key 包含 read model scope signature，清空不会影响正确性。

## 验证 SQL

```sql
select scope_key, status, row_count, generated_at, last_error
from read_model.bank_detail_scopes
order by scope_key desc;

select scope_month, count(*) as rows
from read_model.bank_detail_rows
group by scope_month
order by scope_month desc;

select status, count(*)
from job.read_model_dirty_scopes
where scope_type = 'bank_detail'
group by status;
```

## 监控边界

- `job.outbox_events` 和 `job.read_model_dirty_scopes` 是 durable 状态源。
- RabbitMQ 只投递 envelope，不携带业务 payload。
- Redis 只做短 TTL page cache；Redis miss/error 必须回 SQL read model。
- 分类保存、银行导入、pair relation/candidate/exception、标签字典变更都必须入队受影响月份或 `all`。
