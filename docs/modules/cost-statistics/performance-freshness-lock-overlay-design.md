# 成本统计性能与加载设计

> 本文只记录当前有效设计。旧 Cost read model、worker、freshness gate、五视图和全量 payload 方案已经退休，不得作为实现依据。

日期：2026-08-31

## 结论

当前成本统计采用最短闭环：canonical snapshot → 纯 policy → view-specific page DTO。三个 view 共用一个成本人口，不新增缓存、read model、worker、表或依赖。

## 热路径

```text
HTTP GET explorer
  -> parse/validate view + scope + filters + cursor
  -> open one REPEATABLE READ READ ONLY transaction
  -> batch-load bounded canonical facts
  -> build cost events once
  -> filter/group/page for project | expense_type | bank_account
  -> return JSON
```

性能边界：

- 一次请求一个 connection/snapshot。
- repository 按集合读取，不按流水、关系、OA 单元或账户循环发 SQL。
- scope 尽早下推；命中关系后只扩展完整性和退款需要的关系成员。
- policy 对已加载事实线性遍历。
- `bank_account` 在成本事件上读取预先确定的 `bank_account_label`，不二次访问数据库。
- Explorer 与导出关闭成本行标签投影；详情、退款识别和无 OA 规则按各自合同读取必要标签。
- search 在聚合与分页前执行；cursor 绑定规范化 query 和全部下钻筛选。
- 右栏每页 20 条；前端不累计全量 rows，也不以滚动触发加载。
- `include_statistics=false` 的内容请求不被非关键全局统计阻塞。
- preview 最多 8 行；download 受行数上限保护。

## 加载与错误状态

- 首次没有可用数据时使用页面内轻量交互锁；成功后原子展示当前 surface。
- 切换 view/scope/search 只替换统计 surface。
- 选择左栏只加载中/右栏，选择中栏只加载右栏。
- 分页失败保留已确认当前页并局部重试。
- 详情抽屉 loading/error 与 explorer 隔离。
- 请求失败明确报错；不返回旧 payload，不把空数据伪装为 fresh，不轮询后台状态。

## 鲜度

成本统计没有独立鲜度状态。一次成功响应代表本次数据库一致性快照；事实写入提交后，下一次 GET 自然读取新事实。页面打开期间不主动推送，用户刷新或交互请求重新读取。

禁止恢复：

- Cost outbox、dirty scope、worker、Redis payload cache；
- `202 refreshing` 或 `409 read_model_not_fresh`；
- 旧 `time_rows`/`bank_flow_rows` 兼容 payload；
- 客户端业务聚合或后台预取全期间数据；
- 数据库失败后的本地/历史数据 fallback。

## 性能验证

候选发布至少测量：

1. `project` 根视图；
2. `expense_type` 根视图；
3. `bank_account` 根视图；
4. 一个账户的项目 facets；
5. 一个账户+项目的成本 rows；
6. allocation detail；
7. export preview。

每项多次采样并报告 p50、p95、max、HTTP 状态和关键 row/facet 数。性能目标不是用额外门禁代替测量：如果生产长尾不达预期，先依据 query timing/plan 定位具体热点，再评估索引或 SQL 优化；没有实测证据不得引入缓存或异步投影。

## 隔离验证

- Cost 请求前后没有新增 Cost queue/dirty scope/worker I/O。
- 银行明细仍能独立浏览原始银行流水。
- Workbench、导入、往来款、设置及权限关键只读 smoke 正常。
- 旧 view 返回 400，旧 time-tag endpoint 返回 404。

## 数据安全

该设计不修改 schema 或业务数据，不需要数据库备份。验证只读生产事实；禁止删除主数据库。
