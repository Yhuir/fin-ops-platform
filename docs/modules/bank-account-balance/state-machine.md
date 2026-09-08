# Bank Account Balance 状态机

日期：2026-09-08（同时间顺序修复本地实施中，未发布）

## Bank Details 页面状态

`GET /api/bank-details/accounts` 已迁移为 direct canonical query，不再消费 read-model/worker 状态。

| 状态 | 判定 | 页面行为 |
| --- | --- | --- |
| loading | direct GET 未完成 | 显示加载态，不渲染假账户。 |
| ready | direct GET 200 | 显示账户、最新余额、范围笔数与汇总。 |
| empty | direct GET 200 且 `accounts=[]` | 显示真实空账户语义。 |
| error | 参数非法或 query 失败 | 显示错误；不轮询、不回退旧 projection。 |

账户请求失败独立显示“账户未更新”；流水、标签统计和规则分别保存自身错误，任一成功不能消除其他失败。切账户晚返回和旧 header 刷新的规则响应不得覆盖更新结果。accounts 与 transactions 是两个独立快照，页面刷新不提供跨 HTTP 请求的数据库同一时点保证。

## 余额证据状态

| `balance_status` | 判定 | 页面行为 |
| --- | --- | --- |
| `confirmed` | 最新已导入组末余额可靠，账户币种唯一，最新日期没有缺时间歧义 | 显示原始余额；末笔身份无法证明时 ID 可为 null。 |
| `last_known` | 最新组全部缺余额，最近有余额历史组末余额可靠 | 显示“最后已知余额”和来源日期；不计入完整总余额。 |
| `unresolved` | 最新组部分有余额但终点不可靠、历史候选组不可靠、最新日时间歧义，或账户多币种 | 显示“余额待核实”，金额与来源为 null；不任选有值行，不连续跨过冲突组。 |
| `missing` | 单币种账户全历史没有非空余额 | 显示余额为空/破折号，账户及笔数继续可见，不补 0。 |

状态优先处理同账户多币种，再判断全历史无余额；因此多币种账户即使全无余额仍为 `unresolved`。`has_balance` 只表示有可显示来源值，`confirmed/last_known` 为 true，其他为 false。余额确认为真实零时仍是可显示的 `0.00`。

每币种的全部应计账户均 `confirmed` 才显示该币种完整合计；`total_balance=null` 表示没有可输出的 CNY 完整合计，不能格式化为零。未完整时显示“暂无法确定完整总余额”，不显示另一套估算合计。同账户多币种使其底层涉及的每个币种合计都不完整，展示币种为 null。

所有证据状态在 GET 内派生，无人工“确认排序”或“修改余额”状态转换。通过原银行来源核实，缺项走正式补导、错误走既有受控纠错或符合条件的批次撤回/重导；事务提交后的下一次 GET 重新判定。

禁止页面状态：

- `fresh` / `refreshing` / `stale` / `schema_mismatch` / read-model `missing`；不禁止上文独立的 `balance_status=missing`
- `balance_read_model_status`、refresh job、operation barrier
- 用 `bank_detail` rows、旧 balance projection、Python 或浏览器全量聚合替代 canonical SQL

## 已退役 Runtime

旧 `bank_account_balance:all` manifest/worker/repository/backfill 和部署注册已删除。历史 migration 文件
只作不可变记录；migration `0149` 已删除 projection schema。不得恢复旧 reader/writer。

## 变更记录

| 日期 | 变更 | 验证 |
| --- | --- | --- |
| 2026-09-08 | 账户余额分为 confirmed/last_known/unresolved/missing，完整合计可为 null；增加局部请求失败与过期响应保护，未发布 | 本地验证进度见同时间修复计划 |
| 2026-07-27 | Bank Details accounts 改为 direct canonical SQL；页面退出 balance RM freshness/polling | `tests/test_bank_details_canonical_query.py`、`tests/test_bank_details_routes.py`、Bank Details frontend/E2E tests |
