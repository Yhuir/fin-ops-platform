# 关联台模块边界与 I/O

日期：2026-08-13

## 职责

### 负责

- 通过 direct canonical API 读取 OA、银行流水、发票、ETC 批次和正式关系，并把当前提交事实划分为 `paired` / `unpaired`。
- 提供同一只读快照内的首屏统计与两区首页、区域级搜索/筛选/排序、cursor 分页、filter options、group/row detail 和异常抽屉。
- 提供人工正式关联、关系级撤回、自动异常 ignore/restore；撤回恢复最近一次确认前的稳定拓扑。
- 保持权限、审计、幂等、canonical member exact-set、preview fingerprint、relation/entity version 和稳定加锁顺序。
- 写成功后由页面执行一次普通 direct GET，读取已提交事实；页面不等待 projection worker。

### 不负责

- 不维护 Workbench 页面 read model、active generation、freshness/source-version gate、page Redis payload cache、refresh-status polling 或 page refresh worker。
- 不把 OA、银行流水、发票复制成新的统一写模型。
- 不持久化自动候选、matching decision 或 `open/proposed` 关系状态。
- 不根据金额、旧 `case_id`、UI metadata 或来源前缀在 route/前端本地推断正式关系。
- 不直接写 relation SQL、matching dirty-scope SQL 或 outbox SQL；写入必须进入对应 command/UoW。
- 不拥有其他页面消费的 `workbench_relation` shared read model，也不拥有 `workbench-matching` worker。

## 读取链路

```text
ReconciliationWorkbenchPage
  -> Workbench HTTP routes
  -> WorkbenchQueryFacade
  -> PostgresWorkbenchPageQueryRepository
  -> PostgreSQL canonical facts + active formal relations
```

- route 只做认证、权限、参数验证和 HTTP 错误映射。
- facade 只编排 direct repository 和稳定 DTO；不得依赖 Redis、refresh gateway、runtime queue 或 read-model repository。
- repository 拥有 PostgreSQL 表结构、参数化 SQL、短 `REPEATABLE READ READ ONLY` 事务和 statement timeout。
- GET 必须是纯读：零 enqueue、零 RabbitMQ、零 page Redis、零 generation/read-model table I/O。
- DTO 组装可在取完原始结果并释放数据库连接后完成；禁止 assembler/service 隐藏额外 SQL。

## 输入 I/O

| 输入 | Owner | 合同 |
| --- | --- | --- |
| canonical OA | OA canonical repositories | 同一 tenant 下合并 completed OA 与 in-progress admission；输出稳定 typed identity 和 `workflow_status=completed|in_progress`。同一 OA 同时命中两源时 fail closed。费用子项仅用于展示和金额比较，不成为 relation member。 |
| canonical bank | bank canonical repositories | 使用稳定 typed identity、权威金额/方向/账号/交易日期和既有有效分类结果；页面查询不重新实现分类规则。 |
| canonical invoice / ETC | invoice / ETC canonical repositories | 只读取可见 canonical invoice、正式 OA attachment link、已提交 ETC business batch/link；ETC summary identity 保持 deterministic，禁止从 raw payload 猜 owner。 |
| active formal relations | workbench-relations | 只接受 `status=active` 的正式关系。成员以 `(row_type,row_id)` 精确匹配；parallel `row_types/row_ids` 长度不一致、typed owner 重复或缺 canonical member 时 fail closed。 |
| completion metadata | workbench-relations | 关系是否要求 OA/发票及 mode 豁免使用确认时持久化事实，不在 GET 中重跑当前规则。关系含 in-progress OA 时完整 case 保留在 `unpaired`。 |
| anomaly decisions | workbench exception repository | OA/发票自动异常按当前 canonical group set-based 计算；ignore/restore decision 以 scenario/fingerprint 关联。历史 WEX/row-ignore 只保留审计，不重新进入页面分区。 |
| list query | Workbench API | `month`、`zone`、allowlisted sort、区域 search、column/time filters、可选 `exception_bucket`、`page_size` 和 opaque `cursor`。所有字符串和集合有界，SQL 参数化。 |
| write command | Workbench action routes | server-authenticated actor/tenant、canonical member exact-set、preview id/fingerprint、expected relation/entity versions、idempotency key。页面 read-model version 和 cursor 均不是写 CAS。 |

## Direct SQL 合同

### Scope-first group spine

查询固定遵循以下方向：

```text
requested tenant/scope
  -> scoped canonical fact seeds
  -> touched active relations
  -> typed relation members WITH ORDINALITY
  -> required canonical member ids
  -> narrow member/group spine
  -> completion + anomaly + structured filters/search
  -> exact stats + cursor page keys
  -> only-visible-page set-based hydration
```

- `tenant`、月份、可见状态必须在各源表入口下推；禁止先 materialize 全历史 OA/流水/发票/关系后再过滤 scope。
- 月份查询先找该月触及的正式关系，再补载关系的完整跨月成员；不能截断正式 case。
- GIN `row_ids` 只能做候选剪枝，最终必须按 `row_types/row_ids WITH ORDINALITY` 精确匹配。
- 只在查询计划证明一个小集合被重复消费时使用 `MATERIALIZED`；禁止把 giant canonical CTE 当通用事实层。
- group 指标一次 set-based 聚合得到 totals、三栏 row counts 和排序 min/max；禁止每组 correlated scan。
- hydration 只处理当前 `page_size + 1` keys，按 typed ids 批量取全组成员；SQL 条数不得随 group/member 数增长。

### 首屏与分页

- `GET /api/workbench` 在一个短 `REPEATABLE READ READ ONLY` transaction 内返回 summary、statistics、invoice inventory 与 paired/unpaired 各 50 组首页。
- 首屏 candidate spine 只构建一次；禁止依次执行 summary、paired count/page、unpaired count/page 六套重复 canonical CTE。
- `GET /api/workbench/groups` 返回 `groups,total,row_counts,page_size,has_more,next_cursor`。
- `total` 和 row counts 是当前 query 的精确值；统计发生在 cursor 条件前。cursor 只减少深页排序/hydration，不能把 exact count 伪装成常数复杂度。
- cursor 绑定 scope、zone、sort、search、filters、exception bucket 的规范化 query hash，并保存完整稳定排序 tuple 与 `group_key` tie-breaker。
- cursor 是 opaque pagination boundary，不是 MVCC snapshot、read-model version、permission token 或写 CAS。跨 HTTP 请求采用 latest-committed 语义；并发写时页面在 mutation 成功后清空 cursor/selection 并重读首屏。
- 禁止 OFFSET fallback 和客户端解析 cursor 内容。

### 搜索、筛选与 filter options

- search 只覆盖用户可见的 OA/流水/发票结构化字段；内部 row/group id、`raw_payload`、`source_payload` 和 detail-only 文本不属于搜索面。
- `%`、`_`、反斜杠按 literal escape；金额先 canonicalize 后比较 numeric，日期使用显式表达式。
- 任一成员命中返回完整 group；不得只返回命中行。
- 同列多值 OR，不同列/不同 pane AND；同一 pane 的多个列条件必须由同一 member 满足。
- 银行金额复合筛选内，方向值 OR、付款账号值 OR；两类同时存在时彼此 AND。
- `GET /api/workbench/filter-options` 保留其它条件、移除目标列自身条件，从 eligible groups 直接 distinct；`未填写` sentinel 统一。
- options 按 `(label,value)` cursor 分页，默认 100、最大 200，返回 `options,page_size,has_more,next_cursor`；不计算无用 total，不读取当前浏览器已加载 rows，也不使用 Redis fallback。

### 异常与详情

- `/groups?exception_bucket=active|processed` 在 SQL group spine 上应用 anomaly state/fingerprint 和 ignore decision，精确计数并有界分页；前端不得 drain 全部 full-detail pages 后本地合并。
- group detail 按 active case/group typed owner 窄查；row detail 按 typed identity 与 active relation membership 窄查。
- detail 读取 latest committed 事实，不接受 `expected_read_model_version`，不构建全 scope group CTE。
- summary 列表禁止携带 raw payload、OCR/附件全文和完整 detail fields；折叠内容只在用户展开后读取。

## 输出 I/O

- Workbench bank row DTO 对当前可见页银行流水输出 canonical `category_code`、`category_label`、path/source 字段与必有的 `category_resolution_status`；未命中分类时状态为 `unmatched`。分类投影只对分页后可见 bank typed IDs 在同一只读 snapshot 内批量执行一次，不读取 Bank Details 页面 payload、不复制分类规则、不逐行查询。

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| combined initial | 前端 | `month,scope_key,summary,statistics,invoice_inventory,paired,unpaired`；两区使用相同 zone page shape。禁止 `read_model_status/read_model_version/active_generation_id/source_versions/refresh_enqueued/job`。 |
| zone page | 前端 | `groups,total,row_counts,page_size,has_more,next_cursor`；列表只含 compact summary DTO。 |
| filter options | 表头菜单 | `options[{value,label,missing}],page_size,has_more,next_cursor`；菜单惰性读取并支持 abort/latest-wins。 |
| paired groups | 前端 | 冻结要求满足且关系内 OA workflow 已完成的 active formal relation；`group_type=relation`。 |
| unpaired groups | 前端 | 无 active owner 的 singleton，以及要求未满足或含 in-progress OA 的完整 active relation；不完整 relation 不被强行拆散。 |
| write result | 前端 | 保留业务结果、affected ids/scopes、preview/CAS/idempotency信息；禁止 operation projection 和页面 freshness metadata。成功后恰好一次普通 direct refetch。 |
| shared relation refresh | `workbench_relation` worker / other pages | confirm/withdraw 等 canonical relation 写入仍按 shared relation 合同标记精确 scope；这不是 Workbench 页面读取依赖。 |
| matching dirty scope | `workbench-matching` | 会改变确定性正式关系的 canonical write 继续标记精确月份；页面 GET 不触发 matching。 |

## 写入与一致性

- 页面是否可写只由 session/permission、global mutation block 和 OA sync safety gate 决定；不再存在 page read-model freshness/version gate。
- preview 从 canonical typed selection 一次有界读取所选成员和必要 OA attachment context；不读取完整页面 payload。
- submit 在 relation UoW 内重读并锁定 canonical rows，验证 exact-set、case owner、版本、preview/topology fingerprint 和幂等。
- confirm 接受至少两个不同 canonical 成员，允许同类型组合；仅 `amount_check.requires_note=true` 时要求备注。
- withdraw 只接受一个完整可撤回 active relation 的精确成员集合，恢复最近一次确认前的稳定拓扑；当前与前序关系锁集合一次全局稳定排序后加锁。
- 写事务成功不 enqueue `workbench.read_model.refresh`。前端不应用本地 operation projection，不轮询 generation；direct refetch 失败时明确显示“写已提交、页面刷新失败”，不得重试 mutation。

## 前端请求拓扑

- mount：一个 combined initial、权威 OA sync status、settings；不请求 `/api/workbench/refresh-status`。
- query/filter/sort 变化：abort 上一请求，只重取受影响 zone 并清空该区 cursor；不重复读取 summary 和另一 zone。
- pagination/filter options/detail：每个 owner single-flight 或 latest-wins，有界 payload。
- mutation：一个 POST；成功后清 selection/cursor，并执行一次 normal direct GET。
- 保留 OA sync safety poll、全局 App Health 与 background jobs provider；它们不是 Workbench page read model，不能借本迁移删除。
- 页面 rows 不写入 session storage/长期 cache。长列表继续分页；DOM virtualization 属于独立前端性能任务，不用 read-model 迁移夹带新框架。

## 共享边界与跨页面隔离

必须保留：

- `workbench_relation` manifest/worker/repository/read facade，以及其真实跨页面 consumers。
- `workbench-matching` dirty scopes、worker、orchestrator 和正式 relation command。
- canonical identity、active formal relation、history、异常 decision、preview/UoW、审计和幂等。
- 独立 no-OA API/service；Workbench confirm 不恢复内部转账到 no-OA batch 的旧分流。
- 其他页面自己的 direct APIs、read models、workers、Redis keys、RabbitMQ events 和 App Status entries。

Workbench direct repository 不得被其他页面当通用 fact gateway。其他页面在下一次自身 API 读取中观察 canonical write，或继续按其已声明的 shared relation/read-model 合同收敛。

## 页面 read model 退役合同

同一 release 的 active runtime 必须删除：

- Workbench page manifest/scope policy/App Status entry。
- `workbench.read_model.refresh` enqueue、handler、Rabbit dispatcher event 和 worker registration/env/unit。
- page generation projection/freshness/status/cache/version owners及其生产 wiring。
- `/api/workbench/refresh-status`、前端 poll/reload/forced-fresh/operation projection。
- generation rehydrate/convergence/prune active tooling和 prune timer。
- SLO probe、deploy gate、tests 和长期文档中的 page-generation 当前事实。

本 release 不物理删除已应用 migration 或 `read_model.workbench_*` 派生表。它们只作为上一 immutable release 的短期离线回滚材料，新 runtime 对它们必须为零 I/O。稳定窗口关闭后，物理 drop 由独立 forward migration 决策；禁止删除 `workbench_relation` 表或主数据库。

## 性能合同

- 当前生产硬合同：authenticated bounded GET 错误为 0，Workbench blocking probe P95 `<=1000ms`、P99 `<=2000ms`，连接池无 timeout/backpressure。
- 优化目标：P50 `<=600ms`、P95 `<=800ms`、P99 `<=1200ms`；目标未达到时必须如实报告，不能因为低于硬合同就宣称比旧 read model 更快。
- 每个 endpoint 的 SQL 数量必须有界且无 N+1。当前 direct page repository 的固定业务 SQL 上限（不计 `SET TRANSACTION` / `SET LOCAL` 两条事务控制语句）为：initial `<=9`、groups `<=7`、filter options `=1`、group detail `<=7`、row detail `<=5`、preview `<=6`、exception page `<=8`。这些是防 N+1 的回归上限，不是延迟目标；2026-08 disposable PostgreSQL 小型 fixture 实测 initial `9`、groups `7`、filter options `1`、group detail `7`、row detail `5`、preview `6`，主 candidate SQL 约 `5–16ms`，ETC page hydration 已从 `5` 条合并为 `1` 条。生产验收仍以本节 p95/p99、pool hold time、buffer/temp-spill 和目标规模 EXPLAIN 为准；不得用固定条数替代性能证据。
- 先重写 query shape，再用测试库 `EXPLAIN (ANALYZE, BUFFERS)` 判断索引；禁止先堆索引或引入第二套物化结构。
- 生产只运行 bounded authenticated GET 和 plain `EXPLAIN`；不在生产运行 `EXPLAIN ANALYZE`。
- `month=all + exact total + 任意 substring search` 的成本不可能与数据规模无关。若重写和证据索引后仍不达 SLO，必须显式调整产品合同或重新评估物化读取，不能暗加 Redis/fallback 冒充 direct。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Routes / wiring | `backend/src/fin_ops_platform/app/routes_workbench.py`、`backend/src/fin_ops_platform/app/server.py` |
| Query service | `backend/src/fin_ops_platform/services/workbench_query_facade.py`、`workbench_filter_options.py`、`workbench_page_cursor.py` |
| Direct repository | `backend/src/fin_ops_platform/services/postgres_repositories/workbench_page_query.py`、`workbench_page_hydration.py`、`workbench_page_selection.py` |
| Relation writes | `workbench_write_facade.py`、`workbench_relation_command_service.py`、`workbench_uow.py`、relation repositories |
| Frontend | `web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/features/workbench/`、`web/src/components/workbench/` |
| Runtime/deploy | page retirement portions of runtime registry/manifest/worker/deploy；shared relation/matching files不属于删除范围 |
| Tests | `tests/test_workbench_*`、`web/src/test/Workbench*`、`web/e2e/workbench-*` 及跨页面 regression |

## 测试与验证

- 业务核心：typed identity、任意类型组合、不完整 relation、amount note、exact-set、withdraw 前序拓扑、异常 ignore/restore。
- repository/service：单请求 RR/RO、scope-first、fixed query count、batch hydration、exact totals、cursor/query hash、search/filter/facet/exception 等价、timeout/rollback。
- API：direct response shape、不含 RM 字段、refresh-status 不存在、GET 零 queue/cache、权限和稳定错误映射、action 无 expected RM version。
- runtime：page `workbench` registry/manifest/event/worker/timer 为零；`workbench_relation` 与 matching 正常。
- frontend：mount 无 status poll、zone-only query、cursor pagination、bounded exception drawer、OA/global gates、每次写一次 mutation + 一次 refetch。
- E2E：direct load、confirm/refetch、withdraw 恢复、incomplete relation、异常、权限、no-OA 隔离、direct failure 不 fallback。
- 跨页面：bank details、pending invoices、OA、cost/turnover、batch accounting、no-OA、App Health 和 operations 不产生回归或污染 I/O。

## 数据与回滚安全

- 主切换不创建任务专属数据库备份，不 drop canonical facts、page generation tables 或主数据库。
- 发布只从合并后 exact remote-main SHA 的干净 release checkout 激活。
- 自动/人工回滚必须先进入维护模式，使用上一 immutable release 对保留的 page generation 表执行全 scope rehydrate 和 audit，验证 fresh 后再同时开放旧 backend/frontend/worker；禁止把 stale old generation 先暴露给用户。
- 若未来为物理表清理单独创建临时逻辑备份，只能删除该任务明确记录并核验的临时文件；平台 PITR/组织级备份不属于任务临时备份，不得删除。
