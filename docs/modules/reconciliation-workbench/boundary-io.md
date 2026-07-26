# 关联台模块边界与 I/O

日期：2026-07-27

## 职责

### 负责

- 从 PostgreSQL canonical OA、银行流水、发票、ETC snapshot 和 active 正式关系直接构造关联台页面。
- 提供 initial、groups 分页、group detail、row detail、ignored rows 和 relation preview 的页面专属查询。
- 复用现有纯 grouping、zone、completion requirement、override/exception 展示 policy。
- 提供搜索、筛选、排序、服务端分页、详情、写后重新 GET，以及 loading/empty/error 用户状态。

### 不负责

- 不读取或发布 Workbench active generation，不使用 `workbench_relation` distribution 作为页面事实源。
- 不暴露 read-model freshness、source versions、refresh enqueue、SSE 或 polling。
- 不在请求期运行 `WorkbenchSqlProjectionBuilder` 的 generation rebuild/publish。
- 不把 OA、银行、发票或 ETC 复制到统一写模型，不新增 cache、queue、worker、materialized view 或双读 fallback。
- 不直接写 relation SQL、history、idempotency 或 audit。

## 输入 I/O

| 输入 | Owner | 合同 |
| --- | --- | --- |
| OA facts | OA canonical owner | `app.oa_applications` 中当前可见/完成 OA，稳定 row identity、月份、金额和 display payload |
| 银行 facts | Bank canonical owner | `app.bank_transactions` 中当前 canonical rows、方向、账号、日期、tag/display payload |
| 发票 facts | Invoice canonical owner | `app.invoices` 中非删除、非 ETC 隐藏的 canonical invoice；强 identity 去重时 active relation owner 优先 |
| ETC collapsed facts | ETC owner | active invoice link 优先，其次有真实 `app.etc_invoices` 的已提交/关闭 business batch，最后才是有隐藏/已提交 invoice 证据的 submission batch；一个 external batch 在 scope 内只形成一个 owner |
| active relations | workbench-relations | 只读取 `app.workbench_pair_relations.status='active'`；row ids/types 对齐且成员独占 |
| override/exception display | Workbench control repositories | 复用既有优先级 formal relation > override > exception；不改变 canonical identity ownership |
| query | Workbench API | `month=YYYY-MM|all`、zone、page/page_size、status/source_kind/search/sort、column/time filters、detail level；search 最长 200 字符，page size 上限 200 |
| relation preview | Workbench API | 最多 20 个去重 row ids；只返回 selected rows 和最多 100 条必要 OA attachment context |
| relation mutation | Workbench API | server session actor/tenant、preview id、idempotency key/fingerprint、canonical relation expected versions；不接收页面 read-model version |

外部 OA/Mongo/MySQL/对象存储不得进入页面请求热路径；这里只读取已经同步到 PostgreSQL 的 canonical snapshot。

## 输出 I/O

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| combined initial | 前端 | `GET /api/workbench` 返回同一 snapshot 的 summary 与 paired/unpaired 各 page 1、page size 50；各区含 total、row_counts、has_more、groups |
| groups page | 前端 | `GET /api/workbench/groups` 固定服务端分页；精确 total/counts 与当前页 payload 来自同一 snapshot，禁止浏览器全量过滤 |
| group detail | 前端 | `GET /api/workbench/groups/detail` 按 zone/group/detail key 有界读取；missing 返回 404 |
| row detail | 前端 | `GET /api/workbench/rows/{row_id}` 有界读取；missing 返回 404 |
| relation preview | confirm/withdraw drawer | canonical selected rows、context rows、group/金额/alias 展示；不输出 generation proof |
| ignored rows | exception/restore UI | canonical row + override/exception 展示结果；不回退 generation snapshot |
| mutation result | 前端/调用方 | relation/version/affected rows/months、audit/idempotency；成功后前端普通 GET 重读当前 scope |

所有公开页面 payload 都不得含 `active_generation_id`、`refresh_enqueued`、`source_versions` 或任何 `read_model_*` 字段。业务对象自己的 `status` 字段不受影响。

## Snapshot、SQL 与性能合同

- 每个公开 read repository 调用开启一个显式 `REPEATABLE READ READ ONLY` transaction，并设置 `statement_timeout='2s'`。
- initial 的 summary、paired/unpaired counts/pages 共用该 transaction；不在 route 或 service 拆成多个连接快照。
- groups 使用 SQL `LIMIT/OFFSET` 和 `page_size + 1` 判定 `has_more`；最大 200 groups 一次批量 hydration，不逐组查询。
- row/group detail 先执行有界 selector，再按成员类型批量加载。
- 20-row preview 每种 canonical row type 最多一次批量 loader，并对 context size fail closed。
- confirm/withdraw UoW 在同一写事务内用一次有界 canonical selection query 重验全部 selected identities；active ownership、business versions、history、idempotency 和 audit 继续由 relation transaction 保护。
- 新增索引必须先有真实 PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` 或端点测量证据；本迁移不新增索引。

当前结构 guard：

- 默认 initial 空集固定 10 条数据库语句（含 2 条 transaction setup）。
- groups 空集/最大分页 selector 固定 4 条（含 setup），最大 200 条仍一次 hydration 调用。
- missing group detail/row detail 固定 3 条（含 setup）。
- transaction 内 canonical revalidation 固定 1 条有界查询。

这些是查询形状证据，不是生产延迟证据；真实最大月份、`all` scope 和并发 p95 必须由主控部署后测量。

## 写事务与冲突

- preview 的 selected rows 是展示数据，不是 command 事实源。
- confirm 在 transaction 内重验 row identity 和 row type；withdraw/cancel 在 transaction 内重验 identity 存在性。
- relation command/repository 在同一 transaction 内锁定并验证 active case/member ownership、expected business version、幂等 fingerprint。
- canonical identity 缺失或类型变化返回 `409 workbench_canonical_selection_conflict`；active occupancy/version/idempotency 冲突继续返回既有 409 合同。
- route 只做鉴权、参数解析和 HTTP 映射；业务组合在 facade/service，SQL 只在 repository。

## 依赖方向

```text
frontend -> page API -> route -> query facade -> canonical query repository
                                      -> pure grouping/requirement policy

mutation route -> write facade -> relation command/UoW -> canonical relation repository
```

- service 构造函数接收明确依赖，不接收 `Application`。
- repository 可以知道 SQL 表结构；route/service 不散落业务 SQL。
- 前端只消费 API，不从 provenance、old case metadata 或 refresh status 推断关系。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/`、`web/src/features/workbench/` |
| Routes | `backend/src/fin_ops_platform/app/routes_workbench.py` |
| Query service | `backend/src/fin_ops_platform/services/workbench_query_facade.py` |
| Query repository | `backend/src/fin_ops_platform/services/postgres_repositories/workbench_canonical_query.py` |
| Write service | `backend/src/fin_ops_platform/services/workbench_write_facade.py` |
| Minimal wiring | `backend/src/fin_ops_platform/app/server.py` |
| Tests | `tests/test_workbench_canonical_query_repository.py`、`tests/test_workbench_*`、`web/src/test/Workbench*`、`web/e2e/workbench-stale-error-flow.spec.ts` |

## 已删除的页面独占旧链

- Workbench page groups Redis cache。
- Workbench page freshness service 和 refresh-status payload/provider。
- Workbench page SSE active-stream registry。
- 前端 `/refresh-status` 轮询、`/events` SSE、refreshing/failed read-model UI 分支。
- 页面 `expected_read_model_version` / generation-bound preview 和 write gate。

## 共享 HANDOFF

以下资源仍可能被 batch-accounting 或其它消费方使用，本模块不删除：

- Workbench active-generation tables、builder、refresh worker、manifest/registry/env。
- `PostgresReadModelRepository` 的 generation readers 与 batch-accounting 专属 Workbench loaders。
- `workbench_relation` distribution、worker、queue 和 downstream freshness facade。
- active-generation consistency/Audit/repair/diagnostic 工具。

主控必须在 whole-repo 调用方全部迁移后再统一删除或改名，不能把这些共享资源重新接回关联台页面。
