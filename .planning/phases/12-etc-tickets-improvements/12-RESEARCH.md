# Phase 12: ETC 票据高性能与暂存闭环 - Research

**Researched:** 2026-07-18
**Scope:** 仅用于实施计划；未修改业务代码或生产数据

## 结论

ETC 页面数秒首屏不是单一 SQL 问题，而是四段叠加：首屏读取全部 reconciliation task 详情、同一 business batch detail 重复请求、每次 list/detail 全量 hydrate PostgreSQL ETC snapshot、详情逐发票访问对象存储。提交按钮当前生产不可用的直接原因是 business batch 永久停在 `oa_draft_creating`；task 已是 `imported` 且 64 张发票已导入。现有 Audit 未识别该悬挂状态。

最小生产级方案不需要新 read model/cache/worker：复用现有 business batch、`oa_confirmation_pending`、state store/repository、application service、OA client 和 Page Audit；把页面读路径改为 canonical 窄查询，把 OA command 改为锁外外部 I/O，并删除旧双选择/全量 task/重复 detail 链。

## 已验证的当前链路

### 页面读取

1. `EtcTicketManagementPage` 首屏同时调用 business batch list 和 `/api/etc/reconciliation-tasks`。
2. task list 为每个 task 序列化 source files、card/ticket/supplement/reconciled items、parse issues 和 audit events。
3. 选择 batch 后，一个 effect 读取 batch detail；另一个由 selected task 推导 import batch 后再次读取相同 detail。
4. submit eligibility 同时依赖 selected business batch、selected task、task import detail loading 和前端状态集合。

### 后端读取

- `EtcService.list_business_batches/get_business_batch` 在 PostgreSQL runtime 每次调用 `_reload_from_state_store()`。
- `PostgresOpsTaxEtcRepository.load_etc_state()`读取全部 ETC invoices/import batches/submission batches/business batches 的 raw payload。
- reconciliation task list/detail 同样读取并 hydrate 全部 task/file state。
- business batch list 在 Python 中过滤、计数、分页，并复用详情级 payload。
- detail 对每张发票的 PDF/XML 调用远程 existence check；64 张发票最多形成 128 次对象存储 I/O。

### OA command

- business batch 先持久化 `oa_draft_creating`，随后在同一业务锁内创建 submission batch、读取附件、上传附件并调用 OA。
- route/frontend 没有贯通已有 `idempotencyKey` payload。
- 只对已映射 `EtcDraftRequestError` 回落；进程中断、未映射异常或外部成功但响应丢失会留下悬挂/重复风险。
- `EtcBatch` 已提供稳定 `etc_batch_id` 和包含 `business_batch_id` 的 `oa_marker`；可复用 submission batch ID 作为 attempt ID，无需新 attempt 表。

## 生产基线

- business batch list：中位约 189ms，最慢约 284ms，约 3.5KB。
- 全量 reconciliation task list：中位约 399ms，最慢约 1.96s，约 556KB。
- batch detail：中位约 779ms，最慢约 1.57s，约 99KB。
- 相同 detail 两次并发请求：页面等待约 1.02s，下载两份相同 payload。
- 当前活动 batch：task=`imported`，64 张发票已导入，batch=`oa_draft_creating`，缺 OA draft ID/URL；Page Audit 仍通过。

## 最小复用设计

### Query I/O

复用现有 state store/repository 边界，增加 ETC 页面所需的窄读方法，不建立 projection：

- list 输入：actor scope、bucket、plate、keyword、page/pageSize。
- list 输出：batch summary、三 bucket counts、pagination、后端 action contract。
- detail 输入：actor scope、businessBatchId。
- detail 输出：一个 business batch、其 invoice detail 和绑定 task 的必要摘要/精确明细。
- PostgreSQL 实现从 formal columns 和必要 raw payload 标量查询；local/test state store 从现有 snapshot 实现同一合同。
- query 不调用对象存储、OA、queue 或其他页面 read model，不写状态。

### Command I/O

- prepare：校验 actor/version/status/task/invoices/idempotency，创建并持久化 submission attempt，更新 batch creating/audit/version，然后释放锁。
- execute：基于不可变 attempt snapshot 读取附件并调用 OA；不持锁/事务。
- finalize：以 businessBatchId + submissionBatchId + expected creating version CAS，成功进入 pending，明确失败进入 failed，结果未知保持禁止重试并进入恢复门。
- 复用 `submission_batch_id` 作为 attempt ID，复用 business batch `updated_at`/creating audit event 作为 startedAt，新增字段仅限无法从现有 durable facts 表达的 OA operation idempotency/outcome。

### 三 bucket

- `unsubmitted`：现有 active 状态扣除 `oa_confirmation_pending` 和正常短暂 creating。
- `staged`：仅 `oa_confirmation_pending`。
- `submitted`：`oa_submitted/manually_marked_submitted/closed`。
- creating 不成为第四个正常 tab；短期显示处理中，超过固定保守期限后 Audit 报告 recovery required。

### 外部结果未知

实施前先用非生产破坏性方式确认 OA 是否支持 idempotency 或按稳定 marker 查询。若支持，复用其合同；若不支持，不能自动重试未知结果。最小恢复路径是受管理员权限保护、带审计和 expected version 的显式收敛：采纳已经核实的 draft ID/URL，或在有“外部未创建”证据后标记 failed 允许重试。不得直接 SQL 修状态，不恢复旧 OA 自动检测 worker。

## 旧链删除清单

必须删除新 ETC 页面链中的：

1. 初始 `loadReconciliationTasks()` 全量 consumer。
2. `selectedTaskId/reconciliationTasks` 对 business batch 选择的第二所有权。
3. `selectedTaskImportBatchId/selectedTaskImportBatchCanSubmit` 分支。
4. 第二次 batch detail effect。
5. 两 bucket 映射和 pending 归 active/unsubmitted 的旧语义。
6. list 复用 detail serializer 的 invoice IDs/import attempts/audit events 输出。
7. list/detail 调用全量 state hydration 的 page path。
8. detail 中逐发票对象存储 existence checks。
9. create-draft route/application 忽略 idempotency 的逻辑。
10. OA 外部 I/O 位于 business lock 内的实现。
11. 重复 `UploadedEtcZipFile` 声明。
12. 删除上述生产代码后失去调用方的 mocks、tests、CSS 和文档描述。

`/api/etc/reconciliation-tasks` 仍是导入/核对正式合同；从 ETC 首屏移除不等于删除 route。只有全仓 production/frontend/script/probe/deploy scan 和 owner attestation 证明无 consumer 时，才删除旧 list shape。静态 architecture guard 必须禁止 ETC 首屏重新消费它。

## Validation Architecture

### 最小自动化层

1. 纯状态/资格测试：三个 bucket、action reason、状态转换、idempotent replay、version conflict、unknown outcome。
2. state store/repository 测试：summary/detail 精确集合、owner scope、分页计数、固定 SQL/调用次数、零 object-store call。
3. API contract：三 bucket response、action contract、create/recover/manual status 权限和错误结构。
4. 前端交互：首屏无全量 task、同一 detail 一次、按钮显示明确原因、刷新后 staged durable、not-submitted 回到 unsubmitted 且数据保留。
5. E2E：imported -> creating -> staged -> submitted；staged -> not_submitted -> unsubmitted；ambiguous OA -> blocked recovery。
6. 回归：Import Center ready-for-import、ETC source file/confirm/delete/reset、Workbench/tax/cost 正式 canonical 影响合同不变。

### 性能证明

- API probe 记录 duration、status、bytes；浏览器记录 navigation 到 list/action-ready/detail-ready。
- 记录首屏请求清单，断言 full task request=0、duplicate detail=0。
- repository test 注入 object-store spy，断言 list/detail call=0。
- 使用生产同等数据量和 64+ 发票批次；至少 warm/cold 各 20 次，以 p95/p99 而非单次最优值验收。
- 混合负载同时读取 ETC 与关联台/成本/OA 页面，确认 ETC OA 外部操作不阻塞查询且其他页面结果/延迟无回归。

### 目标

- list p95<=300ms/p99<=500ms。
- detail p95<=500ms/p99<=800ms。
- 首批可操作内容 p95<=500ms/p99<=800ms。
- 核心数据完整 p95<=800ms/p99<=1.2s。
- 本地写后 bucket 可见 p95<=500ms/p99<=800ms。
- 首屏 JSON<=250KB；DB query/object-store/HTTP 调用数有固定上界。

## 风险与发布门

- 当前生产 creating 批次必须先核实 OA 外部结果；代码修复不能自动猜测历史结果。
- OA provider 无 idempotency/query 合同时，只能提供明确人工恢复，不得宣称自动 exactly-once。
- query contract 改动必须与官方 frontend 原子部署；不保留隐藏 fallback。
- 无 schema migration 是首选；只有 durable CAS/Audit 无法用现有 payload/columns 表达或 EXPLAIN 证明索引必要才增加 migration。
- 部署后先 read-only list/detail/Audit canary，再用可回滚测试批次验证两个暂存出口，最后跑混合负载；失败立即回滚代码并保留 canonical 业务数据。

## RESEARCH COMPLETE

