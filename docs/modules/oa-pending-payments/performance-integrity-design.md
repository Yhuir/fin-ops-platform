# OA 待付款核对：Direct Canonical Query 性能与完整性设计

日期：2026-07-28

## 结论

页面直接读取已经同步到 PostgreSQL 的 canonical facts。正确性边界是单次显式 `REPEATABLE READ READ ONLY` snapshot，不是 freshness/version/cache/worker。页面热路径不访问 OA Mongo/MySQL、Redis、RabbitMQ、read model 或 Workbench projection。

## 请求分段

```text
auth + parameter validation
  -> begin RR/RO snapshot
  -> selector statement
       canonical groups
       filters/sort
       pagination
       summary/statistics/facets
       current-page descriptors
  -> fixed-count batch hydrate
       completed/in-progress OA
       active formal/pending relations
       bank/input invoices
       payment statuses
  -> pure row composition
  -> JSON serialization
```

selector 和 hydrate 共享同一 snapshot；不得先查 total/summary，再在不同事务查 rows。

## SQL 设计

- canonical completed OA：`app.oa_applications`。
- canonical in-progress OA：tenant-scoped `app.oa_pending_payment_admissions`。
- formal relation：`app.workbench_pair_relations where status='active'`，不按 relation mode 排除；只把可解析 outflow bank member 计入支付展示和金额。
- pending relation：active `app.oa_pending_payment_bank_relations`。
- bank/input invoice：只按 relation member IDs 批量 hydrate。
- selector 用 CTE 形成 typed columns，SQL 内完成 keyword/filter/sort/page/summary/facets。
- bank candidates 用独立单条 SQL 在同类 RR/RO snapshot 内完成 active formal/pending relation 分类、keyword/status filter、total 和分页。
- 最大 page size 200；不得先加载全量 rows 再由 Python/浏览器处理。
- row/detail builder 复用既有纯函数，避免复制金额、relation 和 writeback 业务规则。

## 查询次数合同

| 阶段 | 查询次数 | 是否随 page size 增长 |
| --- | --- | --- |
| transaction setup | 1 statement | 否 |
| selector + aggregates + descriptors | 1 read | 否 |
| completed OA | 0/1 batch read | 否 |
| in-progress admission | 0/1 batch read | 否 |
| active formal relation | 0/1 batch read | 否 |
| active pending relation | 0/1 batch read | 否 |
| bank/invoice facts | 各 0/1 batch read | 否 |
| payment status | 0/1 batch read | 否 |
| bank candidate list | 1 set-based read | 否 |

本地 guard 比较 1 与 200 descriptors 的 repository read count，必须相同。任何 per-row/per-group loop I/O 都是阻断回归。

## 一致性不变量

- rows、total、summary、status counts、view counts、statistics 和 facets 必须来自同一 snapshot。
- selector descriptor 必须可由同 snapshot 的 canonical facts hydrate；缺失时 fail fast，禁止静默丢行。
- active relation withdraw 在下一次 snapshot 立即生效；旧 raw payload 或 projection 不得复活。
- active OA+outflow relation 无论 relation mode 都必须在同一 snapshot 的 canonical consumer 中可见。
- 混合收支关系的 inflow 不进入 bank paid total、页面流水或支付写回金额；只有 inflow 时保持 unpaid。
- payment status 只按同 tenant + selected flow IDs 批量读取。
- command 的外部写回和 PostgreSQL snapshot reconcile 失败时不返回成功。

## 本地证据

自动化 guard：

- explicit `REPEATABLE READ READ ONLY`。
- selector 仅 1 次 `fetch_one`，包含 server `limit/offset`。
- SQL 引用 canonical tables 和 active relation predicate。
- Page Audit 用统一事实源 active OA+outflow 期望集对照同一 canonical consumer，防止 selector/hydrate 过滤造成假通过。
- SQL 不引用 OA/workbench read model、dirty/outbox。
- 1 与 200 descriptors 的 hydrate query count 相同且有上限。
- bank candidate list 为 1 次服务端分页查询，不调用 import snapshot 全量扫描。
- frontend 成功页经过 550ms 仍只有首个 rows 请求；手工刷新只新增一个 normal GET。

这些 guard 证明结构，不等于真实 PostgreSQL plan 或生产延迟证据。

## 生产验证

### 数据集

- 使用生产等量级只读副本或可证明等量级的脱敏副本。
- 记录 completed/in-progress OA、active relations、bank/invoices、月份跨度和最大 relation group size。
- page size 分别取 20/50/100/200；覆盖 all-month 与单月、空集、高选择性和低选择性 filters。

### EXPLAIN

对 selector 和各 batch hydrate 运行：

```sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)
...
```

记录 planning/execution time、actual rows/loops、shared/temp blocks、sort method、spill、最慢节点。只有出现可复现瓶颈时提出索引；本分支不创建索引 migration。

### Endpoint

- 至少 1000 次 rows 请求：p50/p95/p99/max/error rate。
- 目标：server `p95 <=250ms`，`p99 <=500ms`。
- 记录 connection acquire、snapshot setup、selector、hydrate、composition、serialization。
- 确认查询次数对 page size 固定。
- 同时观察 Workbench、input invoice usage、invoice lifecycle，不允许通过扩大共享连接池转移瓶颈。

### 写后可见性

分别验证 active confirm、withdraw、pending link、promotion 和 paid writeback：

1. 记录 canonical commit 完成时间。
2. 立即执行本页 normal GET。
3. 验证新 snapshot 可见且无 queue/worker/barrier wait。
4. 外部写回路径另记录 MySQL 与 PostgreSQL reconcile 分段。

## 回滚

回滚代码 release 不等于恢复页面旧 read-model 双读。若 direct query 有阻断性 SQL 问题，应回滚整个页面 release 到前一稳定版本；禁止在同一版本加入 live/read-model fallback、shadow read 或 cache 掩盖。共享旧 resources 的最终删除由主控统一 migration 管理。

## 明确不做

- 不新增 cache、materialized view、worker、queue、cursor pagination 或新依赖。
- 不把 summary/facets 拆成多个事务。
- 不读取 Workbench page payload 或 `workbench_relation` projection。
- 不用 Python/浏览器全量过滤分页。
- 不凭静态猜测添加索引。
