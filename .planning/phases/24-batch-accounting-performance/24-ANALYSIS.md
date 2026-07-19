# 批量账务性能全量分析

日期：2026-07-20

## 结论

批量账务当前没有前端重复加载，也没有 worker 堵塞。生产 `GET /api/batch-accounting` 的主要慢点是 `workbench_relation` 查询端按 scope 逐个证明 freshness：一次请求产生约 52–66 次数据库查询。其次，未提交列表会读取所有 OA 附件发票，再在 Python 中关联到当前 OA 候选；这会随历史数据增长而放大。

首次发布后 query count 已降到 p95 `10`，但 40 样本 unsubmitted HTTP p95 仍为 `612.217ms`；dashboard 显示 API 内部 p95 `400.374ms`、DB p95 `256.256ms`，压缩响应仅 `3629 bytes`。剩余根因是银行候选 SQL 对结构化 `counterparty_name` 与两个历史 payload 字段做 `OR`，使既有 `workbench_rows_bank_counterparty_scope_idx` 无法稳定命中。当前 projection/Audit 已保证结构化列，因此 payload fallback 是可删除旧链，不需要新索引或缓存。

第二次发布删除银行 fallback 后，40 样本 unsubmitted p95 仍为 `580.757ms`，dashboard DB p95 `274.008ms`、query count p95 `10`。这排除了响应体、connection acquire、worker 和银行 fallback 作为主瓶颈；剩余候选 SQL 中只有 OA 类型筛选仍以两个 JSON 字段的前导通配 `OR` 做全扫描。最终最小方案因此增加一个仅覆盖非 `all` OA 行、且表达式与查询完全一致的部分 trigram 索引；不增加结构化列、第二 read model、缓存或 worker。

第三次发布应用 OA 类型索引后，40 样本 unsubmitted p95 降到 `514.231ms`，但仍比硬门槛高 `14.231ms`；dashboard 显示 API/DB/connection/query-count p95 为 `346.122ms` / `246.317ms` / `0.267ms` / `10`。剩余可控耗时是同一候选快照仍分成银行、OA、附件三个顺序数据库 round-trip。它们共享 active-generation 一致性边界和输出 DTO，合为一个 repository I/O 可删除两次往返，不需要增加新抽象或基础设施。

第四次发布把候选读取降为一个 I/O 后，query count p95 从 `10` 降为 `8`，但 unsubmitted p95 仍为 `513.385ms`；dashboard API/DB/connection p95 为 `349.779ms` / `254.613ms` / `0.230ms`。生产数据量只有银行 `989`、OA `253`、OA 附件 `196`，排除数据体量和连接获取后，剩余成本是 batch 专用 relation 读取内部仍有两组串行往返：候选 row lookup 后分别读取 scope proof 与 groups，年度计数分别读取 scope proof 与 count。第五轮只把这两组各合为一个 repository I/O，将页面请求从 `8` 条降到目标 `6` 条；不增加索引、缓存、read model、worker 或公共抽象。

第五次发布后 unsubmitted 的实际 query-count 已降到约 `6`，但 40 样本外部 p95 为 `523.595ms`；dashboard API/DB/connection/query-count p95 为 `389.325ms` / `262.648ms` / `0.202ms` / `7`（同一 endpoint 窗口混合 unsubmitted 与 submitted，后者查询数更高）。剩余最后一次可避免往返是同一 batch-only repository 方法内部先读 relation rows、再读其 scope proof/groups。第六轮把 rows/proof/groups 作为一个 SQL 快照返回，使 unsubmitted 再减少一次往返；这是当前边界内最后一个简单、确定且不跨模块的合并点。

第六次发布后 unsubmitted 查询数约为 `5`，40 样本外部 p95 为 `520.481ms`；shell `113.305ms`、submitted `311.506ms`、Page Audit `295.298ms` 均通过，160/160 请求全部为 2xx/fresh/0 enqueue。dashboard 混合 endpoint API/DB/connection/query-count p95 为 `388.908ms` / `277.282ms` / `0.183ms` / `6`。剩余唯一独立的未提交 relation I/O 是年度 submitted count，它读取同一 `workbench_relation` 事实与 freshness scopes。第七轮因此把年度 scopes 和 `submitted_count` 合并进既有候选 relation bundle，并删除独立 count facade/port/repository/manifest 合同；目标 unsubmitted 查询数约为 `4`。这仍是同一 batch-only 边界内的单快照读取，不增加基础设施或影响通用 reader。

第七次发布已达到约 `4` 条 unsubmitted 查询，但 40 样本外部 p95 为 `538.172ms`；已提交 `311.865ms`、Audit `355.048ms` 通过，未提交 40/40 fresh、0 enqueue。dashboard 混合 endpoint API/DB/connection/query-count p95 为 `377.917ms` / `279.912ms` / `0.189ms` / `6`。结构审阅发现候选 active-generation SQL 仍为每条银行/OA/附件选择 `raw_payload`，而 `_read_model_payload` 在这些行存在规范化 `payload` 时绝不会读取该列；生产 HTTP 响应仅 `19541` bytes，原始 OA/附件 JSON 却可能远大于最终 DTO。第八轮只删除这个未消费列，保留 submit 窄 loader、事实源和所有跨页 reader，不新增索引。

第八次发布删除列表 `raw_payload` 后，40 样本 unsubmitted p95 为 `536.798ms`，仅改善 `1.374ms`；dashboard 混合 endpoint API/DB/connection/query-count p95 为 `415.061ms` / `239.217ms` / `0.181ms` / `6`，说明旧 I/O 应删除但不是主要尾延迟。剩余 relation bundle 中，年度 count 按 `tenant + linked + special_metadata.source + bank_year/year + 12 scopes` 过滤并 `count(distinct group_id)`，现有索引只覆盖 tenant/scope/relation_kind 或 tenant/group_id，没有覆盖该谓词。第九轮增加一个只包含 linked batch-accounting 行的 partial expression index；本地真实 PostgreSQL 以 5,000 条非 batch relation 验证执行计划命中，不改变任何运行时 I/O 或其他页面查询。

本轮应保留现有 Workbench + workbench_relation 事实源，不新增独立 read model、缓存、表、队列或 worker。schema 变化只包括生产复测逐步证明必需的两个 batch-only partial index：0112 OA 类型表达式索引和 0113 relation 年度计数表达式索引。最小而完整的生产方案是：

1. 新增批量账务专用的 relation 批量读取 I/O，一条 SQL 同时证明 12 个或候选涉及的全部 scope。
2. 未提交候选只读取当前 OA IDs 对应的附件发票。
3. 银行候选只读取 Workbench projection 的结构化 `counterparty_name`，删除两个 JSON fallback，让既有复合索引生效。
4. OA 类型筛选把两个字段规范为一个稳定表达式，并由 `0112` 部分 trigram 索引覆盖。
5. 银行、OA、当前 OA 附件作为同一 active-generation 候选快照，由一个 repository SQL I/O 返回；submit 继续使用自己的窄 loader。
6. 批量账务不再调用通用的逐 scope relation 读取入口；通用入口继续服务其他页面，行为不变。
7. 候选 relation 的 scope proof+groups 由一个 batch-only SQL 返回，年度 scope proof+count 先收敛为独立固定 I/O。
8. 候选 relation rows 与其 scope proof/groups 最终由同一个 batch-only repository 快照返回，不再先 rows 后 proof/groups。
9. 年度 scopes proof 和 `submitted_count` 最终并入同一候选 relation bundle；删除独立年度 count facade/port/repository/manifest 合同，未提交 relation 只保留一个 owner I/O。
10. 删除候选列表未消费的 `raw_payload`；年度 count 命中 0113 batch-only partial expression index，不向其他页面增加运行时分支。

## 生产基线

- 页面 shell：p95 `104.966ms`，通过 `500ms` 门槛。
- 未提交 2026：p95 `638.061ms`，20/20 fresh、0 enqueue，未通过 `500ms` 门槛。
- 已提交 2026：p95 `390.986ms`，通过 `500ms` 门槛。
- Page Audit：p95 `375.765ms`，通过 `1000ms` 门槛。
- `/api/batch-accounting` 52 个生产样本：DB query count p50 `52`、p95 `66`、p99 `71`；SQL execute/fetch p95 `349.462ms`，connection acquire p95 `0.905ms`。
- `workbench_relation` worker：近 15 分钟/1 小时 refresh p95 `20.391ms`、stale `0`、unavailable `0`，不是当前瓶颈。

## 当前链路与边界

输入 I/O：

- `GET /api/batch-accounting?bank_year=YYYY&bucket=unsubmitted|submitted`
- Workbench active generation：批量账务银行候选、日常报销 OA、OA 附件发票。
- workbench_relation：候选是否已关联、年度已提交 relation、freshness/source_versions。

输出 I/O：

- 既有 API response shape、分页、`read_model_status`、`read_model_scope_keys`、`stale_reasons`、`refresh_enqueued`。
- 既有前端 loading/empty/error/refreshing 行为。

事实源：

- 业务 relation 事实：`app.workbench_pair_relations`。
- 关系读模型：`read_model.workbench_relation_*`。
- freshness/refresh 事实：PostgreSQL durable queue `job.read_model_dirty_scopes` / `job.outbox_events`。
- 候选行：Workbench active generation。

明确不改变：

- submit/withdraw command service、canonical relation 写入、affected scopes、derived lifecycle。
- 其他页面的 WorkbenchRelationReadFacade 通用 `get_by_row_ids`、`list_by_month` 和 worker/read model 合同。
- API DTO、权限、页面状态机和业务筛选规则。

## 根因证据

### 1. relation freshness N+1

`_workbench_relation_payload_from_rows(...)` 对每个 scope 分别执行：

1. 查询 `read_model.workbench_relation_scopes`。
2. 查询 `job.read_model_dirty_scopes` 的当前状态。

年度 count 为 12 个 scope 的 24 次证明 + 1 次 count。年度 list 先证明 24 次，读 groups 后又证明 24 次。候选 row lookup 还会再次按实际/hint scope 逐个证明，因此生产观测到 p95 66 次查询。

### 2. OA 附件查询未按候选收窄

未提交 loader 已经先得到 OA 候选，但附件 SQL 仍读取所有非 `all` scope 的 `oa_attachment_invoice`，最后才在 service 中构建 OA→invoice 关系。当前生产数据量尚小，但这是确定性的扩张风险，也违反“页面读取应由当前输入界定”的 I/O 约束。

### 3. 前端、连接与 worker 不是根因

- 前端一次依赖变化只发一次 list 请求，没有重复 fetch。
- connection acquire p95 小于 1ms。
- worker refresh p95 约 20ms 且无 stale/unavailable。

因此不应增加前端轮询、缓存、worker 并发、数据库连接池或新 read model。

## 旧代码识别与移除范围

本轮要从批量账务链路移除：

- BatchAccountingService 对通用 `get_by_row_ids` 的依赖。
- 年度 count/list 内逐月 `_workbench_relation_payload_from_rows` 证明以及 list 的第二次重复证明。
- 未提交 loader 中无 OA ID 约束的全量附件 SQL。
- 银行候选 SQL 中绕过结构化投影列的 `payload.counterparty_name` / `payload.counterparty_name_raw` fallback。
- OA 类型两个 JSON 字段各自前导通配再 `OR` 的未索引条件，以及列表银行/OA/附件三个顺序 round-trip。

不会删除：

- 通用 `get_by_row_ids` 和逐 scope payload 逻辑，因为仍有其他合法调用方；只禁止批量账务继续进入该旧路径。
- submit/withdraw 已有窄读取和 canonical command 路径。

静态 guard 必须证明批量账务 service 使用专用 relation I/O，列表候选只有一个 repository `fetch_all`，附件由当前 OA candidate CTE 界定，并且银行候选只读取结构化 `counterparty_name`。

## Grill-me 三轮审阅

### 第一次：正确性与一致性

- 批量 proof 必须保持原顺序、状态优先/覆盖行为、`missing_scope:*` 和 `refreshing|stale:*` reason 格式。
- source_versions 仍取第一个存在且非空的 scope metadata；没有时才使用 rows/groups fallback。
- 非 fresh 仍由既有 facade 统一 enqueue；不得伪装 fresh。
- 年度 12 scope 合同和空 scope 行为不变。
- 结论：可实施，但必须以“输出等价”和 fresh/missing/refreshing/stale 测试作为门禁。

### 第二次：模块隔离与旧链删除

- 若直接优化通用 helper，会扩大对其他页面的运行时影响面，不符合本轮隔离目标。
- 因此增加 Batch Accounting 专用 repository/port/facade 方法；其他页面的通用方法不改调用关系。
- 可以复用一个纯内部 payload 组装 helper，但批量方法必须显式拥有自己的批量 scope proof I/O。
- 旧无界附件 SQL直接替换，不保留 fallback。
- 结论：边界清晰，只有 Workbench/read-model 作为显式共享事实，不会改变其他页面的功能输出。

### 第三次：性能、复杂度与运维

- 未提交最终目标约 6 次业务查询：1 个候选快照 + 2–3 个专用 relation lookup + 2 个年度 count；请求级观测门为 p95 `<=8`。
- 已提交目标固定约 6 次查询：1 个银行读取 + 2 个年度 relation list + 3 个 relation detail lookup。
- 不新增基础设施；migrations 0112/0113 只增加可独立保留的 batch-only 读性能索引。应用回滚只需部署上一 release，索引不改变读写语义；如需物理清理，另行在维护窗口 `drop index concurrently`。
- 只有候选单 I/O 部署后 p95 仍大于 `500ms`，才依据新的生产 dashboard 继续分析；不提前增加 server-side candidate paging、缓存或第二 read model。
- 结论：方案不是过度设计；它直接删除已量化的 N+1 和无界读取，并保留完整 freshness、审计、回滚和隔离闭环。

## 验收门槛

- 页面 shell p95 `<=500ms`。
- unsubmitted/submitted GET p95 `<=500ms`，目标 `<=300ms`；20 次全部 2xx。
- fresh 样本 `refresh_enqueued=false`，状态与 scope 合同保持一致。
- Page Audit p95 `<=1000ms`，结果 pass/fresh/drained/ready/0 issue。
- DB query count 不随 scope/candidate 月份数线性增长；单请求目标 `<=10`。
- command API p95 `<=1000ms`，committed-to-fresh p95 `<=2000ms`、hard max `3000ms`；生产写验证受全局 App Health preflight 门禁约束，门禁未通过时必须延后到最终系统门，不得绕过。
- 直接模块及关联台、银行明细、流水统计/成本统计 Page Audit 无回归。
