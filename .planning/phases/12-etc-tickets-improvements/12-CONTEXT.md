# Phase 12: ETC 票据高性能与暂存闭环 - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning
**Source:** 用户确认的 Grill Me 全链路分析

<domain>
## Phase Boundary

仅优化 ETC 票据管理页面及其直属 business batch、reconciliation task、OA draft command、PostgreSQL query、Page Audit 和测试/文档边界。解决首屏数秒、提交审批按钮因永久 `oa_draft_creating` 而不可用、`未提交 -> 暂存 -> 已提交/退回未提交` 用户闭环，并删除继续污染新链路的旧实现。不得修改或复用其他页面 read model，不得让关联台、成本统计、OA 待付款、税务或其他页面产生回归。

</domain>

<decisions>
## Implementation Decisions

### 状态与产品语义
- [D-01] 不新增业务状态；现有 `oa_confirmation_pending` 是唯一“暂存”事实，页面展示 `未提交 | 暂存 | 已提交` 三个互斥 bucket。
- [D-02] 创建 OA 草稿成功并持久化 `oaDraftId/oaDraftUrl` 后才进入“暂存”；短暂 `oa_draft_creating` 是内部操作态，不是正常业务 bucket。
- [D-03] 暂存选择“我已在 OA 提交”进入 `manually_marked_submitted`；选择“我未在 OA 提交/需要修改”进入 `not_submitted` 并回到“未提交”。
- [D-04] 回到“未提交”保留本地业务批次、已导入发票、上传文件和核对结果；清除本地 OA draft/submission 关联和发票提交占用；不删除 OA 系统草稿。
- [D-05] 永久删除继续使用独立“删除批次”入口和二次确认，不与“未在 OA 提交”合并。

### 按钮与选择事实源
- [D-06] `selectedBusinessBatchId` 是 ETC 页面唯一选择事实源；删除 `selectedTask`/`selectedTaskImportBatch` 对提交资格的并行所有权和重复详情请求。
- [D-07] 后端用同一条纯业务资格判定同时保护 command 与输出 `createOaDraftAction={enabled,code,message}`；前端只渲染结果和明确禁用原因，不复制状态规则。
- [D-08] 当前生产卡死的 `oa_draft_creating` 批次必须先核实 OA 外部结果，禁止直接改回 imported 后盲目重试。

### 性能与查询边界
- [D-09] ETC 页面保持 direct-canonical，无新增 read model、cache、Redis、RabbitMQ、worker、WebSocket 或轮询体系。
- [D-10] 首屏只读取 business batch 摘要；不再读取全量 `/api/etc/reconciliation-tasks`。选中批次后最多一次 batch detail，确有需要时最多一次精确 task detail。
- [D-11] PostgreSQL query 在数据库内完成 owner scope、bucket、筛选、排序、分页和计数；禁止页面读路径全量 hydrate ETC state 后 Python 过滤。
- [D-12] 列表 DTO 不含 invoice IDs、import attempts、audit events 或 task 嵌套详情；详情不逐发票访问对象存储，下载/Audit 才做真实对象与 hash 验证。
- [D-13] 性能门槛：列表 API p95<=300ms/p99<=500ms；详情 p95<=500ms/p99<=800ms；首批可操作内容 p95<=500ms/p99<=800ms；核心数据完整可用 p95<=800ms/p99<=1.2s；本地写后 bucket 更新 p95<=500ms/p99<=800ms。
- [D-14] 硬门：首屏全量 task 请求 0、相同 batch detail 重复请求 0、列表/详情对象存储请求 0、DB 查询数不随历史 task/发票数量增长、首屏业务 JSON <=250KB。索引只在生产 `EXPLAIN (ANALYZE, BUFFERS)` 证明需要时增加。

### OA 外部 I/O、幂等与恢复
- [D-15] 创建草稿拆为本地 prepare CAS、锁外 execute external、以 attempt/version finalize CAS；外部附件/OA HTTP 期间不得持 ETC 业务锁或数据库事务。
- [D-16] 前后端贯通并持久化稳定 `idempotencyKey`、attempt ID、startedAt 和 OA marker；重复相同操作返回同一结果，不生成第二个本地提交批次。
- [D-17] OA 错误必须区分明确失败和结果未知；明确失败进入 `oa_draft_failed`，结果未知禁止自动重试，并由受权限保护的核实/恢复门收敛。
- [D-18] 实施前验证 OA 是否支持 idempotency 或按稳定 marker 查询。若两者均不支持，不伪造 exactly-once；保留人工核实后“采纳已有草稿/确认外部未创建并允许重试”的最小恢复路径，不恢复旧自动 OA 检测 worker。

### Audit、旧链删除与隔离
- [D-19] ETC Page Audit 必须识别超时 creating、缺 attempt 字段、pending 缺 draft/submission 关系、三 bucket 集合/计数不等、退回后占用未释放，并保持 repeatable-read read-only 保证边界。
- [D-20] 删除两 bucket 旧映射、首屏全量 task consumer、双选择 owner、重复 detail effect、详情级列表 serializer、页面全量 reload、详情对象存储 N+1、忽略 idempotency 的 route/application 逻辑、锁内 OA I/O、重复 `UploadedEtcZipFile` 和失去调用方的旧 mock/test/docs/CSS。
- [D-21] `/api/etc/reconciliation-tasks` 仍是核对/导入正式 API；只从 ETC 首屏链路移除。全仓 production/frontend/script/probe/deploy consumer scan 与 owner attestation 证明无其他调用方后，才允许删除旧 list shape；不得为新链保留隐藏 fallback。
- [D-22] 不修改其他页面代码、DTO、read model、cache、worker 或 freshness gateway。ETC 合法 canonical relation/invoice 变化继续走现有 lifecycle/relation 边界；不得直接写其他页面 read model。

### 验证与发布约束
- [D-23] 七类测试按适用性覆盖 business 状态机、service/repository、API、direct-canonical/Audit、前端交互、端到端流程和其他页面回归；必须验证权限、version conflict、幂等、部分失败、结果未知、刷新恢复与无重复请求。
- [D-24] 生产验证包含三 bucket、Audit、页面首屏、详情、写后可见、混合页面负载和当前卡死批次安全恢复；未完成 OA 外部能力核实和卡死批次处置前不得声称闭环。

### the agent's Discretion
- 在不改变上述决策和现有 API 事实源的前提下，选择最少的现有 service/repository/helper 修改点、具体测试文件和顺序。
- 优先无 schema migration；只有现有 durable payload 无法满足 CAS/Audit 或生产 EXPLAIN 证明需要索引时，才计划 migration。

</decisions>

<canonical_refs>
## Canonical References

### 模块与边界
- `AGENTS.md` — 仓库模块化、I/O、测试、旧链删除和 worker/read model 治理规则。
- `docs/architecture/module-boundaries/README.md` — 模块边界总规则。
- `docs/architecture/module-boundaries/inventory.md` — ETC 及上下游模块登记。
- `docs/architecture/module-boundaries/read-model-contracts.md` — direct-canonical/read model 合同。
- `docs/modules/etc-tickets/README.md` — ETC 模块入口与当前事实。
- `docs/modules/etc-tickets/boundary-io.md` — ETC 输入/输出、文件范围和隔离边界。
- `docs/modules/etc-tickets/state-machine.md` — ETC 当前状态机。
- `docs/modules/etc-tickets/tests.md` — ETC 测试矩阵。
- `docs/operations/etc-business-batches.md` — ETC 生产运维与恢复边界。

### 代码入口
- `web/src/pages/EtcTicketManagementPage.tsx` — 页面请求瀑布、双选择、三 bucket 和按钮交互。
- `web/src/features/etc/api.ts` — ETC API client 与 idempotency payload。
- `web/src/features/etc/types.ts` — 页面合同类型。
- `backend/src/fin_ops_platform/app/routes_etc.py` — business batch HTTP 映射。
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py` — reconciliation task HTTP 合同。
- `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py` — batch/query/command 编排。
- `backend/src/fin_ops_platform/services/etc_service.py` — ETC aggregate、状态机、OA client 和对象存储边界。
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py` — task aggregate。
- `backend/src/fin_ops_platform/services/etc_reconciliation_task_payload_facade.py` — 当前全量 task payload。
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py` — 当前全量 ETC state load/save。
- `backend/src/fin_ops_platform/services/postgres_repositories/etc_tickets_page_audit.py` — ETC Page Audit。

### 复用参考
- `docs/modules/input-invoice-usage/oa-reverse-design.md` — `待处理 | 暂存 | 已提交` 产品语义；只复用交互语义，不跨模块复用 repository/state。
- `.planning/phases/00-cross-page-dependency-baseline/` — 跨页依赖、legacy、测试和实施顺序基线。
- `.planning/phases/12-etc-tickets-improvements/12-PAGE-BASELINE.md` — ETC 页面 L2 基线。

</canonical_refs>

<specifics>
## Specific Ideas

- 生产只读基线：business batch list 中位约 189ms；全量 reconciliation task list 中位约 399ms、最慢约 1.96s、约 556KB；batch detail 中位约 779ms、最慢约 1.57s、约 99KB；同一 detail 有两次并发重复请求。
- 当前生产活动批次已导入 64 张发票、task=`imported`，但 business batch 永久停在 `oa_draft_creating` 且没有 draft ID/URL；现有 Page Audit 仍错误通过。
- 当前详情最多对 64 张发票执行 128 次 PDF/XML 远程 existence check。

</specifics>

<deferred>
## Deferred Ideas

- ETC 发票 OCR、附件解析策略和导入识别能力不在本阶段。
- OA 系统功能改造、删除 OA 外部草稿、自动 OA 状态检测和跨页面 read model 重构不在本阶段。
- 不为未来数据量预建 cache、projection、通用 workflow engine 或额外消息系统。

</deferred>

<scope_fence>
## Scope Fence

- 本阶段只写 `.planning/phases/12-etc-tickets-improvements/` 计划产物；规划阶段不修改业务代码、生产数据或部署。
- 后续执行若发现必须跨出 ETC 及直属共享 lifecycle/relation 边界，先停止并重新确认范围。

</scope_fence>

---

*Phase: 12-etc-tickets-improvements*
*Context gathered: 2026-07-18 from confirmed user decisions*
