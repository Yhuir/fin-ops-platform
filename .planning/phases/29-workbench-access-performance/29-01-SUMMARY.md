---
phase: 29-workbench-access-performance
plan: "01"
status: complete
completed_at: "2026-07-25T21:40:10+08:00"
commits:
  - 6ec4bc48a
  - f06711b7a
production_release: main-f06711b7-20260725213147
---

# Phase 29 Plan 01 执行总结

## 结果

关联台写后恢复和页面访问热路径已完成生产闭环。页面不再在 active generation
恢复期间重复拉取完整 paired/unpaired payload；一次触发 load 后只读取轻量
refresh-status，canonical proof 返回 fresh 后再读取一次完整页面。

生产 `/api/workbench/groups` 14 个滚动样本的 p50 为 `350.996 ms`，p95/p99 为
`2882.325 ms`；相对首个候选的 p95 `3476.949 ms` 改善约 `17.1%`。发布后的 5 次
hot all-scope 搜索请求为 `340–756 ms`，refresh-status 为 `272–655 ms`。历史
`6.9s` 已不是当前稳定访问水平。

六个 consumer 并发访问时，confirm 后 Workbench exact/all 分别为
`4616.117/3106.452 ms`，withdraw 恢复后分别为 `3108.711/4271.318 ms`。因此本阶段
可以证明完整、正确、最终 fresh 和明显改善，但不能宣称所有并发请求绝对低于 3 秒；
硬 3 秒 SLO 仍按已确认范围单独延期。

## 实现

1. `WorkbenchQueryFacade.refresh_status` 复用既有轻量
   `get_workbench_groups_freshness_status` repository port；完整 diagnostic 仅保留给
   缺少该 port 的非生产 legacy test double。
2. 关联台操作等待改为一次 combined initial 触发、轻量 refresh-status 等待和一次最终
   fresh combined initial；删除恢复期间重复完整 payload 轮询。
3. 首个候选一次性生产验证定位到 all-scope 带筛选查询的共同 SQL 根因：
   `active_workbench_members AS MATERIALIZED` 阻止筛选条件下推并制造临时 I/O。
   最终修复仅改为 `NOT MATERIALIZED`，保留同一 SQL owner、active generation、
   total/row counts/matching ids 和 response shape。

没有新增 cache、表、索引、migration、queue、worker、协调器、SSE 或第二 freshness
系统；没有恢复写后 fan-out，也没有增加页面专用 fallback 或并行旧查询实现。

## 本地验证

- 首个候选的 Workbench/read-model/API/frontend 定向回归约 593 tests passed。
- 最终 SQL 修复后的 backend Workbench SQL/facade/status/v2/query/routes：
  278 tests passed。
- 最终 frontend Workbench selection/runtime path：64 tests passed。
- Vite/TypeScript production build：passed；仅有既有 HeroUI CSS syntax 和
  大 chunk warning。
- `ruff`、docs gate、`git diff --check`：passed。
- PostgreSQL 17、20 万 active-member 对照：
  - `MATERIALIZED`：3747 个 temp blocks，`258.863 ms`。
  - `NOT MATERIALIZED`：无 temp I/O，`94.614 ms`。
- 临时 PostgreSQL 数据库已删除。
- 未运行无关的 183 个浏览器测试或全量 CI。

## 生产验证

- active release：`main-f06711b7-20260725213147`。
- test-owned fixture：`txn_imported_1278` 与 `txn_imported_1348`，通过正式
  confirm/withdraw API 验证；最终恢复为 inactive，临时 scenario 文件已精确删除。
- confirm mutation：`270.306 ms`；withdraw mutation：`164.554 ms`。
- confirm/withdraw 均满足：
  - 所有业务、配对和输入隔离断言通过。
  - Workbench、Cost、Turnover consumer 最终均返回 `fresh`。
  - forbidden Workbench/Cost/Turnover/Search 等写后 fan-out 全部为 0。
- confirm 并发 consumer：
  - Workbench exact/all：`4616.117/3106.452 ms`。
  - Cost active/all：`1245.992/1689.331 ms`。
  - Turnover：`3815.665 ms`。
- withdraw recovery 并发 consumer：
  - Workbench exact/all：`3108.711/4271.318 ms`。
  - Cost active/all：`5986.349/6212.350 ms`。
  - Turnover：`2680.462 ms`。
- Workbench worker 最近 15 分钟 p50/p95/p99：
  `1584.380/1799.628/1827.874 ms`；stale/unavailable 均为 0。
- System Audit：integrity `pass`、freshness `fresh`、queue `drained`，
  issue/error/warning/blocking 全部为 0，`database_snapshot=true`。
- Durable outbox：pending/publishing/failed/publish_failed 全部为 0。
- 24 个 required worker：全部 current/effective、available、idle。
- `/health/ready`：`ready`。

RabbitMQ management metrics 对 17 个队列仍不可用，但 RabbitMQ 不是 read model 状态
事实源；PostgreSQL durable queue、System Audit、worker 和 consumer payload 已完成
authoritative 收敛。外部银行/OA/发票/ETC 控制证据继续按既有合同为
`external=unknown`。

## 七类测试责任

1. 业务核心单元：不适用；未修改金额、配对、标签或状态转换业务规则。
2. Service layer：已覆盖 facade、repository freshness port、timeout 和 fallback。
3. API contract：response shape 未变；既有 refresh-status/groups/routes 回归通过。
4. Read model/cache/background job：已覆盖 stale/refreshing/fresh、active generation、
   exact recovery、queue drain 和 worker completion。
5. Frontend interaction：已覆盖操作触发、轻量等待、最终完整 fresh payload、失败和撤回。
6. E2E business flow：生产 test-owned confirm -> 并发访问 -> withdraw -> 并发恢复已覆盖。
7. Existing regression：Workbench v2/query/routes、Cost、Turnover、zero fan-out、
   System Audit 和 runtime isolation 已覆盖。

## 遗留风险

没有本阶段正确性、完整性、隔离、恢复、数据安全或运行时阻断项。硬 3 秒并发 SLO
尚未完全满足；最慢 Workbench 样本为 `4616.117 ms`。withdraw recovery 中 Cost
`5986–6212 ms` 和 confirm 中 Turnover `3815.665 ms` 是独立 consumer 性能尾延迟，
不由本次 Workbench CTE 修改引入，留给后续独立性能阶段统一处理。
