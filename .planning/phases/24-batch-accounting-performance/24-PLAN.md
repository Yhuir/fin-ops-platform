# 批量账务性能实施计划

日期：2026-07-20

## 目标

在不改变业务口径、API shape、权限、read model/worker 和其他页面通用 I/O 的前提下，将批量账务读取从按 scope 线性查询降为固定查询次数，并删除未提交列表的无界附件读取。

## 实施步骤

### 1. 专用 relation repository I/O

- 增加 `get_batch_accounting_relation_rows_by_ids(...)`。
- 增加内部批量 scope proof：用一个有序 `unnest(scope_keys)` 查询同时读取 scope metadata 和 current-effective dirty status。
- 年度 count 改为“1 次批量 proof + 1 次 count”。
- 年度 list 改为“1 次批量 proof + 1 次 groups”，组装结果时复用第一次 proof，不再二次证明。
- 保持 status、stale reasons、source versions、scope keys 和 rows/groups DTO 等价。

### 2. 端口与 facade

- `WorkbenchRelationReadModelRepositoryPort` 仅暴露新增的窄方法。
- `WorkbenchRelationReadFacade` 增加 `get_batch_accounting_by_row_ids(...)`，继续复用既有 `_result_from_repository_payload` 与 refresh gateway。
- 更新 read model manifest 的 repository port contract。
- BatchAccountingService 的未提交候选排除和已提交明细只调用新方法；不提供通用旧方法 fallback，依赖缺失时 fail closed。

### 3. 收窄 OA 附件 I/O

- 从已读取 OA payload 中提取 OA row IDs。
- 附件 SQL 只查询这些 OA IDs/兼容 row-id/source-links，空 OA 列表时不查附件。
- submit 现有窄 loader 与 list loader 复用同一私有读取 helper；参数明确控制是否允许 `all` scope fallback，保持 submit 既有语义和 list 的非-all语义。
- 删除 list 原有无 OA 条件的全量附件 SQL，不保留兼容分支。

### 4. 生产证据触发的候选索引修复

- 首次部署后若 relation query count 已达标、但 unsubmitted p95 仍失败，使用 dashboard DB duration、响应大小和现有索引合同定位剩余慢 SQL。
- 银行候选只按结构化 `workbench_rows.counterparty_name` 过滤，删除两个历史 JSON `OR` fallback，使既有 `workbench_rows_bank_counterparty_scope_idx` 可用。
- 若该 release 仍失败，唯一剩余无索引条件是 OA `apply_type/expense_type` 的前导通配扫描：把两个 JSON 字段规范为一个稳定表达式，并用 migration 0112 添加只覆盖 `source_kind='oa' and scope_key<>'all'` 的部分 trigram 索引。
- 若索引 release 已把 p95 降到接近门槛但仍失败，且 dashboard 证明 query-count p95 仍为 `10`、connection acquire 可忽略，则把同属一个 active-generation 候选快照的银行/OA/附件读取合为一个 repository SQL I/O；附件仍只引用当前 OA candidate CTE，submit 窄 loader 不变。
- 若候选单 I/O release 已把 query-count p95 降到 `8`、但列表仍只差小幅未达门槛，则合并 batch-only relation 内剩余两组天然同边界读取：候选 `scope proof + referenced groups` 一次返回，年度 `scope proof + submitted count` 一次返回；目标 query-count p95 `<=6`。不改通用 relation reader 和 submitted list 已达标路径。
- 若该 release 已把 unsubmitted 查询数降到约 `6`、但生产外部 p95 仍略高于门槛，则把同一 batch-only repository 方法的 relation rows 与它们决定的 scope proof/referenced groups 合为一个 JSON bundle 快照，目标 unsubmitted 请求查询数再减 `1`。若仍失败，必须先依据新生产证据审阅剩余 I/O，不得盲目增加基础设施或跨边界合并。
- 第六次 release 把 unsubmitted 查询数降到约 `5` 后仍为 `520.481ms`；新证据确认剩余独立年度 count 与候选 bundle 读取同一 relation 事实和 freshness scopes。将 `submitted_year` 作为 batch-only bundle 的显式输入，由同一 SQL 返回年度 proof 与 `submitted_count`，并删除独立 count facade/port/repository/manifest 方法；目标查询数约为 `4`。这是边界内最后一次合并，不再新增 cache、projection、worker 或公共抽象；若仍失败，必须停止并基于新生产证据重新审阅。
- 第七次 release 达到约 `4` 条查询但 p95 仍为 `538.172ms` 后，不再合并跨边界 SQL。删除候选列表 SELECT 中未消费的 `raw_payload`，保留规范化 `payload` 和既有单 I/O；测试必须证明列表查询不再包含该列且真实 PostgreSQL 行/附件结果等价。若仍失败，必须重新采集证据，不能把提交窄 loader或其他页面通用 Workbench reader一并改变。
- 不新增结构化列、缓存、projection 或第二套候选 read model；真实 PostgreSQL 测试必须执行 0001–0112 并由 `EXPLAIN` 证明查询命中精确索引，静态 guard 禁止银行 fallback 和 OA 未索引 `OR` 回流。

### 5. 测试与架构门禁

1. 业务核心单元：不改变业务规则，不新增专门业务单测；既有筛选、金额、submit/withdraw 状态测试回归。
2. Service：验证候选和 submitted detail 只使用 batch 专用 facade 方法，缺失依赖 fail closed。
3. API contract：完整 `tests/test_batch_accounting_api.py`，确保 response/status/refresh contract 不变。
4. Read model/cache/job：
   - fresh/missing/refreshing/stale 的批量 proof 等价测试；
   - 未提交候选/年度 proof、groups、count 固定为一个 relation bundle，已提交年度 list 查询数固定；
   - row lookup 查询数不随 scope 数增长；
   - non-fresh 仍由 facade enqueue；
   - OA 附件只按候选 IDs 查询，列表银行/OA/附件固定为一个 repository I/O。
5. Frontend：无前端行为改动；运行 BatchAccountingPage/API 既有组件测试作为回归，不新增实现细节测试。
6. E2E：运行批量账务关键流测试；本地/生产写入分别受环境和 App Health preflight 约束。
7. Existing regression：运行 workbench relation facade、SQL runtime、manifest、architecture guards，并验证关联台/银行明细/成本统计等直接共享消费者 Audit。

### 6. 文档

- 更新 batch-accounting README、boundary-io、tests、implementation-notes。
- 更新 workbench-relations boundary I/O、read-model contracts 与 runtime ownership/manifest 事实。
- API shape 和产品口径不变，不改产品 spec/API contract；若实现核验发现长期事实描述需要更新，再做最小修订。

### 7. 发布与生产验证

- 相关测试、lint、docs、diff-check 通过后，提交并 push `main`。
- 使用 `./scripts/deploy-oa.sh` 部署精确 SHA。
- authenticated 20-sample：shell、unsubmitted 2026、submitted 2026、Page Audit。
- 读取 dashboard 的 duration、DB duration、query count；最终候选单 I/O release 验证 query p95 `<=8`。
- 做直接及跨页 Page Audit。
- 生产 submit→fresh→withdraw→fresh 仅在 `app-health-operations` 强制 preflight 通过后执行；否则记录为最终系统门待办，绝不绕过。
- 失败回滚：回滚本轮代码 commit 并重新部署上一精确 release；0112 只增加读性能索引，可安全留存且不改变数据/API。需要物理删除时必须另走维护窗口 `drop index concurrently`，不在失败回滚热路径阻塞表。

## 第三次计划反审阅

- 生产级：包含权限/契约保持、freshness、审计、回滚、生产指标和失败门禁。
- 模块化：批量账务拥有专用 relation read I/O；共享事实源只读，其他页面入口不变。
- 简洁：只增加 batch-only 批量 proof/组合读取能力和一个收窄附件 helper，无新基础设施或抽象层。
- 高性能：直接消除生产量化的 52–66 查询扇出和无界附件扫描。
- 旧链删除：service 不再调用通用 relation lookup；年度重复 proof 和无条件附件 SQL 被删除，并由 guard 固化。
- 隔离：不改变 shared generic facade 行为、API DTO、worker、command 或其他页面 read model。
- 闭环：代码、七类测试判定、文档、提交、部署、生产读写门禁、跨页 Audit、回滚均有明确完成条件。

审阅结论：计划满足要求，没有需要在实现前新增的层或基础设施。唯一条件性后续是：部署后若 p95 仍未达标，必须依据 EXPLAIN/生产 dashboard 再决定是否做候选 SQL 分页或索引，不提前设计。
