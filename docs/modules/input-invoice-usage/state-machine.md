# 进项发票使用情况 状态机


> 修改 `进项发票使用情况` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

- 当前状态：页面本身是只读查询页，业务状态主要来自行 payload 中的 `paymentStatus`、OA 关联、银行流水关联和发票生命周期判断。
- 状态事实源：`read_model.input_invoice_usage_rows.payload` 是页面读取事实；发票、OA、银行流水和 workbench 关系由 read model worker 构建时投影进入 payload。
- 允许流转：支付状态规则、OA 反提、workbench 关系确认或撤销会通过 read model refresh 影响页面展示。
- 禁止流转：页面列表查询不直接修改发票、OA 或银行流水事实；缺失或过期 read model 不能回退为 live scan 伪装 fresh。

## UI 状态

- loading：前端请求 `/api/input-invoice-usage/rows` 与 filter options 时显示页面加载态。
- empty：API 返回 `read_model_status=fresh` 且 `pagination.total=0` 时展示标准空态。
- error：API 或解析失败时展示“进项发票使用情况加载失败，请稍后重试。”。
- stale/refreshing：API 返回 `read_model_status=refreshing` 时，页面不展示旧 rows，保持刷新提示/轮询语义；服务端应入队对应 scope 的 read model refresh。
- permission disabled/hidden：列表读取无独立权限状态；OA 反提、支付规则保存等 mutation 能力按对应接口权限和前端按钮状态控制。

## Read Model / Worker 状态

- fresh：SQL read model payload 的 `refresh_status=fresh`，且 `source_versions` 覆盖服务端期望版本时，API 返回 rows 并设置 `read_model_status=fresh`。
- missing：repository 没有可用 payload 时，API 返回 `202` 和 `read_model_status=refreshing`，并以 `api_miss` 入队。
- refreshing：dirty scope 处于 `pending`/`processing`，或 API 判定 schema/source version stale 后，会返回空 rows 的 refreshing payload。
- stale/failed/unavailable：dirty scope 失败或依赖不可用时不得把旧 rows 伪装为 fresh；调用方应触发 refresh 或展示可恢复状态。
- all scope：默认不传 `month` 的页面查询使用 `scope_key=all`。当没有单独 `all` scope 行时，repository 会从各月份 scope 聚合共同一致的顶层 `source_versions`；月份间 `workbench_relation_source_versions` 等嵌套版本可不同，不应导致基础版本被清空。若任一月份 cache status 非 fresh，all scope 仍判定不可 fresh。
- refresh 触发来源：API miss、schema stale、source version stale、业务写入后的 read model invalidation、worker all scope 展开月 shard。
- 失败恢复：通过 durable queue 重新刷新对应 month 或 all scope；all scope refresh 会展开到月 shard 后完成 queue 状态。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| - | 初始骨架 | 待补充 | - |
| 2026-06-10 | 明确 all scope source_versions 聚合规则 | 修复默认 all 查询因月份间 workbench 关系嵌套版本不同而被 API 误判 `refreshing` 的风险 | `tests.test_invoice_usage_collection_sql_runtime`、`tests.test_input_invoice_usage_api`、`tests.test_read_model_freshness`、`web/src/test/InputInvoiceUsagePage.test.tsx` |
